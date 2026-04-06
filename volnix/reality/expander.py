"""Condition expander -- preset + overrides -> WorldConditions + LLM context.

The expander does NOT mutate entities.  It packages conditions as structured
context for the LLM to interpret during world generation and animation.
The LLM decides how personality traits manifest in concrete entities.
"""

from __future__ import annotations

from typing import Any

from volnix.core.errors import InvalidLabelError
from volnix.reality.dimensions import WorldConditions
from volnix.reality.labels import (
    LABEL_SCALES,
    DIMENSION_DEFAULTS,
    is_valid_label,
    resolve_dimension,
)
from volnix.reality.presets import load_preset


class ConditionExpander:
    """Expands reality presets + overrides into WorldConditions and LLM prompt context.

    The expander does NOT mutate entities.  It packages conditions as
    structured context for the LLM to interpret during world generation
    and animation.  The LLM decides how personality traits manifest.
    """

    def expand(
        self,
        preset: str,
        overrides: dict[str, Any] | None = None,
    ) -> WorldConditions:
        """Load preset, apply per-dimension overrides, return resolved WorldConditions.

        Parameters
        ----------
        preset:
            The base reality preset name (e.g. ``"messy"``).
        overrides:
            Optional dict mapping dimension names to label strings or
            per-attribute dicts.

        Returns
        -------
        WorldConditions:
            The fully resolved conditions.
        """
        conditions = load_preset(preset)
        if overrides:
            conditions = self.merge_overrides(conditions, overrides)
        return conditions

    def build_prompt_context(self, conditions: WorldConditions) -> dict[str, Any]:
        """Package conditions as structured LLM prompt context.

        Returns a dict suitable for injection into LLM system prompts::

            {
                "reality_summary": "This is a messy world where...",
                "dimensions": {
                    "information": {
                        "level": "somewhat_neglected",
                        "attributes": {"staleness": 30, ...},
                        "description": "Information management has been neglected..."
                    },
                    ...
                }
            }
        """
        context: dict[str, Any] = {"dimensions": {}}
        for dim_name in ["information", "reliability", "friction", "complexity", "boundaries"]:
            dim = getattr(conditions, dim_name)
            level_label = self._find_closest_label(dim_name, dim)
            attrs = dim.to_dict()
            context["dimensions"][dim_name] = {
                "level": level_label,
                "attributes": attrs,
                "description": self._describe_dimension(dim_name, level_label, attrs),
            }
        context["reality_summary"] = self._build_summary(context["dimensions"])
        return context

    def get_summary(self, conditions: WorldConditions) -> str:
        """Return a human-readable one-paragraph summary of the conditions."""
        ctx = self.build_prompt_context(conditions)
        return ctx["reality_summary"]

    def merge_overrides(
        self,
        base: WorldConditions,
        overrides: dict[str, Any],
    ) -> WorldConditions:
        """Merge per-dimension overrides onto a base WorldConditions.

        Parameters
        ----------
        base:
            The base conditions (typically from a preset).
        overrides:
            Dict mapping dimension names to label strings or attribute dicts.

        Returns
        -------
        WorldConditions:
            New WorldConditions with overrides applied.

        Raises
        ------
        InvalidLabelError:
            If an override key is not a valid dimension name.
        """
        dims: dict[str, Any] = {}
        valid_dims = {"information", "reliability", "friction", "complexity", "boundaries"}
        for dim_name, value in overrides.items():
            if dim_name not in valid_dims:
                raise InvalidLabelError(
                    f"Unknown dimension in overrides: {dim_name!r}",
                    context={"dimension": dim_name},
                )
            dims[dim_name] = resolve_dimension(dim_name, value)
        # Build new WorldConditions, keeping base values for non-overridden dims
        return WorldConditions(
            information=dims.get("information", base.information),
            reliability=dims.get("reliability", base.reliability),
            friction=dims.get("friction", base.friction),
            complexity=dims.get("complexity", base.complexity),
            boundaries=dims.get("boundaries", base.boundaries),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_closest_label(self, dim_name: str, dim: Any) -> str:
        """Find the label whose default values are closest to the actual values."""
        if dim_name not in LABEL_SCALES:
            return "unknown"
        scale = LABEL_SCALES[dim_name]
        defaults_table = DIMENSION_DEFAULTS[dim_name]
        actual = dim.to_dict()

        best_label = scale[0]
        best_distance = float("inf")

        # Ordinal mapping for string fields like sophistication
        _STR_ORDINAL = {"low": 0, "medium": 50, "high": 100}

        for label in scale:
            label_defaults = defaults_table[label]
            # Compute sum of squared differences for ALL fields
            distance = 0.0
            for key, default_val in label_defaults.items():
                actual_val = actual.get(key, 0)
                if isinstance(default_val, (int, float)) and isinstance(actual_val, (int, float)):
                    distance += (actual_val - default_val) ** 2
                elif isinstance(default_val, str) and isinstance(actual_val, str):
                    # Map ordinal strings to numeric for distance calc
                    d_num = _STR_ORDINAL.get(default_val, 50)
                    a_num = _STR_ORDINAL.get(actual_val, 50)
                    distance += (a_num - d_num) ** 2
            if distance < best_distance:
                best_distance = distance
                best_label = label
        return best_label

    def _describe_dimension(self, name: str, label: str, attrs: dict[str, Any]) -> str:
        """Generate a natural-language description of a dimension for LLM context."""
        descriptions: dict[tuple[str, str], str] = {
            # Information
            ("information", "pristine"): (
                "Information is perfectly maintained. All data is current, complete, "
                "consistent, and free of noise."
            ),
            ("information", "mostly_clean"): (
                "Information is generally well-maintained. Minor staleness and small gaps "
                "exist but rarely cause problems."
            ),
            ("information", "somewhat_neglected"): (
                "Information management has been neglected. Some records are outdated, "
                "some fields are missing, data across sources sometimes conflicts."
            ),
            ("information", "poorly_maintained"): (
                "Information quality is poor. Many records are outdated or incomplete. "
                "Cross-referencing data often reveals conflicts and noise is common."
            ),
            ("information", "chaotic"): (
                "Information is in a chaotic state. Most records are outdated, incomplete, "
                "or contradictory. Noise makes it hard to find reliable data."
            ),
            # Reliability
            ("reliability", "rock_solid"): (
                "Infrastructure is rock-solid. Services never fail, never timeout, "
                "and maintain peak performance."
            ),
            ("reliability", "mostly_reliable"): (
                "Infrastructure is mostly reliable. Rare failures and occasional minor "
                "slowdowns, but nothing disruptive."
            ),
            ("reliability", "occasionally_flaky"): (
                "Infrastructure is somewhat unreliable. Services occasionally fail or "
                "timeout, especially under load."
            ),
            ("reliability", "frequently_broken"): (
                "Infrastructure is frequently broken. Services fail regularly, timeouts "
                "are common, and degraded operation is the norm."
            ),
            ("reliability", "barely_functional"): (
                "Infrastructure is barely functional. Most services fail or timeout "
                "regularly. Significant degradation across the board."
            ),
            # Friction
            ("friction", "everyone_helpful"): (
                "Everyone is helpful and cooperative. External actors act in good faith "
                "and communication is straightforward."
            ),
            ("friction", "mostly_cooperative"): (
                "Most people are cooperative. Occasional minor friction but generally "
                "good-faith interactions."
            ),
            ("friction", "some_difficult_people"): (
                "Some people are difficult to work with. A noticeable minority are "
                "uncooperative or occasionally deceptive."
            ),
            ("friction", "many_difficult_people"): (
                "Many people are difficult. A significant portion of actors are "
                "uncooperative, some are deceptive, and hostility is not uncommon."
            ),
            ("friction", "actively_hostile"): (
                "The social environment is actively hostile. Most actors are uncooperative, "
                "deception is widespread, and overt hostility is common."
            ),
            # Complexity
            ("complexity", "straightforward"): (
                "Situations are straightforward. Requirements are clear, no edge cases, "
                "no contradictions, no time pressure."
            ),
            ("complexity", "mostly_clear"): (
                "Situations are mostly clear. Minor ambiguities and rare edge cases, "
                "but generally manageable."
            ),
            ("complexity", "moderately_challenging"): (
                "Situations are moderately challenging. Noticeable ambiguity, some edge "
                "cases, occasional contradictions, and moderate time pressure."
            ),
            ("complexity", "frequently_confusing"): (
                "Situations are frequently confusing. Significant ambiguity, many edge "
                "cases, contradictions are common, and urgency adds pressure."
            ),
            ("complexity", "overwhelmingly_complex"): (
                "Situations are overwhelmingly complex. Extreme ambiguity, constant edge "
                "cases, rampant contradictions, high urgency, and rapid change."
            ),
            # Boundaries
            ("boundaries", "locked_down"): (
                "Boundaries are locked down. Access controls are strict, rules are clear, "
                "and no gaps exist."
            ),
            ("boundaries", "well_controlled"): (
                "Boundaries are well-controlled. Minor gaps exist but access controls "
                "and rules are mostly effective."
            ),
            ("boundaries", "a_few_gaps"): (
                "A few gaps exist in boundaries. Some access controls are loose, "
                "some rules are unclear, and minor boundary gaps are present."
            ),
            ("boundaries", "many_gaps"): (
                "Many gaps exist in boundaries. Access controls are inconsistent, "
                "rules are often unclear, and significant boundary gaps are present."
            ),
            ("boundaries", "wide_open"): (
                "Boundaries are wide open. Access controls are minimal, rules are "
                "unclear, and large boundary gaps are common."
            ),
        }
        return descriptions.get((name, label), f"{name}: {label}")

    def _build_summary(self, dimensions: dict[str, Any]) -> str:
        """Build a one-paragraph summary from all dimension descriptions."""
        parts: list[str] = []
        for dim_name in ["information", "reliability", "friction", "complexity", "boundaries"]:
            dim_data = dimensions.get(dim_name, {})
            level = dim_data.get("level", "unknown")
            desc = dim_data.get("description", "")
            if desc:
                parts.append(desc)
        if not parts:
            return "A default world with no special conditions."
        return " ".join(parts)
