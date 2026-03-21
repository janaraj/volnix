"""World Packs -- service simulation building blocks.

This package provides the two-tier service simulation abstraction:

- **Tier 1 (ServicePack)**: Verified packs with deterministic state machines
  and canonical tools for an entire service category.
- **Tier 2 (ServiceProfile)**: Profiled overlays that add service-specific
  behavioural annotations, response schemas, and responder prompts.

Re-exports the primary public API surface::

    from terrarium.packs import ServicePack, ServiceProfile
"""

from terrarium.packs.base import ServicePack, ServiceProfile

__all__ = [
    "ServicePack",
    "ServiceProfile",
]
