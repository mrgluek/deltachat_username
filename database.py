import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

DB_PATH = os.getenv("DB_PATH", "username.db")
_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db():
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()

            # Config table for admin settings, base_url, etc.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            # Usernames mapping table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usernames (
                    username TEXT PRIMARY KEY,
                    invite_link TEXT NOT NULL,
                    claimed_by_chat_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_usernames_chat_id ON usernames(claimed_by_chat_id)')

            # Pending username state table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_usernames (
                    chat_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
            ''')

            # Transport statistics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transport_stats (
                    addr TEXT PRIMARY KEY,
                    msgs_sent INTEGER DEFAULT 0,
                    msgs_received INTEGER DEFAULT 0,
                    last_sent_at INTEGER,
                    last_received_at INTEGER
                )
            ''')

            conn.commit()
        finally:
            conn.close()


def set_config(key: str, value: str):
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value) if value is not None else None))
            conn.commit()
        finally:
            conn.close()


def get_config(key: str) -> Optional[str]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()


def get_admin_email() -> Optional[str]:
    db_val = get_config("admin_dc_email")
    if db_val and db_val.strip():
        return db_val.strip().lower()
    env_val = os.getenv("ADMIN_DC_EMAIL")
    return env_val.strip().lower() if env_val else None


def set_admin_email(email: str):
    if email:
        email = email.strip().lower()
    set_config("admin_dc_email", email)


def get_admin_fingerprint() -> Optional[str]:
    fp = get_config("admin_dc_fingerprint")
    if not fp:
        fp = os.getenv("ADMIN_DC_FINGERPRINT", "")
    if fp:
        cleaned = fp.strip().replace(" ", "").replace(":", "").upper()
        if re.match(r"^[0-9A-F]{32,64}$", cleaned):
            return cleaned
    return None


def set_admin_fingerprint(fp: str):
    if fp:
        cleaned = fp.strip().replace(" ", "").replace(":", "").upper()
        set_config("admin_dc_fingerprint", cleaned)
    else:
        set_config("admin_dc_fingerprint", "")


def is_authorized_sender(sender_addr: str, fingerprint: Optional[str] = None) -> bool:
    admin_email = get_admin_email()
    admin_fp = get_admin_fingerprint()

    if not admin_email and not admin_fp:
        return False

    sender_addr_clean = (sender_addr or "").strip().lower()

    if admin_email and sender_addr_clean == admin_email:
        if admin_fp:
            if fingerprint:
                fp_clean = fingerprint.strip().replace(" ", "").replace(":", "").upper()
                return admin_fp in fp_clean
            return False
        return True

    if admin_fp and fingerprint:
        fp_clean = fingerprint.strip().replace(" ", "").replace(":", "").upper()
        return admin_fp in fp_clean

    return False


def get_username_claim(username: str) -> Optional[Dict[str, Any]]:
    clean_username = username.strip().lower()
    with _lock:
        conn = get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usernames WHERE username = ?", (clean_username,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_username_by_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    str_chat_id = str(chat_id)
    with _lock:
        conn = get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usernames WHERE claimed_by_chat_id = ?", (str_chat_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def claim_username(username: str, invite_link: str, chat_id: str) -> Dict[str, Any]:
    clean_username = username.strip().lower()
    str_chat_id = str(chat_id)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM usernames WHERE claimed_by_chat_id = ?", (str_chat_id,))
            cursor.execute(
                """
                INSERT INTO usernames (username, invite_link, claimed_by_chat_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    invite_link = excluded.invite_link,
                    claimed_by_chat_id = excluded.claimed_by_chat_id,
                    updated_at = excluded.updated_at
                """,
                (clean_username, invite_link, str_chat_id, now_iso),
            )
            conn.commit()
        finally:
            conn.close()

    return {
        "username": clean_username,
        "invite_link": invite_link,
        "claimed_by_chat_id": str_chat_id,
        "updated_at": now_iso,
    }


def update_username_invite_metadata(username: str, new_invite_link: str) -> bool:
    """Update invite link for an existing claimed username and refresh timestamp."""
    clean_username = username.strip().lower()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE usernames SET invite_link = ?, updated_at = ? WHERE username = ?",
                (new_invite_link, now_iso, clean_username),
            )
            changed = cursor.rowcount > 0
            conn.commit()
            return changed
        finally:
            conn.close()


def unlink_username(username: str) -> bool:
    clean_username = username.strip().lower()
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM usernames WHERE username = ?", (clean_username,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()


def unlink_chat_username(chat_id: str) -> Optional[str]:
    str_chat_id = str(chat_id)
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM usernames WHERE claimed_by_chat_id = ?", (str_chat_id,))
            row = cursor.fetchone()
            if row:
                unbound_uname = row[0]
                cursor.execute("DELETE FROM usernames WHERE claimed_by_chat_id = ?", (str_chat_id,))
                conn.commit()
                return unbound_uname
            return None
        finally:
            conn.close()


def set_pending_username(chat_id: str, username: str):
    str_chat_id = str(chat_id)
    clean_username = username.strip().lower()
    now_ts = int(time.time())

    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO pending_usernames (chat_id, username, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    username = excluded.username,
                    created_at = excluded.created_at
                """,
                (str_chat_id, clean_username, now_ts),
            )
            conn.commit()
        finally:
            conn.close()


def get_pending_username(chat_id: str, ttl_seconds: int = 600) -> Optional[str]:
    str_chat_id = str(chat_id)
    now_ts = int(time.time())

    with _lock:
        conn = get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT username, created_at FROM pending_usernames WHERE chat_id = ?", (str_chat_id,))
            row = cursor.fetchone()

            if not row:
                return None

            created_at = row["created_at"]
            username = row["username"]

            if now_ts - created_at > ttl_seconds:
                cursor.execute("DELETE FROM pending_usernames WHERE chat_id = ?", (str_chat_id,))
                conn.commit()
                return None

            return username
        finally:
            conn.close()


def clear_pending_username(chat_id: str):
    str_chat_id = str(chat_id)
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_usernames WHERE chat_id = ?", (str_chat_id,))
            conn.commit()
        finally:
            conn.close()


def cleanup_expired_pending(ttl_seconds: int = 600):
    cutoff = int(time.time()) - ttl_seconds
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_usernames WHERE created_at < ?", (cutoff,))
            conn.commit()
        finally:
            conn.close()


def get_all_usernames() -> Dict[str, Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usernames")
            rows = cursor.fetchall()
            result = {}
            for r in rows:
                result[r["username"]] = {
                    "invite_link": r["invite_link"],
                    "claimed_by_chat_id": r["claimed_by_chat_id"],
                    "updated_at": r["updated_at"],
                }
            return result
        finally:
            conn.close()


def get_username_count() -> int:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM usernames")
            count = cursor.fetchone()[0]
            return count
        finally:
            conn.close()


# Transport statistics tracking (buffered in memory)
_transport_stats_buffer: dict[str, dict[str, int]] = {}
_transport_stats_lock = threading.Lock()
_last_transport_flush = time.time()
TRANSPORT_FLUSH_INTERVAL = 30.0  # seconds


def increment_transport_sent(addr: str):
    """Increment the sent counter for a transport address (buffered in memory)."""
    if not addr or not isinstance(addr, str) or "@" not in addr:
        return
    now = int(time.time())
    should_flush = False
    with _transport_stats_lock:
        if addr not in _transport_stats_buffer:
            _transport_stats_buffer[addr] = {"sent": 0, "recv": 0, "last_sent": 0, "last_recv": 0}
        _transport_stats_buffer[addr]["sent"] += 1
        _transport_stats_buffer[addr]["last_sent"] = now
        global _last_transport_flush
        if now - _last_transport_flush >= TRANSPORT_FLUSH_INTERVAL:
            should_flush = True
    if should_flush:
        flush_transport_stats()


def increment_transport_received(addr: str):
    """Increment the received counter for a transport address (buffered in memory)."""
    if not addr or not isinstance(addr, str) or "@" not in addr:
        return
    now = int(time.time())
    should_flush = False
    with _transport_stats_lock:
        if addr not in _transport_stats_buffer:
            _transport_stats_buffer[addr] = {"sent": 0, "recv": 0, "last_sent": 0, "last_recv": 0}
        _transport_stats_buffer[addr]["recv"] += 1
        _transport_stats_buffer[addr]["last_recv"] = now
        global _last_transport_flush
        if now - _last_transport_flush >= TRANSPORT_FLUSH_INTERVAL:
            should_flush = True
    if should_flush:
        flush_transport_stats()


def flush_transport_stats():
    """Flush buffered transport stats to the database in a single transaction."""
    global _last_transport_flush
    with _transport_stats_lock:
        if not _transport_stats_buffer:
            _last_transport_flush = time.time()
            return
        pending = dict(_transport_stats_buffer)
        _transport_stats_buffer.clear()
        _last_transport_flush = time.time()

    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            for addr, counts in pending.items():
                if not isinstance(addr, str) or "@" not in addr:
                    continue
                sent = int(counts.get("sent", 0))
                recv = int(counts.get("recv", 0))
                last_s = counts.get("last_sent") or None
                last_r = counts.get("last_recv") or None
                cursor.execute(
                    """
                    INSERT INTO transport_stats (addr, msgs_sent, msgs_received, last_sent_at, last_received_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(addr) DO UPDATE SET
                        msgs_sent = msgs_sent + excluded.msgs_sent,
                        msgs_received = msgs_received + excluded.msgs_received,
                        last_sent_at = COALESCE(excluded.last_sent_at, transport_stats.last_sent_at),
                        last_received_at = COALESCE(excluded.last_received_at, transport_stats.last_received_at)
                    """,
                    (addr, sent, recv, last_s, last_r),
                )
            conn.commit()
        finally:
            conn.close()


def get_all_transport_stats() -> List[Dict[str, Any]]:
    """Get statistics for all tracked transports."""
    flush_transport_stats()
    with _lock:
        conn = get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM transport_stats ORDER BY msgs_sent + msgs_received DESC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def cleanup_old_records(retention_days: int = 1) -> dict[str, int]:
    """Clean up expired pending usernames and flush transport stats."""
    flush_transport_stats()
    cleanup_expired_pending(ttl_seconds=retention_days * 86400)
    return {"status": "ok"}


init_db()
