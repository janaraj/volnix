"""Phase 4C Step 4 — rename tests for the pre-4C LLM
``Session`` dataclass → ``LLMConversationSession``.

Locks the module-level deprecation alias contract: importing the
old name emits ``DeprecationWarning`` but still resolves to the
new class (so pre-4C consumers keep working during the 0.2.0
migration window; breakage lands at 0.3.0).
"""

from __future__ import annotations

import importlib
import warnings

import pytest


def test_negative_importing_deprecated_session_warns() -> None:
    """Accessing ``volnix.llm.conversation.Session`` must emit
    ``DeprecationWarning`` with the rename rationale (for a
    consumer auditing deprecation logs before 0.3.0)."""
    module = importlib.import_module("volnix.llm.conversation")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        _ = module.Session
    depr = [w for w in captured if issubclass(w.category, DeprecationWarning)]
    assert depr, "expected a DeprecationWarning on Session attribute access"
    assert "LLMConversationSession" in str(depr[0].message)


def test_positive_new_name_imports_without_warning() -> None:
    """The canonical name must NOT trigger a warning. Catches a
    future refactor that accidentally routes ``LLMConversationSession``
    through the same ``__getattr__`` branch."""
    module = importlib.import_module("volnix.llm.conversation")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        cls = module.LLMConversationSession
        assert cls is not None
    depr = [w for w in captured if issubclass(w.category, DeprecationWarning)]
    assert not depr, f"unexpected DeprecationWarning(s): {depr}"


def test_positive_deprecated_alias_equals_new_class() -> None:
    """The alias must resolve to the SAME class object — pre-4C
    ``isinstance`` checks on stored session objects must continue
    to succeed during the migration window."""
    module = importlib.import_module("volnix.llm.conversation")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        old_name = module.Session
    assert old_name is module.LLMConversationSession


def test_negative_unknown_attribute_still_raises() -> None:
    """The ``__getattr__`` hook must not swallow real typos —
    requesting a missing attribute must still raise
    ``AttributeError`` (not return ``None`` or re-emit a
    deprecation warning)."""
    module = importlib.import_module("volnix.llm.conversation")
    with pytest.raises(AttributeError):
        _ = module.SomethingThatDoesntExist


def test_positive_package_root_exports_new_llm_conversation_session_name() -> None:
    """``volnix.llm.__all__`` must ship ``LLMConversationSession``
    so ``from volnix.llm import LLMConversationSession`` works
    without a submodule reach."""
    import volnix.llm as llm_pkg

    assert "LLMConversationSession" in llm_pkg.__all__


def test_negative_package_root_does_not_export_old_session_name() -> None:
    """Consumers reaching through the package root (``from
    volnix.llm import Session``) migrate hard at 0.2.0 — no alias
    path through the root, per D4f. This test locks that contract."""
    import volnix.llm as llm_pkg

    assert "Session" not in llm_pkg.__all__
