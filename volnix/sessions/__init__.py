"""Platform sessions — PMF Plan Phase 4C Step 5.

A Session is a sibling of World and Run — within one World, ≥1
Runs are grouped under one Session. Sessions persist across
process restarts via SQLite-backed storage (``SessionStore``) and
drive lifecycle events through ``SessionManager``.

Public API: ``SessionManager`` (exported at ``volnix.SessionManager``).
``SlotAssignment`` is re-exported from ``store.py`` for consumers
who type-hint the return of ``SessionManager.slots_for_session()``
(audit-fold M2). Types (``Session``, ``SessionStatus``,
``SessionType``, ``SessionId``) live in ``volnix.core.session`` /
``volnix.core.types``.
"""

from volnix.sessions.manager import SessionManager
from volnix.sessions.store import SlotAssignment

__all__ = ["SessionManager", "SlotAssignment"]
