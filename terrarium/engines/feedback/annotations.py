"""Annotation store -- persistent per-service behavioral annotations.

Uses :class:`AppendOnlyLog` from the persistence module (same pattern
as the event bus and ledger).  Annotations are stored per-service and
surfaced to profile maintainers for curation.

Examples::

    terrarium annotate stripe "Refunds on charges >180 days should fail"
    terrarium annotate jira "Status transitions require assignee in project role"
"""
from __future__ import annotations

import logging
from typing import Any

from terrarium.core import ServiceId
from terrarium.core.types import RunId
from terrarium.persistence.append_log import AppendOnlyLog
from terrarium.persistence.database import Database

logger = logging.getLogger(__name__)


def _escape_like(query: str) -> str:
    """Escape SQL LIKE special characters (``%``, ``_``, ``\\``)."""
    return (
        query
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


class AnnotationStore:
    """Persistent store for service annotations backed by SQLite.

    Table schema (``annotations``)::

        sequence_id  INTEGER PRIMARY KEY AUTOINCREMENT
        service_id   TEXT NOT NULL
        text         TEXT NOT NULL
        author       TEXT NOT NULL   -- "user", "agent:<id>", "system"
        tag          TEXT            -- optional category tag
        run_id       TEXT            -- optional: which run this came from
        created_at   TEXT            -- auto-populated
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._log = AppendOnlyLog(
            db=db,
            table_name="annotations",
            columns=[
                ("service_id", "TEXT NOT NULL"),
                ("text", "TEXT NOT NULL"),
                ("author", "TEXT NOT NULL"),
                ("tag", "TEXT"),
                ("run_id", "TEXT"),
            ],
        )

    async def initialize(self) -> None:
        """Create table and indexes."""
        await self._log.initialize()
        await self._log.create_index("service_id")
        await self._log.create_index("run_id")
        logger.info("AnnotationStore: initialized")

    async def add(
        self,
        service_id: ServiceId | str,
        text: str,
        author: str,
        tag: str | None = None,
        run_id: RunId | str | None = None,
    ) -> int:
        """Add an annotation and return its sequence_id."""
        values: dict[str, Any] = {
            "service_id": str(service_id),
            "text": text,
            "author": author,
        }
        if tag is not None:
            values["tag"] = tag
        if run_id is not None:
            values["run_id"] = str(run_id)
        seq = await self._log.append(values)
        logger.debug(
            "AnnotationStore: added annotation #%d for '%s' by '%s'",
            seq, service_id, author,
        )
        return seq

    async def get_by_service(
        self, service_id: ServiceId | str
    ) -> list[dict[str, Any]]:
        """Return all annotations for a service, ordered by creation."""
        return await self._log.query(
            filters={"service_id": str(service_id)}
        )

    async def get_by_run(
        self, run_id: RunId | str
    ) -> list[dict[str, Any]]:
        """Return all annotations tagged with a specific run."""
        return await self._log.query(filters={"run_id": str(run_id)})

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Search annotations by text content (SQL LIKE).

        Special characters (``%``, ``_``) are escaped so they match
        literally.
        """
        escaped = _escape_like(query)
        sql = (
            "SELECT * FROM annotations "
            "WHERE text LIKE ? ESCAPE '\\' "
            "ORDER BY sequence_id ASC"
        )
        return await self._db.fetchall(sql, (f"%{escaped}%",))

    async def count_by_service(
        self, service_id: ServiceId | str
    ) -> int:
        """Return the number of annotations for a service."""
        return await self._log.count(
            filters={"service_id": str(service_id)}
        )
