"""Ledger redaction hook plumbing (PMF Plan Phase 4C Step 14).

The platform ships a default no-op redactor (``identity_redactor``)
that returns its input unchanged. Products register a custom
redactor by setting ``VolnixConfig.privacy.ledger_redactor`` to
a dotted-path string in the form ``"package.module:callable_name"``
(the same format trait_extractor_hook uses in Step 12).

Contract:
- Callable signature: ``(LedgerEntry) -> LedgerEntry``.
- Callable is called BEFORE ``Ledger.append`` writes to disk.
- Returning ``None`` is a programming error — raises a loud
  ``TypeError`` so silent data drops surface immediately
  (post-impl audit scope: no silent None-drops).

Scope (documented limit): the redactor runs on ledger entries
only. In-memory state that never reaches the ledger (actor
state, LLM request bodies pre-router, bus events) is NOT
redacted by this hook. Consumers requiring in-memory redaction
layer their own hook at the LLM-router / activator boundary.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from volnix.core.errors import VolnixError

if TYPE_CHECKING:
    from volnix.ledger.entries import LedgerEntry


LedgerRedactor = Callable[["LedgerEntry"], "LedgerEntry"]


class LedgerRedactorError(VolnixError):
    """Raised when a ``ledger_redactor`` config string cannot be
    resolved to a callable. Surfaces at boot via
    :func:`resolve_ledger_redactor` rather than silently falling
    back to the identity redactor (products that set a hook
    expect it to be honored).

    Subclass of ``VolnixError`` per the error-hierarchy lock.
    """


def identity_redactor(entry: LedgerEntry) -> LedgerEntry:
    """Default no-op redactor. Returns its input unchanged.

    Products override via
    ``VolnixConfig.privacy.ledger_redactor = "mypackage:my_redactor"``.
    """
    return entry


def resolve_ledger_redactor(hook: str | None) -> LedgerRedactor:
    """Resolve a dotted-path hook string to the underlying
    callable. ``None`` / empty returns :func:`identity_redactor`.

    Format: ``"package.module:callable_name"`` (Python entry-
    point convention — colon separator between module path and
    attribute).

    Raises:
        LedgerRedactorError: on missing colon, invalid module,
            missing attribute, or non-callable resolved target.
    """
    if hook is None or not hook.strip():
        return identity_redactor
    raw = hook.strip()
    if ":" not in raw:
        raise LedgerRedactorError(
            f"ledger_redactor {raw!r}: expected 'package.module:callable_name' (colon separator)."
        )
    module_path, _, attr = raw.partition(":")
    if not module_path or not attr:
        raise LedgerRedactorError(
            f"ledger_redactor {raw!r}: module path and callable name must both be non-empty."
        )
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise LedgerRedactorError(f"ledger_redactor {raw!r}: import failed: {exc}") from exc
    try:
        resolved = getattr(module, attr)
    except AttributeError as exc:
        raise LedgerRedactorError(
            f"ledger_redactor {raw!r}: module {module_path!r} has no attribute {attr!r}"
        ) from exc
    if not callable(resolved):
        raise LedgerRedactorError(
            f"ledger_redactor {raw!r}: resolved target is not "
            f"callable (got {type(resolved).__name__})."
        )
    return resolved
