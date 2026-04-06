"""World lifecycle manager.

Worlds are the generated "stage" — entities, actors, initial state — before
any agent performs. Multiple runs can reference the same world for fair
comparison. Follows the same storage pattern as RunManager.
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from volnix.core.types import WorldId

logger = logging.getLogger(__name__)


class WorldManager:
    """Manages world lifecycle and disk storage.

    Each world gets a directory at ``{data_dir}/{world_id}/`` containing:

    - ``metadata.json`` — world identity, status, timestamps
    - ``plan.json`` — compiled WorldPlan (serialized)
    - ``state.db`` — initial entity state (never modified after generation)
    """

    def __init__(self, data_dir: str = "data/worlds") -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._worlds: dict[str, dict[str, Any]] = {}
        self._load_existing_worlds()

    async def create_world(
        self,
        name: str,
        plan_data: dict[str, Any],
        seed: int = 42,
        services: list[str] | None = None,
    ) -> WorldId:
        """Create a world record and directory.

        Does NOT generate entities — that happens in the compiler via
        ``VolnixApp.create_world()`` which calls this first, then
        points the StateEngine at the world's ``state.db`` and runs
        ``generate_world()``.

        Returns:
            The new world's ID.
        """
        world_id = WorldId(f"world_{uuid.uuid4().hex[:12]}")
        now = datetime.now(UTC).isoformat()

        metadata: dict[str, Any] = {
            "world_id": str(world_id),
            "name": name,
            "seed": seed,
            "services": services or [],
            "status": "created",
            "created_at": now,
            "entity_count": 0,
            "actor_count": 0,
        }

        self._worlds[str(world_id)] = metadata

        # Create directory + persist metadata + plan
        world_dir = self._data_dir / str(world_id)
        world_dir.mkdir(parents=True, exist_ok=True)
        self._save_metadata(world_id)

        plan_path = world_dir / "plan.json"
        plan_path.write_text(json.dumps(plan_data, indent=2, default=str))

        logger.info("Created world '%s' (%s)", name, world_id)
        return world_id

    async def mark_generated(
        self,
        world_id: WorldId,
        entity_count: int,
        actor_count: int,
    ) -> None:
        """Mark a world as fully generated after entity population."""
        wid = str(world_id)
        if wid in self._worlds:
            self._worlds[wid]["status"] = "generated"
            self._worlds[wid]["entity_count"] = entity_count
            self._worlds[wid]["actor_count"] = actor_count
            self._save_metadata(world_id)
            logger.info(
                "World %s generated: %d entities, %d actors",
                world_id, entity_count, actor_count,
            )

    async def mark_failed(self, world_id: WorldId, error: str = "") -> None:
        """Mark a world as failed during generation."""
        wid = str(world_id)
        if wid in self._worlds:
            self._worlds[wid]["status"] = "failed"
            self._worlds[wid]["error"] = error
            self._save_metadata(world_id)
            logger.warning("World %s generation failed: %s", world_id, error)

    async def list_worlds(self, limit: int = 50) -> list[dict[str, Any]]:
        """List worlds, newest first."""
        worlds = sorted(
            self._worlds.values(),
            key=lambda w: w["created_at"],
            reverse=True,
        )
        return worlds[:limit]

    async def get_world(self, world_id: WorldId) -> dict[str, Any] | None:
        """Get world metadata by ID."""
        return self._worlds.get(str(world_id))

    def get_state_db_path(self, world_id: WorldId) -> str:
        """Get the filesystem path to this world's state.db."""
        return str(self._data_dir / str(world_id) / "state.db")

    def get_world_dir(self, world_id: WorldId) -> Path:
        """Get the filesystem directory for this world."""
        return self._data_dir / str(world_id)

    async def load_plan(self, world_id: WorldId) -> Any:
        """Load the saved WorldPlan for a world.

        Returns ``None`` if the world or ``plan.json`` doesn't exist.
        """
        plan_path = self.get_world_dir(world_id) / "plan.json"
        if not plan_path.exists():
            return None
        plan_data = json.loads(plan_path.read_text())
        from volnix.engines.world_compiler.plan import WorldPlan
        return WorldPlan.model_validate(plan_data)

    async def delete_world(self, world_id: WorldId) -> bool:
        """Delete a world and all its data from disk."""
        wid = str(world_id)
        if wid not in self._worlds:
            return False
        del self._worlds[wid]
        world_dir = self._data_dir / wid
        if world_dir.exists():
            shutil.rmtree(world_dir)
        logger.info("Deleted world %s", world_id)
        return True

    # ── Private helpers ──────────────────────────────────────

    def _save_metadata(self, world_id: WorldId) -> None:
        """Persist world metadata to disk."""
        world_dir = self._data_dir / str(world_id)
        world_dir.mkdir(parents=True, exist_ok=True)
        meta_path = world_dir / "metadata.json"
        meta_path.write_text(
            json.dumps(self._worlds[str(world_id)], indent=2, default=str)
        )

    def _load_existing_worlds(self) -> None:
        """Reload previously persisted worlds from disk.

        Stale "created" worlds (generation never completed, older than 1 hour)
        are marked "failed" so the dashboard shows the correct state.
        """
        if not self._data_dir.exists():
            return
        now = datetime.now(UTC)
        for meta_path in self._data_dir.glob("*/metadata.json"):
            try:
                data = json.loads(meta_path.read_text())
                wid = data["world_id"]
                # Clean up stale "created" worlds (generation never completed)
                if data.get("status") == "created":
                    created = datetime.fromisoformat(data.get("created_at", ""))
                    if (now - created).total_seconds() > 3600:
                        data["status"] = "failed"
                        data["error"] = "generation_timeout"
                        meta_path.write_text(
                            json.dumps(data, indent=2, default=str)
                        )
                self._worlds[wid] = data
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.warning(
                    "Skipping corrupted world metadata: %s", meta_path,
                )
                continue
