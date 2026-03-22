"""World Packs -- service simulation building blocks.

This package provides the two-tier service simulation abstraction:

- **Tier 1 (ServicePack)**: Verified packs with deterministic state machines
  and canonical tools for an entire service category.
- **Tier 2 (ServiceProfile)**: Profiled overlays that add service-specific
  behavioural annotations, response schemas, and responder prompts.

Re-exports the primary public API surface::

    from terrarium.packs import ServicePack, ServiceProfile, PackRegistry, PackRuntime
"""

from terrarium.packs.base import ActionHandler, ServicePack, ServiceProfile
from terrarium.packs.loader import discover_packs, discover_profiles
from terrarium.packs.registry import PackRegistry
from terrarium.packs.runtime import PackRuntime

__all__ = [
    "ActionHandler",
    "PackRegistry",
    "PackRuntime",
    "ServicePack",
    "ServiceProfile",
    "discover_packs",
    "discover_profiles",
]
