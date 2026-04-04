"""Google Gemini SDK + Terrarium integration example.

Zero Terrarium imports. Uses the Gemini compat endpoint to discover
and execute tools against a running Terrarium world.

Prerequisites:
    pip install google-genai httpx
    terrarium serve --world <world_id> --port 8080

Usage:
    python main.py
"""

import json

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()  # loads .env from current directory or parent

TERRARIUM_URL = "http://localhost:8080"
ACTOR_ID = "gemini-analyst"


def main():
    # 1. Discover tools from Terrarium (Gemini function declaration format)
    tool_defs = httpx.get(f"{TERRARIUM_URL}/gemini/v1/tools").json()
    print(f"Discovered {len(tool_defs)} tools from Terrarium")

    # 2. Convert to Gemini FunctionDeclarations
    declarations = []
    for t in tool_defs:
        declarations.append(types.FunctionDeclaration(
            name=t["name"],
            description=t.get("description", ""),
            parameters_json_schema=t.get("parameters_json_schema", {}),
        ))
    gemini_tools = [types.Tool(function_declarations=declarations)]

    # 3. Create Gemini client (uses GOOGLE_API_KEY from env)
    client = genai.Client()

    prompt = (
        "You are a financial analyst doing a comprehensive AAPL review. "
        "1. Get the account status to check buying power. "
        "2. Get AAPL snapshot for current price. "
        "3. Get latest AAPL news. "
        "4. Check social sentiment on AAPL. "
        "Then provide a full investment recommendation."
    )
    contents = [
        types.Content(
            role="user",
            parts=[types.Part(text=prompt)],
        )
    ]

    # 4. Standard Gemini function-calling loop
    for turn in range(10):
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                tools=gemini_tools,
                temperature=0.7,
            ),
        )

        # Check for function calls in response
        function_calls = []
        text_parts = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, "function_call") and part.function_call:
                function_calls.append(part.function_call)
            elif hasattr(part, "text") and part.text:
                text_parts.append(part.text)

        # If no function calls, agent is done
        if not function_calls:
            print(f"\n{'='*60}")
            print("AGENT RESPONSE:")
            print(f"{'='*60}")
            print("\n".join(text_parts))
            break

        # Add model response to conversation
        contents.append(response.candidates[0].content)

        # 5. Execute each function call against Terrarium world
        function_responses = []
        for fc in function_calls:
            args = dict(fc.args) if fc.args else {}
            print(f"  Tool call: {fc.name}({json.dumps(args)[:80]}...)")

            result = httpx.post(
                f"{TERRARIUM_URL}/gemini/v1/tools/call",
                json={
                    "name": fc.name,
                    "args": args,
                    "actor_id": ACTOR_ID,
                },
            ).json()

            print(f"    → OK")

            function_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response=result.get("response", result),
                )
            )

        # Add function responses to conversation
        contents.append(types.Content(
            role="user",
            parts=function_responses,
        ))

    print(f"\nCompleted in {turn + 1} turns")


if __name__ == "__main__":
    main()
