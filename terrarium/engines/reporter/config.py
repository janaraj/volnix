"""Configuration model for the report generator engine."""

from __future__ import annotations

from pydantic import BaseModel


class ReporterConfig(BaseModel):
    """Configuration for the report generator engine."""

    output_formats: list[str]
    output_dir: str
