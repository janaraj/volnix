"""Annotation store -- persistent storage for service annotations."""

from __future__ import annotations

from typing import Any

from terrarium.core import ServiceId
from terrarium.persistence.database import Database


class AnnotationStore:
    """Persistent store for service annotations."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def initialize(self) -> None:
        """Create tables / indexes if they do not exist."""
        ...

    async def add(
        self, service_id: ServiceId, text: str, author: str
    ) -> int:
        """Add an annotation and return its integer id."""
        ...

    async def get_by_service(
        self, service_id: ServiceId
    ) -> list[dict[str, Any]]:
        """Return all annotations for a service."""
        ...

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Search annotations by text content."""
        ...
