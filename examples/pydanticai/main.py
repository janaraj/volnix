"""PydanticAI + Terrarium integration example.

Zero Terrarium imports. PydanticAI connects directly via MCP —
Terrarium's tools appear as native PydanticAI toolsets.

Based on PydanticAI MCP client docs:
  https://ai.pydantic.dev/mcp/client/

Prerequisites:
    pip install pydantic-ai[openai]
    terrarium serve --world <world_id> --port 8080

Usage:
    python main.py
"""

import asyncio

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP

load_dotenv()  # loads .env from current directory or parent

TERRARIUM_MCP = "http://localhost:8080/mcp/"


async def main():
    # Connect to Terrarium via MCP — zero Terrarium imports
    server = MCPServerStreamableHTTP(TERRARIUM_MCP)
    agent = Agent("openai:gpt-4.1-mini", toolsets=[server])

    async with agent:
        result = await agent.run(
            "You are a financial analyst doing a comprehensive AAPL review. "
            "1. Get the account status to check buying power. "
            "2. Get AAPL snapshot for current price. "
            "3. Get latest AAPL news. "
            "4. Check social sentiment on AAPL. "
            "Then provide a full investment recommendation."
        )
        print(result.output)


if __name__ == "__main__":
    asyncio.run(main())
