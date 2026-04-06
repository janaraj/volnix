"""Template composer for merging multiple world definitions.

The :class:`TemplateComposer` combines partial world definitions from
multiple templates into a single unified world definition, with support
for overlay overrides.
"""

from __future__ import annotations


class TemplateComposer:
    """Merges multiple template outputs into a single world definition."""

    def compose(self, templates: list[dict], overrides: dict | None = None) -> dict:
        """Compose multiple template output dicts into a unified world definition.

        Args:
            templates: List of world definition dicts to merge.
            overrides: Optional final overrides applied after merging.

        Returns:
            The merged world definition dictionary.
        """
        ...

    def merge_services(self, base: dict, overlay: dict) -> dict:
        """Merge service definitions from *overlay* into *base*.

        Args:
            base: The base service definitions.
            overlay: Service definitions to merge in.

        Returns:
            Merged service definitions.
        """
        ...

    def merge_actors(self, base: list, overlay: list) -> list:
        """Merge actor lists, deduplicating by actor identity.

        Args:
            base: Base actor definitions.
            overlay: Overlay actor definitions.

        Returns:
            Merged actor list.
        """
        ...

    def merge_policies(self, base: list, overlay: list) -> list:
        """Merge policy lists, deduplicating by policy identity.

        Args:
            base: Base policy definitions.
            overlay: Overlay policy definitions.

        Returns:
            Merged policy list.
        """
        ...
