"""Secret resolution for LLM API keys and credentials.

SecretResolver protocol with implementations:
- EnvVarResolver: resolves from os.environ
- FileResolver: resolves from files in a directory
- ChainResolver: tries resolvers in order
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretResolver(Protocol):
    """Protocol for resolving secret references to their actual values."""

    def resolve(self, ref: str) -> str | None:
        """Resolve a secret reference to its value.

        Args:
            ref: The secret reference (e.g. env var name or file name).

        Returns:
            The secret value, or ``None`` if not found.
        """
        ...


class EnvVarResolver:
    """Resolves secrets from environment variables."""

    def resolve(self, ref: str) -> str | None:
        """Look up *ref* in ``os.environ``.

        Args:
            ref: The environment variable name.

        Returns:
            The variable value, or ``None`` if not set.
        """
        return os.environ.get(ref)


class FileResolver:
    """Resolves secrets from files in a directory.

    Each secret is stored as a plain-text file whose name matches the
    reference.  Leading/trailing whitespace is stripped.
    """

    def __init__(self, secrets_dir: str = ".secrets") -> None:
        self._dir = Path(secrets_dir)

    def resolve(self, ref: str) -> str | None:
        """Read the secret from ``<secrets_dir>/<ref>``.

        Args:
            ref: The filename within the secrets directory.

        Returns:
            File contents (stripped), or ``None`` if the file does not exist
            or if the resolved path escapes the secrets directory.
        """
        path = (self._dir / ref).resolve()
        if not path.is_relative_to(self._dir.resolve()):
            return None  # path traversal attempt
        if path.is_file():
            return path.read_text().strip()
        return None

    async def async_resolve(self, ref: str) -> str | None:
        """Async version of resolve that doesn't block the event loop."""
        import asyncio

        return await asyncio.to_thread(self.resolve, ref)


class ChainResolver:
    """Tries multiple resolvers in order, returning the first hit.

    This allows layering resolution strategies (e.g. env vars first,
    then file-based secrets).
    """

    def __init__(self, resolvers: list[SecretResolver] | None = None) -> None:
        self._resolvers: list[SecretResolver] = resolvers or []

    def resolve(self, ref: str) -> str | None:
        """Try each resolver in order and return the first non-``None`` result.

        Args:
            ref: The secret reference.

        Returns:
            The resolved value, or ``None`` if no resolver could find it.
        """
        for r in self._resolvers:
            val = r.resolve(ref)
            if val is not None:
                return val
        return None

    async def async_resolve(self, ref: str) -> str | None:
        """Async version of resolve that doesn't block the event loop."""
        import asyncio

        return await asyncio.to_thread(self.resolve, ref)
