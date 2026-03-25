"""Context Hub integration -- fetch real API docs for 600+ services.

Uses the ``chub`` CLI from the ``@aisuite/chub`` npm package.
Install: ``npm install -g @aisuite/chub``

The chub CLI returns curated, versioned API documentation:
  chub get stripe/api -> endpoint descriptions, parameter schemas,
  auth patterns, common gotchas, response formats.

Repository: https://github.com/andrewyng/context-hub
All content is open and maintained as markdown -- agents read
exactly what the community has curated.

This is the BEST source for unknown services because it provides
real, curated API documentation -- not LLM inference.
"""
import asyncio
import logging
import shutil
from typing import Any

logger = logging.getLogger(__name__)


class ContextHubProvider:
    """Fetches API docs from Context Hub via ``chub`` CLI.

    CLI commands used:
      chub search <query>   -- search available docs and skills
      chub get <id>         -- fetch docs by ID (e.g. ``stripe/api``)
    """

    provider_name = "context_hub"

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._command = "chub"

    async def is_available(self) -> bool:
        """Check if chub CLI is installed."""
        return shutil.which(self._command) is not None

    async def supports(self, service_name: str) -> bool:
        """Check if Context Hub has docs for this service.

        Runs ``chub search <service>`` and returns True if results
        are found.  Falls back to False on any error.
        """
        if not await self.is_available():
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                self._command, "search", service_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=10.0
            )
            if proc.returncode != 0:
                return False
            # If search returns any results, this service is supported
            content = stdout.decode().strip()
            return bool(content)
        except Exception:
            return False

    async def fetch(self, service_name: str) -> dict[str, Any] | None:
        """Fetch API documentation via ``chub get {service}/api``.

        Returns structured dict with raw_content, endpoints (if parseable),
        and metadata.  Returns ``None`` if chub is not installed or the
        service is not found.
        """
        if not await self.is_available():
            logger.debug("chub CLI not installed -- skipping Context Hub")
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                self._command, "get", f"{service_name}/api",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )

            if proc.returncode != 0:
                logger.debug(
                    "chub get %s/api failed (rc=%d): %s",
                    service_name,
                    proc.returncode,
                    stderr.decode()[:200],
                )
                return None

            content = stdout.decode()
            if not content.strip():
                return None

            return {
                "source": "context_hub",
                "service": service_name,
                "raw_content": content,
                "content_type": "markdown",
            }

        except asyncio.TimeoutError:
            logger.warning(
                "chub get %s/api timed out after %.0fs",
                service_name,
                self._timeout,
            )
            return None
        except FileNotFoundError:
            logger.debug("chub command not found")
            return None
        except Exception as exc:
            logger.warning("chub get %s/api error: %s", service_name, exc)
            return None

    async def list_available(self) -> list[str]:
        """Search Context Hub for all services (returns IDs)."""
        if not await self.is_available():
            return []
        try:
            proc = await asyncio.create_subprocess_exec(
                self._command, "search", "",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            if proc.returncode == 0:
                return [
                    line.strip()
                    for line in stdout.decode().splitlines()
                    if line.strip()
                ]
        except Exception:
            pass
        return []
