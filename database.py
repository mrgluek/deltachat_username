import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

DB_PATH = os.getenv("DB_PATH", "username.db")
_lock = threading.Lock()


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _lock:
        conn = get_connection()
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
        conn.close()


def set_config(key: str, value: str):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()


def get_config(key: str) -> Optional[str]:
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None


def get_admin_fingerprint() -> Optional[str]:
    fp = get_config("admin_dc_fingerprint")
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


def get_username_claim(username: str) -> Optional[Dict[str, Any]]:
    clean_username = username.strip().lower()
    with _lock:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usernames WHERE username = ?", (clean_username,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None


def get_username_by_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    str_chat_id = str(chat_id)
    with _lock:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usernames WHERE claimed_by_chat_id = ?", (str_chat_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None


def claim_username(username: str, invite_link: str, chat_id: str) -> Dict[str, Any]:
    clean_username = username.strip().lower()
    str_chat_id = str(chat_id)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
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
        conn.close()

    return {
        "username": clean_username,
        "invite_link": invite_link,
        "claimed_by_chat_id": str_chat_id,
        "updated_at": now_iso,
    }


def set_pending_username(chat_id: str, username: str):
    str_chat_id = str(chat_id)
    clean_username = username.strip().lower()
    now_ts = int(time.time())

    with _lock:
        conn = get_connection()
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
        conn.close()


def get_pending_username(chat_id: str, ttl_seconds: int = 600) -> Optional[str]:
    str_chat_id = str(chat_id)
    now_ts = int(time.time())

    with _lock:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT username, created_at FROM pending_usernames WHERE chat_id = ?", (str_chat_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        created_at = row["created_at"]
        username = row["username"]

        if now_ts - created_at > ttl_seconds:
            cursor.execute("DELETE FROM pending_usernames WHERE chat_id = ?", (str_chat_id,))
            conn.commit()
            conn.close()
            return None

        conn.close()
        return username


def clear_pending_username(chat_id: str):
    str_chat_id = str(chat_id)
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_usernames WHERE chat_id = ?", (str_chat_id,))
        conn.commit()
        conn.close()


def cleanup_expired_pending(ttl_seconds: int = 600):
    cutoff = int(time.time()) - ttl_seconds
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_usernames WHERE created_at < ?", (cutoff,))
        conn.commit()
        conn.close()


def get_all_usernames() -> Dict[str, Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usernames")
        rows = cursor.fetchall()
        conn.close()

    result = {}
    for r in rows:
        result[r["username"]] = {
            "invite_link": r["invite_link"],
            "claimed_by_chat_id": r["claimed_by_chat_id"],
            "updated_at": r["updated_at"],
        }
    return result


def get_username_count() -> int:
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usernames")
        count = cursor.fetchone()[0]
        conn.close()
        return count


def increment_transport_sent(addr: str):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO transport_stats (addr, msgs_sent, msgs_received, last_sent_at)
            VALUES (?, 1, 0, CAST(strftime('%s','now') AS INTEGER))
            ON CONFLICT(addr) DO UPDATE SET
                msgs_sent = msgs_sent + 1,
                last_sent_at = CAST(strftime('%s','now') AS INTEGER)
        """,
            (addr,),
        )
        conn.commit()
        conn.close()


def increment_transport_received(addr: str):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO transport_stats (addr, msgs_sent, msgs_received, last_received_at)
            VALUES (?, 0, 1, CAST(strftime('%s','now') AS INTEGER))
            ON CONFLICT(addr) DO UPDATE SET
                msgs_received = msgs_received + 1,
                last_received_at = CAST(strftime('%s','now') AS INTEGER)
        """,
            (addr,),
        )
        conn.commit()
        conn.close()


def get_all_transport_stats() -> List[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM transport_stats ORDER BY msgs_sent + msgs_received DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]


init_db()
