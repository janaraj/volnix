"""Anthropic SDK + Volnix integration example.

Zero Volnix imports. Uses the Anthropic compat endpoint to discover
and execute tools against a running Volnix world.

Prerequisites:
    pip install anthropic httpx
    volnix serve --world <world_id> --port 8080

Usage:
    python main.py
"""

import json

import httpx
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # loads .env from current directory or parent

VOLNIX_URL = "http://localhost:8080"
ACTOR_ID = "anthropic-analyst"


def main():
    # 1. Discover tools from Volnix (Anthropic tool use format)
    tools = httpx.get(f"{VOLNIX_URL}/anthropic/v1/tools").json()
    print(f"Discovered {len(tools)} tools from Volnix")

    # 2. Create Anthropic client (uses ANTHROPIC_API_KEY from env)
    client = Anthropic()

    messages = [
        {
            "role": "user",
            "content": (
                "You are a financial analyst doing a comprehensive AAPL review. "
                "1. Get the account status to check buying power. "
                "2. Get AAPL snapshot for current price. "
                "3. Get latest AAPL news. "
                "4. Check social sentiment on AAPL. "
                "Then provide a full investment recommendation."
            ),
        }
    ]

    # 3. Standard Anthropic tool-calling loop
    for turn in range(10):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=messages,
            tools=tools,
        )

        # Separate text and tool_use blocks
        text_blocks = []
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                text_blocks.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        # If no tool calls, agent is done
        if not tool_uses:
            print(f"\n{'='*60}")
            print("AGENT RESPONSE:")
            print(f"{'='*60}")
            print("\n".join(text_blocks))
            break

        # Add assistant message
        messages.append({"role": "assistant", "content": response.content})

        # 4. Execute each tool call against Volnix world
        tool_results = []
        for tu in tool_uses:
            print(f"  Tool call: {tu.name}({json.dumps(tu.input)[:80]}...)")

            result = httpx.post(
                f"{VOLNIX_URL}/anthropic/v1/tools/call",
                json={
                    "name": tu.name,
                    "input": tu.input,
                    "actor_id": ACTOR_ID,
                },
            ).json()

            is_error = result.get("is_error", False)
            print(f"    → {'ERROR' if is_error else 'OK'}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result.get("content", json.dumps(result)),
                "is_error": is_error,
            })

        # Add tool results
        messages.append({"role": "user", "content": tool_results})

    print(f"\nCompleted in {turn + 1} turns")


if __name__ == "__main__":
    main()
