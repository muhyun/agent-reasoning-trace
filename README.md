# agent-reasoning-trace

OTEL traces reveal how AI agents reason and plan — built with [Strands Agent SDK](https://strandsagents.com/) and Claude Sonnet 4.5 on Amazon Bedrock.

See the full write-up: [What OTEL Traces Reveal About How AI Agents Actually Think](blog-reasoning-otel-traces.md)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the agent

```bash
# Interactive multi-turn conversation
python agent.py

# Generate a reasoning trace example
python run_example.py
```

## Extract reasoning from traces

```bash
# List all traces
python extract_reasoning.py traces.jsonl --list-traces

# Show full reasoning flow
python extract_reasoning.py traces.jsonl

# Only extended thinking blocks
python extract_reasoning.py traces.jsonl --thinking-only

# Filter to a specific trace
python extract_reasoning.py traces.jsonl --trace-id <id>

# JSON output
python extract_reasoning.py traces.jsonl --json
```

## View traces in Jaeger

```bash
docker run -d -p 16686:16686 -p 4318:4318 jaegertracing/jaeger:latest
# Open http://localhost:16686
```

## Requirements

- Python 3.10+
- AWS credentials configured (for Bedrock)
- Docker (optional, for Jaeger)
