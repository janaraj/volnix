"""Policy template loading and instantiation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PolicyTemplate(BaseModel):
    """A reusable policy template with parameterised placeholders."""

    id: str
    description: str
    parameters: dict[str, Any]
    policies: list[dict[str, Any]]


class PolicyTemplateLoader:
    """Loads and instantiates policy templates from YAML definitions."""

    def load_template(self, yaml_path: str) -> PolicyTemplate:
        """Load a single policy template from a YAML file."""
        ...

    def instantiate(
        self, template: PolicyTemplate, parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Instantiate a template with concrete parameter values."""
        ...
