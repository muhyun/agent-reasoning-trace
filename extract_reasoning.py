#!/usr/bin/env python3
"""Extract reasoning, thinking, and tool-use chains from OTEL trace files.

Parses the pretty-printed JSON spans exported by Strands' console exporter
and reconstructs the agent's reasoning flow as a readable tree.

Usage:
    python extract_reasoning.py traces.jsonl
    python extract_reasoning.py traces.jsonl --trace-id 0xabc123
    python extract_reasoning.py traces.jsonl --thinking-only
    python extract_reasoning.py traces.jsonl --json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime


def parse_spans(filepath):
    """Parse pretty-printed JSON spans from a trace file."""
    spans = []
    current = []
    depth = 0

    with open(filepath) as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            if stripped == "{" and depth == 0:
                current = [line]
                depth = 1
            elif depth > 0:
                current.append(line)
                depth += stripped.count("{") - stripped.count("}")
                if depth == 0:
                    try:
                        spans.append(json.loads("".join(current)))
                    except json.JSONDecodeError:
                        pass
                    current = []
    return spans


def extract_content_parts(content_str):
    """Parse a content string (JSON array) into structured parts."""
    try:
        parts = json.loads(content_str)
        if not isinstance(parts, list):
            return [{"type": "text", "text": str(parts)}]
        return parts
    except (json.JSONDecodeError, TypeError):
        return [{"type": "text", "text": str(content_str)}]


def extract_reasoning_from_span(span):
    """Extract reasoning/thinking content and tool calls from a span."""
    results = []
    span_name = span.get("name", "")
    attrs = span.get("attributes", {})
    events = span.get("events", [])

    for event in events:
        event_name = event.get("name", "")
        event_attrs = event.get("attributes", {})

        content_str = event_attrs.get("content") or event_attrs.get("message")
        if not content_str:
            continue

        parts = extract_content_parts(content_str)
        for part in parts:
            if isinstance(part, dict):
                # Extended thinking / reasoning content
                if "reasoningContent" in part:
                    rc = part["reasoningContent"]
                    text = rc.get("reasoningText", {}).get("text", "") if isinstance(rc, dict) else str(rc)
                    if text:
                        results.append({
                            "type": "thinking",
                            "event": event_name,
                            "content": text,
                            "span_name": span_name,
                        })

                # OTEL GenAI reasoning part type
                if part.get("type") == "reasoning" or part.get("type") == "reasoningContent":
                    content = part.get("content", "")
                    if isinstance(content, dict):
                        content = content.get("reasoningText", {}).get("text", "") or json.dumps(content)
                    if content:
                        results.append({
                            "type": "thinking",
                            "event": event_name,
                            "content": content,
                            "span_name": span_name,
                        })

                # Text output from assistant
                if "text" in part and event_name == "gen_ai.choice":
                    results.append({
                        "type": "assistant_text",
                        "event": event_name,
                        "content": part["text"],
                        "span_name": span_name,
                    })

                # Tool use
                if "toolUse" in part:
                    tu = part["toolUse"]
                    results.append({
                        "type": "tool_call",
                        "event": event_name,
                        "name": tu.get("name", "unknown"),
                        "input": tu.get("input", {}),
                        "tool_use_id": tu.get("toolUseId", ""),
                        "span_name": span_name,
                    })

                # Tool result
                if "toolResult" in part:
                    tr = part["toolResult"]
                    result_content = tr.get("content", [])
                    text = ""
                    if isinstance(result_content, list):
                        text = " ".join(
                            item.get("text", "") for item in result_content if isinstance(item, dict)
                        )
                    else:
                        text = str(result_content)
                    results.append({
                        "type": "tool_result",
                        "event": event_name,
                        "tool_use_id": tr.get("toolUseId", ""),
                        "content": text,
                        "span_name": span_name,
                    })

    return results


def build_span_tree(spans):
    """Build parent-child tree from spans."""
    by_id = {}
    children = defaultdict(list)
    roots = []

    for span in spans:
        ctx = span.get("context", {})
        span_id = ctx.get("span_id", "")
        parent_id = span.get("parent_id")
        span["_span_id"] = span_id
        span["_parent_id"] = parent_id
        by_id[span_id] = span

        if parent_id and parent_id != "null":
            children[parent_id].append(span)
        else:
            roots.append(span)

    return roots, children, by_id


def get_traces(spans):
    """Group spans by trace_id."""
    traces = defaultdict(list)
    for span in spans:
        trace_id = span.get("context", {}).get("trace_id", "unknown")
        traces[trace_id].append(span)
    return traces


def format_thinking(text, width=100):
    """Format thinking content with a left border."""
    lines = text.split("\n")
    formatted = []
    for line in lines:
        while len(line) > width:
            formatted.append(f"  | {line[:width]}")
            line = line[width:]
        formatted.append(f"  | {line}")
    return "\n".join(formatted)


def print_reasoning_flow(spans, thinking_only=False):
    """Print the reasoning flow from spans in chronological order."""
    chat_spans = [s for s in spans if s.get("name") == "chat"]
    chat_spans.sort(key=lambda s: s.get("start_time", ""))

    if not chat_spans:
        print("  No chat spans found in this trace.")
        return

    has_thinking = False
    for i, span in enumerate(chat_spans):
        items = extract_reasoning_from_span(span)

        thinking_items = [it for it in items if it["type"] == "thinking"]
        if thinking_items:
            has_thinking = True

        if thinking_only and not thinking_items:
            continue

        attrs = span.get("attributes", {})
        start = span.get("start_time", "")[:19]
        duration_ms = attrs.get("gen_ai.server.request.duration", "?")
        input_tokens = attrs.get("gen_ai.usage.input_tokens", "?")
        output_tokens = attrs.get("gen_ai.usage.output_tokens", "?")

        print(f"\n--- Chat {i+1} [{start}] (duration: {duration_ms}ms, tokens: {input_tokens}in/{output_tokens}out) ---")

        for item in items:
            if thinking_only and item["type"] != "thinking":
                continue

            if item["type"] == "thinking":
                print(f"\n  THINKING:")
                print(format_thinking(item["content"]))

            elif item["type"] == "tool_call":
                input_str = json.dumps(item["input"], indent=2)
                if len(input_str) > 300:
                    input_str = input_str[:300] + "..."
                print(f"\n  TOOL CALL: {item['name']}")
                print(f"  {input_str}")

            elif item["type"] == "tool_result":
                content = item["content"]
                if len(content) > 500:
                    content = content[:500] + "..."
                print(f"\n  TOOL RESULT:")
                print(f"  {content}")

            elif item["type"] == "assistant_text":
                text = item["content"]
                if len(text) > 500:
                    text = text[:500] + "..."
                print(f"\n  RESPONSE: {text}")

    if thinking_only and not has_thinking:
        print("\n  No extended thinking/reasoning content found in traces.")
        print("  Enable extended thinking on the model to capture reasoning blocks.")
        print("  For Bedrock: additional_request_fields={\"thinking\": {\"type\": \"enabled\", \"budget_tokens\": 4096}}")


def print_json(spans, thinking_only=False):
    """Output reasoning flow as JSON."""
    traces = get_traces(spans)
    output = []

    for trace_id, trace_spans in traces.items():
        chat_spans = [s for s in trace_spans if s.get("name") == "chat"]
        chat_spans.sort(key=lambda s: s.get("start_time", ""))

        trace_data = {"trace_id": trace_id, "interactions": []}
        for span in chat_spans:
            items = extract_reasoning_from_span(span)
            if thinking_only:
                items = [it for it in items if it["type"] == "thinking"]
            if items:
                attrs = span.get("attributes", {})
                trace_data["interactions"].append({
                    "start_time": span.get("start_time"),
                    "duration_ms": attrs.get("gen_ai.server.request.duration"),
                    "input_tokens": attrs.get("gen_ai.usage.input_tokens"),
                    "output_tokens": attrs.get("gen_ai.usage.output_tokens"),
                    "items": items,
                })
        if trace_data["interactions"]:
            output.append(trace_data)

    print(json.dumps(output, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Extract reasoning from OTEL trace files")
    parser.add_argument("file", help="Path to trace file (pretty-printed JSON spans)")
    parser.add_argument("--trace-id", help="Filter to a specific trace ID")
    parser.add_argument("--thinking-only", action="store_true", help="Only show extended thinking/reasoning blocks")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--list-traces", action="store_true", help="List all trace IDs")
    args = parser.parse_args()

    spans = parse_spans(args.file)
    if not spans:
        print(f"No spans found in {args.file}", file=sys.stderr)
        sys.exit(1)

    if args.list_traces:
        traces = get_traces(spans)
        for tid, tspans in traces.items():
            agent_spans = [s for s in tspans if s.get("name") == "Agent"]
            chat_spans = [s for s in tspans if s.get("name") == "chat"]
            times = [s.get("start_time", "") for s in tspans if s.get("start_time")]
            start = min(times)[:19] if times else "?"
            print(f"  {tid}  ({len(tspans)} spans, {len(chat_spans)} chats, started {start})")
        return

    if args.trace_id:
        spans = [s for s in spans if s.get("context", {}).get("trace_id") == args.trace_id]
        if not spans:
            print(f"No spans found for trace {args.trace_id}", file=sys.stderr)
            sys.exit(1)

    if args.json:
        print_json(spans, thinking_only=args.thinking_only)
        return

    traces = get_traces(spans)
    for trace_id, trace_spans in traces.items():
        print(f"\n{'='*80}")
        print(f"TRACE: {trace_id}")
        print(f"{'='*80}")
        print_reasoning_flow(trace_spans, thinking_only=args.thinking_only)

    print()


if __name__ == "__main__":
    main()
