"""Replay mode dashboard routes.

Provides endpoints for replaying completed runs with timeline
navigation, play/pause controls, and tick seeking.
"""

from __future__ import annotations


async def replay_view(run_id: str) -> dict:
    """Render the replay page for a specific run.

    Args:
        run_id: The run to replay.

    Returns:
        An HTML response with the replay interface.
    """
    ...


async def replay_timeline(run_id: str) -> dict:
    """Return timeline data for the replay scrubber.

    Args:
        run_id: The run to get timeline data for.

    Returns:
        A JSON response with tick-level event summaries.
    """
    ...


async def replay_seek(run_id: str, tick: int) -> dict:
    """Seek to a specific tick in the replay.

    Args:
        run_id: The run being replayed.
        tick: The target tick number.

    Returns:
        A JSON response with the world state at the target tick.
    """
    ...


async def replay_play_pause(run_id: str, action: str) -> dict:
    """Toggle play/pause state of the replay.

    Args:
        run_id: The run being replayed.
        action: One of ``"play"`` or ``"pause"``.

    Returns:
        A JSON response with the updated replay state.
    """
    ...
