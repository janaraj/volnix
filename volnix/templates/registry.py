"""Template registry for discovering and retrieving world templates.

The :class:`TemplateRegistry` maintains a catalogue of available
templates and supports both explicit registration and automatic
discovery of built-in templates.
"""

from __future__ import annotations

from volnix.templates.base import BaseTemplate


class TemplateRegistry:
    """Registry of available world templates.

    Templates can be registered explicitly via :meth:`register` or
    discovered automatically from the ``builtin/`` package via
    :meth:`discover_builtin`.
    """

    def __init__(self) -> None:
        self._templates: dict[str, BaseTemplate] = {}

    def register(self, template: BaseTemplate) -> None:
        """Register a template instance.

        Args:
            template: The template to register.
        """
        ...

    def get(self, template_id: str) -> BaseTemplate | None:
        """Retrieve a template by its identifier.

        Args:
            template_id: The unique template identifier.

        Returns:
            The template instance, or ``None`` if not found.
        """
        ...

    def list_templates(self) -> list[dict]:
        """Return summary metadata for all registered templates.

        Returns:
            A list of dicts with ``template_id``, ``template_name``,
            and ``description`` keys.
        """
        ...

    def discover_builtin(self) -> None:
        """Auto-discover and register all templates in the builtin package."""
        ...
