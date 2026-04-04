"""OpenAI SDK + Terrarium integration example.

Zero Terrarium imports. Uses the OpenAI compat endpoint to discover
and execute tools against a running Terrarium world.

Prerequisites:
    pip install openai httpx
    terrarium serve --world <world_id> --port 8080

Usage:
    python main.py
"""

import json
import os

import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # loads .env from current directory or parent

TERRARIUM_URL = "http://localhost:8080"
ACTOR_ID = "financial-analyst"


def main():
    # 1. Discover tools from Terrarium (OpenAI function calling format)
    tools = httpx.get(f"{TERRARIUM_URL}/openai/v1/tools").json()
    print(f"Discovered {len(tools)} tools from Terrarium")

    # 2. Create OpenAI client (uses OPENAI_API_KEY from env)
    client = OpenAI()

    messages = [
        {
            "role": "user",
            "content": (
                "You are a financial analyst doing a comprehensive AAPL review. "
                "1. Get the account status to check buying power. "
                "2. Get AAPL snapshot for current price. "
                "3. Get AAPL daily bars for recent price history. "
                "4. Get latest AAPL news. "
                "5. Check social sentiment on AAPL. "
                "Then provide a full investment recommendation."
            ),
        }
    ]

    # 3. Standard OpenAI tool-calling loop
    for turn in range(10):  # max turns
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            tools=tools,
        )

        message = response.choices[0].message

        # If no tool calls, agent is done
        if not message.tool_calls:
            print(f"\n{'='*60}")
            print("AGENT RESPONSE:")
            print(f"{'='*60}")
            print(message.content)
            break

        # Add assistant message with tool calls
        messages.append(message)

        # 4. Execute each tool call against Terrarium world
        for tc in message.tool_calls:
            print(f"  Tool call: {tc.function.name}({tc.function.arguments[:80]}...)")

            result = httpx.post(
                f"{TERRARIUM_URL}/openai/v1/tools/call",
                json={
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                    "actor_id": ACTOR_ID,
                },
            ).json()

            # Add tool result to messages (standard OpenAI format)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result.get("content", json.dumps(result)),
                }
            )

            is_error = result.get("is_error", False)
            status = "ERROR" if is_error else "OK"
            print(f"    → {status}")

    print(f"\nCompleted in {turn + 1} turns")


if __name__ == "__main__":
    main()
