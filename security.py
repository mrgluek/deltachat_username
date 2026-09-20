import os
import threading
import time

from fastapi import Request

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


# --- CRAWLER DETECTION FOR OPENGRAPH PREVIEWS ---
CRAWLER_USER_AGENTS = [
    "telegrambot", "twitterbot", "facebookexternalhit", "discordbot",
    "slackbot", "whatsapp", "vkshare", "w3c_validator", "redditbot",
    "applebot", "bingbot", "googlebot", "yandex", "linkedinbot",
    "mastodon", "matrix", "embedly", "quora link preview", "outbrain",
    "pinterest", "skypeuripreview", "webpreview", "deltachat",
    "preview", "bot", "crawler", "spider", "scraper", "fetch",
    "curl", "wget", "http-client", "python", "requests", "httpx",
    "aiohttp", "urllib", "axios", "got", "node", "ruby",
    "go-http-client", "java", "okhttp", "libwww", "feed",
]
TELEGRAM_IP_PREFIXES = ("149.154.", "91.108.", "95.161.")


def is_crawler_request(request: Request) -> bool:
    """Detect if request comes from a social media crawler, preview bot, or scraper."""
    ua = request.headers.get("user-agent", "").lower()
    if not ua:
        return True
    if any(crawler in ua for crawler in CRAWLER_USER_AGENTS):
        return True
    client_ip = get_client_ip(request)
    if any(client_ip.startswith(prefix) for prefix in TELEGRAM_IP_PREFIXES):
        return True
    return False
