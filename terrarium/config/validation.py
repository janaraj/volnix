"""Cross-section configuration validation for the Terrarium framework.

Validates that pipeline step references resolve to registered engines,
LLM routing entries point to valid providers/models, and inter-section
references are consistent.
"""

from __future__ import annotations

from terrarium.config.schema import TerrariumConfig


class ConfigValidator:
    """Validates configuration consistency across sections."""

    def validate_pipeline_steps(
        self, config: TerrariumConfig, available_engines: list[str]
    ) -> list[str]:
        """Validate that all pipeline steps reference available engines.

        Args:
            config: The root configuration to validate.
            available_engines: Names of engines currently registered.

        Returns:
            A list of error messages (empty if valid).
        """
        ...

    def validate_llm_routing(self, config: TerrariumConfig) -> list[str]:
        """Validate that LLM routing entries reference defined providers.

        Args:
            config: The root configuration to validate.

        Returns:
            A list of error messages (empty if valid).
        """
        ...

    def validate_cross_references(self, config: TerrariumConfig) -> list[str]:
        """Validate inter-section references are consistent.

        Args:
            config: The root configuration to validate.

        Returns:
            A list of error messages (empty if valid).
        """
        ...

    def validate_all(self, config: TerrariumConfig) -> list[str]:
        """Run all validation checks and aggregate errors.

        Args:
            config: The root configuration to validate.

        Returns:
            A combined list of all error messages (empty if valid).
        """
        ...
