"""Context Hub integration -- fetch real API docs for 70+ services.

Uses the `chub` CLI from @anthropic/context-hub npm package.
Install: npm install -g @anthropic/context-hub

The chub CLI returns structured API documentation:
  chub get stripe/api -> endpoint descriptions, parameter schemas,
  auth patterns, common gotchas, response formats.

This is the BEST source for unknown services because it has
real, curated API documentation -- not LLM inference.
"""
import asyncio
import logging
import shutil
from typing import Any

logger = logging.getLogger(__name__)

# FIX-13: Known services as class-level constant (not rebuilt per call)
_KNOWN_SERVICES: frozenset[str] = frozenset({
    "stripe", "github", "slack", "gmail", "twilio", "sendgrid",
    "openai", "anthropic", "firebase", "supabase", "vercel",
    "aws", "gcp", "azure", "shopify", "salesforce", "hubspot",
    "notion", "airtable", "linear", "jira", "asana",
    "datadog", "pagerduty", "sentry", "grafana",
    # ... 70+ more
})


class ContextHubProvider:
    """Fetches API docs from Context Hub via chub CLI."""

    provider_name = "context_hub"

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._command = "chub"

    async def is_available(self) -> bool:
        """Check if chub CLI is installed."""
        return shutil.which(self._command) is not None

    async def supports(self, service_name: str) -> bool:
        """Check if Context Hub likely has this service.

        Quick heuristic: check if the service name is in the known catalog.
        For a more accurate check, we'd need to query chub list.
        """
        return service_name.lower() in _KNOWN_SERVICES

    async def fetch(self, service_name: str) -> dict[str, Any] | None:
        """Fetch API documentation via chub get {service}/api.

        Returns structured dict with raw_content, endpoints (if parseable),
        and metadata. Returns None if chub not installed or service not found.
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
                logger.debug("chub get %s/api failed (rc=%d): %s",
                             service_name, proc.returncode, stderr.decode()[:200])
                return None

            content = stdout.decode()
            if not content.strip():
                return None

            return {
                "source": "context_hub",
                "service": service_name,
                "raw_content": content,
                "content_type": "markdown",
                # Future: parse endpoints, schemas from the markdown
            }

        except asyncio.TimeoutError:
            logger.warning("chub get %s/api timed out after %.0fs", service_name, self._timeout)
            return None
        except FileNotFoundError:
            logger.debug("chub command not found")
            return None
        except Exception as exc:
            logger.warning("chub get %s/api error: %s", service_name, exc)
            return None

    async def list_available(self) -> list[str]:
        """List services available in Context Hub (if chub supports it)."""
        if not await self.is_available():
            return []
        try:
            proc = await asyncio.create_subprocess_exec(
                self._command, "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            if proc.returncode == 0:
                return [line.strip() for line in stdout.decode().splitlines() if line.strip()]
        except Exception:
            pass
        return []
