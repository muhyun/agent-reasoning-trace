"""Run a multi-turn reasoning example to generate a good trace."""

from agent import create_agent

agent = create_agent()

prompts = [
    (
        "A startup has $500K in funding and needs to decide between two strategies: "
        "(A) Build an AI-powered product for enterprise customers with longer sales cycles but higher revenue per customer, or "
        "(B) Build a consumer app with viral growth potential but uncertain monetization. "
        "They have a 3-person technical team and 18 months of runway. "
        "Analyze this decision thoroughly — consider financials, risk, team fit, and market timing."
    ),
    (
        "Good analysis. Now assume they pick Strategy A (enterprise AI). "
        "Create a detailed 18-month execution plan with milestones, "
        "and identify the top 3 risks that could kill the company."
    ),
    (
        "One more thing — their lead engineer just got an offer from Google. "
        "How does this change the analysis? What should they do in the next 48 hours?"
    ),
]

for i, prompt in enumerate(prompts, 1):
    print(f"\n{'='*60}")
    print(f"TURN {i}")
    print(f"{'='*60}")
    print(f"User: {prompt[:100]}...")
    print(f"\nAgent: ", end="", flush=True)
    response = agent(prompt)
    print(f"\n")

print("Done. Traces written to traces.jsonl")
