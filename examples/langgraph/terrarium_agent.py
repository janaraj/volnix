from collections.abc import Sequence
from typing import Annotated, Literal, TypedDict

from langchain_anthropic import ChatAnthropic
# TERRARIUM CHANGE: Replace TavilySearchResults with Terrarium world tools
import asyncio
from terrarium.adapters.langgraph import langgraph_tools
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, add_messages
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

# TERRARIUM CHANGE: One line swap — tools from Terrarium world instead of Tavily
tools = asyncio.get_event_loop().run_until_complete(
    langgraph_tools("http://localhost:8080", actor_id="langgraph-analyst")
)

model_anth = ChatAnthropic(temperature=0, model_name="claude-3-sonnet-20240229")
model_oai = ChatOpenAI(temperature=0)

model_anth = model_anth.bind_tools(tools)
model_oai = model_oai.bind_tools(tools)


class AgentContext(TypedDict):
    model: Literal["anthropic", "openai"]


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


# Define the function that determines whether to continue or not
def should_continue(state):
    messages = state["messages"]
    last_message = messages[-1]
    # If there are no tool calls, then we finish
    if not last_message.tool_calls:
        return "end"
    # Otherwise if there is, we continue
    else:
        return "continue"


# Define the function that calls the model
def call_model(state, runtime: Runtime[AgentContext] = None):
    if runtime and runtime.context and runtime.context.get("model") == "anthropic":
        model = model_anth
    else:
        model = model_oai
    messages = state["messages"]
    response = model.invoke(messages)
    # We return a list, because this will get added to the existing list
    return {"messages": [response]}


# Define the function to execute tools
tool_node = ToolNode(tools)


# Define a new graph
workflow = StateGraph(AgentState, context_schema=AgentContext)

# Define the two nodes we will cycle between
workflow.add_node("agent", call_model)
workflow.add_node("action", tool_node)

# Set the entrypoint as `agent`
# This means that this node is the first one called
workflow.set_entry_point("agent")

# We now add a conditional edge
workflow.add_conditional_edges(
    # First, we define the start node. We use `agent`.
    # This means these are the edges taken after the `agent` node is called.
    "agent",
    # Next, we pass in the function that will determine which node is called next.
    should_continue,
    # Finally we pass in a mapping.
    # The keys are strings, and the values are other nodes.
    # END is a special node marking that the graph should finish.
    # What will happen is we will call `should_continue`, and then the output of that
    # will be matched against the keys in this mapping.
    # Based on which one it matches, that node will then be called.
    {
        # If `tools`, then we call the tool node.
        "continue": "action",
        # Otherwise we finish.
        "end": END,
    },
)

# We now add a normal edge from `tools` to `agent`.
# This means that after `tools` is called, `agent` node is called next.
workflow.add_edge("action", "agent")

# Finally, we compile it!
# This compiles it into a LangChain Runnable,
# meaning you can use it as you would any other runnable
graph = workflow.compile()

if __name__ == "__main__":
    import asyncio as _asyncio
    from langchain_core.messages import HumanMessage

    async def _run():
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=(
            "You are a financial analyst doing a comprehensive AAPL review. "
            "1. Get the account status to check buying power. "
            "2. Get AAPL snapshot for current price. "
            "3. Get latest AAPL news. "
            "4. Check social sentiment on AAPL. "
            "Then provide a full investment recommendation."
        ))]},
        )
        print(result["messages"][-1].content)

    _asyncio.run(_run())
