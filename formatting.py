import base64
import io
import os
import re
from urllib.parse import parse_qs

from fastapi import Request

try:
    import qrcode
except ImportError:
    qrcode = None

import database
import identicon

BASE_URL = os.getenv("BASE_URL", "https://deltachat.id").rstrip("/")


def get_request_base_url(request: Request) -> str:
    """Extract public base URL dynamically from incoming request headers or fallback to configured BASE_URL."""
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme or "https")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host:
        return f"{forwarded_proto}://{host}".rstrip("/")
    return database.get_config("base_url") or BASE_URL

def format_username_card_text(username: str, invite_link: str, updated_at_iso: str, base_url: str) -> str:
    """Generate rich verification card text with identicon, emoji badge, and formatted fingerprint."""
    metadata = identicon.parse_invite_metadata(invite_link, updated_at_iso)
    raw_link = metadata["canonical_link"]
    if "/#" in raw_link:
        canonical_link = "https://i.delta.chat/#" + raw_link[raw_link.find("/#") + 2 :]
    else:
        canonical_link = raw_link

    lines = [f"🔗 **Username @{username}**"]

    if metadata.get("relative_time"):
        lines.append(f"📅 **Linked:** {metadata['relative_time']}")

    target_type = metadata.get("target_type", "contact")
    if target_type == "group":
        if metadata.get("display_name"):
            lines.append(f"👥 **Group:** {metadata['display_name']}")
    elif target_type == "channel":
        if metadata.get("display_name"):
            lines.append(f"📢 **Channel:** {metadata['display_name']}")
    else:
        if metadata.get("email"):
            lines.append(f"📧 **Email:** `{metadata['email']}`")
        if metadata.get("display_name"):
            lines.append(f"👤 **Name:** {metadata['display_name']}")

    line1, line2 = metadata.get("formatted_fp", ("", ""))
    if line1 or line2:
        lines.append("\n🔐 **Fingerprint:**")
        if line1:
            lines.append(f"`{line1}`")
        if line2:
            lines.append(f"`{line2}`")

    if metadata.get("identicon"):
        lines.append("\n🛡️ **Visual Key Art:**")
        lines.append("```")
        lines.append(metadata["identicon"])
        lines.append("```")

    if metadata.get("emoji_hash"):
        lines.append(f"✨ **Visual Badge:** {metadata['emoji_hash']}")

    lines.append(f"\n🌐 **Direct Invite Link:**\n{canonical_link}")
    lines.append(f"\n🔗 **Short Link:** {base_url}/{username}")

    return "\n".join(lines)


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
    Supports 1-on-1 contact links (i, s, a, n), channel/broadcast links (x, j, s, a, n, b),
    and group links across official and mirror domains.
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

    # Must contain at least one token parameter (i or x or j or g)
    token_present = any(k in params and params[k][0] for k in ["i", "x", "j", "g"])
    # Must contain at least signature, address, or broadcast parameter
    id_present = any(k in params and params[k][0] for k in ["s", "a", "b", "n"])

    if not (token_present and id_present):
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
