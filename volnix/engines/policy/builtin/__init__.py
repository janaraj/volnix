"""Built-in policy gates shipped with the policy engine.

These are Python-coded gates (distinct from YAML-defined user policies)
that run as part of the policy pipeline step but are registered
directly on :class:`PolicyEngine` at composition time via
:meth:`PolicyEngine.register_gate`.

A gate is any object that implements :meth:`evaluate(ctx) -> StepResult`.
Gates run BEFORE YAML policies. A gate's ``DENY`` verdict short-circuits
the step, preventing the action from progressing through the pipeline.
"""

from volnix.engines.policy.builtin.game_active import GameActivePolicy

__all__ = ["GameActivePolicy"]
