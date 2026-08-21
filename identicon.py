"""
Identicon, Visual Key Hash, and Metadata Parsing Module for Delta Chat Username Bot.
Provides:
- 5x5 symmetric Unicode block identicon
- 256-emoji deterministic visual hash
- Formatted PGP fingerprint groups (10 groups of 4 hex chars)
- Invite link metadata parser with relative registration age
- Dynamic PNG and SVG OpenGraph card generators with caching
"""

import hashlib
import io
import os
import re
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional
from urllib.parse import parse_qs, unquote

try:
    import resvg_py
    HAS_RESVG = True
except ImportError:
    HAS_RESVG = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Curated list of 256 visually distinct, universally supported Unicode emojis
EMOJI_PALETTE = [
    # Animals & Nature (0-63)
    "🐶", "🐱", "🐭", "🐹", "🐰", "🦊", "🐻", "🐼", "🐨", "🐯", "🦁", "🐮", "🐷", "🐸", "🐵", "🐔",
    "🐧", "🐦", "🐤", "🦆", "🦅", "🦉", "🦇", "🐺", "🐗", "🐴", "🦄", "🐝", "🐛", "🦋", "🐌", "🐞",
    "🐜", "🐢", "🐍", "🦎", "🐙", "🦑", "🦐", "🦞", "🦀", "🐡", "🐠", "🐟", "🐬", "🐳", "🦈", "🐊",
    "🐅", "🐆", "🦓", "🦍", "🦧", "🐘", "🦛", "🦏", "🐪", "🐫", "🦒", "🦘", "🦥", "🦦", "🦨", "🦔",
    # Plants & Celestial (64-103)
    "🌸", "🌹", "🌺", "🌻", "🌼", "🌷", "🌱", "🌲", "🌳", "🌴", "🌵", "🌾", "🌿", "🍀", "🍁", "🍂",
    "🍃", "🍄", "🌰", "🌍", "🌕", "🌙", "⭐", "🌟", "⚡", "☄️", "💥", "🔥", "🌈", "☀️", "☁️", "❄️",
    "🌊", "💧", "🪐", "✨", "💫", "🌋", "🏔️", "🏕️",
    # Food & Drink (104-143)
    "🍏", "🍎", "🍐", "🍊", "🍋", "🍌", "🍉", "🍇", "🍓", "🫐", "🍈", "🍒", "🍑", "🥭", "🍍", "🥥",
    "🥝", "🍅", "🥑", "🍆", "🥦", "🌽", "🥕", "🍞", "🧀", "🍖", "🍗", "🍔", "🍟", "🍕", "🌭", "🥪",
    "🌮", "🌯", "🥚", "🍿", "🍩", "🍪", "🎂", "🧁",
    # Activities, Objects & Tech (144-207)
    "⚽", "🏀", "🏈", "⚾", "🎾", "🏐", "🏉", "🎱", "🏓", "🏸", "🥊", "🏹", "🎣", "🛹", "🎯", "🎮",
    "🎲", "🧩", "🎨", "🎭", "🎪", "🎤", "🎧", "🎷", "🎸", "🎹", "🎺", "🎻", "🥁", "🎬", "📡", "🔋",
    "🔌", "💻", "🖥️", "📷", "📹", "🔍", "💡", "🔦", "🏮", "📖", "📚", "🏷️", "🔑", "🗝️", "🔨", "🪓",
    "🔧", "⚙️", "🧲", "🧪", "🧬", "🔬", "🔭", "💎", "👑", "🏆", "🥇", "🥈", "🥉", "🎖️", "🏅", "🎟️",
    # Travel & Transport (208-231)
    "🚗", "🚕", "🚙", "🚌", "🏎️", "🚓", "🚑", "🚒", "🚐", "🚚", "🚜", "🛵", "🏍️", "🚲", "🛴", "🚀",
    "🛸", "🚁", "🛶", "⛵", "🚤", "🚢", "⚓", "🪂",
    # Badges, Shields & Symbols (232-255)
    "🔮", "🧿", "🪄", "🛡️", "⚔️", "🗡️", "🔔", "📣", "📢", "🧭", "⏱️", "⏳", "⌛", "🔒", "🔓", "🔏",
    "✉️", "📦", "💌", "📮", "📌", "📍", "🚩", "🏁"
]

# Ensure exact length of 256 for 1-byte indexing
assert len(EMOJI_PALETTE) == 256, f"EMOJI_PALETTE must contain exactly 256 items, got {len(EMOJI_PALETTE)}"

# In-memory LRU/dict cache for generated PNG images: key -> bytes
_PNG_CACHE: Dict[str, bytes] = {}
_PNG_CACHE_MAX_ITEMS = 500


def format_fingerprint_groups(raw_hex: str) -> Tuple[str, str]:
    """
    Format a 32/40/64-character hexadecimal fingerprint into standard Delta Chat / PGP groups:
    10 groups of 4 hex digits split across 2 lines (5 groups per line).
    """
    clean_hex = re.sub(r"[^0-9A-Fa-f]", "", raw_hex).upper()
    if not clean_hex:
        return ("", "")

    # Group into 4-character chunks
    chunks = [clean_hex[i:i + 4] for i in range(0, len(clean_hex), 4)]

    # Split into 2 lines
    mid = (len(chunks) + 1) // 2
    line1 = " ".join(chunks[:mid])
    line2 = " ".join(chunks[mid:])
    return (line1, line2)


def generate_symmetric_identicon(hex_fingerprint: str) -> str:
    """
    Generate a 5x5 horizontally symmetric Unicode identicon from fingerprint bytes.
    Symmetry: columns 0, 1, 2 determine columns 4, 3, 2 ([c0, c1, c2, c1, c0]).
    Uses full block characters ('██') for foreground and spaces ('  ') for background.
    """
    clean_hex = re.sub(r"[^0-9A-Fa-f]", "", hex_fingerprint)
    if not clean_hex:
        clean_hex = hashlib.sha256(b"default").hexdigest()

    # Convert hex to bytes (pad with sha256 if needed)
    try:
        raw_bytes = bytes.fromhex(clean_hex)
    except ValueError:
        raw_bytes = hashlib.sha256(clean_hex.encode("utf-8")).digest()

    if len(raw_bytes) < 4:
        raw_bytes = hashlib.sha256(raw_bytes).digest()

    # We need 15 bits for a 5x3 half-matrix (5 rows * 3 cells)
    # Extract bits from first 2-3 bytes
    bit_stream = 0
    for b in raw_bytes[:3]:
        bit_stream = (bit_stream << 8) | b

    lines = []
    lines.append("+---[ IDENTICON ]---+")
    for row in range(5):
        c0 = (bit_stream >> (row * 3 + 0)) & 1
        c1 = (bit_stream >> (row * 3 + 1)) & 1
        c2 = (bit_stream >> (row * 3 + 2)) & 1

        # 5 cells: c0, c1, c2, c1, c0
        cells = [c0, c1, c2, c1, c0]
        row_str = "".join("██" if c else "  " for c in cells)
        lines.append(f"|   {row_str}    |")
    lines.append("+-------------------+")

    return "\n".join(lines)


def generate_emoji_hash(hex_fingerprint: str, count: int = 5) -> str:
    """
    Deterministically map fingerprint bytes to a sequence of `count` distinct emojis (default: 5).
    Provides ~40 bits of visual entropy.
    """
    clean_hex = re.sub(r"[^0-9A-Fa-f]", "", hex_fingerprint)
    if not clean_hex:
        clean_hex = hashlib.sha256(b"default").hexdigest()

    try:
        raw_bytes = bytes.fromhex(clean_hex)
    except ValueError:
        raw_bytes = hashlib.sha256(clean_hex.encode("utf-8")).digest()

    # If raw_bytes is shorter than needed, expand with SHA-256
    if len(raw_bytes) < count:
        raw_bytes = hashlib.sha256(raw_bytes).digest()

    # Select `count` bytes spread across the fingerprint
    selected_emojis = []
    step = max(1, len(raw_bytes) // count)
    for i in range(count):
        idx = (i * step) % len(raw_bytes)
        byte_val = raw_bytes[idx]
        selected_emojis.append(EMOJI_PALETTE[byte_val % len(EMOJI_PALETTE)])

    return " ".join(selected_emojis)


def format_relative_time(iso_timestamp: str, now_dt: Optional[datetime] = None) -> str:
    """
    Format an ISO timestamp (e.g. '2026-08-19T14:30:00Z') into a human-readable relative time string.
    Example: '19 Aug 2026 (2 days ago)', 'Today (3 hours ago)', 'Just now'.
    """
    if not iso_timestamp:
        return "Unknown date"

    try:
        clean_ts = iso_timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        current_now = now_dt or datetime.now(timezone.utc)
        diff = current_now - dt

        total_seconds = int(diff.total_seconds())
        formatted_date = dt.strftime("%d %b %Y")

        if total_seconds < 60:
            return f"{formatted_date} (just now)"
        elif total_seconds < 3600:
            mins = total_seconds // 60
            return f"{formatted_date} ({mins} min{'s' if mins != 1 else ''} ago)"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"{formatted_date} ({hours} hour{'s' if hours != 1 else ''} ago)"
        elif total_seconds < 86400 * 30:
            days = total_seconds // 86400
            return f"{formatted_date} ({days} day{'s' if days != 1 else ''} ago)"
        elif total_seconds < 86400 * 365:
            months = total_seconds // (86400 * 30)
            return f"{formatted_date} ({months} month{'s' if months != 1 else ''} ago)"
        else:
            years = total_seconds // (86400 * 365)
            return f"{formatted_date} ({years} year{'s' if years != 1 else ''} ago)"
    except Exception:
        return iso_timestamp


def parse_invite_metadata(invite_link: str, updated_at_iso: str = "") -> Dict[str, Any]:
    """
    Parse Delta Chat invite link and return structured metadata:
    - fingerprint (40 hex string)
    - formatted_fp (tuple of 2 lines)
    - email (address from `a` param)
    - display_name (name from `n` param)
    - target_type ('contact', 'group', 'channel', or 'broadcast')
    - identicon (5x5 text identicon)
    - emoji_hash (5-emoji string)
    - relative_time (formatted registration date)
    - canonical_link (clean invite URL)
    """
    result: Dict[str, Any] = {
        "fingerprint": "",
        "formatted_fp": ("", ""),
        "email": "",
        "display_name": "",
        "target_type": "contact",
        "identicon": "",
        "emoji_hash": "",
        "relative_time": format_relative_time(updated_at_iso),
        "canonical_link": invite_link,
    }

    if not invite_link or "/#" not in invite_link:
        return result

    hash_idx = invite_link.find("/#")
    fragment_part = invite_link[hash_idx + 2:]

    # The fragment starts with the hex fingerprint or parameters
    query_str = ""
    fp_part = ""

    if "&" in fragment_part:
        fp_part, query_str = fragment_part.split("&", 1)
    elif "?" in fragment_part:
        fp_part, query_str = fragment_part.split("?", 1)
    else:
        fp_part = fragment_part

    # Clean fingerprint
    clean_fp = re.sub(r"[^0-9A-Fa-f]", "", fp_part).upper()
    result["fingerprint"] = clean_fp
    result["formatted_fp"] = format_fingerprint_groups(clean_fp)
    result["identicon"] = generate_symmetric_identicon(clean_fp)
    result["emoji_hash"] = generate_emoji_hash(clean_fp, count=5)

    # Parse query parameters
    if query_str:
        params = parse_qs(query_str)
        if "a" in params and params["a"][0]:
            result["email"] = unquote(params["a"][0].strip())

        # Determine target type & primary display name
        if "g" in params and params["g"][0]:
            result["target_type"] = "group"
            result["group_name"] = unquote(params["g"][0].strip())
            result["display_name"] = result["group_name"]
            if "n" in params and params["n"][0]:
                result["inviter_name"] = unquote(params["n"][0].strip())
        elif "b" in params and params["b"][0]:
            result["target_type"] = "channel"
            result["channel_name"] = unquote(params["b"][0].strip())
            result["display_name"] = result["channel_name"]
            if "n" in params and params["n"][0]:
                result["inviter_name"] = unquote(params["n"][0].strip())
        elif "x" in params and "j" in params:
            result["target_type"] = "channel"
            if "n" in params and params["n"][0]:
                result["display_name"] = unquote(params["n"][0].strip())
        else:
            result["target_type"] = "contact"
            if "n" in params and params["n"][0]:
                result["display_name"] = unquote(params["n"][0].strip())

    return result


def get_color_from_fingerprint(hex_fp: str) -> Tuple[int, int, int]:
    """Derive a vibrant RGB color from fingerprint for identicon rendering."""
    clean_hex = re.sub(r"[^0-9A-Fa-f]", "", hex_fp)
    if len(clean_hex) >= 6:
        r = int(clean_hex[0:2], 16)
        g = int(clean_hex[2:4], 16)
        b = int(clean_hex[4:6], 16)
    else:
        r, g, b = 56, 189, 248  # Delta Chat sky blue fallback

    # Ensure good brightness/contrast on dark background
    max_val = max(r, g, b, 1)
    if max_val < 140:
        factor = 180 / max_val
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))

    return (r, g, b)


def generate_svg_card(username: str, metadata: Dict[str, Any], base_url: str = "https://d.gluek.info") -> str:
    """Generate a clean, scalable SVG card (1200x630) for web and OpenGraph preview."""
    fp = metadata.get("fingerprint", "")
    line1, line2 = metadata.get("formatted_fp", ("", ""))
    email = metadata.get("email", "")
    name = metadata.get("display_name", username)
    emoji_hash = metadata.get("emoji_hash", "")
    rel_time = metadata.get("relative_time", "")
    target_type_raw = metadata.get("target_type", "contact")
    target_type = target_type_raw.capitalize()
    if target_type_raw == "group":
        detail_label = "Group"
        detail_val = name
    elif target_type_raw == "channel":
        detail_label = "Channel"
        detail_val = name
    else:
        detail_label = "Email"
        detail_val = email or "Not specified"

    fg_r, fg_g, fg_b = get_color_from_fingerprint(fp)
    fg_color = f"rgb({fg_r}, {fg_g}, {fg_b})"

    # Calculate 5x5 identicon cell rects
    clean_hex = re.sub(r"[^0-9A-Fa-f]", "", fp)
    try:
        raw_bytes = bytes.fromhex(clean_hex) if clean_hex else b"\x00" * 3
    except ValueError:
        raw_bytes = b"\x00" * 3

    bit_stream = 0
    for b in raw_bytes[:3]:
        bit_stream = (bit_stream << 8) | b

    identicon_rects = []
    cell_size = 36
    start_x = 90
    start_y = 190

    for row in range(5):
        c0 = (bit_stream >> (row * 3 + 0)) & 1
        c1 = (bit_stream >> (row * 3 + 1)) & 1
        c2 = (bit_stream >> (row * 3 + 2)) & 1
        cells = [c0, c1, c2, c1, c0]
        for col, active in enumerate(cells):
            if active:
                x = start_x + col * cell_size
                y = start_y + row * cell_size
                identicon_rects.append(f'<rect x="{x}" y="{y}" width="{cell_size-2}" height="{cell_size-2}" rx="4" fill="{fg_color}" />')

    rects_svg = "\n        ".join(identicon_rects)

    # Font family definitions with broad cross-platform support (Linux DejaVu/Liberation, macOS System, Windows)
    sans_font = "DejaVu Sans, Liberation Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    mono_font = "DejaVu Sans Mono, Liberation Mono, Menlo, Monaco, Consolas, Courier New, monospace"
    emoji_font = "Apple Color Emoji, Segoe UI Emoji, Noto Color Emoji, Android Emoji, EmojiSymbols, sans-serif"

    emojis = metadata.get("emoji_hash", "").split()
    emoji_tags = []
    for i, em in enumerate(emojis):
        cx = 80 + 20 + i * 40
        emoji_tags.append(
            f'<text x="{cx}" y="440" font-family="{emoji_font}" font-size="32" text-anchor="middle">{em}</text>'
        )
    emojis_svg = "\n    ".join(emoji_tags)

    svg = f"""<svg width="1200" height="630" viewBox="0 0 1200 630" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#0f172a" />
            <stop offset="100%" stop-color="#1e1b4b" />
        </linearGradient>
        <linearGradient id="card-bg" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#1e293b" stop-opacity="0.9" />
            <stop offset="100%" stop-color="#0f172a" stop-opacity="0.9" />
        </linearGradient>
    </defs>

    <!-- Background -->
    <rect width="1200" height="630" fill="url(#bg)" />

    <!-- Main Container Card -->
    <rect x="50" y="50" width="1100" height="530" rx="28" fill="url(#card-bg)" stroke="rgba(255,255,255,0.12)" stroke-width="2" />

    <!-- Header Badge -->
    <rect x="90" y="90" width="160" height="40" rx="20" fill="rgba(56,189,248,0.15)" />
    <text x="170" y="116" font-family="{sans_font}" font-size="16" font-weight="bold" fill="#38bdf8" text-anchor="middle">DELTA CHAT</text>

    <text x="270" y="116" font-family="{sans_font}" font-size="16" fill="#94a3b8">{target_type} • Linked: {rel_time}</text>

    <!-- Identicon Frame -->
    <rect x="80" y="180" width="200" height="200" rx="16" fill="rgba(15,23,42,0.6)" stroke="rgba(255,255,255,0.08)" stroke-width="1.5" />
    <g>
        {rects_svg}
    </g>

    <!-- Info Column -->
    <text x="320" y="215" font-family="{sans_font}" font-size="44" font-weight="800" fill="#f8fafc">{name}</text>
    <text x="320" y="260" font-family="{sans_font}" font-size="26" font-weight="600" fill="#38bdf8">@{username}</text>

    <!-- Details -->
    <text x="320" y="315" font-family="{sans_font}" font-size="20" fill="#94a3b8">{detail_label}: <tspan font-family="{mono_font}" fill="#e2e8f0">{detail_val}</tspan></text>

    <!-- Fingerprint Box -->
    <rect x="320" y="340" width="790" height="110" rx="12" fill="rgba(15,23,42,0.7)" stroke="rgba(255,255,255,0.06)" stroke-width="1" />
    <text x="340" y="372" font-family="{sans_font}" font-size="15" font-weight="bold" fill="#94a3b8">🔐 CRYPTOGRAPHIC FINGERPRINT</text>
    <text x="340" y="405" font-family="{mono_font}" font-size="20" font-weight="bold" fill="#38bdf8" letter-spacing="2">{line1}</text>
    <text x="340" y="435" font-family="{mono_font}" font-size="20" font-weight="bold" fill="#38bdf8" letter-spacing="2">{line2}</text>

    <!-- Emojis aligned under Identicon -->
    {emojis_svg}

    <line x1="90" y1="490" x2="1110" y2="490" stroke="rgba(255,255,255,0.08)" stroke-width="1" />
    <text x="90" y="535" font-family="{sans_font}" font-size="18" fill="#64748b">Verified invite short link: <tspan fill="#38bdf8">{base_url}/{username}</tspan></text>
</svg>"""
    return svg


def generate_og_png_bytes(username: str, metadata: Dict[str, Any], base_url: str = "https://d.gluek.info") -> bytes:
    """
    Generate crisp 1200x630 PNG card using resvg (matching browser SVG exactly),
    with Pillow fallback and fast in-memory caching.
    Guarantees full compatibility across Telegram, WhatsApp, Twitter, Discord, iMessage.
    """
    fp = metadata.get("fingerprint", "")
    updated_at = metadata.get("relative_time", "")
    cache_key = f"{username}:{fp}:{updated_at}"

    if cache_key in _PNG_CACHE:
        return _PNG_CACHE[cache_key]

    svg_text = generate_svg_card(username, metadata, base_url=base_url)

    if HAS_RESVG:
        try:
            # Common Linux and macOS font directories
            search_dirs = [
                "/usr/share/fonts",
                "/usr/local/share/fonts",
                "/usr/share/fonts/truetype",
                "/System/Library/Fonts",
                "/Library/Fonts",
            ]
            valid_dirs = [d for d in search_dirs if os.path.exists(d)]
            png_bytes = resvg_py.svg_to_bytes(
                svg_text,
                font_dirs=valid_dirs if valid_dirs else None,
            )
            if len(_PNG_CACHE) >= _PNG_CACHE_MAX_ITEMS:
                _PNG_CACHE.pop(next(iter(_PNG_CACHE)))
            _PNG_CACHE[cache_key] = png_bytes
            return png_bytes
        except Exception:
            pass

    if not HAS_PIL:
        return b""

    width, height = 1200, 630
    img = Image.new("RGBA", (width, height), (15, 23, 42, 255))
    draw = ImageDraw.Draw(img)

    # Draw rounded background card
    card_rect = [50, 50, 1150, 580]
    draw.rounded_rectangle(card_rect, radius=28, fill=(30, 41, 59, 240), outline=(255, 255, 255, 30), width=2)

    # Load default fonts
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 44)
        font_uname = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
        font_body = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        font_mono = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 21)
        font_badge = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    except Exception:
        font_title = ImageFont.load_default()
        font_uname = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_mono = ImageFont.load_default()
        font_badge = ImageFont.load_default()

    # Draw Header Badge
    draw.rounded_rectangle([90, 90, 250, 130], radius=20, fill=(56, 189, 248, 40))
    draw.text((170, 100), "DELTA CHAT", font=font_badge, fill=(56, 189, 248), anchor="mt")

    target_type = metadata.get("target_type", "contact").capitalize()
    rel_time = metadata.get("relative_time", "")
    draw.text((270, 100), f"{target_type} • Linked: {rel_time}", font=font_body, fill=(148, 163, 184))

    # Identicon Box & Drawing
    draw.rounded_rectangle([80, 180, 280, 380], radius=16, fill=(15, 23, 42, 180), outline=(255, 255, 255, 20), width=1)
    fg_r, fg_g, fg_b = get_color_from_fingerprint(fp)
    fg_color = (fg_r, fg_g, fg_b, 255)

    clean_hex = re.sub(r"[^0-9A-Fa-f]", "", fp)
    try:
        raw_bytes = bytes.fromhex(clean_hex) if clean_hex else b"\x00" * 3
    except ValueError:
        raw_bytes = b"\x00" * 3

    bit_stream = 0
    for b in raw_bytes[:3]:
        bit_stream = (bit_stream << 8) | b

    cell_size = 36
    start_x = 90
    start_y = 190
    for row in range(5):
        c0 = (bit_stream >> (row * 3 + 0)) & 1
        c1 = (bit_stream >> (row * 3 + 1)) & 1
        c2 = (bit_stream >> (row * 3 + 2)) & 1
        cells = [c0, c1, c2, c1, c0]
        for col, active in enumerate(cells):
            if active:
                x0 = start_x + col * cell_size
                y0 = start_y + row * cell_size
                draw.rounded_rectangle([x0, y0, x0 + cell_size - 2, y0 + cell_size - 2], radius=4, fill=fg_color)

    # Info column
    name = metadata.get("display_name", username) or username
    draw.text((320, 175), name, font=font_title, fill=(248, 250, 252))
    draw.text((320, 235), f"@{username}", font=font_uname, fill=(56, 189, 248))

    email = metadata.get("email", "")
    draw.text((320, 285), f"Email: {email or 'Not specified'}", font=font_body, fill=(148, 163, 184))

    # Fingerprint Box
    draw.rounded_rectangle([320, 330, 1110, 450], radius=12, fill=(15, 23, 42, 200), outline=(255, 255, 255, 15), width=1)
    draw.text((340, 345), "🔐 CRYPTOGRAPHIC FINGERPRINT", font=font_badge, fill=(148, 163, 184))

    line1, line2 = metadata.get("formatted_fp", ("", ""))
    draw.text((340, 375), line1, font=font_mono, fill=(56, 189, 248))
    draw.text((340, 408), line2, font=font_mono, fill=(56, 189, 248))

    # Footer
    draw.line([90, 490, 1110, 490], fill=(255, 255, 255, 20), width=1)
    draw.text((90, 520), f"Verified invite short link: {base_url}/{username}", font=font_body, fill=(100, 116, 139))

    # Convert to PNG buffer
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    png_bytes = buf.getvalue()

    # Store in LRU cache
    if len(_PNG_CACHE) >= _PNG_CACHE_MAX_ITEMS:
        _PNG_CACHE.pop(next(iter(_PNG_CACHE)))
    _PNG_CACHE[cache_key] = png_bytes

    return png_bytes


def clear_png_cache():
    """Clear in-memory PNG cache."""
    _PNG_CACHE.clear()
