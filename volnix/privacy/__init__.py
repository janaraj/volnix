"""Privacy primitives (PMF Plan Phase 4C Step 14).

Two product-facing surfaces:

1. **Redaction hook** — a product registers a dotted-path
   ``ledger_redactor`` in ``VolnixConfig.privacy``. The hook is
   called before every ``Ledger.append`` so sensitive payload
   fields can be stripped / hashed / replaced before landing
   on disk. Default is a no-op (``identity_redactor``).

2. **Ephemeral mode** — ``VolnixConfig.privacy.ephemeral = True``
   asks consumers to suppress disk writes. As of this ship the
   guard lives ONLY on ``Ledger.append``; bus persistence,
   snapshot stores, run-artifact sinks, and ``llm_debug``
   flat-files continue to write. A privacy-sensitive consumer
   who needs zero disk writes must also set
   ``bus.persistence_enabled=False`` and disable the
   run-artifact / snapshot sinks directly. Per-sink ephemeral
   is a follow-up step.

Composition root resolves the redactor once at boot via
:func:`resolve_ledger_redactor` and injects the resolved
callable into the ``Ledger`` — the ledger module never imports
from ``volnix.privacy``, preserving module isolation.
"""

from volnix.privacy.redaction import (
    LedgerRedactor,
    LedgerRedactorError,
    identity_redactor,
    resolve_ledger_redactor,
)

__all__ = [
    "LedgerRedactor",
    "LedgerRedactorError",
    "identity_redactor",
    "resolve_ledger_redactor",
]
