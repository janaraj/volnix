"""Profile-to-surface conversion.

Converts a ServiceProfileData (Tier 2 YAML profile) into a ServiceSurface
for use by MCP/HTTP/Gateway adapters. This is the bridge between the
data-file world (profiles) and the runtime world (surfaces).
"""

from __future__ import annotations

import logging

from terrarium.kernel.surface import APIOperation, ServiceSurface
from terrarium.packs.profile_schema import ServiceProfileData

logger = logging.getLogger(__name__)


def profile_to_surface(profile: ServiceProfileData) -> ServiceSurface:
    """Convert a Tier 2 profile to ServiceSurface for MCP/HTTP/Gateway.

    Maps each ProfileOperation to an APIOperation, each ProfileEntity
    to an entity_schema entry, and each ProfileStateMachine to a
    state_machines entry.
    """
    # Validate service_name consistency across operations
    for op in profile.operations:
        if op.service != profile.service_name:
            logger.warning(
                "Operation '%s' has service='%s' but profile service_name='%s'",
                op.name,
                op.service,
                profile.service_name,
            )

    operations = [
        APIOperation(
            name=op.name,
            service=profile.service_name,
            description=op.description,
            http_method=op.http_method,
            http_path=op.http_path,
            parameters=op.parameters,
            required_params=op.required_params,
            response_schema=op.response_schema,
            is_read_only=op.is_read_only,
            creates_entity=op.creates_entity,
            mutates_entity=op.mutates_entity,
        )
        for op in profile.operations
    ]

    entity_schemas = {
        entity.name: {
            "type": "object",
            "x-terrarium-identity": entity.identity_field,
            "required": entity.required,
            "properties": entity.fields,
        }
        for entity in profile.entities
    }

    state_machines = {
        sm.entity_type: {"field": sm.field, "transitions": sm.transitions}
        for sm in profile.state_machines
    }

    surface = ServiceSurface(
        service_name=profile.service_name,
        category=profile.category,
        source=profile.fidelity_source,
        fidelity_tier=2,
        confidence=profile.confidence,
        operations=operations,
        entity_schemas=entity_schemas,
        state_machines=state_machines,
        auth_pattern=profile.auth_pattern,
        base_url=profile.base_url,
    )

    # Validate the surface
    validation_errors = surface.validate_surface()
    if validation_errors:
        logger.warning(
            "Profile '%s' surface has validation issues: %s",
            profile.profile_name,
            validation_errors[:3],
        )

    return surface
