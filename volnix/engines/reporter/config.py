"""Configuration model for the report generator engine."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReporterConfig(BaseModel):
    """Configuration for the report generator engine."""

    output_formats: list[str] = Field(default_factory=lambda: ["json", "markdown"])
    output_dir: str = "reports"
