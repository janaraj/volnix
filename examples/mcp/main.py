"""MCP + Volnix integration example.

Connects to a running Volnix world via MCP (Streamable HTTP transport).
Works with any MCP client — Claude Desktop, Cursor, OpenClaw, or this script.

Prerequisites:
    pip install mcp
    volnix serve --world <world_id> --port 8080

Usage:
    python main.py

For Claude Desktop / Cursor, add to your MCP config:
    See claude_desktop_config.json (HTTP) or stdio_config.json (stdio)
"""

import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

VOLNIX_URL = "http://localhost:8080/mcp"


async def main():
    # 1. Connect to Volnix's MCP endpoint
    async with streamablehttp_client(VOLNIX_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 2. Discover tools
            tools = await session.list_tools()
            print(f"Discovered {len(tools.tools)} tools via MCP")
            for t in tools.tools[:5]:
                print(f"  {t.name}: {t.description[:60]}")

            # 3. Call tools
            print("\n--- get_account ---")
            result = await session.call_tool("get_account", {})
            data = json.loads(result.content[0].text)
            print(f"  Account: {data.get('status')} | Equity: ${data.get('equity')}")

            print("\n--- get_snapshot ---")
            result = await session.call_tool("get_snapshot", {"symbol": "AAPL"})
            data = json.loads(result.content[0].text)
            quote = data.get("latestQuote", {})
            print(f"  AAPL: bid=${quote.get('bid_price')} ask=${quote.get('ask_price')}")

            print("\n--- get_news ---")
            result = await session.call_tool("get_news", {"symbols": "AAPL", "limit": 3})
            data = json.loads(result.content[0].text)
            for n in data.get("news", [])[:3]:
                print(f"  {n.get('headline', '')[:70]}")

            print("\n--- social_get_sentiment ---")
            result = await session.call_tool("social_get_sentiment", {"symbol": "AAPL"})
            data = json.loads(result.content[0].text)
            print(f"  Sentiment: {data.get('score')} ({data.get('positive_count')}+ / {data.get('negative_count')}-)")

    print("\nMCP E2E complete — 4 tool calls via Streamable HTTP")


if __name__ == "__main__":
    asyncio.run(main())
