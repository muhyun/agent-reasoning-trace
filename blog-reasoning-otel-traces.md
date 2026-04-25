# What OTEL Traces Reveal About How AI Agents Actually Think

When you ask an AI agent to "analyze this decision" or "create a plan," what actually happens under the hood? Most people see only the final response. But with OpenTelemetry instrumentation, we can crack open the black box and watch the agent's entire cognitive process unfold — every moment of deliberation, every tool call, every course correction.

In this post, I'll show you what reasoning and planning look like inside OTEL traces from a real AI agent, and what those patterns reveal about agent execution quality.

## The Setup

I built a multi-turn planning agent using the [Strands Agent SDK](https://strandsagents.com/) with Claude Sonnet 4.5 on Amazon Bedrock, extended thinking enabled. The agent has six custom tools: `analyze`, `create_plan`, `update_plan_step`, `save_finding`, `list_findings`, and `get_plan`. OTEL traces are exported via the SDK's built-in telemetry to both Jaeger and a local trace file.

I gave it a three-turn scenario: analyze a startup strategy decision, build an execution plan, then respond to a crisis (a key engineer getting poached by Google).

## What Lives Inside a Trace

A Strands agent trace has a four-level span hierarchy:

```
Agent span (full invocation)
  └── Cycle span (one per event-loop iteration)
        └── Chat span (model invocation with token counts, latency)
        └── Tool span (tool execution with inputs/outputs)
```

Each `chat` span contains OTEL events that capture the full conversation exchange:

- **`gen_ai.system.message`** — the system prompt
- **`gen_ai.user.message`** — user input
- **`gen_ai.choice`** — the model's response, including text, tool calls, and critically, **thinking blocks**

When extended thinking is enabled, Claude produces `reasoningContent` blocks before generating its visible response. These get captured in the trace as structured content parts — the agent's internal deliberation, preserved in full.

## Finding 1: Thinking Blocks Reveal the Agent's Metacognition

Here's what the first thinking block looks like when the agent receives a complex strategy question:

```
THINKING:
  | This is a complex strategic decision that requires systematic
  | analysis. Let me break this down into multiple dimensions:
  |
  | 1. Financial considerations
  | 2. Risk analysis
  | 3. Team fit
  | 4. Market timing
  | 5. Runway and burn rate
  | 6. Go-to-market strategies
  | 7. Success metrics
  |
  | I should use the analyze tool first to structure my thinking,
  | then create a plan to work through this systematically, and
  | save findings as I discover important insights.
```

This isn't the response the user sees. It's the model reasoning about *how to approach the problem* before taking any action. In OTEL terms, this appears as a `reasoningContent` part within the `gen_ai.choice` event of a `chat` span.

What's valuable here from a quality perspective: the thinking block shows **task decomposition** and **tool selection strategy** happening before execution. When this step is absent or shallow, it's a leading indicator that the agent will produce unfocused or incomplete work.

## Finding 2: The Execution Pattern Tells a Story

By looking at the sequence of chat spans within a trace, we can extract an execution pattern. Each chat span either contains Thinking (T), tool Calls (C), or just a Response (R):

```
Turn 1 (strategy analysis):
  TC -> TC -> TC -> TC -> TC -> TC -> TC -> ... (17 cycles)

Turn 2 (execution plan):
  TC -> TC -> TC -> TC -> TC -> TC -> TC -> ... (16 cycles)

Turn 3 (crisis response):
  TC -> TC -> TC -> TC -> TC -> TC -> TC -> ... (13 cycles)
```

Every single cycle includes both thinking and tool calls. The agent never acts without deliberating first — a `TC` pattern. This is the trace signature of a disciplined reasoning agent: **think, then act, repeat**.

Contrast this with what a poorly-instrumented or poorly-prompted agent might look like:

```
C -> C -> C -> C -> R  (tool spam, no deliberation)
```

Or an over-thinking agent:

```
T -> T -> T -> T -> R  (all thinking, no tool use, hallucinated answers)
```

The execution pattern extracted from traces is a quality fingerprint. You can monitor it in production to detect when agents deviate from expected behavior.

## Finding 3: Context Growth Reveals Cognitive Load

One pattern visible in traces is how input token counts escalate across chat spans within a single turn:

```
Turn 1:  1,559 → 2,190 → 2,561 → 3,058 → 3,287 → ...  tokens in
Turn 2: 10,764 → 11,321 → 11,946 → 12,408 → ...        tokens in
Turn 3: 28,116 → 28,946 → 29,291 → ...                  tokens in
```

Each cycle appends previous tool results to the conversation, so input tokens grow monotonically. But the *rate* of growth and the *starting point* tell you something important:

- **Turn 1 starts at 1,559 tokens** — fresh context, just system prompt and user message.
- **Turn 2 starts at 10,764** — carries the full history from Turn 1's 17-cycle analysis.
- **Turn 3 starts at 28,116** — accumulated context from both prior turns.

This is the agent's cognitive load. In our three-turn example, the agent processed a total of **810,005 input tokens** and produced **35,766 output tokens** across 46 chat cycles. The context escalation is why conversation management strategies (sliding window, summarization) matter — without them, later turns become slower and more expensive.

From OTEL traces, you can set alerts when input token counts exceed thresholds, catching runaway context before it blows up your costs.

## Finding 4: Tool Call Distribution Reveals Agent Strategy

The tool call distribution across each trace tells you how the agent chose to work:

```
Turn 1 (analyze a decision):
  analyze: 34, create_plan: 32, update_plan_step: 152
  save_finding: 82, list_findings: 4

Turn 2 (build execution plan):
  analyze: 32, create_plan: 64, update_plan_step: 426
  save_finding: 224, list_findings: 36

Turn 3 (crisis response):
  analyze: 52, create_plan: 76, update_plan_step: 546
  save_finding: 256, list_findings: 56
```

Several patterns emerge:

**`update_plan_step` dominates** — the agent spends most of its effort recording progress and intermediate results, not just planning or analyzing. This is the trace signature of a methodical agent that maintains state across its reasoning.

**`list_findings` increases across turns** — in Turn 1, the agent barely reviews its notes (4 calls). By Turn 3, it's checking its findings 56 times. The agent learned to reference accumulated knowledge as context grew. You can see *learning within a session* in the trace data.

**`create_plan` increases in crisis mode** — Turn 3 shows 76 plan creation calls versus 32 in Turn 1. When confronted with the engineer-departure crisis, the agent created and revised plans more frequently, reflecting the higher uncertainty of the situation.

## Finding 5: Thinking Blocks Show Genuine Adaptation

The most striking evidence of agent quality comes from comparing thinking blocks across turns. In Turn 1, the thinking is templated — "break this down into dimensions." By Turn 3, the thinking shows genuine situational awareness:

```
THINKING:
  | Oh wow, this is a CRITICAL crisis moment. Let me think
  | through the implications:
  |
  | 1. They're choosing the enterprise strategy
  |    (which I already said was risky)
  | 2. They have a 3-person technical team
  | 3. One of those 3 just got a Google offer
  | 4. They haven't even started yet (this is pre-launch)
  |
  | This is potentially company-ending. Let me analyze:
  |
  | IMMEDIATE IMPLICATIONS:
  | - Lose 33% of technical capacity
  | - Enterprise strategy already required all 3 people
  | - Google offers are lucrative and hard to compete with
  | - 48-hour window suggests engineer is considering it
  |
  | STRATEGIC IMPLICATIONS:
  | - Enterprise strategy becomes nearly impossible with 2 people
  | - Consumer strategy also very hard but slightly more feasible
  | - This is a forcing function to make hard decisions NOW
```

This thinking block references findings from previous turns ("which I already said was risky"), connects the new information to existing analysis, and correctly identifies this as a severity escalation. Without OTEL traces, this internal reasoning would be completely invisible.

## What This Means for Production Agent Systems

These trace patterns suggest a concrete set of things to monitor:

**1. Thinking-to-action ratio.** A healthy agent should show `TC` patterns. Pure `C` (action without thinking) or pure `T` (thinking without acting) are warning signs. Calculate this from span event types.

**2. Context growth rate.** Plot input tokens per cycle. Linear growth is expected; super-linear growth means tool results are too verbose or the conversation manager isn't compacting effectively.

**3. Tool call distribution entropy.** An agent that calls the same tool repeatedly may be stuck in a loop. An agent that uses a diverse set of tools proportionally is more likely to be making progress. Track the distribution per trace.

**4. Planning depth.** Count the ratio of `create_plan` to `update_plan_step` calls. A high ratio means the agent keeps re-planning without executing. A low ratio means it's executing without reflecting. The sweet spot is in between.

**5. Cross-turn reference frequency.** How often does the agent call `list_findings` or reference previous context? Increasing frequency across turns suggests the agent is building on prior reasoning rather than starting fresh each time.

## The OTEL GenAI Semantic Conventions

The OpenTelemetry community has formalized how to capture this data. The `gen_ai.*` semantic conventions define standard attributes for LLM spans:

- `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` — token accounting per model call
- `gen_ai.system.message`, `gen_ai.user.message`, `gen_ai.choice` — conversation events
- `gen_ai.server.request.duration` — model latency

For reasoning specifically, the spec now includes a `ReasoningPart` type (`"type": "reasoning"`) within message events, designed to capture thinking blocks from Claude, OpenAI o-series, Deepseek R1, and similar models. A proposed `gen_ai.usage.reasoning.output_tokens` attribute (not yet merged) would enable tracking reasoning token costs separately.

The Strands SDK maps Claude's `reasoningContent` blocks through a generic content handler, so they appear in traces as structured parts that tools like our `extract_reasoning.py` can parse.

## Try It Yourself

The full code is available in the [agent-reasoning-trace](https://github.com/muhyun/agent-reasoning-trace) repo:

- [`agent.py`](https://github.com/muhyun/agent-reasoning-trace/blob/main/agent.py) — Multi-turn reasoning agent with Strands SDK, Claude Sonnet 4.5 on Bedrock, and extended thinking
- [`extract_reasoning.py`](https://github.com/muhyun/agent-reasoning-trace/blob/main/extract_reasoning.py) — Tool to extract reasoning/thinking blocks from OTEL trace files
- [`run_example.py`](https://github.com/muhyun/agent-reasoning-trace/blob/main/run_example.py) — Example runner that generates a 3-turn reasoning trace

To reproduce:

```bash
pip install 'strands-agents[anthropic]' strands-agents-tools

# Run the agent
python agent.py

# Extract reasoning from traces
python extract_reasoning.py traces.jsonl --thinking-only
python extract_reasoning.py traces.jsonl --list-traces
python extract_reasoning.py traces.jsonl --trace-id <id>

# Or view in Jaeger
docker run -d -p 16686:16686 -p 4318:4318 jaegertracing/jaeger:latest
# Then open http://localhost:16686
```

## Conclusion

OTEL traces on AI agents aren't just operational telemetry — they're a window into *how the agent reasons*. The thinking blocks show metacognition and adaptation. The execution patterns reveal discipline or chaos. The token growth curves expose efficiency. The tool distributions map strategy.

For anyone building production agent systems, these traces are the difference between "it seems to work" and "I can prove how it works." Instrument your agents, read their traces, and let the data tell you whether your agent is actually thinking — or just generating text.
