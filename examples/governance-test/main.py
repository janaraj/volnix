"""Governance E2E test — 3 agents with different permissions and budgets.

Runs against the governance_test world (Stripe + Zendesk + Slack).
Each agent tries the same tasks — Volnix enforces the rules.

Prerequisites:
    volnix serve governance_test --agents tests/fixtures/agents/governance_test_agents.yaml --port 8080

Usage:
    python main.py
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
                print(f"    ✗ BLOCKED_AT_PERMISSION")
            elif is_error and "policy" in content.lower():
                print(f"    ✗ BLOCKED_AT_POLICY")
            elif is_error and "budget" in content.lower():
                print(f"    ✗ BLOCKED_AT_BUDGET")
            elif is_error:
                print(f"    ✗ BLOCKED: {content[:80]}")
            else:
                print(f"    ✓ OK")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": content,
            })


def main():
    print("=" * 70)
    print("VOLNIX GOVERNANCE E2E TEST")
    print("World: governance_test (Stripe + Zendesk + Slack)")
    print("=" * 70)

    # Junior: can read zendesk+slack, can only write to slack
    run_agent(
        "junior-support",
        "You are a junior support agent. "
        "1. List all support tickets from zendesk. "
        "2. Try to update ticket TK-102 status to 'solved'. "
        "3. Post a message in slack saying you checked the tickets. "
        "Report what succeeded and what was blocked."
    )

    # Senior: can read+write zendesk+slack, but NOT stripe
    run_agent(
        "senior-support",
        "You are a senior support agent. "
        "1. List support tickets. "
        "2. Try to process a $50 refund on Stripe (charge ch_reg_001). "
        "3. Update ticket TK-102 with a comment. "
        "Report what succeeded and what was blocked."
    )

    # Manager: full access, but policy blocks refunds over 500 (compiled world threshold)
    run_agent(
        "manager",
        "You are a support manager. "
        "1. List refunds on Stripe. "
        "2. Process a refund of 30 cents (amount=30) for charge ch_reg_001. "
        "This charge is 50 cents so 30 is valid. "
        "3. Try to process a refund of 80000 cents (amount=80000) for charge ch_acme_001. "
        "This should be blocked by the refund policy. "
        "Report what succeeded and what was blocked."
    )

    # Check budgets
    print(f"\n{'='*70}")
    print("BUDGET STATUS")
    print(f"{'='*70}")
    for agent in ["junior-support", "senior-support", "manager"]:
        run_id = httpx.get(f"{VOLNIX_URL}/api/v1/runs?limit=1").json()["runs"][0]["run_id"]
        actor = httpx.get(f"{VOLNIX_URL}/api/v1/runs/{run_id}/actors/{agent}").json()
        budget = actor.get("budget", {})
        actions = actor.get("action_count", 0)
        spend = budget.get("spend_usd_remaining", "n/a")
        api = budget.get("api_calls_remaining", "n/a")
        print(f"  {agent}: {actions} actions | api_calls={api} | spend_usd={spend}")


if __name__ == "__main__":
    main()
