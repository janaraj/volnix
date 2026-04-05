"""World Templates -- composable, parameterised world definitions.

This package provides the template abstraction layer for creating and
composing world definitions from reusable building blocks.

Re-exports the primary public API surface::

    from volnix.templates import BaseTemplate, TemplateRegistry, TemplateComposer
"""

from volnix.templates.base import BaseTemplate
from volnix.templates.composer import TemplateComposer
from volnix.templates.config import TemplateConfig
from volnix.templates.loader import TemplateLoader
from volnix.templates.registry import TemplateRegistry

__all__ = [
    "BaseTemplate",
    "TemplateComposer",
    "TemplateConfig",
    "TemplateLoader",
    "TemplateRegistry",
]
