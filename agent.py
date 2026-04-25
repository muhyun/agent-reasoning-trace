import os
import json
from datetime import datetime

from strands import Agent, tool, ToolContext
from strands.models import BedrockModel
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.telemetry import StrandsTelemetry


# --- Custom tools ---

@tool(context=True)
def create_plan(goal: str, steps: list[str], tool_context: ToolContext) -> str:
    """Create a structured plan to achieve a goal. Use this before starting complex tasks.

    Args:
        goal: The high-level goal to achieve
        steps: Ordered list of steps to accomplish the goal
    """
    plan = {"goal": goal, "steps": steps, "status": ["pending"] * len(steps), "created_at": datetime.now().isoformat()}
    tool_context.agent.state.set("current_plan", plan)
    formatted = f"Plan created for: {goal}\n"
    for i, step in enumerate(steps, 1):
        formatted += f"  {i}. [ ] {step}\n"
    return formatted


@tool(context=True)
def update_plan_step(step_number: int, status: str, notes: str, tool_context: ToolContext) -> str:
    """Mark a plan step as completed or in-progress, with optional notes.

    Args:
        step_number: The 1-based step number to update
        status: New status - one of 'completed', 'in_progress', 'blocked', 'skipped'
        notes: Notes about what was done or learned in this step
    """
    plan = tool_context.agent.state.get("current_plan")
    if not plan:
        return "Error: No active plan. Create one first with create_plan."

    idx = step_number - 1
    if idx < 0 or idx >= len(plan["steps"]):
        return f"Error: Invalid step number {step_number}. Plan has {len(plan['steps'])} steps."

    plan["status"][idx] = status
    if "notes" not in plan:
        plan["notes"] = {}
    plan["notes"][str(step_number)] = notes
    tool_context.agent.state.set("current_plan", plan)

    symbols = {"completed": "x", "in_progress": "~", "blocked": "!", "skipped": "-"}
    symbol = symbols.get(status, "?")

    result = f"Step {step_number} marked as {status}.\n\nCurrent plan:\n"
    for i, step in enumerate(plan["steps"]):
        s = plan["status"][i]
        sym = symbols.get(s, " ")
        result += f"  [{sym}] {i+1}. {step}\n"
    return result


@tool(context=True)
def get_plan(tool_context: ToolContext) -> str:
    """Retrieve the current plan and its status."""
    plan = tool_context.agent.state.get("current_plan")
    if not plan:
        return "No active plan."

    symbols = {"completed": "x", "in_progress": "~", "blocked": "!", "skipped": "-", "pending": " "}
    result = f"Goal: {plan['goal']}\n"
    for i, step in enumerate(plan["steps"]):
        s = plan["status"][i]
        sym = symbols.get(s, " ")
        note = plan.get("notes", {}).get(str(i + 1), "")
        result += f"  [{sym}] {i+1}. {step}"
        if note:
            result += f"  -- {note}"
        result += "\n"

    completed = sum(1 for s in plan["status"] if s == "completed")
    result += f"\nProgress: {completed}/{len(plan['steps'])} steps completed"
    return result


@tool(context=True)
def save_finding(title: str, content: str, tags: list[str], tool_context: ToolContext) -> str:
    """Save an important finding or insight discovered during reasoning.

    Args:
        title: Short title for the finding
        content: Detailed content of the finding
        tags: List of tags to categorize the finding
    """
    findings = tool_context.agent.state.get("findings") or []
    findings.append({
        "title": title,
        "content": content,
        "tags": tags,
        "timestamp": datetime.now().isoformat(),
    })
    tool_context.agent.state.set("findings", findings)
    return f"Finding saved: '{title}' [tags: {', '.join(tags)}]. Total findings: {len(findings)}"


@tool(context=True)
def list_findings(tag_filter: str, tool_context: ToolContext) -> str:
    """List all saved findings, optionally filtered by tag.

    Args:
        tag_filter: Tag to filter by, or 'all' to show everything
    """
    findings = tool_context.agent.state.get("findings") or []
    if not findings:
        return "No findings saved yet."

    if tag_filter != "all":
        findings = [f for f in findings if tag_filter in f["tags"]]

    result = f"Findings ({len(findings)}):\n"
    for i, f in enumerate(findings, 1):
        result += f"\n  {i}. [{', '.join(f['tags'])}] {f['title']}\n     {f['content'][:200]}\n"
    return result


@tool
def analyze(question: str, considerations: list[str]) -> str:
    """Structure your reasoning about a question by listing key considerations.
    Use this to think through problems systematically before answering.

    Args:
        question: The question or problem to analyze
        considerations: List of key factors, trade-offs, or perspectives to consider
    """
    result = f"Analysis of: {question}\n\nKey considerations:\n"
    for i, c in enumerate(considerations, 1):
        result += f"  {i}. {c}\n"
    result += f"\nTotal factors considered: {len(considerations)}"
    return result


# --- Agent setup ---

SYSTEM_PROMPT = """\
You are a reasoning and planning agent. You think step-by-step, create plans, \
and track your progress as you work through complex problems.

## How you work

1. **Understand**: When given a task, first clarify what's being asked. Use the \
`analyze` tool to structure your thinking about the problem.

2. **Plan**: For non-trivial tasks, use `create_plan` to break the work into \
concrete steps before starting.

3. **Execute**: Work through your plan step by step. After completing each step, \
use `update_plan_step` to record what you did and what you learned.

4. **Record**: Use `save_finding` to capture important insights, intermediate \
results, or decisions. These persist across turns so you can reference them later.

5. **Reflect**: After completing a plan, review your findings with `list_findings` \
and synthesize a final answer.

## Guidelines

- Always show your reasoning. Don't jump to conclusions.
- When you're uncertain, say so and explain what would reduce uncertainty.
- If a question is ambiguous, analyze the different interpretations before choosing one.
- For multi-part problems, tackle them one piece at a time with a plan.
- Reference your saved findings when building on previous reasoning.
"""


def setup_telemetry():
    trace_file = open("traces.jsonl", "a")
    StrandsTelemetry() \
        .setup_otlp_exporter(endpoint="http://localhost:4318/v1/traces") \
        .setup_console_exporter(out=trace_file, formatter=lambda span: span.to_json() + "\n")


def create_agent():
    setup_telemetry()

    model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        region_name="us-west-2",
        max_tokens=8192,
        additional_request_fields={
            "thinking": {"type": "enabled", "budget_tokens": 4096},
        },
    )

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[create_plan, update_plan_step, get_plan, save_finding, list_findings, analyze],
        conversation_manager=SlidingWindowConversationManager(window_size=40),
        state={"findings": [], "current_plan": None},
        trace_attributes={"session.id": "reasoning-agent", "agent.type": "reasoning-planning"},
    )
    return agent


def main():
    agent = create_agent()
    print("Reasoning Agent ready. Type 'quit' to exit, 'plan' to see current plan, 'findings' to list findings.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("Goodbye!")
            break
        if user_input.lower() == "plan":
            plan = agent.state.get("current_plan")
            if plan:
                print(f"\nCurrent plan: {plan['goal']}")
                for i, step in enumerate(plan["steps"]):
                    print(f"  [{plan['status'][i]}] {i+1}. {step}")
            else:
                print("\nNo active plan.")
            print()
            continue
        if user_input.lower() == "findings":
            findings = agent.state.get("findings") or []
            if findings:
                for f in findings:
                    print(f"  [{', '.join(f['tags'])}] {f['title']}: {f['content'][:100]}")
            else:
                print("No findings yet.")
            print()
            continue

        print("\nAgent: ", end="", flush=True)
        response = agent(user_input)
        print("\n")


if __name__ == "__main__":
    main()
