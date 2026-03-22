"""Live integration tests — require real LLM API keys.

These tests mirror actual user workflows and make REAL LLM calls.
Run separately after significant changes:

    source .env && pytest tests/live/ -v -s

Each test file covers a distinct user flow:
- test_nl_create_world.py    — User describes a world in natural language
- test_yaml_blueprint.py     — User provides YAML world definition + compiler settings
- test_full_simulation.py    — Complete: create → generate → act → query → report
"""
