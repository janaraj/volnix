"""Shared dotted-path hook resolver (Phase 4C cleanup 2/N).

Steps 12 and 14 both shipped near-identical ``resolve_*_hook``
helpers that parse ``"package.module:callable_name"`` strings
and return the resolved callable. The duplication was flagged
by both post-impl audits (Step 14 audit M4). This module
factors the shared logic so future hooks add at most a thin
wrapper.

Consumers:
- ``volnix.actors.trait_extractor.resolve_extractor_hook``
- ``volnix.privacy.redaction.resolve_ledger_redactor``

Each wrapper passes its own error class + default callable +
hook-name prefix; the resolver does the parse + import + getattr
+ callable check and raises the caller's error class on every
failure branch.

NOT part of the public API — module name begins with ``_``.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any


def resolve_dotted_hook(
    hook: str | None,
    *,
    default: Callable[..., Any],
    error_cls: type[Exception],
    hook_name: str,
) -> Callable[..., Any]:
    """Resolve a ``"package.module:callable_name"`` hook string.

    Args:
        hook: Dotted-path hook string. ``None`` / empty /
            whitespace-only returns ``default``.
        default: Callable returned when ``hook`` is None / empty.
        error_cls: Exception class raised on malformed /
            unresolvable hooks. Each caller passes its own domain
            error so the exception hierarchy stays meaningful.
        hook_name: Human-readable identifier for the hook config
            field (e.g. ``"trait_extractor_hook"``). Appears in
            every error message for actionable diagnostics.

    Returns:
        The resolved callable.

    Raises:
        ``error_cls``: on missing colon, empty module / callable
            segment, import failure, missing attribute, or
            non-callable resolved target. Every branch includes
            ``hook_name`` and the raw hook string in the message.
    """
    if hook is None or not hook.strip():
        return default
    raw = hook.strip()
    if ":" not in raw:
        raise error_cls(
            f"{hook_name} {raw!r}: expected 'package.module:callable_name' (colon separator)."
        )
    module_path, _, attr = raw.partition(":")
    if not module_path or not attr:
        raise error_cls(
            f"{hook_name} {raw!r}: module path and callable name must both be non-empty."
        )
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise error_cls(f"{hook_name} {raw!r}: import failed: {exc}") from exc
    try:
        resolved = getattr(module, attr)
    except AttributeError as exc:
        raise error_cls(
            f"{hook_name} {raw!r}: module {module_path!r} has no attribute {attr!r}"
        ) from exc
    if not callable(resolved):
        raise error_cls(
            f"{hook_name} {raw!r}: resolved target is not callable (got {type(resolved).__name__})."
        )
    return resolved
