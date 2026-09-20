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
    """Extract client IP address, trusting only the hop our own reverse proxy appended.

    We deploy behind a single reverse proxy (Caddy) bound to 127.0.0.1, so uvicorn only
    ever sees connections from it. Caddy appends the real peer address as the last entry
    of X-Forwarded-For rather than overwriting it, so the first entry is whatever the
    client itself sent and can be spoofed to defeat the rate limiter below - the last
    entry is the one hop we can actually trust.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
        if parts:
            return parts[-1]
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


def prune_rate_limits():
    """Drop IP entries that have aged out of the rate-limit window entirely.

    is_rate_limited() only trims an IP's own timestamp list when that IP makes a new
    request, so an IP that stops coming back stays in _ip_request_history forever.
    Call this periodically from a background worker to bound memory over long uptime.
    """
    cutoff = time.time() - RATE_LIMIT_WINDOW
    with _rate_limit_lock:
        stale_ips = [ip for ip, timestamps in _ip_request_history.items() if not timestamps or max(timestamps) <= cutoff]
        for ip in stale_ips:
            del _ip_request_history[ip]
