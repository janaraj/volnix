"""Framework adapters for connecting Volnix to agent frameworks.

Each adapter converts Volnix tools into framework-specific tool objects.
Import the adapter for your framework:

    from volnix.adapters.langgraph import langgraph_tools
    from volnix.adapters.autogen import autogen_tools
    from volnix.adapters.crewai import crewai_tools

These adapters require their respective framework packages to be installed
(langchain-core, autogen, crewai). They are optional dependencies.
"""
