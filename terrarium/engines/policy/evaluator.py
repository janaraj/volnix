"""Condition evaluator for policy rules."""

from __future__ import annotations

from typing import Any, Callable


class ConditionEvaluator:
    """Evaluates policy condition expressions against a context dict."""

    def __init__(self) -> None:
        self._functions: dict[str, Callable[..., Any]] = {}

    def evaluate(self, condition: str, context: dict[str, Any]) -> bool:
        """Evaluate a condition string against the given context."""
        ...

    def parse(self, condition: str) -> Any:
        """Parse a condition string into an AST representation."""
        ...

    def register_function(self, name: str, func: Callable[..., Any]) -> None:
        """Register a callable that can be referenced in condition expressions."""
        ...
