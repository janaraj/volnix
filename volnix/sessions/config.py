"""Configuration for the SessionManager (PMF Plan Phase 4C Step 5)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from volnix.core.session import SessionType


class SessionsConfig(BaseModel):
    """Lightweight sessions config — storage handle name + default
    session type. Sessions are always available (D5a) so there's no
    ``enabled`` flag.

    ``default_type`` uses the ``SessionType`` enum (not ``str``) so
    misconfiguration is caught at load time rather than at
    ``SessionManager.start()`` time (audit-fold M8).
    """

    model_config = ConfigDict(frozen=True)

    storage_db_name: str = "sessions"
    default_type: SessionType = SessionType.BOUNDED
