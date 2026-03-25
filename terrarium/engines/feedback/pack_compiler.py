"""Pack compiler -- generate Tier 1 pack scaffold from a Tier 2 profile.

Produces the standard 4-file pack structure that a developer fills in
with deterministic handler logic.  The generated code is a starting
point, NOT a working pack — handlers raise ``NotImplementedError``.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from terrarium.engines.feedback.models import PackCompileResult
from terrarium.packs.profile_schema import ServiceProfileData

logger = logging.getLogger(__name__)


class PackCompiler:
    """Generates a Tier 1 verified pack scaffold from a Tier 2 profile."""

    async def compile(
        self,
        profile: ServiceProfileData,
        output_dir: str | Path | None = None,
    ) -> PackCompileResult:
        """Generate pack files from a profile.

        Creates::

            {output_dir}/{service}/
                __init__.py
                pack.py
                schemas.py
                handlers.py
                state_machines.py

        Args:
            profile: The Tier 2 profile to compile from.
            output_dir: Where to write the pack.  Defaults to
                ``terrarium/packs/verified/``.

        Returns:
            :class:`PackCompileResult` with file list and stub count.
        """
        service = profile.service_name
        if output_dir is None:
            output_dir = Path(__file__).resolve().parents[2] / "packs" / "verified"
        else:
            output_dir = Path(output_dir)

        # All file I/O wrapped in to_thread (H3 fix)
        result = await asyncio.to_thread(
            self._write_pack_files, service, output_dir, profile
        )
        return result

    def _write_pack_files(
        self,
        service: str,
        output_dir: Path,
        profile: ServiceProfileData,
    ) -> PackCompileResult:
        """Sync helper: generate and write all pack files."""
        pack_dir = output_dir / service
        pack_dir.mkdir(parents=True, exist_ok=True)

        files: list[str] = []

        # __init__.py
        init_path = pack_dir / "__init__.py"
        init_path.write_text(
            f'"""Tier 1 verified pack for {service}."""\n'
        )
        files.append(str(init_path))

        # schemas.py
        schemas_path = pack_dir / "schemas.py"
        schemas_path.write_text(self._generate_schemas(profile))
        files.append(str(schemas_path))

        # state_machines.py
        sm_path = pack_dir / "state_machines.py"
        sm_path.write_text(self._generate_state_machines(profile))
        files.append(str(sm_path))

        # handlers.py
        handlers_path = pack_dir / "handlers.py"
        handlers_path.write_text(self._generate_handlers(profile))
        files.append(str(handlers_path))

        # pack.py
        pack_path = pack_dir / "pack.py"
        pack_path.write_text(self._generate_pack(profile))
        files.append(str(pack_path))

        handler_count = len(profile.operations)

        logger.info(
            "PackCompiler: generated %d files for '%s' (%d handler stubs)",
            len(files), service, handler_count,
        )

        return PackCompileResult(
            service_name=service,
            output_dir=str(pack_dir),
            files_generated=files,
            handler_stubs=handler_count,
        )

    # -- Code generation -------------------------------------------------------

    @staticmethod
    def _generate_schemas(profile: ServiceProfileData) -> str:
        """Generate schemas.py with entity schemas and tool definitions."""
        lines = [
            f'"""Entity schemas and tool definitions for {profile.service_name}."""',
            "from __future__ import annotations",
            "",
            "",
        ]

        # Entity schemas
        for entity in profile.entities:
            var_name = f"{entity.name.upper()}_ENTITY_SCHEMA"
            lines.append(f"{var_name} = {{")
            lines.append('    "type": "object",')
            lines.append('    "properties": {')
            for field_name, field_def in entity.fields.items():
                ftype = field_def.get("type", "string") if isinstance(field_def, dict) else "string"
                lines.append(f'        "{field_name}": {{"type": "{ftype}"}},')
            lines.append('    },')
            lines.append(f'    "required": {entity.required},')
            lines.append(f'    "identity_field": "{entity.identity_field}",')
            lines.append("}")
            lines.append("")

        # Tool definitions
        lines.append("")
        lines.append("TOOL_DEFINITIONS = [")
        for op in profile.operations:
            lines.append("    {")
            lines.append(f'        "name": "{op.name}",')
            # M5 fix: escape quotes in description
            safe_desc = op.description.replace('"', '\\"')
            lines.append(f'        "description": "{safe_desc}",')
            lines.append(f'        "parameters": {op.parameters!r},')
            lines.append(f'        "required_params": {op.required_params!r},')
            if op.response_schema:
                lines.append(f'        "response_schema": {op.response_schema!r},')
            lines.append("    },")
        lines.append("]")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _generate_state_machines(profile: ServiceProfileData) -> str:
        """Generate state_machines.py."""
        lines = [
            f'"""State machine definitions for {profile.service_name}."""',
            "from __future__ import annotations",
            "",
            "",
        ]

        if profile.state_machines:
            lines.append("TRANSITIONS = {")
            for sm in profile.state_machines:
                lines.append(f'    "{sm.entity_type}": {{')
                lines.append(f'        "field": "{sm.field}",')
                lines.append('        "transitions": {')
                for state, targets in sm.transitions.items():
                    lines.append(f'            "{state}": {targets!r},')
                lines.append("        },")
                lines.append("    },")
            lines.append("}")
        else:
            lines.append("TRANSITIONS = {}")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _generate_handlers(profile: ServiceProfileData) -> str:
        """Generate handlers.py with one stub per operation."""
        lines = [
            f'"""Action handlers for {profile.service_name}.',
            "",
            "Each handler receives an ActionContext and returns a ResponseProposal.",
            'Implement the deterministic logic to replace the LLM-generated Tier 2 responses."""',
            "from __future__ import annotations",
            "",
            "from terrarium.core.context import ActionContext, ResponseProposal",
            "",
            "",
        ]

        for op in profile.operations:
            func_name = f"handle_{op.name}"
            lines.append(f"async def {func_name}(ctx: ActionContext) -> ResponseProposal:")
            lines.append(f'    """Handle {op.name}: {op.description}')
            lines.append("")
            lines.append(f"    HTTP: {op.http_method} {op.http_path}")
            if op.required_params:
                lines.append(f"    Required params: {op.required_params}")
            if op.creates_entity:
                lines.append(f"    Creates: {op.creates_entity}")
            if op.mutates_entity:
                lines.append(f"    Mutates: {op.mutates_entity}")
            lines.append('    """')
            lines.append(
                f'    raise NotImplementedError("{func_name}: implement deterministic logic")'
            )
            lines.append("")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _generate_pack(profile: ServiceProfileData) -> str:
        """Generate pack.py with ServicePack subclass.

        M6 fix: handles empty operations/entities without syntax errors.
        M5 fix: sanitizes description strings.
        """
        service = profile.service_name
        class_name = (
            "".join(w.capitalize() for w in service.split("_")) + "Pack"
        )

        # Build import lines — guard against empty lists (M6)
        handler_parts = [
            f"handle_{op.name}" for op in profile.operations
        ]
        entity_schema_parts = [
            f"{e.name.upper()}_ENTITY_SCHEMA" for e in profile.entities
        ]

        # Handler imports
        if handler_parts:
            handler_import_line = (
                f"from .handlers import {', '.join(handler_parts)}"
            )
        else:
            handler_import_line = "# No handlers to import"

        # Schema imports
        schema_imports = ["TOOL_DEFINITIONS"]
        schema_imports.extend(entity_schema_parts)
        schema_import_line = (
            f"from .schemas import {', '.join(schema_imports)}"
        )

        # Handler map
        handler_map = "\n".join(
            f'        "{op.name}": handle_{op.name},'
            for op in profile.operations
        )
        if not handler_map:
            handler_map = "        # No handlers defined"

        # Entity refs
        entity_refs = "\n".join(
            f'            "{e.name}": {e.name.upper()}_ENTITY_SCHEMA,'
            for e in profile.entities
        )
        if not entity_refs:
            entity_refs = "            # No entities defined"

        lines = [
            f'"""Tier 1 verified pack for {service}."""',
            "from __future__ import annotations",
            "",
            "from typing import ClassVar",
            "",
            "from terrarium.packs.base import ServicePack",
            "",
            handler_import_line,
            schema_import_line,
            "from .state_machines import TRANSITIONS",
            "",
            "",
            f"class {class_name}(ServicePack):",
            f'    """Verified pack for {service}."""',
            "",
            f'    pack_name: ClassVar[str] = "{service}"',
            f'    category: ClassVar[str] = "{profile.category}"',
            "    fidelity_tier: ClassVar[int] = 1",
            "",
            "    _handlers: ClassVar[dict] = {",
            handler_map,
            "    }",
            "",
            "    def get_tools(self) -> list[dict]:",
            "        return list(TOOL_DEFINITIONS)",
            "",
            "    def get_entity_schemas(self) -> dict:",
            "        return {",
            entity_refs,
            "        }",
            "",
            "    def get_state_machines(self) -> dict:",
            "        return TRANSITIONS",
            "",
        ]
        return "\n".join(lines)
