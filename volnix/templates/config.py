"""Configuration model for the templates subsystem."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateConfig(BaseModel):
    """Configuration for template discovery and loading.

    Attributes:
        template_dirs: Additional directories to scan for templates.
        allow_custom: Whether user-provided custom templates are permitted.
    """

    template_dirs: list[str] = Field(default_factory=list)
    allow_custom: bool = True
