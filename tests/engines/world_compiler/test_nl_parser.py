"""Tests for NLParser — natural language to structured world plan via LLM."""
import json

import pytest
from unittest.mock import AsyncMock

from volnix.core.errors import NLParseError
from volnix.engines.world_compiler.nl_parser import NLParser
from volnix.llm.types import LLMResponse


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNLParser:
    """NLParser tests with mock LLM router."""

    @pytest.mark.asyncio
    async def test_basic_parse(self, mock_llm_router):
        """NLParser returns (world_def, compiler_settings) tuple."""
        # First call returns world def, second returns compiler settings
        world_json = json.dumps({
            "world": {
                "name": "Support Center",
                "description": "A support team",
                "services": {"gmail": "verified/gmail"},
                "actors": [{"role": "agent", "type": "external", "count": 1}],
                "policies": [],
                "seeds": [],
                "mission": "resolve tickets",
            }
        })
        settings_json = json.dumps({
            "compiler": {
                "seed": 42,
                "behavior": "dynamic",
                "fidelity": "auto",
                "mode": "governed",
                "reality": {"preset": "messy"},
            }
        })
        mock_llm_router.route = AsyncMock(side_effect=[
            LLMResponse(content=world_json, provider="mock", model="mock", latency_ms=0),
            LLMResponse(content=settings_json, provider="mock", model="mock", latency_ms=0),
        ])

        parser = NLParser(mock_llm_router)
        world_def, compiler_settings = await parser.parse("Support team with email")

        assert "world" in world_def
        assert world_def["world"]["name"] == "Support Center"
        assert "compiler" in compiler_settings

    @pytest.mark.asyncio
    async def test_uses_router(self, mock_llm_router):
        """NLParser calls the LLM router (at least twice: world def + settings)."""
        parser = NLParser(mock_llm_router)
        await parser.parse("A test world")

        assert mock_llm_router.route.call_count >= 2

    @pytest.mark.asyncio
    async def test_structured_output(self, mock_llm_router):
        """NLParser uses structured_output when available."""
        structured = {
            "world": {
                "name": "Structured",
                "description": "from structured output",
                "services": {"gmail": "verified/gmail"},
                "actors": [],
                "policies": [],
                "seeds": [],
                "mission": "",
            }
        }
        settings = {"compiler": {"seed": 1, "behavior": "static", "fidelity": "auto",
                                  "mode": "governed", "reality": {"preset": "ideal"}}}
        mock_llm_router.route = AsyncMock(side_effect=[
            LLMResponse(content="", structured_output=structured, provider="mock", model="mock", latency_ms=0),
            LLMResponse(content="", structured_output=settings, provider="mock", model="mock", latency_ms=0),
        ])

        parser = NLParser(mock_llm_router)
        world_def, _ = await parser.parse("Structured test")

        assert world_def["world"]["name"] == "Structured"

    @pytest.mark.asyncio
    async def test_json_in_code_block(self, mock_llm_router):
        """NLParser handles JSON wrapped in markdown code blocks."""
        world_json = json.dumps({
            "world": {
                "name": "Code Block",
                "description": "wrapped in backticks",
                "services": {},
                "actors": [],
                "policies": [],
                "seeds": [],
                "mission": "",
            }
        })
        wrapped = f"```json\n{world_json}\n```"
        settings_json = json.dumps({
            "compiler": {"seed": 42, "behavior": "dynamic", "fidelity": "auto",
                         "mode": "governed", "reality": {"preset": "messy"}}
        })

        mock_llm_router.route = AsyncMock(side_effect=[
            LLMResponse(content=wrapped, provider="mock", model="mock", latency_ms=0),
            LLMResponse(content=settings_json, provider="mock", model="mock", latency_ms=0),
        ])

        parser = NLParser(mock_llm_router)
        world_def, _ = await parser.parse("Code block test")

        assert world_def["world"]["name"] == "Code Block"

    @pytest.mark.asyncio
    async def test_reality_hint_passed(self, mock_llm_router):
        """Reality hint is forwarded to the LLM call."""
        parser = NLParser(mock_llm_router)
        await parser.parse("test", reality="hostile")

        # The second call (compiler settings) should include "hostile" in the prompt
        calls = mock_llm_router.route.call_args_list
        assert len(calls) >= 2
        # The request for compiler settings is the second call
        settings_request = calls[1][0][0]  # first positional arg
        assert "hostile" in settings_request.user_content or "hostile" in settings_request.system_prompt

    @pytest.mark.asyncio
    async def test_behavior_hint_passed(self, mock_llm_router):
        """Behavior hint is forwarded to the LLM call."""
        parser = NLParser(mock_llm_router)
        await parser.parse("test", behavior="static")

        calls = mock_llm_router.route.call_args_list
        assert len(calls) >= 2
        settings_request = calls[1][0][0]
        assert "static" in settings_request.user_content or "static" in settings_request.system_prompt

    @pytest.mark.asyncio
    async def test_invalid_response_raises(self, mock_llm_router):
        """NLParser raises NLParseError when LLM returns unparseable content."""
        mock_llm_router.route = AsyncMock(return_value=LLMResponse(
            content="This is not JSON at all",
            provider="mock",
            model="mock",
            latency_ms=0,
        ))

        parser = NLParser(mock_llm_router)
        with pytest.raises(NLParseError):
            await parser.parse("bad response test")
