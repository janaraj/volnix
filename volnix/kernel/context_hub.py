"""Context Hub integration -- fetch curated API docs for 600+ services.

Uses ``npx @aisuite/chub`` so there is nothing to install globally.
Any machine with ``npm`` can use this provider -- ``npx`` auto-downloads
and caches the ``@aisuite/chub`` package on first use.

Repository: https://github.com/andrewyng/context-hub
Package:    npm @aisuite/chub

CLI commands used:
  npx @aisuite/chub search <query>           -- discover content IDs
  npx @aisuite/chub get <id> --lang <py|js>  -- fetch curated docs

Content IDs follow the pattern ``{service}/{topic}`` and vary per
service (e.g. ``stripe/api``, ``twilio/messaging``, ``jira/issues``).
The provider discovers the correct ID via ``search`` before fetching.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from typing import Any

logger = logging.getLogger(__name__)

# Regex for a single result line in ``chub search`` output:
#   twilio/messaging  [doc]  py, ts  [maintainer]
_RESULT_RE = re.compile(r"^\s+(\S+)\s+\[doc\]\s+(.+?)\s+\[")

# Preferred content topic when multiple match (highest priority first)
_TOPIC_PRIORITY = ("api", "package")


class ContextHubProvider:
    """Fetches curated API docs from Context Hub via ``npx @aisuite/chub``.

    Satisfies the :class:`ExternalSpecProvider` protocol.
    """

    provider_name = "context_hub"

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._base_cmd = ("npx", "@aisuite/chub")
        self._search_cache: dict[str, list[tuple[str, list[str]]]] = {}

    # -- ExternalSpecProvider protocol -----------------------------------------

    async def is_available(self) -> bool:
        """True when ``npx`` is on PATH (npm must be installed)."""
        import asyncio

        return await asyncio.to_thread(shutil.which, "npx") is not None

    async def supports(self, service_name: str) -> bool:
        """True when ``chub search`` finds content for *service_name*."""
        if not await self.is_available():
            return False
        try:
            results = await self._search(service_name)
            name = service_name.lower()
            return any(cid.startswith(f"{name}/") for cid, _ in results)
        except Exception:
            return False

    async def fetch(self, service_name: str) -> dict[str, Any] | None:
        """Search for the best content ID, then fetch its docs.

        Two-step:
        1. ``chub search {service}`` → discover content IDs + languages
        2. ``chub get {id} --lang {lang}`` → retrieve curated markdown

        Prefers Python docs (``--lang py``); falls back to the first
        available language.  Returns ``None`` on any failure.
        """
        if not await self.is_available():
            logger.debug("npx not installed -- skipping Context Hub")
            return None

        try:
            results = await self._search(service_name)
            match = self._pick_best_match(results, service_name)
            if match is None:
                logger.debug("Context Hub: no content found for '%s'", service_name)
                return None

            content_id, lang = match
            content = await self._get(content_id, lang)
            if content is None:
                return None

            return {
                "source": "context_hub",
                "service": service_name,
                "content_id": content_id,
                "lang": lang,
                "raw_content": content,
                "content_type": "markdown",
            }
        except Exception as exc:
            logger.warning("Context Hub fetch failed for '%s': %s", service_name, exc)
            return None

    # -- Public helpers --------------------------------------------------------

    async def list_available(self) -> list[str]:
        """Return all content IDs known to Context Hub."""
        if not await self.is_available():
            return []
        try:
            results = await self._search("")
            return [cid for cid, _ in results]
        except Exception:
            return []

    # -- Internal subprocess calls ---------------------------------------------

    async def _search(self, query: str) -> list[tuple[str, list[str]]]:
        """Run ``chub search`` and return parsed results (cached)."""
        key = query.lower()
        if key in self._search_cache:
            return self._search_cache[key]

        proc = await asyncio.create_subprocess_exec(
            *self._base_cmd,
            "search",
            query,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        if proc.returncode != 0:
            self._search_cache[key] = []
            return []

        results = self._parse_search_results(stdout.decode())
        self._search_cache[key] = results
        return results

    async def _get(self, content_id: str, lang: str) -> str | None:
        """Run ``chub get {id} --lang {lang}`` and return content."""
        proc = await asyncio.create_subprocess_exec(
            *self._base_cmd,
            "get",
            content_id,
            "--lang",
            lang,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        if proc.returncode != 0:
            logger.debug(
                "chub get %s --lang %s failed (rc=%d): %s",
                content_id,
                lang,
                proc.returncode,
                stderr.decode()[:200],
            )
            return None

        content = stdout.decode()
        return content if content.strip() else None

    # -- Parsing ---------------------------------------------------------------

    @staticmethod
    def _parse_search_results(
        output: str,
    ) -> list[tuple[str, list[str]]]:
        """Parse ``chub search`` output into ``[(content_id, [langs])]``."""
        results: list[tuple[str, list[str]]] = []
        for line in output.splitlines():
            m = _RESULT_RE.match(line)
            if m:
                content_id = m.group(1)
                langs = [lang.strip() for lang in m.group(2).split(",")]
                results.append((content_id, langs))
        return results

    @staticmethod
    def _pick_best_match(
        results: list[tuple[str, list[str]]],
        service_name: str,
    ) -> tuple[str, str] | None:
        """Pick the best content ID and language for *service_name*.

        Filtering:  only IDs that start with ``{service_name}/``.
        Priority:   ``{service}/api`` > ``{service}/package`` > first match.
        Language:   ``py`` if available, else first in the list.
        """
        name = service_name.lower()
        matching = [(cid, langs) for cid, langs in results if cid.lower().startswith(f"{name}/")]
        if not matching:
            return None

        # Sort by topic priority
        def _sort_key(item: tuple[str, list[str]]) -> int:
            topic = item[0].split("/", 1)[1] if "/" in item[0] else ""
            try:
                return _TOPIC_PRIORITY.index(topic)
            except ValueError:
                return len(_TOPIC_PRIORITY)

        matching.sort(key=_sort_key)
        best_id, best_langs = matching[0]

        # Prefer Python docs
        lang = "py" if "py" in best_langs else best_langs[0]
        return best_id, lang
