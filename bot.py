#!/usr/bin/env python3
import base64
import io
import os
import re
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse
from typing import Optional

from deltachat2 import events, MsgData
from deltabot_cli import BotCli
from fastapi import FastAPI, Response, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
import uvicorn

import database

try:
    import qrcode
except ImportError:
    qrcode = None

VERSION = "1.4.1"

app = FastAPI(title="Delta Chat Username Service")
dc_cli = BotCli("usernamebot")

BASE_URL = os.getenv("BASE_URL", "https://d.gluek.info").rstrip("/")

# --- IN-MEMORY RATE LIMITER FOR GET /{username} ---
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds

_ip_request_history = {}
_rate_limit_lock = threading.Lock()


def get_client_ip(request: Request) -> str:
    """Extract client IP address, respecting reverse proxy headers."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def is_rate_limited(client_ip: str) -> bool:
    """Sliding-window IP rate limiter checking against RATE_LIMIT_REQUESTS within RATE_LIMIT_WINDOW."""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW
    with _rate_limit_lock:
        timestamps = _ip_request_history.get(client_ip, [])
        valid_timestamps = [t for t in timestamps if t > cutoff]

        if len(valid_timestamps) >= RATE_LIMIT_REQUESTS:
            _ip_request_history[client_ip] = valid_timestamps
            return True

        valid_timestamps.append(now)
        _ip_request_history[client_ip] = valid_timestamps
        return False


def clear_rate_limits():
    """Clear in-memory rate limit records (useful for testing)."""
    with _rate_limit_lock:
        _ip_request_history.clear()


# --- HELPER FUNCTIONS ---


def get_invite_base_url() -> str:
    """Get configured invite base URL (e.g. https://i.gluek.info/# or https://i.delta.chat/#)."""
    db_val = database.get_config("invite_base_url")
    if db_val:
        url = db_val.strip()
        if not url.endswith("#"):
            url = url.rstrip("/") + "/#"
        return url

    env_val = os.getenv("INVITE_BASE_URL", "https://i.delta.chat/#").strip()
    if not env_val.endswith("#"):
        env_val = env_val.rstrip("/") + "/#"
    return env_val


def rewrite_invite_link(url: str) -> str:
    """Rewrite any standard or existing invite link to use the currently configured invite base URL."""
    if not url:
        return ""
    target_base = get_invite_base_url()
    if "/#" in url:
        hash_idx = url.find("/#")
        return target_base + url[hash_idx + 2 :]
    return url


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


def is_group_chat(bot, accid: int, chat_id: int) -> bool:
    """
    Determine if a chat is a group chat using Delta Chat RPC basic info,
    full chat info, and chat contacts fallback. Matches standard implementation across all repository bots.
    """
    # 1. Primary check: get_basic_chat_info
    try:
        chat_info = bot.rpc.get_basic_chat_info(accid, chat_id)
        if chat_info:
            if isinstance(chat_info, dict):
                chat_type = chat_info.get("chat_type") or chat_info.get("chatType")
                type_val = chat_info.get("type")
            else:
                chat_type = getattr(chat_info, "chat_type", None) or getattr(chat_info, "chatType", None)
                type_val = getattr(chat_info, "type", None)

            if chat_type is not None:
                if str(chat_type).lower() in ("group", "verifiedgroup", "channel"):
                    return True
                if str(chat_type).lower() == "single":
                    return False

            if type_val is not None:
                if str(type_val) in ("100", "120", "130"):
                    return True
                if str(type_val) in ("1", "single"):
                    return False
    except Exception as e:
        bot.logger.debug(f"get_basic_chat_info failed for chat {chat_id}: {e}")

    # 2. Secondary check: get_full_chat_by_id
    try:
        chat_info = bot.rpc.get_full_chat_by_id(accid, chat_id)
        if chat_info:
            if isinstance(chat_info, dict):
                chat_type = chat_info.get("chat_type") or chat_info.get("chatType")
                type_val = chat_info.get("type")
            else:
                chat_type = getattr(chat_info, "chat_type", None) or getattr(chat_info, "chatType", None)
                type_val = getattr(chat_info, "type", None)

            if chat_type is not None:
                if str(chat_type).lower() in ("group", "verifiedgroup", "channel"):
                    return True
                if str(chat_type).lower() == "single":
                    return False

            if type_val is not None:
                if str(type_val) in ("100", "120", "130"):
                    return True
                if str(type_val) in ("1", "single"):
                    return False
    except Exception as e:
        bot.logger.debug(f"get_full_chat_by_id failed for chat {chat_id}: {e}")

    # 3. Tertiary fallback: get_chat_contacts length check
    try:
        contacts = bot.rpc.get_chat_contacts(accid, chat_id)
        if isinstance(contacts, list):
            if len(contacts) > 1:
                return True
            if len(contacts) == 1:
                return False
    except Exception as e:
        bot.logger.debug(f"get_chat_contacts failed for chat {chat_id}: {e}")

    return False


def validate_username_format(username: str) -> tuple[bool, str]:
    """Validate username rules: length >= 3, alphanumeric with underscores/hyphens."""
    clean = username.strip()
    if len(clean) < 3:
        return (
            False,
            "Usernames shorter than 3 characters are not available for self-selection yet. Please use a name with 3 or more characters.",
        )
    if not re.match(r"^[a-zA-Z0-9_-]{3,32}$", clean):
        return (
            False,
            "Username can only contain letters, numbers, underscores, and hyphens (3 to 32 characters).",
        )
    return (True, "")


def validate_invite_link(url: str) -> bool:
    """
    Validate Delta Chat invite link:
    Must contain /# and required query parameters v=3, i, s, a, n.
    Supports official and mirror domains (e.g. i.delta.chat, i.gluek.info).
    """
    if not url or "/#" not in url:
        return False

    hash_idx = url.find("/#")
    fragment_part = url[hash_idx + 2 :]
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
    """Extract Delta Chat invite link from text if present (supports mirror domains)."""
    if not text:
        return ""
    match = re.search(r"https?://\S+?/#\S+", text)
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
            # Auto-upgrade: if fingerprint became available after initial email setup, save it now!
            if not admin_fp:
                fp = _get_contact_fingerprint(bot, accid, from_id, contact=contact)
                if fp:
                    first_fp = fp.split(",")[0].strip().upper()
                    database.set_admin_fingerprint(first_fp)
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


def _get_contact_fingerprint(bot, accid: int, contact_id: int, contact=None) -> Optional[str]:
    """Retrieve contact's cryptographic PGP fingerprint from Delta Chat RPC, filtering out bot self-fingerprints."""
    self_fps = set()
    try:
        bot_addrs = []
        bot_addr = bot.rpc.get_config(accid, "addr")
        if bot_addr:
            bot_addrs.append(bot_addr.lower().strip())

        try:
            transports = bot.rpc.list_transports(accid)
            for t in transports:
                t_addr = t.get("addr", "") if isinstance(t, dict) else getattr(t, "addr", "")
                if t_addr:
                    bot_addrs.append(t_addr.lower().strip())
        except Exception:
            pass

        if bot_addrs:
            for args in [(accid, contact_id), (contact_id,)]:
                try:
                    enc_info_self = bot.rpc.get_contact_encryption_info(*args)
                    if enc_info_self:
                        blocks = re.split(r"\n\s*\n", enc_info_self.strip())
                        for block in blocks:
                            if any(a in block.lower() for a in bot_addrs):
                                matches = re.findall(
                                    r"[0-9a-fA-F]{32,64}", "".join(block.split()).replace(":", "")
                                )
                                self_fps.update(m.upper() for m in matches)
                        break
                except Exception:
                    continue
    except Exception as e:
        bot.logger.error(f"Error detecting self-fingerprint: {e}")

    # 1. Try directly from contact object if available
    if contact:
        get_val = getattr(contact, "get", lambda k: getattr(contact, k, None))
        for attr in ["fingerprint", "key_fingerprint", "public_key"]:
            val = get_val(attr)
            if val:
                matches = re.findall(r"[0-9a-fA-F]{32,64}", str(val).replace(" ", "").replace(":", ""))
                valid_matches = [m.upper() for m in matches if m.upper() not in self_fps]
                if valid_matches:
                    return ",".join(valid_matches)

    # 2. Try get_contact_config(accid, contact_id, "fp")
    try:
        fp = bot.rpc.get_contact_config(accid, contact_id, "fp")
        if fp:
            clean_fp = fp.upper().replace(" ", "").replace(":", "")
            if clean_fp not in self_fps and re.match(r"^[0-9A-F]{32,64}$", clean_fp):
                return clean_fp
    except Exception:
        pass

    # 3. Try get_contact_encryption_info
    for args in [(accid, contact_id), (contact_id,)]:
        try:
            enc_info = bot.rpc.get_contact_encryption_info(*args)
            if enc_info:
                cleaned_info = "".join(enc_info.split()).replace(":", "")
                matches = re.findall(r"[0-9a-fA-F]{32,64}", cleaned_info)
                valid_matches = [m.upper() for m in matches if m.upper() not in self_fps]
                if valid_matches:
                    return ",".join(valid_matches)
        except Exception as e:
            bot.logger.debug(f"get_contact_encryption_info{args} failed: {e}")
            continue

    return None


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


@app.get("/favicon.ico")
def get_favicon():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    fav_path = os.path.join(base_dir, "favicon.ico")
    if os.path.exists(fav_path):
        return FileResponse(fav_path, media_type="image/x-icon")
    icon_path = os.path.join(base_dir, "icon.png")
    if os.path.exists(icon_path):
        return FileResponse(icon_path, media_type="image/png")
    return Response(status_code=404)


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
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
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
                <div class="command-name">/username [name]</div>
                <div class="command-desc">View your registered username, or look up direct Delta Chat invite link for any username.</div>
            </div>
            <div class="command-card">
                <div class="command-name">/link myname [link]</div>
                <div class="command-desc">Claim or update custom username (min 3 characters).
                <br>• <strong>Private Chat:</strong> Send <code>/link myname https://i.delta.chat/#...</code>
                <br>• <strong>Group Chat:</strong> Send <code>/link myname</code> to auto-generate group invite link.
                </div>
            </div>
            <div class="command-card">
                <div class="command-name">/unlink</div>
                <div class="command-desc">Unlink the current registered username from this chat.</div>
            </div>
        </div>

        <footer>
            Powered by <a href="https://github.com/mrgluek/deltachat_username" target="_blank">Delta Chat Username Bot</a> (<a href="https://git.gluek.info/gluek/deltachat_username" target="_blank">Mirror</a>)
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
def redirect_username(username: str, request: Request):
    clean_username = username.strip().lower()

    # Rate Limit Check (10 requests per minute per IP)
    client_ip = get_client_ip(request)
    if is_rate_limited(client_ip):
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>429 - Too Many Requests</title>
    <style>
        body {
            background: #0f172a; color: #f8fafc;
            font-family: system-ui, sans-serif;
            display: flex; justify-content: center; align-items: center;
            height: 100vh; margin: 0; text-align: center;
        }
        .card {
            background: rgba(30, 41, 59, 0.8); padding: 40px; border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.1); max-width: 450px;
        }
        h1 { font-size: 3rem; margin-bottom: 10px; color: #f59e0b; }
        p { color: #94a3b8; font-size: 1.1rem; margin-bottom: 20px; }
        a { color: #38bdf8; text-decoration: none; font-weight: 600; }
    </style>
</head>
<body>
    <div class="card">
        <h1>429</h1>
        <p>Too many requests. Please wait a minute before trying again.</p>
        <a href="/">Go to Homepage</a>
    </div>
</body>
</html>
"""
        return HTMLResponse(content=html, status_code=429, headers={"Retry-After": "60"})

    claim = database.get_username_claim(clean_username)

    if claim and claim.get("invite_link"):
        target_link = rewrite_invite_link(claim["invite_link"])
        return RedirectResponse(url=target_link, status_code=307)

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
        database.set_config("admin_dc_email", sender_email)
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
        raw_link = claim.get("invite_link", "")
        if "/#" in raw_link:
            canonical_link = "https://i.delta.chat/#" + raw_link[raw_link.find("/#") + 2 :]
        else:
            canonical_link = raw_link

        _dc_send_msg_with_stats(
            bot,
            accid,
            msg.chat_id,
            MsgData(text=f"Username **{target_username}**:\n{canonical_link}"),
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

    prev_claim = database.get_username_by_chat(msg.chat_id)
    old_username = prev_claim["username"] if (prev_claim and prev_claim["username"] != target_username) else None

    claim_owner = f"admin_linked_{target_username}" if (is_admin and existing_claim and str(existing_claim["claimed_by_chat_id"]) != str(msg.chat_id)) else msg.chat_id

    database.claim_username(target_username, invite_url, claim_owner)

    reply_text = f"Done! Your invite link is now:\n{base_url}/{target_username}"
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

    try:
        addr = bot.rpc.get_config(accid, "configured_addr") or bot.rpc.get_config(accid, "addr")
        if addr:
            database.increment_transport_received(addr)
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


@dc_cli.on(events.NewMessage(command="/addtransport"))
def addtransport_command(bot, accid, event):
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ This command is only for the administrator."))
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
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"❌ Failed to add transport: {e}"))


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
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"❌ Failed to remove transport: {e}"))


@dc_cli.on(events.NewMessage(command="/setprimary"))
def setprimary_command(bot, accid, event):
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ This command is only for the administrator."))
        return

    addr = event.payload.strip()
    if not addr:
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="Usage: /setprimary user@example.com"))
        return

    try:
        transports = bot.rpc.list_transports(accid)
        transport_addrs = [t.get("addr", "") if isinstance(t, dict) else getattr(t, "addr", "") for t in transports]
        if addr not in transport_addrs:
            _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"❌ Transport `{addr}` not found."))
            return

        bot.rpc.set_config(accid, "configured_addr", addr)
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"✅ Primary SMTP transport switched to `{addr}`."))
    except Exception as e:
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"❌ Failed to set primary transport: {e}"))


@dc_cli.on(events.NewMessage(command="/resilient"))
def resilient_command(bot, accid, event):
    msg = event.msg
    if not _is_dc_admin(bot, accid, msg.from_id):
        _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text="❌ This command is only for the administrator."))
        return
    resilient = database.get_config("resilient_mode") == "1"
    new_state = "0" if resilient else "1"
    database.set_config("resilient_mode", new_state)
    status_str = "ENABLED (using all available relays)" if new_state == "1" else "DISABLED (using primary relay)"
    _dc_send_msg_with_stats(bot, accid, msg.chat_id, MsgData(text=f"✅ Resilient sending mode is now: **{status_str}**"))


# --- LIFECYCLE HOOKS ---


def run_fastapi(host: str = "0.0.0.0", port: int = 8080):
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


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
            qrdata = rewrite_invite_link(qrdata)
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
