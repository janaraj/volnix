"""Abstract base class for world templates.

A template encapsulates a parameterised recipe for generating a world
definition dict.  Concrete templates live under ``templates/builtin/``
and are auto-discovered by :class:`TemplateRegistry`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar


class BaseTemplate(ABC):
    """Abstract base for all world templates.

    Subclasses must set the three class-level identifiers and implement
    :meth:`generate`.

    Class Attributes:
        template_id: Unique machine-readable identifier.
        template_name: Human-readable display name.
        description: Short description of what the template creates.
    """

    template_id: ClassVar[str] = ""
    template_name: ClassVar[str] = ""
    description: ClassVar[str] = ""

    @abstractmethod
    async def generate(
        self,
        parameters: dict | None = None,
        reality: str = "realistic",
        fidelity: str = "auto",
        mode: str = "governed",
    ) -> dict:
        """Generate a world definition dict from the template.

        Args:
            parameters: Optional parameter overrides for template generation.
            reality: Reality preset (pristine, realistic, harsh).
            fidelity: Fidelity mode (auto, strict, exploratory).
            mode: World mode (governed, ungoverned).

        Returns:
            A world definition dictionary ready for the world compiler.
        """
        ...

    def get_schema(self) -> dict:
        """Return a JSON-Schema-style dict describing accepted parameters.

        Returns:
            Parameter schema dictionary.
        """
        ...

    def validate_parameters(self, params: dict) -> list[str]:
        """Validate parameters and return a list of error messages.

        Args:
            params: Parameters to validate.

        Returns:
            A list of validation error strings; empty if valid.
        """
        ...
