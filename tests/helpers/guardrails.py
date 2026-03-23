"""Helpers for staged fail-closed test guardrails."""

from __future__ import annotations

import pytest


def staged_guardrail(reason: str):
    """Mark a test as a staged guardrail controlled by the pytest switch."""
    return pytest.mark.staged_guardrail(reason=reason)
