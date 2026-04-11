"""Scoring strategies for game evaluations.

GameOrchestrator picks a strategy at configure time based on
``GameDefinition.scoring_mode``:

- ``"behavioral"`` (default) → :class:`BehavioralScorer`
- ``"competitive"`` → :class:`CompetitiveScorer`

Both implement the :class:`GameScorer` protocol. They share the
:class:`ScorerContext` shape but never share competitive-only fields.
See plan section 5 for the routing decision.
"""

from volnix.engines.game.scorers.base import GameScorer, ScorerContext
from volnix.engines.game.scorers.behavioral import BehavioralScorer
from volnix.engines.game.scorers.competitive import CompetitiveScorer

__all__ = ["GameScorer", "ScorerContext", "BehavioralScorer", "CompetitiveScorer"]
