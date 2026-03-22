"""NL parser — converts natural language description to structured world plan.

Uses the LLM as a TRANSLATOR (Layer 1): NL → structured YAML dicts.
This is different from Layer 2 (entity generation in D4b) which uses
LLM as a CREATOR to generate content.
"""
from __future__ import annotations
import json
import logging
from typing import Any

from terrarium.core.errors import NLParseError
from terrarium.engines.world_compiler.prompt_templates import (
    NL_TO_WORLD_DEF,
    NL_TO_COMPILER_SETTINGS,
    PromptTemplate,
)
from terrarium.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class NLParser:
    """Converts natural language world description to structured dicts."""

    def __init__(self, llm_router: LLMRouter) -> None:
        self._router = llm_router

    async def parse(
        self,
        description: str,
        reality: str = "messy",
        behavior: str = "dynamic",
        fidelity: str = "auto",
        seed: int = 42,
        categories: str = "",
        verified_packs: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """NL description → (world_def_dict, compiler_settings_dict).

        Uses two LLM calls:
        1. NL → world definition (services, actors, policies, seeds)
        2. NL → compiler settings (reality, behavior, animator)

        Args:
            description: Natural language world description
            reality: Preset hint (ideal/messy/hostile)
            behavior: Behavior mode hint (static/reactive/dynamic)
            fidelity: Fidelity mode hint (auto/strict/exploratory)
            seed: Reproducibility seed
            categories: Comma-separated category names (for LLM context)
            verified_packs: Comma-separated pack names (for LLM context)

        Returns:
            Tuple of (world_def_dict, compiler_settings_dict)

        Raises:
            NLParseError: If LLM response cannot be parsed
        """
        # Step 1: Generate world definition
        world_def = await self._generate_world_def(description, categories, verified_packs)

        # Step 2: Generate compiler settings
        compiler_settings = await self._generate_compiler_settings(
            description, reality, behavior, fidelity, seed
        )

        return world_def, compiler_settings

    async def _generate_world_def(self, description: str, categories: str, verified_packs: str) -> dict:
        """Use LLM to generate world definition from NL."""
        try:
            response = await NL_TO_WORLD_DEF.execute(
                self._router,
                description=description,
                categories=categories or "communication, work_management, money_transactions, scheduling, code_devops, identity_auth, storage_documents, authority_approvals, monitoring_observability",
                verified_packs=verified_packs or "email, chat, tickets, payments, repos, calendar",
            )
            return NL_TO_WORLD_DEF.parse_json_response(response)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise NLParseError(f"Failed to parse world definition from LLM: {exc}")
        except Exception as exc:
            raise NLParseError(f"LLM call failed: {exc}")

    async def _generate_compiler_settings(
        self, description: str, reality: str, behavior: str, fidelity: str, seed: int
    ) -> dict:
        """Use LLM to generate compiler settings."""
        try:
            response = await NL_TO_COMPILER_SETTINGS.execute(
                self._router,
                _seed=seed,
                description=description,
                reality=reality,
                behavior=behavior,
                fidelity=fidelity,
                seed=seed,
            )
            return NL_TO_COMPILER_SETTINGS.parse_json_response(response)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            # Fallback: use defaults with user hints
            logger.warning("Failed to parse compiler settings from LLM, using defaults: %s", exc)
            return {
                "compiler": {
                    "seed": seed,
                    "behavior": behavior,
                    "fidelity": fidelity,
                    "mode": "governed",
                    "reality": {"preset": reality},
                }
            }
        except Exception as exc:
            logger.warning("Compiler settings LLM call failed, using defaults: %s", exc)
            return {
                "compiler": {
                    "seed": seed,
                    "behavior": behavior,
                    "fidelity": fidelity,
                    "mode": "governed",
                    "reality": {"preset": reality},
                }
            }
