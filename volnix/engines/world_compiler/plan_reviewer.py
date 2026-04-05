"""Plan reviewer — formats, validates, and serialises world plans.

Uses: WorldPlan.validate_plan(), yaml serialization.
"""

from __future__ import annotations

from typing import Any

import yaml

from volnix.engines.world_compiler.plan import WorldPlan


class PlanReviewer:
    """Formats, validates, and serialises world plans for human review."""

    def format_plan(self, plan: WorldPlan) -> str:
        """Format a WorldPlan as a human-readable multi-line report."""
        lines: list[str] = []
        lines.append(f"World: {plan.name}")
        lines.append(f"Description: {plan.description}")
        lines.append(f"Source: {plan.source}")
        lines.append("")

        # Services
        lines.append(f"Services ({len(plan.services)}):")
        for name, res in plan.services.items():
            conf = res.surface.confidence
            lines.append(
                f"  {name}: {res.resolution_source} (confidence={conf:.1f})"
            )
            entity_types = list(res.surface.entity_schemas.keys())
            if entity_types:
                lines.append(f"    entity types: {', '.join(entity_types)}")
            op_count = len(res.surface.operations)
            lines.append(f"    operations: {op_count}")

        # Actors
        lines.append(f"\nActors ({len(plan.actor_specs)}):")
        for spec in plan.actor_specs:
            role = spec.get("role", "?")
            count = spec.get("count", 1)
            atype = spec.get("type", "?")
            hint = spec.get("personality", "")
            line = f"  {role} x{count} ({atype})"
            if hint:
                line += f" — {hint[:60]}"
            lines.append(line)

        # Reality
        info = plan.conditions.information
        lines.append("\nReality:")
        lines.append(
            f"  information: staleness={info.staleness}, "
            f"incompleteness={info.incompleteness}"
        )
        lines.append(
            f"  reliability: failures={plan.conditions.reliability.failures}"
        )
        lines.append(
            f"  friction: uncooperative={plan.conditions.friction.uncooperative}"
        )
        lines.append(
            f"  complexity: ambiguity={plan.conditions.complexity.ambiguity}"
        )
        lines.append(
            f"  boundaries: access_limits={plan.conditions.boundaries.access_limits}"
        )

        # Runtime
        lines.append(
            f"\nBehavior: {plan.behavior}, Mode: {plan.mode}, "
            f"Fidelity: {plan.fidelity}"
        )
        lines.append(f"Seed: {plan.seed}")
        lines.append(f"Seeds: {len(plan.seeds)}, Policies: {len(plan.policies)}")

        if plan.mission:
            lines.append(f"\nMission: {plan.mission}")

        # Validation
        errors = plan.validate_plan()
        if errors:
            lines.append(f"\nValidation errors ({len(errors)}):")
            for err in errors:
                lines.append(f"  - {err}")
        else:
            lines.append("\nValidation: PASS")

        if plan.warnings:
            lines.append(f"\nWarnings ({len(plan.warnings)}):")
            for w in plan.warnings:
                lines.append(f"  - {w}")

        return "\n".join(lines)

    def to_yaml(self, plan: WorldPlan) -> str:
        """Serialise a WorldPlan to YAML string."""
        data = plan.model_dump(mode="json")
        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def from_yaml(self, yaml_str: str) -> dict[str, Any]:
        """Deserialise a YAML string to a dict (for reconstruction)."""
        return yaml.safe_load(yaml_str) or {}

    def validate_plan(self, plan: WorldPlan) -> list[str]:
        """Validate a WorldPlan, returning error messages."""
        return plan.validate_plan()

    def generate_report(
        self,
        plan: WorldPlan,
        generation_result: dict[str, Any],
    ) -> str:
        """Generate a comprehensive world generation report.

        Shows: plan summary, entity counts by type, validation warnings,
        actor summary, seed application status.
        """
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("VOLNIX WORLD GENERATION REPORT")
        lines.append("=" * 60)
        lines.append("")

        # Plan summary
        lines.append(self.format_plan(plan))
        lines.append("")

        # Generation results
        entities = generation_result.get("entities", {})
        lines.append("-" * 40)
        lines.append("GENERATED ENTITIES:")
        total = 0
        for etype, elist in entities.items():
            count = len(elist)
            total += count
            lines.append(f"  {etype}: {count} entities")
        lines.append(f"  TOTAL: {total} entities")

        # Actors
        actors = generation_result.get("actors", [])
        lines.append(f"\nACTORS: {len(actors)} registered")
        friction_count = sum(
            1 for a in actors if getattr(a, "friction_profile", None)
        )
        lines.append(f"  with friction profiles: {friction_count}")

        # Validation
        warnings = generation_result.get("warnings", [])
        lines.append(f"\nVALIDATION WARNINGS: {len(warnings)}")
        for w in warnings[:10]:
            lines.append(f"  - {w}")
        if len(warnings) > 10:
            lines.append(f"  ... and {len(warnings) - 10} more")

        validation_report = generation_result.get("validation_report", {})
        final_world = validation_report.get("final_world", {})
        if final_world:
            lines.append(
                f"\nFINAL VALIDATION: {'PASS' if final_world.get('valid') else 'FAIL'}"
            )
            if final_world.get("errors"):
                for err in final_world["errors"][:5]:
                    lines.append(f"  - {err}")

        retry_counts = generation_result.get("retry_counts", {})
        if retry_counts:
            lines.append("\nRETRY COUNTS:")
            for section, count in sorted(retry_counts.items()):
                lines.append(f"  {section}: {count}")

        # Seeds
        seeds_processed = generation_result.get("seeds_processed", 0)
        lines.append(f"\nSEEDS PROCESSED: {seeds_processed}")

        # Snapshot
        snapshot_id = generation_result.get("snapshot_id")
        if snapshot_id:
            lines.append(f"\nSNAPSHOT: {snapshot_id}")

        lines.append("")
        lines.append("=" * 60)
        status = (
            "SUCCESS"
            if not warnings
            else f"SUCCESS with {len(warnings)} warnings"
        )
        lines.append(f"STATUS: {status}")
        lines.append("=" * 60)

        return "\n".join(lines)
