"""Built-in world templates shipped with Volnix.

Auto-discovered by :meth:`TemplateRegistry.discover_builtin`.
"""

from volnix.templates.builtin.customer_support import CustomerSupportTemplate
from volnix.templates.builtin.incident_response import IncidentResponseTemplate
from volnix.templates.builtin.open_sandbox import OpenSandboxTemplate

__all__ = [
    "CustomerSupportTemplate",
    "IncidentResponseTemplate",
    "OpenSandboxTemplate",
]
