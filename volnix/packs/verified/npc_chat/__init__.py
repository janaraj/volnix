"""NPC-to-NPC chat pack.

Re-exports :class:`NPCChatPack` so ``verified/``-directory auto-discovery
(``volnix/packs/loader.py:21-57``) picks it up without a manifest entry.
"""

from volnix.packs.verified.npc_chat.pack import NPCChatPack

__all__ = ["NPCChatPack"]
