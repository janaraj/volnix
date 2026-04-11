"""Game service responder pack — verified Tier 1.

Handles the four structured negotiation tools (``negotiate_propose``,
``negotiate_counter``, ``negotiate_accept``, ``negotiate_reject``) by
writing deal state deltas atomically through the pipeline commit
transaction. This is the MF1 fix from Cycle B plan validation: state
mutations happen in the responder pack (inside the commit), not in
a bus subscriber (where they would race with subsequent commits).

Entity types owned by this pack:

- ``negotiation_deal``: the deal being negotiated
- ``negotiation_proposal``: audit trail of every propose/counter move
- ``game_player_brief``: per-actor private brief (narrative only)
- ``negotiation_target_terms``: per-actor competitive scoring data
  (ideal_terms, term_weights, batna_score) — only materialized in
  competitive scoring mode
"""

from volnix.packs.verified.game.pack import GamePack

__all__ = ["GamePack"]
