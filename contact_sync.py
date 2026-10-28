"""Keep personal invite links in sync with their owner's contact: address, relays and name.

A link is only touched when the key of the contact in the claiming 1:1 chat has the link's
fingerprint, so a link registered for another profile is never rewritten with the sender's data.

Relay changes reach the bot as core "keyupdate" messages (core 2.60+): the core merges the new
key with its relay list and trashes the message, so no NewMessage event fires. That's why
`sync_all_claims` also runs periodically from bot.py, not only on incoming messages.
"""
import re
from typing import List, Optional

import database
import dc_fingerprint
import identicon
from dc_helpers import _is_private_chat

# How often bot.py re-checks every personal link against the core's contact data
SYNC_INTERVAL_SECONDS = 3600

# Contact ids up to this one are special (self, info, device...) in the core
_LAST_SPECIAL_CONTACT_ID = 9


def parse_relays(encryption_info: str) -> List[str]:
    """Relay addresses from get_contact_encryption_info: the lines after "Relays:".

    The core lists the relays published in the contact's key there. An empty list means
    the key has none (older clients) or the format changed; callers then keep `r` as is."""
    if not encryption_info:
        return []
    parts = re.split(r"^Relays:\s*$", encryption_info, maxsplit=1, flags=re.MULTILINE)
    if len(parts) < 2:
        return []
    relays = []
    for line in parts[1].strip().splitlines():
        line = line.strip()
        if not line:
            break
        if "@" in line and " " not in line:
            relays.append(line)
    return relays


def sync_claim(bot, accid: int, claim: dict, contact_id: int) -> bool:
    """Update a claim's personal invite link from the contact's current data.
    Returns True if the stored link changed."""
    link = claim.get("invite_link") or ""
    meta = identicon.parse_invite_metadata(link)
    # Group, channel and ArcaneChat links describe a chat, not the contact
    if meta.get("target_type") != "contact" or not meta.get("fingerprint"):
        return False

    contact = bot.rpc.get_contact(accid, contact_id)
    if not contact or not getattr(contact, "is_key_contact", False):
        return False
    contact_addr = getattr(contact, "address", "")
    # Picked by key, not by address: core 2.66 no longer prints addresses next to fingerprints
    if dc_fingerprint.get_contact_fingerprint(bot.rpc, accid, contact_id) != meta["fingerprint"]:
        bot.logger.debug(f"Contact sync: @{claim.get('username')} link key differs from contact {contact_id}, skipped")
        return False
    relays = parse_relays(bot.rpc.get_contact_encryption_info(accid, contact_id))

    updated_link, changed = identicon.update_invite_link_contact_info(
        link,
        new_email=contact_addr,
        # auth_name is the name the contact set; display_name falls back to the address
        new_display_name=getattr(contact, "auth_name", "") or getattr(contact, "name", ""),
        new_relays=relays,
    )
    if not changed:
        return False
    database.update_username_invite_metadata(claim["username"], updated_link)
    identicon.clear_png_cache()
    bot.logger.info(f"Contact sync: updated invite link of @{claim['username']}")
    return True


def _single_contact_id(bot, accid: int, chat_id: int) -> Optional[int]:
    """The other member of a 1:1 chat, or None for groups and missing chats."""
    if not _is_private_chat(bot, accid, chat_id):
        return None
    chat = bot.rpc.get_full_chat_by_id(accid, chat_id)
    contact_ids = [c for c in (getattr(chat, "contact_ids", None) or []) if c > _LAST_SPECIAL_CONTACT_ID]
    return contact_ids[0] if len(contact_ids) == 1 else None


def sync_all_claims(bot, accid: int) -> int:
    """Re-check every personal link whose claim belongs to a 1:1 chat. Returns how many changed."""
    changed = 0
    for username, claim in database.get_all_usernames().items():
        chat_id = str(claim.get("claimed_by_chat_id") or "")
        # admin_<name> claims belong to groups/channels registered by the admin
        if not chat_id.isdigit():
            continue
        try:
            contact_id = _single_contact_id(bot, accid, int(chat_id))
            if contact_id and sync_claim(bot, accid, {**claim, "username": username}, contact_id):
                changed += 1
        except Exception as e:
            bot.logger.debug(f"Contact sync: @{username} (chat {chat_id}) skipped: {e}")
    return changed
