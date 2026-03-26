"""Framework adapters for connecting Terrarium to agent frameworks.

Each adapter converts Terrarium tools into framework-specific tool objects.
Import the adapter for your framework:

    from terrarium.adapters.langgraph import langgraph_tools
    from terrarium.adapters.autogen import autogen_tools
    from terrarium.adapters.crewai import crewai_tools

These adapters require their respective framework packages to be installed
(langchain-core, autogen, crewai). They are optional dependencies.
"""
