#!/usr/bin/env python3
import base64
import io
import os
import re
import sys
import threading
from urllib.parse import parse_qs, urlparse

from deltachat2 import events, MsgData
from deltabot_cli import BotCli
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn

import database

try:
    import qrcode
except ImportError:
    qrcode = None

VERSION = "1.0.0"

app = FastAPI(title="Delta Chat Username Service")
dc_cli = BotCli("usernamebot")

BASE_URL = os.getenv("BASE_URL", "https://d.gluek.info").rstrip("/")


# --- HELPER FUNCTIONS ---


def configure_bot_profile(bot, accid: int):
    """Configure bot display name, status text, and avatar icon from environment or default files."""
    try:
        bot_name = os.environ.get("DISPLAY_NAME", "Username Bot")
        bot.rpc.set_config(accid, "displayname", bot_name)
    except Exception as e:
        bot.logger.warning(f"Failed to set displayname: {e}")

    try:
        status_text = os.environ.get(
            "STATUS_TEXT",
            "Short custom invite link service for Delta Chat: https://d.gluek.info",
        )
        bot.rpc.set_config(accid, "selfstatus", status_text)
    except Exception as e:
        bot.logger.warning(f"Failed to set selfstatus: {e}")

    try:
        avatar_env = os.environ.get("AVATAR_PATH")
        avatar_paths = []
        base_dir = os.path.dirname(os.path.abspath(__file__))

        if avatar_env:
            if os.path.isabs(avatar_env):
                avatar_paths.append(avatar_env)
            else:
                avatar_paths.append(os.path.join(base_dir, avatar_env))
                avatar_paths.append(os.path.abspath(avatar_env))

        avatar_paths.extend(
            [
                os.path.join(base_dir, "icon.png"),
                os.path.join(base_dir, "icon.jpg"),
                os.path.join(base_dir, "icon.jpeg"),
            ]
        )

        for path in avatar_paths:
            if os.path.exists(path):
                bot.rpc.set_config(accid, "selfavatar", path)
                bot.logger.info(f"Avatar set from {path}")
                break
    except Exception as e:
        bot.logger.warning(f"Failed to set selfavatar: {e}")


def is_group_chat(chat) -> bool:
    """Check whether a chat object or dict represents a group chat."""
    if isinstance(chat, dict):
        t = chat.get("type")
        if t is not None:
            return t != 1
        ct = chat.get("chat_type")
        if ct is not None:
            return str(ct) != "Single"
        return False
    else:
        t = getattr(chat, "type", None)
        if t is not None:
            return t != 1
        ct = getattr(chat, "chat_type", "Single")
        return str(ct) != "Single"


def validate_username_format(username: str) -> tuple[bool, str]:
    """Validate username rules: length >= 5, alphanumeric with underscores/hyphens."""
    clean = username.strip()
    if len(clean) < 5:
        return (
            False,
            "Usernames shorter than 5 characters are not available for self-selection yet. Please use a name with 5 or more characters.",
        )
    if not re.match(r"^[a-zA-Z0-9_-]{5,32}$", clean):
        return (
            False,
            "Username can only contain letters, numbers, underscores, and hyphens (5 to 32 characters).",
        )
    return (True, "")


def validate_invite_link(url: str) -> bool:
    """
    Validate Delta Chat invite link:
    Must start with https://i.delta.chat/# and contain v=3, i, s, a, n query parameters.
    """
    if not url or not url.startswith("https://i.delta.chat/#"):
        return False

    fragment_part = url[len("https://i.delta.chat/#") :]
    if "?" in fragment_part:
        query_str = fragment_part.split("?", 1)[1]
    else:
        query_str = fragment_part

    params = parse_qs(query_str)
    required_params = ["i", "s", "a", "n"]

    for p in required_params:
        if p not in params or not params[p][0]:
            return False

    if "v" in params and params["v"][0] != "3":
        return False

    return True


def extract_invite_link(text: str) -> str:
    """Extract Delta Chat invite link from text if present."""
    if not text:
        return ""
    match = re.search(r"https://i\.delta\.chat/#\S+", text)
    return match.group(0) if match else ""


def _is_dc_admin(bot, accid: int, from_id: int) -> bool:
    """Check whether a contact is an authorized administrator."""
    admin_email = database.get_config("admin_dc_email")
    admin_fp = database.get_admin_fingerprint()

    if not admin_email and not admin_fp:
        return False

    try:
        contact = bot.rpc.get_contact(accid, from_id)
        if admin_email and contact.address and contact.address.lower() == admin_email.lower():
            return True
    except Exception:
        pass

    try:
        fp = _get_contact_fingerprint(bot, accid, from_id)
        if admin_fp and fp and admin_fp.upper() in [f.upper() for f in fp.split(",")]:
            return True
    except Exception:
        pass

    return False


def _get_contact_fingerprint(bot, accid: int, from_id: int, contact=None) -> str:
    """Retrieve contact's cryptographic fingerprint from Delta Chat RPC."""
    try:
        if hasattr(bot.rpc, "get_contact_encryption_info"):
            info = bot.rpc.get_contact_encryption_info(accid, from_id)
            if isinstance(info, dict):
                return info.get("fingerprint", "") or info.get("qr_code", "")
            return str(info)
        elif hasattr(bot.rpc, "get_contact"):
            c = contact or bot.rpc.get_contact(accid, from_id)
            return getattr(c, "fingerprint", "") or ""
    except Exception:
        pass
    return ""


def _dc_send_msg_with_stats(bot, accid: int, chat_id: int, msg_data: MsgData):
    """Send a message via Delta Chat RPC and update sent statistics."""
    bot.rpc.send_msg(accid, chat_id, msg_data)
    try:
        addr = bot.rpc.get_config(accid, "configured_addr") or bot.rpc.get_config(accid, "addr")
        if addr:
            database.increment_transport_sent(addr)
    except Exception:
        pass


def generate_qr_data_uri(text: str) -> str:
    """Generate a base64 Data URI for a QR code image."""
    if not qrcode or not text:
        return ""
    try:
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return ""


# --- FASTAPI WEB ENDPOINTS ---


@app.get("/", response_class=HTMLResponse)
def get_index_page():
    base_url = database.get_config("base_url") or BASE_URL
    bot_invite = database.get_config("bot_invite_url") or ""
    bot_addr = database.get_config("bot_addr") or ""

    qr_img = generate_qr_data_uri(bot_invite) if bot_invite else ""

    qr_html = ""
    if qr_img:
        qr_html = f'''
        <div class="qr-container">
            <img src="{qr_img}" alt="Delta Chat Bot QR Code" class="qr-code">
            <a href="{bot_invite}" class="btn-primary">💬 Start Chat in Delta Chat</a>
        </div>
        '''
    elif bot_invite:
        qr_html = f'''
        <div class="qr-container">
            <a href="{bot_invite}" class="btn-primary">💬 Start Chat in Delta Chat</a>
        </div>
        '''
    elif bot_addr:
        qr_html = f'''
        <div class="qr-container">
            <p>Send an email/message in Delta Chat to: <code>{bot_addr}</code></p>
        </div>
        '''

    total_usernames = database.get_username_count()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Delta Chat Username & Short Link Service</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.7);
            --border-color: rgba(255, 255, 255, 0.1);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-color: #38bdf8;
            --accent-hover: #0284c7;
            --code-bg: #020617;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            max-width: 800px;
            width: 100%;
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }}
        header {{ text-align: center; margin-bottom: 30px; }}
        h1 {{ font-size: 2rem; margin-bottom: 10px; color: var(--text-primary); }}
        p.subtitle {{ color: var(--text-secondary); font-size: 1.1rem; }}
        .badge {{
            display: inline-block;
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent-color);
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 0.875rem;
            margin-top: 10px;
        }}
        .qr-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            margin: 25px 0;
            padding: 20px;
            background: rgba(15, 23, 42, 0.4);
            border-radius: 16px;
            border: 1px solid var(--border-color);
        }}
        .qr-code {{
            width: 180px;
            height: 180px;
            border-radius: 12px;
            margin-bottom: 15px;
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.3);
        }}
        .btn-primary {{
            display: inline-block;
            background: var(--accent-color);
            color: #0f172a;
            font-weight: 600;
            padding: 12px 24px;
            border-radius: 12px;
            text-decoration: none;
            transition: all 0.2s ease;
        }}
        .btn-primary:hover {{
            background: var(--accent-hover);
            color: #ffffff;
            transform: translateY(-2px);
        }}
        .section-title {{
            font-size: 1.25rem;
            margin: 30px 0 15px 0;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
        }}
        .commands-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 12px;
        }}
        .command-card {{
            background: rgba(15, 23, 42, 0.5);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
        }}
        .command-name {{
            font-family: monospace;
            font-size: 1rem;
            color: var(--accent-color);
            margin-bottom: 4px;
        }}
        .command-desc {{
            color: var(--text-secondary);
            font-size: 0.95rem;
        }}
        footer {{
            text-align: center;
            margin-top: 35px;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }}
        footer a {{ color: var(--accent-color); text-decoration: none; }}
        code {{
            background: var(--code-bg);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: monospace;
            color: #e2e8f0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔗 Delta Chat Username Service</h1>
            <p class="subtitle">Short custom invite links for Delta Chat users and group chats</p>
            <span class="badge">Active Registered Usernames: {total_usernames}</span>
        </header>

        {qr_html}

        <h2 class="section-title">⚡️ How It Works</h2>
        <div class="commands-grid">
            <div class="command-card">
                <div class="command-name">/username</div>
                <div class="command-desc">Check your current registered username and short invite link.</div>
            </div>
            <div class="command-card">
                <div class="command-name">/username myname</div>
                <div class="command-desc">Claim or update a custom username (min 5 characters).
                <br>• <strong>Private Chat:</strong> Reserve your username, then send your Delta Chat invite link.
                <br>• <strong>Group Chat:</strong> Immediately binds <code>{base_url}/myname</code> to the group chat invite link.
                </div>
            </div>
            <div class="command-card">
                <div class="command-name">Send Invite Link</div>
                <div class="command-desc">Send your standard <code>https://i.delta.chat/#...</code> link to complete user registration.</div>
            </div>
        </div>

        <footer>
            Powered by <a href="https://delta.chat" target="_blank">Delta Chat</a> &bull; Short links format: <code>{base_url}/&lt;username&gt;</code>
        </footer>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html, status_code=200)


@app.get("/health")
def health_check():
    return {"status": "ok", "usernames_claimed": database.get_username_count()}


@app.get("/{username}")
def redirect_username(username: str):
    clean_username = username.strip().lower()
    claim = database.get_username_claim(clean_username)

    if claim and claim.get("invite_link"):
        return RedirectResponse(url=claim["invite_link"], status_code=307)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>404 - Username Not Found</title>
    <style>
        body {{
            background: #0f172a; color: #f8fafc;
            font-family: system-ui, sans-serif;
            display: flex; justify-content: center; align-items: center;
            height: 100vh; margin: 0; text-align: center;
        }}
        .card {{
            background: rgba(30, 41, 59, 0.8); padding: 40px; border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.1); max-width: 450px;
        }}
        h1 {{ font-size: 3rem; margin-bottom: 10px; color: #ef4444; }}
        p {{ color: #94a3b8; font-size: 1.1rem; margin-bottom: 20px; }}
        a {{ color: #38bdf8; text-decoration: none; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>404</h1>
        <p>The username <code>{clean_username}</code> is not registered or has no active invite link.</p>
        <a href="/">Go to Homepage</a>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html, status_code=404)


# --- DELTA CHAT BOT EVENT HANDLERS ---


def get_help_text(bot, accid: int, from_id: int) -> str:
    admin_email = database.get_config("admin_dc_email")
    base_url = database.get_config("base_url") or BASE_URL

    help_text = (
        f"🤖 **Delta Chat Username Bot v{VERSION}**\n\n"
        f"Claim short invite links for your profile or group chat! (`{base_url}/<username>`)\n\n"
        f"**Commands:**\n"
        f"/username — Check your current registered username\n"
        f"/username <name> — Claim or update custom username (min 5 chars)\n"
        f"/donate — Support bot development ❤️\n"
        f"/help — Show this help message\n\n"
    )

    is_actually_admin = _is_dc_admin(bot, accid, from_id)
    if not admin_email:
        help_text += f"**Initialisation Command:**\n" f"/initadmin — Claim bot ownership (if no admin is set)\n\n"
    elif is_actually_admin:
        admin_fp = database.get_admin_fingerprint()
        fp_suffix = f" ({admin_fp[-8:].upper()})" if admin_fp else ""
        help_text += f"👑 **Admin:** `{admin_email}`{fp_suffix}\n\n"
        help_text += (
            f"**Admin Commands:**\n"
            f"/stats — Show usage statistics\n"
            f"/url <url> — Set bot public short domain URL\n"
            f"/transports — Show configured mail relays & stats\n"
            f"/addtransport — Add backup mail relay\n"
            f"/rmtransport <addr> — Remove mail relay\n"
            f"/setprimary <addr> — Set primary mail relay\n"
            f"/resilient — Toggle resilient sending mode\n\n"
        )

    help_text += f"Run your own bot: https://github.com/mrgluek/deltachat_username"
    return help_text


@dc_cli.on(events.NewMessage(command="/help"))
def help_command(bot, accid, event):
    msg = event.msg
    help_text = get_help_text(bot, accid, msg.from_id)
    _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=help_text))


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
    admin_email = database.get_config("admin_dc_email")
    admin_fp = database.get_admin_fingerprint()

    if admin_email or admin_fp:
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text="❌ Admin is already set. Use `set_admin.py` on the server to change."),
        )
        return

    contact = bot.rpc.get_contact(accid, msg.from_id)
    email = contact.address
    database.set_config("admin_dc_email", email)

    fp = _get_contact_fingerprint(bot, accid, msg.from_id, contact=contact)
    if fp:
        first_fp = fp.split(",")[0]
        database.set_admin_fingerprint(first_fp)
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text=f"✅ You are now the admin!\n\nEmail: `{email}`\nFingerprint: `{first_fp[-8:]}`"),
        )
    else:
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(
                text=f"✅ You are now the admin!\n\nEmail: `{email}`\n⚠️ Fingerprint not available yet (will be used after key exchange)."
            ),
        )


@dc_cli.on(events.NewMessage(command="/username"))
def username_command(bot, accid, event):
    msg = event.msg
    base_url = database.get_config("base_url") or BASE_URL
    raw_payload = event.payload.strip()

    try:
        chat = bot.rpc.get_chat(accid, msg.chat_id)
    except Exception:
        chat = {}

    is_group = is_group_chat(chat)

    # --- SCENARIO A: CHECK CURRENT STATUS ---
    if not raw_payload:
        current_claim = database.get_username_by_chat(msg.chat_id)
        if current_claim:
            uname = current_claim["username"]
            if is_group:
                _dc_send_msg_with_stats(
                    bot,
                    accid,
                    msg.chat_id,
                    MsgData(
                        text=f"This group chat's username is: **{uname}**.\nInvite link: {base_url}/{uname}"
                    ),
                )
            else:
                _dc_send_msg_with_stats(
                    bot,
                    accid,
                    msg.chat_id,
                    MsgData(text=f"Your current username is: **{uname}**.\nYour invite link: {base_url}/{uname}"),
                )
        else:
            if is_group:
                _dc_send_msg_with_stats(
                    bot,
                    accid,
                    msg.chat_id,
                    MsgData(
                        text="This group chat doesn't have a registered username yet. Send `/username <name>` to claim one."
                    ),
                )
            else:
                _dc_send_msg_with_stats(
                    bot,
                    accid,
                    msg.chat_id,
                    MsgData(
                        text="You don't have a registered username yet. Send `/username <name>` to claim one."
                    ),
                )
        return

    # --- SCENARIO B: CLAIM OR UPDATE USERNAME ---
    target_username = raw_payload.lower()

    # Step 1: Validation
    valid, err_msg = validate_username_format(target_username)
    if not valid:
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"❌ {err_msg}"))
        return

    # Step 2: Check Availability
    existing_claim = database.get_username_claim(target_username)
    if existing_claim and str(existing_claim["claimed_by_chat_id"]) != str(msg.chat_id):
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text=f"Username `{target_username}` is already taken by another user. Please choose another."),
        )
        return

    # Step 3: Binding
    if is_group:
        # Group Chat: Automatically get bot's invite link for this group chat
        try:
            invite_url = bot.rpc.get_chat_invite_url(accid, msg.chat_id)
        except Exception as e:
            _dc_send_msg_with_stats(
                bot, accid, msg.chat_id, MsgData(text=f"❌ Could not generate group invite link: {e}")
            )
            return

        database.claim_username(target_username, invite_url, msg.chat_id)
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text=f"Done! This group chat's invite link is now:\n{base_url}/{target_username}"),
        )
    else:
        # Private Chat: Reserve username in pending state and ask user for invite link
        database.set_pending_username(msg.chat_id, target_username)
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(
                text=f"Username `{target_username}` is ready to link. Please send your Delta Chat invite link starting with:\nhttps://i.delta.chat/#...&v=3&i=...&s=...&a=...&n=..."
            ),
        )


@dc_cli.on(events.NewMessage)
def on_new_message(bot, accid, event):
    msg = event.msg
    if msg.is_info:
        return

    # Track received stats
    try:
        addr = bot.rpc.get_config(accid, "configured_addr") or bot.rpc.get_config(accid, "addr")
        if addr:
            database.increment_transport_received(addr)
    except Exception:
        pass

    text = (msg.text or "").strip()
    if not text or text.startswith("/"):
        return

    # --- SCENARIO C: PROCESS & VALIDATE INVITE LINK ---
    invite_url = extract_invite_link(text)
    if invite_url:
        pending_username = database.get_pending_username(msg.chat_id)
        if not pending_username:
            # Check if user already has a claimed username, allowing quick link update
            current_claim = database.get_username_by_chat(msg.chat_id)
            if current_claim:
                pending_username = current_claim["username"]

        if not pending_username:
            _dc_send_msg_with_stats(
                bot,
                accid,
                msg.chat_id,
                MsgData(text="You haven't requested a username claim yet. Send `/username <name>` first."),
            )
            return

        if not validate_invite_link(invite_url):
            _dc_send_msg_with_stats(
                bot,
                accid,
                msg.chat_id,
                MsgData(
                    text="❌ Invalid invite link format. Please make sure your link starts with `https://i.delta.chat/#` and includes required parameters (v=3, i, s, a, n)."
                ),
            )
            return

        # Save claimed username mapping
        database.claim_username(pending_username, invite_url, msg.chat_id)
        database.clear_pending_username(msg.chat_id)

        base_url = database.get_config("base_url") or BASE_URL
        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text=f"Done! Your invite link: {base_url}/{pending_username}"),
        )


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


@dc_cli.on(events.NewMessage(command="/stats"))
def stats_command(bot, accid, event):
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ This command is only for the administrator."))
        return

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
        bot.rpc.send_msg(accid, msg.chat_id, MsgData(text=f"❌ Failed to list transports: {e}"))
        return

    if not transports:
        bot.rpc.send_msg(accid, msg.chat_id, MsgData(text="No transports configured."))
        return

    stats_map = {s["addr"]: s for s in database.get_all_transport_stats()}
    lines = ["📡 **Configured Transports:**\n"]

    for t in transports:
        addr = t.get("addr", "") if isinstance(t, dict) else getattr(t, "addr", "")
        s = stats_map.get(addr, {})
        sent = s.get("msgs_sent", 0)
        recv = s.get("msgs_received", 0)
        lines.append(f"• `{addr}` — Sent: {sent}, Recv: {recv}")

    _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="\n".join(lines)))


# --- LIFECYCLE HOOKS ---


def run_fastapi(host: str = "0.0.0.0", port: int = 8080):
    uvicorn.run(app, host=host, port=port, log_level="info")


@dc_cli.on_init
def on_init(bot, _args):
    port = int(os.getenv("PORT", "8080"))
    web_thread = threading.Thread(target=run_fastapi, kwargs={"port": port}, daemon=True)
    web_thread.start()

    accounts = bot.rpc.get_all_account_ids()
    for accid in accounts:
        configure_bot_profile(bot, accid)


@dc_cli.on_start
def on_start(bot, _args):
    bot.logger.info(f"🚀 Delta Chat Username Bot v{VERSION} is now fully running. Waiting for events...")
    accounts = bot.rpc.get_all_account_ids()
    if accounts:
        accid = accounts[0]
        configure_bot_profile(bot, accid)

        admin_email = database.get_config("admin_dc_email")
        admin_fp = database.get_admin_fingerprint()
        if admin_email:
            fp_suffix = f" ({admin_fp[-8:].upper()})" if admin_fp else ""
            print(f"👑 Bot Administrator: {admin_email}{fp_suffix}")

        try:
            addr = bot.rpc.get_config(accid, "configured_addr") or bot.rpc.get_config(accid, "addr") or ""
            if addr:
                database.set_config("bot_addr", addr)
        except Exception:
            pass

        try:
            transports = bot.rpc.list_transports(accid)
            print("\n" + "=" * 50)
            print("📡 Configured Bot Transports (Relays):")
            for t in transports:
                t_addr = t.get("addr", "") if isinstance(t, dict) else getattr(t, "addr", "")
                print(f" - {t_addr}")
        except Exception:
            pass

        try:
            qrdata = bot.rpc.get_chat_securejoin_qr_code(accid, None)
            database.set_config("bot_invite_url", qrdata)
            print("\nTo add this bot, scan the QR code or copy the link below:\n")

            if qrcode:
                qr = qrcode.QRCode(version=1, box_size=1, border=2)
                qr.add_data(qrdata)
                qr.make(fit=True)
                f = io.StringIO()
                qr.print_ascii(out=f)
                print(f.getvalue())

            print(qrdata)
            print("\n" + "=" * 50 + "\n")
        except Exception as e:
            bot.logger.error(f"Failed to generate QR code: {e}")


# --- MAIN RUNNER ---


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("serve")
    dc_cli.start()
