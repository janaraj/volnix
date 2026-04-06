"""Cross-section configuration validation for the Volnix framework.

Validates that pipeline step references resolve to registered engines,
LLM routing entries point to valid providers/models, and inter-section
references are consistent.
"""

from __future__ import annotations

from volnix.config.schema import VolnixConfig

_VALID_REALITY_PRESETS = {"ideal", "messy", "hostile"}
_VALID_FIDELITY_MODES = {"auto", "strict", "exploratory"}
_VALID_SIMULATION_MODES = {"governed", "ungoverned"}


class ConfigValidator:
    """Validates configuration consistency across sections."""

    def validate_pipeline_steps(
        self, config: VolnixConfig, available_engines: list[str]
    ) -> list[str]:
        """Validate that all pipeline steps reference available engines.

        Args:
            config: The root configuration to validate.
            available_engines: Names of engines currently registered.

        Returns:
            A list of error messages (empty if valid).
        """
        errors: list[str] = []
        engine_set = set(available_engines)
        for step in config.pipeline.steps:
            if step not in engine_set:
                errors.append(
                    f"Pipeline step '{step}' is not in available engines: {sorted(engine_set)}"
                )
        return errors

    def validate_llm_routing(self, config: VolnixConfig) -> list[str]:
        """Validate that LLM routing entries reference defined providers.

        Args:
            config: The root configuration to validate.

        Returns:
            A list of error messages (empty if valid).
        """
        errors: list[str] = []
        provider_names = set(config.llm.providers.keys())
        for route_name, entry in config.llm.routing.items():
            if entry.provider and entry.provider not in provider_names:
                errors.append(
                    f"LLM routing '{route_name}' references unknown provider "
                    f"'{entry.provider}'; available: {sorted(provider_names)}"
                )
        return errors

    def validate_cross_references(self, config: VolnixConfig) -> list[str]:
        """Validate inter-section references are consistent.

        Checks reality preset, fidelity mode, and simulation mode against
        known valid values.

        Args:
            config: The root configuration to validate.

        Returns:
            A list of error messages (empty if valid).
        """
        errors: list[str] = []

        preset = config.simulation.reality.preset
        if preset not in _VALID_REALITY_PRESETS:
            errors.append(
                f"Reality preset '{preset}' is not valid; "
                f"expected one of {sorted(_VALID_REALITY_PRESETS)}"
            )

        fidelity_mode = config.simulation.fidelity.mode
        if fidelity_mode not in _VALID_FIDELITY_MODES:
            errors.append(
                f"Fidelity mode '{fidelity_mode}' is not valid; "
                f"expected one of {sorted(_VALID_FIDELITY_MODES)}"
            )

        sim_mode = config.simulation.mode
        if sim_mode not in _VALID_SIMULATION_MODES:
            errors.append(
                f"Simulation mode '{sim_mode}' is not valid; "
                f"expected one of {sorted(_VALID_SIMULATION_MODES)}"
            )

        return errors

    def validate_all(
        self,
        config: VolnixConfig,
        available_engines: list[str] | None = None,
    ) -> list[str]:
        """Run all validation checks and aggregate errors.

        Args:
            config: The root configuration to validate.
            available_engines: Known engine names for pipeline step validation.
                If None, pipeline step validation is skipped.

        Returns:
            A combined list of all error messages (empty if valid).
        """
        errors: list[str] = []
        if available_engines is not None:
            errors.extend(self.validate_pipeline_steps(config, available_engines))
        errors.extend(self.validate_llm_routing(config))
        errors.extend(self.validate_cross_references(config))
        return errors
