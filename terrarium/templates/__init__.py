"""World Templates -- composable, parameterised world definitions.

This package provides the template abstraction layer for creating and
composing world definitions from reusable building blocks.

Re-exports the primary public API surface::

    from terrarium.templates import BaseTemplate, TemplateRegistry, TemplateComposer
"""

from terrarium.templates.base import BaseTemplate
from terrarium.templates.composer import TemplateComposer
from terrarium.templates.config import TemplateConfig
from terrarium.templates.loader import TemplateLoader
from terrarium.templates.registry import TemplateRegistry

__all__ = [
    "BaseTemplate",
    "TemplateComposer",
    "TemplateConfig",
    "TemplateLoader",
    "TemplateRegistry",
]
