"""Database and Authentication module for AI Voice Studio.
Uses built-in SQLite3 and standard library hashlib/secrets for zero-dependency reliability.
"""
import datetime
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
from typing import Optional

BASE_DIR = Path(__file__).parent
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)
DB_PATH = OUTPUTS_DIR / "voice_studio.db"
METADATA_JSON = OUTPUTS_DIR / "metadata.json"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables and migrate legacy metadata.json if present."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                is_guest INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                last_active INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                title TEXT,
                full_text TEXT,
                kind TEXT,
                voice_or_effect TEXT,
                format TEXT,
                duration REAL,
                size INTEGER,
                created_at TEXT,
                timestamp INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_files_user ON files(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
        """)

        # Check if legacy metadata.json exists and migrate
        if METADATA_JSON.exists():
            try:
                data = json.loads(METADATA_JSON.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM files")
                    count = cur.fetchone()[0]
                    if count == 0:
                        # Migrate legacy files under a default system/demo user
                        for item in data:
                            cur.execute("""
                                INSERT OR IGNORE INTO files (
                                    id, user_id, filename, title, full_text, kind,
                                    voice_or_effect, format, duration, size, created_at, timestamp
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                item.get("id"),
                                "legacy_shared",
                                item.get("filename", ""),
                                item.get("title", ""),
                                item.get("full_text", ""),
                                item.get("kind", "tts"),
                                item.get("voice_or_effect", ""),
                                item.get("format", "mp3"),
                                item.get("duration", 0.0),
                                item.get("size", 0),
                                item.get("created_at", ""),
                                item.get("timestamp", int(datetime.datetime.now().timestamp()))
                            ))
                        conn.commit()
            except Exception:
                pass


# ---------------- Auth Utilities ----------------

def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()


def create_user(username: str, password: str) -> dict:
    username = username.strip()
    if len(username) < 3 or len(username) > 32:
        raise ValueError("Username must be between 3 and 32 characters.")
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters long.")

    user_id = f"u_{secrets.token_hex(8)}"
    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)
    now_str = datetime.datetime.now().strftime("%b %d, %Y, %I:%M %p")

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, pw_hash, salt, now_str)
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError("Username is already taken. Please choose another one.")

    return {"id": user_id, "username": username, "created_at": now_str}


def authenticate_user(username: str, password: str) -> Optional[dict]:
    username = username.strip()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, username, password_hash, salt, created_at FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        if not row:
            return None
        pw_hash = _hash_password(password, row["salt"])
        if pw_hash == row["password_hash"]:
            return {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}
    return None


def create_session(user_id: str, username: str, is_guest: bool = False) -> str:
    token = secrets.token_hex(32)
    now = int(datetime.datetime.now().timestamp())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, username, is_guest, created_at, last_active) VALUES (?, ?, ?, ?, ?, ?)",
            (token, user_id, username, 1 if is_guest else 0, now, now)
        )
        conn.commit()
    return token


def get_session(token: str) -> Optional[dict]:
    if not token:
        return None
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT token, user_id, username, is_guest, created_at, last_active FROM sessions WHERE token = ?", (token,))
        row = cur.fetchone()
        if not row:
            return None
        now = int(datetime.datetime.now().timestamp())
        # Update last_active
        conn.execute("UPDATE sessions SET last_active = ? WHERE token = ?", (now, token))
        conn.commit()
        return {
            "token": row["token"],
            "user_id": row["user_id"],
            "username": row["username"],
            "is_guest": bool(row["is_guest"]),
        }


def delete_session(token: str):
    if not token:
        return
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def create_guest_session() -> tuple[str, dict]:
    guest_id = f"guest_{secrets.token_hex(8)}"
    token = create_session(user_id=guest_id, username="Guest", is_guest=True)
    return token, {"id": guest_id, "username": "Guest", "is_guest": True}


# ---------------- Files Scoping ----------------

def save_file_record(
    file_id: str,
    user_id: str,
    filename: str,
    title: str,
    full_text: str,
    kind: str,
    voice_or_effect: str,
    fmt: str,
    duration: float,
    size: int,
    created_at: str,
    timestamp: int
) -> dict:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO files (
                id, user_id, filename, title, full_text, kind,
                voice_or_effect, format, duration, size, created_at, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id, user_id, filename, title, full_text, kind,
            voice_or_effect, fmt, duration, size, created_at, timestamp
        ))
        conn.commit()

    return {
        "id": file_id,
        "filename": filename,
        "title": title[:80] + ("…" if len(title) > 80 else ""),
        "full_text": full_text,
        "kind": kind,
        "voice_or_effect": voice_or_effect,
        "format": fmt,
        "duration": round(duration, 2),
        "size": size,
        "created_at": created_at,
        "timestamp": timestamp,
        "url": f"/api/files/{file_id}/audio",
    }


def list_user_files(user_id: str) -> list[dict]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, filename, title, full_text, kind, voice_or_effect,
                   format, duration, size, created_at, timestamp
            FROM files
            WHERE user_id = ?
            ORDER BY timestamp DESC
        """, (user_id,))
        rows = cur.fetchall()
        return [
            {
                "id": r["id"],
                "filename": r["filename"],
                "title": r["title"],
                "full_text": r["full_text"],
                "kind": r["kind"],
                "voice_or_effect": r["voice_or_effect"],
                "format": r["format"],
                "duration": round(r["duration"], 2),
                "size": r["size"],
                "created_at": r["created_at"],
                "timestamp": r["timestamp"],
                "url": f"/api/files/{r['id']}/audio",
            }
            for r in rows
        ]


def get_file_record(file_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    with get_db() as conn:
        cur = conn.cursor()
        if user_id:
            cur.execute("SELECT * FROM files WHERE id = ? AND user_id = ?", (file_id, user_id))
        else:
            cur.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        r = cur.fetchone()
        if not r:
            return None
        return dict(r)


def delete_user_file(file_id: str, user_id: str) -> Optional[str]:
    """Deletes file record if owned by user. Returns filename if deleted, None otherwise."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT filename FROM files WHERE id = ? AND user_id = ?", (file_id, user_id))
        r = cur.fetchone()
        if not r:
            return None
        filename = r["filename"]
        conn.execute("DELETE FROM files WHERE id = ? AND user_id = ?", (file_id, user_id))
        conn.commit()
        return filename


def clear_all_user_files(user_id: str) -> list[str]:
    """Deletes all file records owned by user. Returns list of filenames to remove from disk."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT filename FROM files WHERE user_id = ?", (user_id,))
        rows = cur.fetchall()
        filenames = [r["filename"] for r in rows]
        conn.execute("DELETE FROM files WHERE user_id = ?", (user_id,))
        conn.commit()
        return filenames


def migrate_guest_files(from_guest_id: str, to_user_id: str):
    """Transfer files from a guest session into a registered account."""
    if not from_guest_id or not to_user_id or from_guest_id == to_user_id:
        return
    with get_db() as conn:
        conn.execute("UPDATE files SET user_id = ? WHERE user_id = ?", (to_user_id, from_guest_id))
        conn.commit()
