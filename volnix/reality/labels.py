"""Label system -- two-level config mapping labels to dimension values.

Labels are human-friendly names for intensity levels across each dimension.
Each dimension has 5 labels ordered from benign to severe.  A label resolves
to a set of default attribute values that the LLM interprets as personality
traits.
"""

from __future__ import annotations

from typing import Any

from volnix.core.errors import InvalidLabelError
from volnix.reality.dimensions import (
    BaseDimension,
    BoundaryDimension,
    ComplexityDimension,
    InformationQualityDimension,
    ReliabilityDimension,
    SocialFrictionDimension,
)

# ---------------------------------------------------------------------------
# Label scales -- ordered from benign to severe per dimension
# ---------------------------------------------------------------------------

LABEL_SCALES: dict[str, list[str]] = {
    "information": [
        "pristine",
        "mostly_clean",
        "somewhat_neglected",
        "poorly_maintained",
        "chaotic",
    ],
    "reliability": [
        "rock_solid",
        "mostly_reliable",
        "occasionally_flaky",
        "frequently_broken",
        "barely_functional",
    ],
    "friction": [
        "everyone_helpful",
        "mostly_cooperative",
        "some_difficult_people",
        "many_difficult_people",
        "actively_hostile",
    ],
    "complexity": [
        "straightforward",
        "mostly_clear",
        "moderately_challenging",
        "frequently_confusing",
        "overwhelmingly_complex",
    ],
    "boundaries": [
        "locked_down",
        "well_controlled",
        "a_few_gaps",
        "many_gaps",
        "wide_open",
    ],
}

# ---------------------------------------------------------------------------
# Label -> default attribute values (complete mapping tables)
# ---------------------------------------------------------------------------

INFORMATION_DEFAULTS: dict[str, dict[str, Any]] = {
    "pristine": {"staleness": 0, "incompleteness": 0, "inconsistency": 0, "noise": 0},
    "mostly_clean": {"staleness": 10, "incompleteness": 12, "inconsistency": 5, "noise": 8},
    "somewhat_neglected": {
        "staleness": 30,
        "incompleteness": 35,
        "inconsistency": 20,
        "noise": 30,
    },
    "poorly_maintained": {
        "staleness": 55,
        "incompleteness": 60,
        "inconsistency": 40,
        "noise": 55,
    },
    "chaotic": {"staleness": 80, "incompleteness": 85, "inconsistency": 70, "noise": 80},
}

RELIABILITY_DEFAULTS: dict[str, dict[str, Any]] = {
    "rock_solid": {"failures": 0, "timeouts": 0, "degradation": 0},
    "mostly_reliable": {"failures": 8, "timeouts": 5, "degradation": 3},
    "occasionally_flaky": {"failures": 20, "timeouts": 15, "degradation": 10},
    "frequently_broken": {"failures": 50, "timeouts": 35, "degradation": 25},
    "barely_functional": {"failures": 80, "timeouts": 60, "degradation": 50},
}

FRICTION_DEFAULTS: dict[str, dict[str, Any]] = {
    "everyone_helpful": {
        "uncooperative": 0,
        "deceptive": 0,
        "hostile": 0,
        "sophistication": "low",
    },
    "mostly_cooperative": {
        "uncooperative": 10,
        "deceptive": 5,
        "hostile": 2,
        "sophistication": "low",
    },
    "some_difficult_people": {
        "uncooperative": 30,
        "deceptive": 15,
        "hostile": 8,
        "sophistication": "medium",
    },
    "many_difficult_people": {
        "uncooperative": 55,
        "deceptive": 30,
        "hostile": 20,
        "sophistication": "medium",
    },
    "actively_hostile": {
        "uncooperative": 75,
        "deceptive": 50,
        "hostile": 40,
        "sophistication": "high",
    },
}

COMPLEXITY_DEFAULTS: dict[str, dict[str, Any]] = {
    "straightforward": {
        "ambiguity": 0,
        "edge_cases": 0,
        "contradictions": 0,
        "urgency": 0,
        "volatility": 0,
    },
    "mostly_clear": {
        "ambiguity": 10,
        "edge_cases": 8,
        "contradictions": 3,
        "urgency": 5,
        "volatility": 3,
    },
    "moderately_challenging": {
        "ambiguity": 35,
        "edge_cases": 25,
        "contradictions": 15,
        "urgency": 20,
        "volatility": 15,
    },
    "frequently_confusing": {
        "ambiguity": 60,
        "edge_cases": 45,
        "contradictions": 30,
        "urgency": 40,
        "volatility": 30,
    },
    "overwhelmingly_complex": {
        "ambiguity": 85,
        "edge_cases": 70,
        "contradictions": 55,
        "urgency": 65,
        "volatility": 55,
    },
}

BOUNDARIES_DEFAULTS: dict[str, dict[str, Any]] = {
    "locked_down": {"access_limits": 0, "rule_clarity": 0, "boundary_gaps": 0},
    "well_controlled": {"access_limits": 10, "rule_clarity": 8, "boundary_gaps": 3},
    "a_few_gaps": {"access_limits": 25, "rule_clarity": 30, "boundary_gaps": 12},
    "many_gaps": {"access_limits": 50, "rule_clarity": 55, "boundary_gaps": 30},
    "wide_open": {"access_limits": 75, "rule_clarity": 80, "boundary_gaps": 55},
}

# ---------------------------------------------------------------------------
# Dimension name -> defaults table + model class
# ---------------------------------------------------------------------------

DIMENSION_DEFAULTS: dict[str, dict[str, dict[str, Any]]] = {
    "information": INFORMATION_DEFAULTS,
    "reliability": RELIABILITY_DEFAULTS,
    "friction": FRICTION_DEFAULTS,
    "complexity": COMPLEXITY_DEFAULTS,
    "boundaries": BOUNDARIES_DEFAULTS,
}

_DIMENSION_CLASSES: dict[str, type[BaseDimension]] = {
    "information": InformationQualityDimension,
    "reliability": ReliabilityDimension,
    "friction": SocialFrictionDimension,
    "complexity": ComplexityDimension,
    "boundaries": BoundaryDimension,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_label(dimension_name: str, label: str) -> BaseDimension:
    """Convert a label to a dimension model with default attribute values.

    Parameters
    ----------
    dimension_name:
        One of: information, reliability, friction, complexity, boundaries.
    label:
        A valid label for the specified dimension.

    Returns
    -------
    BaseDimension:
        The appropriate dimension model populated with default values for the label.

    Raises
    ------
    InvalidLabelError:
        If the label is not valid for the specified dimension.
    """
    if dimension_name not in DIMENSION_DEFAULTS:
        raise InvalidLabelError(
            f"Unknown dimension: {dimension_name!r}",
            context={"dimension": dimension_name},
        )
    defaults_table = DIMENSION_DEFAULTS[dimension_name]
    if label not in defaults_table:
        raise InvalidLabelError(
            f"Unknown label {label!r} for dimension {dimension_name!r}",
            context={"dimension": dimension_name, "label": label},
        )
    cls = _DIMENSION_CLASSES[dimension_name]
    return cls(**defaults_table[label])


def resolve_dimension(dimension_name: str, value: str | dict[str, Any]) -> BaseDimension:
    """Resolve either a label string OR a per-attribute dict to a dimension model.

    Parameters
    ----------
    dimension_name:
        One of: information, reliability, friction, complexity, boundaries.
    value:
        Either a label string (e.g. "somewhat_neglected") or a dict of
        attribute values (e.g. {"staleness": 30, "incompleteness": 35}).

    Returns
    -------
    BaseDimension:
        The resolved dimension model.
    """
    if isinstance(value, str):
        return resolve_label(dimension_name, value)
    if dimension_name not in _DIMENSION_CLASSES:
        from volnix.core.errors import DimensionValueError

        raise DimensionValueError(
            f"Unknown dimension: {dimension_name!r}",
        )
    cls = _DIMENSION_CLASSES[dimension_name]
    return cls(**value)


def label_to_intensity(label: str, dimension_name: str) -> int:
    """Get the approximate center intensity (0-100) for a label.

    The intensity is the position of the label in the 5-step scale mapped
    to [0, 25, 50, 75, 100].

    Parameters
    ----------
    label:
        A valid label for the dimension.
    dimension_name:
        The dimension name.

    Returns
    -------
    int:
        Approximate intensity value (0, 25, 50, 75, or 100).
    """
    if dimension_name not in LABEL_SCALES:
        raise InvalidLabelError(
            f"Unknown dimension: {dimension_name!r}",
            context={"dimension": dimension_name},
        )
    scale = LABEL_SCALES[dimension_name]
    if label not in scale:
        raise InvalidLabelError(
            f"Unknown label {label!r} for dimension {dimension_name!r}",
            context={"dimension": dimension_name, "label": label},
        )
    idx = scale.index(label)
    return idx * 25


def is_valid_label(label: str, dimension_name: str) -> bool:
    """Check if a label is valid for a dimension.

    Parameters
    ----------
    label:
        The label to check.
    dimension_name:
        The dimension to check against.

    Returns
    -------
    bool:
        True if the label is valid for the dimension.
    """
    if dimension_name not in LABEL_SCALES:
        return False
    return label in LABEL_SCALES[dimension_name]
