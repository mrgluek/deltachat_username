import os
import threading
import time

from deltachat2 import events, MsgData
from deltabot_cli import BotCli

import database
import transports_view
import identicon
from dc_helpers import (
    is_group_chat,
    _is_private_chat,
    _is_dc_admin,
    _get_contact_fingerprint,
    _dc_send_msg_with_stats,
)
from formatting import (
    BASE_URL,
    format_username_card_text,
    get_invite_base_url,
    rewrite_invite_link,
    validate_username_format,
    validate_invite_link,
)

VERSION = "1.12.0"

dc_cli = BotCli("usernamebot")

# --- DELTA CHAT BOT EVENT HANDLERS ---


def get_help_text(bot, accid: int, from_id: int) -> str:
    admin_email = database.get_config("admin_dc_email")
    base_url = database.get_config("base_url") or BASE_URL

    help_text = (
        f"🤖 **Delta Chat Username Bot v{VERSION}**\n\n"
        f"Claim short invite links for your profile or group chat! (`{base_url}/<username>`)\n\n"
        f"**Commands:**\n"
        f"/username — Check your current registered username\n"
        f"/username <name> — Look up direct Delta Chat invite link for any registered username\n"
        f"/link <name> <link> — Bind username to invite link (Group: `/link <name>`)\n"
        f"/unlink — Unlink registered username from this chat\n"
        f"/donate — Support bot development ❤️\n"
        f"/help — Show this help message\n\n"
    )

    is_actually_admin = _is_dc_admin(bot, accid, from_id)
    if not admin_email or not database.get_admin_fingerprint():
        help_text += f"**Initialisation Command:**\n" f"/initadmin — Claim bot ownership or link admin fingerprint\n\n"

    if is_actually_admin:
        admin_fp = database.get_admin_fingerprint()
        fp_suffix = f" ({admin_fp[-8:].upper()})" if admin_fp else ""
        help_text += f"👑 **Admin:** `{admin_email}`{fp_suffix}\n\n"
        help_text += (
            f"**Admin Commands:**\n"
            f"/unlink <name> — Force unlink a registered username\n"
            f"/link <name> <url> — Admin custom link binding\n"
            f"/inviteurl <url> — Set invite base domain (e.g. https://i.gluek.info/#)\n"
            f"/url <url> — Set bot public short domain URL\n"
            f"/stats — Show usage statistics\n"
            f"/transports — Show configured mail relays & stats\n"
            f"/addtransport — Add backup mail relay\n"
            f"/rmtransport <addr> — Remove mail relay\n\n"
        )

    help_text += f"Run your own bot: https://github.com/mrgluek/deltachat_username"
    return help_text


HELP_PRIVATE_NOTE = "\n\n💬 Sent privately because you asked in a group. Use /help@username there to show it to everyone."


def _get_help_chat_id(bot, accid, msg):
    """Plain /help in a group is answered privately to the sender so several bots
    don't flood the group; /help@<bot> is still answered in the group itself."""
    cmd = msg.text.split(maxsplit=1)[0] if msg.text else ""
    if "@" in cmd or _is_private_chat(bot, accid, msg.chat_id):
        return msg.chat_id
    return bot.rpc.create_chat_by_contact_id(accid, msg.from_id)


@dc_cli.on(events.NewMessage(command="/help"))
def help_command(bot, accid, event):
    msg = event.msg
    help_text = get_help_text(bot, accid, msg.from_id)
    chat_id = _get_help_chat_id(bot, accid, msg)
    if chat_id != msg.chat_id:
        help_text += HELP_PRIVATE_NOTE
    _dc_send_msg_with_stats(bot, accid, chat_id, MsgData(text=help_text))


@dc_cli.on(events.NewMessage(command="/donate"))
def donate_command(bot, accid, event):
    msg = event.msg
    _dc_send_msg_with_stats(
        bot,
        accid,
        msg.chat_id,
        MsgData(
            text="❤️ Support Bot Development\n\n"
            "If you find this bot useful, you can support its development:\n\n"
            "☕️ Ko-fi: https://ko-fi.com/gluek (🌍 world cards, paypal)\n"
            "🚀 Tribute: https://web.tribute.tg/d/IWb (🇷🇺 russian cards, SBP)\n\n"
            "Thank you! 🙏"
        ),
    )


@dc_cli.on(events.NewMessage(command="/initadmin"))
def initadmin_command(bot, accid, event):
    msg = event.msg
    if not _is_private_chat(bot, accid, msg.chat_id):
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text="❌ For security reasons, /initadmin can only be used in a private 1:1 chat with the bot."),
        )
        return

    admin_email = database.get_admin_email()
    admin_fp = database.get_admin_fingerprint()

    if admin_email and admin_fp:
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text="❌ Admin is already set. Use `set_admin.py` on the server to change."),
        )
        return

    contact = bot.rpc.get_contact(accid, msg.from_id)
    sender_email = (contact.address or "").strip()

    if admin_email:
        if sender_email.lower() != admin_email.lower():
            _dc_send_msg_with_stats(
                bot,
                accid,
                msg.chat_id,
                MsgData(
                    text=f"❌ Admin email is configured as `{admin_email}`. Only messages sent from this email address can link the admin identity."
                ),
            )
            return
    else:
        database.set_admin_email(sender_email)
        admin_email = sender_email

    fp = _get_contact_fingerprint(bot, accid, msg.from_id, contact=contact)
    if fp:
        first_fp = fp.split(",")[0].strip().upper()
        database.set_admin_fingerprint(first_fp)
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(
                text=f"✅ You are now confirmed as admin!\n\nEmail: `{admin_email}`\nFingerprint: `{first_fp[-8:]}`"
            ),
        )
    else:
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(
                text=f"✅ Email confirmed as admin: `{admin_email}`\n⚠️ Fingerprint not available yet (will be linked after key exchange)."
            ),
        )


def _send_username_card_reply(
    bot, accid: int, chat_id: int, username: str, invite_link: str, updated_at: str, base_url: str
):
    """Send visual WebP card image attachment accompanied by direct i.delta.chat invite link."""
    metadata = identicon.parse_invite_metadata(invite_link, updated_at)
    raw_link = metadata.get("canonical_link") or invite_link
    if "/#" in raw_link:
        canonical_link = "https://i.delta.chat/#" + raw_link[raw_link.find("/#") + 2 :]
    else:
        canonical_link = raw_link

    caption = canonical_link
    card_file = identicon.get_or_create_card_webp_path(username, metadata, base_url=base_url)

    if card_file and os.path.exists(card_file):
        _dc_send_msg_with_stats(
            bot,
            accid,
            chat_id,
            MsgData(text=caption, file=card_file),
        )
    else:
        card_text = format_username_card_text(username, invite_link, updated_at, base_url)
        _dc_send_msg_with_stats(bot, accid, chat_id, MsgData(text=card_text))


@dc_cli.on(events.NewMessage(command="/username"))
def username_command(bot, accid, event):
    msg = event.msg
    base_url = database.get_config("base_url") or BASE_URL
    raw_payload = event.payload.strip()

    is_group = is_group_chat(bot, accid, msg.chat_id)

    # --- SCENARIO A: CHECK CURRENT CHAT'S USERNAME ---
    if not raw_payload:
        current_claim = database.get_username_by_chat(msg.chat_id)
        if current_claim:
            uname = current_claim["username"]
            _send_username_card_reply(
                bot,
                accid,
                msg.chat_id,
                uname,
                current_claim["invite_link"],
                current_claim.get("updated_at", ""),
                base_url,
            )
        else:
            if is_group:
                _dc_send_msg_with_stats(
                    bot,
                    accid,
                    msg.chat_id,
                    MsgData(
                        text="This group chat doesn't have a registered username yet. Send `/link <username>` to claim one."
                    ),
                )
            else:
                _dc_send_msg_with_stats(
                    bot,
                    accid,
                    msg.chat_id,
                    MsgData(
                        text="You don't have a registered username yet. Send `/link <username> <invite_link>` to claim one."
                    ),
                )
        return

    # --- SCENARIO B: LOOKUP ANY USERNAME DIRECT INVITE LINK ---
    target_username = raw_payload.lower()
    claim = database.get_username_claim(target_username)
    if claim:
        _send_username_card_reply(
            bot,
            accid,
            msg.chat_id,
            target_username,
            claim["invite_link"],
            claim.get("updated_at", ""),
            base_url,
        )
    else:
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text=f"Username `{target_username}` is not registered."),
        )


@dc_cli.on(events.NewMessage(command="/link"))
def link_command(bot, accid, event):
    msg = event.msg
    base_url = database.get_config("base_url") or BASE_URL
    raw_payload = event.payload.strip()
    is_group = is_group_chat(bot, accid, msg.chat_id)
    is_admin = _is_dc_admin(bot, accid, msg.from_id)

    parts = raw_payload.split(None, 1) if raw_payload else []

    # --- SCENARIO A: GROUP CHAT LINKING ---
    if is_group:
        if not parts:
            _dc_send_msg_with_stats(
                bot,
                accid,
                msg.chat_id,
                MsgData(text="Usage in group chat:\n/link <username>"),
            )
            return

        target_username = parts[0].lower()
        provided_link = parts[1].strip() if len(parts) > 1 else None

        valid, err_msg = validate_username_format(target_username)
        if not valid:
            _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"❌ {err_msg}"))
            return

        existing_claim = database.get_username_claim(target_username)
        if existing_claim and str(existing_claim["claimed_by_chat_id"]) != str(msg.chat_id) and not is_admin:
            _dc_send_msg_with_stats(
                bot,
                accid,
                msg.chat_id,
                MsgData(text=f"Username `{target_username}` is already taken by another user/chat. Please choose another."),
            )
            return

        if provided_link:
            if not validate_invite_link(provided_link):
                _dc_send_msg_with_stats(
                    bot,
                    accid,
                    msg.chat_id,
                    MsgData(text="❌ Invalid invite link format. Must contain `/#` and required query parameters."),
                )
                return
            invite_url = rewrite_invite_link(provided_link)
        else:
            try:
                invite_url = bot.rpc.get_chat_securejoin_qr_code(accid, msg.chat_id)
                invite_url = rewrite_invite_link(invite_url)
            except Exception as e:
                _dc_send_msg_with_stats(
                    bot, accid, msg.chat_id, MsgData(text=f"❌ Could not generate group invite link: {e}")
                )
                return

        prev_claim = database.get_username_by_chat(msg.chat_id)
        old_username = prev_claim["username"] if (prev_claim and prev_claim["username"] != target_username) else None

        database.claim_username(target_username, invite_url, msg.chat_id)
        identicon.clear_png_cache()

        reply_text = f"Done! This group chat's invite link is now:\n{base_url}/{target_username}"
        if old_username:
            reply_text += f"\n\n(Previous username `{old_username}` was unlinked)"

        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=reply_text))
        return

    # --- SCENARIO B: PRIVATE CHAT (USER OR ADMIN LINKING) ---
    if len(parts) < 2:
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(
                text="Usage:\n"
                "/link <username> <invite_link>\n"
                "Example: /link myname https://i.delta.chat/#..."
            ),
        )
        return

    target_username, invite_url = parts[0].lower(), parts[1].strip()

    valid, err_msg = validate_username_format(target_username)
    if not valid:
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"❌ {err_msg}"))
        return

    if not validate_invite_link(invite_url):
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(
                text="❌ Invalid invite link format. Must contain `/#` and required query parameters."
            ),
        )
        return

    invite_url = rewrite_invite_link(invite_url)

    existing_claim = database.get_username_claim(target_username)
    if existing_claim and str(existing_claim["claimed_by_chat_id"]) != str(msg.chat_id) and not is_admin:
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text=f"Username `{target_username}` is already taken by another user. Please choose another."),
        )
        return

    meta = identicon.parse_invite_metadata(invite_url)
    is_channel_or_group = meta.get("target_type") in ("channel", "group")
    prev_claim = database.get_username_by_chat(msg.chat_id)

    # For Admin: allow registering multiple custom usernames (channels, groups, aliases)
    # without destroying personal profile claims or channel claims
    if is_admin:
        if is_channel_or_group:
            claim_owner = f"admin_{target_username}"
            old_username = None
        elif prev_claim and prev_claim["username"] != target_username:
            # If the current chat's claim was a channel/group, preserve it under admin_ namespace
            prev_meta = identicon.parse_invite_metadata(prev_claim["invite_link"])
            if prev_meta.get("target_type") in ("channel", "group"):
                database.claim_username(
                    prev_claim["username"],
                    prev_claim["invite_link"],
                    f"admin_{prev_claim['username']}",
                )
            claim_owner = msg.chat_id
            old_username = None
        else:
            claim_owner = msg.chat_id
            old_username = None
    else:
        claim_owner = msg.chat_id
        old_username = prev_claim["username"] if (prev_claim and prev_claim["username"] != target_username) else None

    database.claim_username(target_username, invite_url, claim_owner)
    identicon.clear_png_cache()

    reply_text = f"Done! The invite link for **{target_username}** is now:\n{base_url}/{target_username}"
    if old_username:
        reply_text += f"\n\n(Previous username `{old_username}` was unlinked)"

    _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=reply_text))


@dc_cli.on(events.NewMessage(command="/unlink"))
def unlink_command(bot, accid, event):
    msg = event.msg
    payload = event.payload.strip()

    # Case 1: /unlink <username> (Admin forced unlinking)
    if payload:
        if not _is_dc_admin(bot, accid, msg.from_id):
            _dc_send_msg_with_stats(
                bot,
                accid,
                msg.chat_id,
                MsgData(text="❌ Admin privileges required to unlink other users' usernames."),
            )
            return

        target_username = payload.lower()
        unlinked = database.unlink_username(target_username)
        if unlinked:
            identicon.clear_png_cache()
            _dc_send_msg_with_stats(
                bot,
                accid,
                msg.chat_id,
                MsgData(text=f"✅ Username `{target_username}` has been unlinked."),
            )
        else:
            _dc_send_msg_with_stats(
                bot,
                accid,
                msg.chat_id,
                MsgData(text=f"❌ Username `{target_username}` not found."),
            )
        return

    # Case 2: /unlink without parameters (Unlink current chat's username)
    unbound = database.unlink_chat_username(msg.chat_id)
    if unbound:
        identicon.clear_png_cache()
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text=f"✅ Username `{unbound}` has been unlinked from this chat."),
        )
    else:
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text="You don't have a registered username linked to this chat."),
        )


@dc_cli.on(events.NewMessage)
def on_new_message(bot, accid, event):
    msg = event.msg
    if msg.is_info:
        return

    # Automatically sync sender's active email relay & display name if they own a username
    try:
        chat_id = str(msg.chat_id)
        claim = database.get_username_by_chat(chat_id)
        if claim and claim.get("invite_link") and msg.from_id:
            contact = bot.rpc.get_contact(accid, msg.from_id)
            if contact:
                user_email = getattr(contact, "addr", "")
                user_name = getattr(contact, "display_name", "") or getattr(contact, "name", "")
                updated_link, changed = identicon.update_invite_link_contact_info(
                    claim["invite_link"],
                    new_email=user_email,
                    new_display_name=user_name,
                )
                if changed:
                    database.update_username_invite_metadata(claim["username"], updated_link)
                    identicon.clear_png_cache()
    except Exception:
        pass

    _is_dc_admin(bot, accid, msg.from_id)


@dc_cli.on(events.NewMessage(command="/url"))
def url_command(bot, accid, event):
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ This command is only for the administrator."))
        return

    payload = event.payload.strip()
    if not payload:
        current_url = database.get_config("base_url") or BASE_URL
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"🔗 Base domain URL: `{current_url}`"))
        return

    url = payload.rstrip("/")
    if not url.startswith("http://") and not url.startswith("https://"):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ URL must start with http:// or https://"))
        return

    database.set_config("base_url", url)
    _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"✅ Base domain URL set to: `{url}`"))


@dc_cli.on(events.NewMessage(command="/inviteurl"))
def inviteurl_command(bot, accid, event):
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ This command is only for the administrator."))
        return

    payload = event.payload.strip()
    if not payload:
        current_url = get_invite_base_url()
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"🔗 Invite base URL: `{current_url}`"))
        return

    url = payload.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ URL must start with http:// or https://"))
        return

    if not url.endswith("#"):
        url = url.rstrip("/") + "/#"

    database.set_config("invite_base_url", url)
    _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"✅ Invite base URL set to: `{url}`"))


@dc_cli.on(events.NewMessage(command="/stats"))
def stats_command(bot, accid, event):
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ This command is only for the administrator."))
        return

    database.flush_transport_stats()
    count = database.get_username_count()
    stats = (
        f"📊 **Bot Statistics**\n\n"
        f"• Total Registered Usernames: `{count}`\n"
        f"• Database Path: `{database.DB_PATH}`\n"
    )
    _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=stats))


@dc_cli.on(events.NewMessage(command="/transports"))
def transports_command(bot, accid, event):
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ This command is only for the administrator."))
        return

    try:
        transports = bot.rpc.list_transports(accid)
    except Exception as e:
        bot.logger.error(f"Failed to list transports: {e}")
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ Failed to list transports."))
        return

    if not transports:
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="No transports configured."))
        return

    # Which relay the core really sends through, its send queue, and per-relay
    # incoming status and storage (see transports_view.py).
    reply = transports_view.build_transports_report(bot.rpc, accid, transports)
    _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=reply))


@dc_cli.on(events.NewMessage(command="/addtransport"))
def addtransport_command(bot, accid, event):
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ This command is only for the administrator."))
        return

    if not _is_private_chat(bot, accid, msg.chat_id):
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text="❌ For security reasons, /addtransport can only be used in a private 1:1 chat with the bot."),
        )
        return

    payload = event.payload.strip()
    if not payload:
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(
                text="Usage:\n"
                "/addtransport DCACCOUNT:server.example\n"
                "/addtransport user@example.com password123"
            ),
        )
        return

    try:
        if payload.startswith("DCACCOUNT:"):
            bot.rpc.add_transport_from_qr(accid, payload)
            _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="✅ Backup transport added via chatmail URI."))
        else:
            parts = payload.split(None, 1)
            if len(parts) < 2:
                _dc_send_msg_with_stats(
                    bot,
                    accid,
                    msg.chat_id,
                    MsgData(
                        text="❌ For email accounts, provide both address and password:\n"
                        "/addtransport user@example.com password123"
                    ),
                )
                return
            addr, password = parts[0], parts[1]
            bot.rpc.add_or_update_transport(accid, {"addr": addr, "password": password})
            _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"✅ Backup transport `{addr}` added."))
    except Exception as e:
        bot.logger.error(f"Failed to add transport: {e}")
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ Failed to add transport."))


@dc_cli.on(events.NewMessage(command="/rmtransport"))
def rmtransport_command(bot, accid, event):
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ This command is only for the administrator."))
        return

    addr = event.payload.strip()
    if not addr:
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="Usage: /rmtransport user@example.com"))
        return

    try:
        transports = bot.rpc.list_transports(accid)
        transport_addrs = [t.get("addr", "") if isinstance(t, dict) else getattr(t, "addr", "") for t in transports]
        if len(transport_addrs) <= 1:
            _dc_send_msg_with_stats(
                bot, accid, msg.chat_id, MsgData(text="❌ Cannot remove the last transport. Add another one first.")
            )
            return
        if addr not in transport_addrs:
            _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"❌ Transport `{addr}` not found."))
            return

        bot.rpc.delete_transport(accid, addr)
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"✅ Transport `{addr}` removed."))
    except Exception as e:
        bot.logger.error(f"Failed to remove transport: {e}")
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ Failed to remove transport."))


RELAY_SELECTION_NOTE = (
    "Since core 2.61 the core picks the sending relay itself: it tries the newest relay first "
    "and falls back to the next one if a relay is unreachable. "
    "Use /addtransport and /rmtransport to control relays."
)


@dc_cli.on(events.NewMessage(command="/setprimary"))
def setprimary_command(bot, accid, event):
    """Deprecated: the core no longer uses configured_addr to pick the SMTP relay."""
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ Only the bot administrator can use /setprimary."))
        return
    _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"⚠️ /setprimary is deprecated and disabled. {RELAY_SELECTION_NOTE}"))

@dc_cli.on(events.NewMessage(command="/resilient"))
def resilient_command(bot, accid, event):
    """Deprecated: relay failover is handled by the core."""
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ Only the bot administrator can use /resilient."))
        return
    _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"⚠️ /resilient is deprecated and disabled. {RELAY_SELECTION_NOTE}"))

