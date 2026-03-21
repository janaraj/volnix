"""Built-in world templates shipped with Terrarium.

Auto-discovered by :meth:`TemplateRegistry.discover_builtin`.
"""

from terrarium.templates.builtin.customer_support import CustomerSupportTemplate
from terrarium.templates.builtin.incident_response import IncidentResponseTemplate
from terrarium.templates.builtin.open_sandbox import OpenSandboxTemplate

__all__ = [
    "CustomerSupportTemplate",
    "IncidentResponseTemplate",
    "OpenSandboxTemplate",
]
