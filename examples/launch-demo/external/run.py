"""E-commerce External Demo — governed AI in 5 minutes.

Two agents (support-bot, admin) handle the same tasks.
Volnix enforces different outcomes based on permissions and policies.

Prerequisites:
    volnix serve demo_ecommerce --agents examples/launch-demo/external/agents.yaml --port 8080

Usage:
    python run.py
"""

import json

import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

VOLNIX_URL = "http://localhost:8080"


def run_agent(actor_id: str, task: str):
    """Run an OpenAI agent with a specific Volnix identity."""
    tools = httpx.get(f"{VOLNIX_URL}/openai/v1/tools").json()
    client = OpenAI()

    messages = [{"role": "user", "content": task}]

    print(f"\n{'='*70}")
    print(f"AGENT: {actor_id}")
    print(f"TASK: {task}")
    print(f"{'='*70}")

    for turn in range(5):
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            tools=tools,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            print(f"\nRESPONSE: {message.content[:300]}")
            break

        messages.append(message)

        for tc in message.tool_calls:
            args_str = tc.function.arguments[:60]
            print(f"  → {tc.function.name}({args_str})")

            result = httpx.post(
                f"{VOLNIX_URL}/openai/v1/tools/call",
                json={
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                    "actor_id": actor_id,
                },
            ).json()

            is_error = result.get("is_error", False)
            content = result.get("content", "")

            if is_error and "permission" in content.lower():
                print("    ✗ BLOCKED_AT_PERMISSION")
            elif is_error and "policy" in content.lower():
                print("    ✗ BLOCKED_AT_POLICY")
            elif is_error and "budget" in content.lower():
                print("    ✗ BLOCKED_AT_BUDGET")
            elif is_error:
                print(f"    ✗ BLOCKED: {content[:80]}")
            else:
                print("    ✓ OK")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": content,
            })


def main():
    print("=" * 70)
    print("VOLNIX DEMO: E-commerce Order Management (External)")
    print("World: demo_ecommerce (Stripe + Zendesk + Slack)")
    print("=" * 70)

    # Agent 1: support-bot — can read stripe but NOT write
    run_agent(
        "support-bot",
        "You are a customer support bot for an e-commerce store. "
        "1. List all support tickets to see pending issues. "
        "2. Try to process a refund of 4500 cents (amount=4500) for charge ch_bob_001. "
        "3. Post a message in slack channel #orders summarizing what you did. "
        "Report what succeeded and what was blocked."
    )

    # Agent 2: admin — full write access, but policy blocks large refunds
    run_agent(
        "admin",
        "You are the store admin. "
        "1. List all refunds on Stripe. "
        "2. Process a refund of 4500 cents (amount=4500) for charge ch_bob_001. "
        "This is Bob's $45 refund request. "
        "3. Try to process a large refund of 50000 cents (amount=50000) for charge ch_alice_001. "
        "This should be blocked by the refund policy (max $250). "
        "Report what succeeded and what was blocked."
    )

    # Budget status
    print(f"\n{'='*70}")
    print("BUDGET STATUS")
    print(f"{'='*70}")
    for agent in ["support-bot", "admin"]:
        run_id = httpx.get(f"{VOLNIX_URL}/api/v1/runs?limit=1").json()["runs"][0]["run_id"]
        actor = httpx.get(f"{VOLNIX_URL}/api/v1/runs/{run_id}/actors/{agent}").json()
        budget = actor.get("budget", {})
        actions = actor.get("action_count", 0)
        spend = budget.get("spend_usd_remaining", "n/a")
        api = budget.get("api_calls_remaining", "n/a")
        print(f"  {agent}: {actions} actions | api_calls={api} | spend_usd={spend}")


if __name__ == "__main__":
    main()
