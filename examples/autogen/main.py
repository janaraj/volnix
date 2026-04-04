"""AutoGen + Terrarium integration example.

Based on the official AutoGen teams tutorial:
  python/docs/src/user-guide/agentchat-user-guide/tutorial/teams.ipynb

The ONLY change: tools come from Terrarium instead of local Python functions.

Prerequisites:
    pip install autogen-agentchat autogen-ext[openai] terrarium
    terrarium serve --world <world_id> --port 8080

Usage:
    python main.py
"""

import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv

from terrarium.adapters.autogen import autogen_tools

load_dotenv()  # loads .env from current directory or parent

TERRARIUM_URL = "http://localhost:8080"


async def main():
    # ── THIS IS THE ONLY CHANGE ──────────────────────────────────
    # BEFORE (from AutoGen tutorial):
    #   tools = [increment_number]  # local Python function
    #
    # AFTER: Each agent gets tools bound to its Terrarium identity.
    # Permissions + budgets are defined in the agent YAML profile
    # and enforced by Terrarium's governance pipeline.
    researcher_tools = await autogen_tools(url=TERRARIUM_URL, actor_id="research-analyst")
    advisor_tools = await autogen_tools(url=TERRARIUM_URL, actor_id="investment-advisor")
    print(f"Discovered {len(researcher_tools)} tools from Terrarium")
    # ──────────────────────────────────────────────────────────────

    tool_model = OpenAIChatCompletionClient(model="gpt-4.1-mini", parallel_tool_calls=False)

    # Multi-agent team — each agent has its own Terrarium identity
    researcher = AssistantAgent(
        "researcher",
        model_client=tool_model,
        tools=researcher_tools,
        system_message=(
            "You are a research analyst. Use tools to gather AAPL data: "
            "get_account, get_snapshot, get_news, social_get_sentiment. "
            "Call all 4 tools, then summarize the raw data. Do not give recommendations."
        ),
    )
    advisor = AssistantAgent(
        "advisor",
        model_client=tool_model,
        tools=advisor_tools,
        system_message="You are an investment advisor. Review the researcher's data and give a buy/hold/sell recommendation with reasoning.",
    )

    termination_condition = TextMessageTermination("advisor")

    team = RoundRobinGroupChat(
        [researcher, advisor],
        termination_condition=termination_condition,
    )

    # Run the team (official tutorial pattern)
    async for message in team.run_stream(
        task=(
            "Do a comprehensive AAPL review: "
            "1. Get account status. "
            "2. Get AAPL snapshot. "
            "3. Get latest AAPL news. "
            "4. Check social sentiment. "
            "Then provide a recommendation."
        )
    ):
        print(type(message).__name__, getattr(message, "content", "")[:200] if hasattr(message, "content") else message)

    await tool_model.close()


if __name__ == "__main__":
    asyncio.run(main())
