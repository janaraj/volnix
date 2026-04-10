"""Game-type-specific round evaluators.

Each evaluator inherits from BaseRoundEvaluator (for audited state writes,
ledger integration, and player ID resolution) and implements the
RoundEvaluator protocol. Registration in ROUND_EVALUATOR_REGISTRY happens
via the runner's lazy-load mechanism.
"""

from volnix.game.evaluators.base import BaseRoundEvaluator
from volnix.game.evaluators.negotiation import NegotiationEvaluator

__all__ = ["BaseRoundEvaluator", "NegotiationEvaluator"]
