"""
Database Management and SQLite Persistence for DropPrint Counter Server.
Enforces WAL mode, foreign keys, clean migrations, and secure token/credential utilities.
"""

from __future__ import annotations

import binascii
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, Optional

from .config import ROOT, settings

logger = logging.getLogger(__name__)

DATA_DIR = settings.data_dir
DATA_DIR.mkdir(parents=True, exist_ok=True)

_env_db = os.environ.get("PRINT_SYSTEM_DB_PATH")
if _env_db:
    _p = Path(_env_db)
    DB_PATH = _p if _p.is_absolute() else (ROOT / _p).resolve()
else:
    DB_PATH = (DATA_DIR / "print_system.db").resolve()

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
SESSION_SECRET = settings.session_secret
PBKDF2_ITERATIONS = 100_000


def get_db_connection() -> sqlite3.Connection:
    """Direct database connection with Row factory, foreign keys, and WAL mode enabled."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency yielding a managed SQLite connection."""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initializes SQLite database schema, creates indexes, and inserts seed records."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS shops (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS shop_devices (
            id TEXT PRIMARY KEY,
            shop_id TEXT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            is_active INTEGER NOT NULL DEFAULT 1,
            last_seen_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS shopkeepers (
            id TEXT PRIMARY KEY,
            shop_id TEXT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pricing_rules (
            id TEXT PRIMARY KEY,
            shop_id TEXT NOT NULL UNIQUE REFERENCES shops(id) ON DELETE CASCADE,
            bw_per_page REAL NOT NULL DEFAULT 2.0,
            color_per_page REAL NOT NULL DEFAULT 10.0,
            duplex_discount REAL NOT NULL DEFAULT 0.5,
            min_charge REAL NOT NULL DEFAULT 0.0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS print_jobs (
            id TEXT PRIMARY KEY,
            shop_id TEXT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
            tracking_token TEXT NOT NULL UNIQUE,
            short_code TEXT,
            filename TEXT NOT NULL,
            file_r2_key TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            page_count INTEGER NOT NULL,
            copies INTEGER NOT NULL DEFAULT 1,
            color_mode TEXT NOT NULL CHECK(color_mode IN ('bw', 'color')),
            duplex_mode TEXT NOT NULL DEFAULT 'simplex' CHECK(duplex_mode IN ('simplex', 'duplex')),
            paper_size TEXT NOT NULL DEFAULT 'A4',
            page_range TEXT DEFAULT 'all',
            total_price REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            status TEXT NOT NULL CHECK(status IN ('UPLOADED', 'PENDING_PAYMENT', 'PAID', 'APPROVED', 'QUEUED', 'PRINTING', 'COMPLETED', 'REJECTED', 'CANCELLED', 'FAILED')),
            payment_status TEXT NOT NULL DEFAULT 'UNPAID' CHECK(payment_status IN ('UNPAID', 'PAID')),
            approved_by TEXT REFERENCES shopkeepers(id) ON DELETE SET NULL,
            approved_at TEXT,
            gateway_device_id TEXT REFERENCES shop_devices(id) ON DELETE SET NULL,
            spooler_job_id INTEGER,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS print_job_events (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES print_jobs(id) ON DELETE CASCADE,
            previous_status TEXT,
            new_status TEXT NOT NULL,
            actor_type TEXT NOT NULL CHECK(actor_type IN ('customer', 'shopkeeper', 'gateway', 'system')),
            actor_id TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS device_heartbeats (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL REFERENCES shop_devices(id) ON DELETE CASCADE,
            printer_name TEXT,
            printer_status TEXT,
            accepting_jobs INTEGER NOT NULL DEFAULT 1,
            error_state TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_print_jobs_shop_id ON print_jobs(shop_id);
        CREATE INDEX IF NOT EXISTS idx_print_jobs_tracking_token ON print_jobs(tracking_token);
        CREATE INDEX IF NOT EXISTS idx_print_jobs_status ON print_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_print_jobs_payment_status ON print_jobs(payment_status);
        CREATE INDEX IF NOT EXISTS idx_print_jobs_created_at ON print_jobs(created_at);
        CREATE INDEX IF NOT EXISTS idx_print_job_events_job_id ON print_job_events(job_id);
        CREATE INDEX IF NOT EXISTS idx_shop_devices_shop_id ON shop_devices(shop_id);
        CREATE INDEX IF NOT EXISTS idx_pricing_rules_shop_id ON pricing_rules(shop_id);
        """)

        # Migration safe check for short_code column
        try:
            cur.execute("ALTER TABLE print_jobs ADD COLUMN short_code TEXT")
        except Exception:
            pass

        # Migration safe check for page_range column
        try:
            cur.execute("ALTER TABLE print_jobs ADD COLUMN page_range TEXT DEFAULT 'all'")
        except Exception:
            pass

        # Ensure min_charge defaults to 0.0 for honest pricing
        cur.execute("UPDATE pricing_rules SET min_charge = 0.0 WHERE min_charge = 5.0")

        # Seed initial shop data if empty
        cur.execute("SELECT COUNT(*) FROM shops")
        if cur.fetchone()[0] == 0:
            seed_default_data(conn)

        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("Failed to initialize database: %s", exc)
        raise
    finally:
        conn.close()


def seed_default_data(conn: sqlite3.Connection) -> None:
    """Seeds default shops, linear pricing rules, and shopkeeper credentials."""
    cur = conn.cursor()
    raw_token = "dev-gateway-token-1234567890"
    tok_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    pwd_hash = hash_password_py("admin123")

    shops_to_seed = [
        ("default", "Express Print Counter"),
        ("shop-default-1", "Central Print Express"),
        ("shop_default", "Main Counter Print"),
    ]

    for s_id, s_name in shops_to_seed:
        cur.execute(
            "INSERT OR IGNORE INTO shops (id, name, currency) VALUES (?, ?, ?)",
            (s_id, s_name, "INR"),
        )
        cur.execute(
            """INSERT OR IGNORE INTO pricing_rules (id, shop_id, bw_per_page, color_per_page, duplex_discount, min_charge)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), s_id, settings.bw_rate, settings.color_rate, settings.duplex_discount, settings.min_charge),
        )
        cur.execute(
            "INSERT OR IGNORE INTO shopkeepers (id, shop_id, username, password_hash) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), s_id, "admin", pwd_hash),
        )
        cur.execute(
            "INSERT OR IGNORE INTO shop_devices (id, shop_id, name, token_hash, is_active) VALUES (?, ?, ?, ?, 1)",
            (f"device-{s_id}", s_id, f"Counter Hardware Spooler ({s_id})", tok_hash),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Cryptography & Password Helpers
# ---------------------------------------------------------------------------

def hash_password_py(password: str) -> str:
    """Generates PBKDF2-SHA256 password hash."""
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32)
    return f"pbkdf2:sha256:{PBKDF2_ITERATIONS}${binascii.hexlify(salt).decode()}${binascii.hexlify(derived).decode()}"


def verify_password_py(password: str, stored_hash: str) -> bool:
    """Verifies candidate password against stored PBKDF2 hash."""
    if not stored_hash or not stored_hash.startswith("pbkdf2:sha256:"):
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 3:
            return False
        header = parts[0].split(":")
        iterations = int(header[2])
        salt = binascii.unhexlify(parts[1])
        expected = binascii.unhexlify(parts[2])
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
        return hmac.compare_digest(derived, expected)
    except Exception:
        return False


def hash_token_py(token: str) -> str:
    """Returns SHA256 hex digest of raw token."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def create_session_token_py(payload: dict, secret: str = SESSION_SECRET) -> str:
    """Creates signed URL-safe JWT-like session token."""
    session_data = {
        **payload,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(datetime.now(timezone.utc).timestamp()) + (86400 * 7),
    }
    raw_json = json.dumps(session_data, separators=(",", ":")).encode("utf-8")
    import base64

    encoded_payload = base64.urlsafe_b64encode(raw_json).decode().rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).digest()
    encoded_sig = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{encoded_payload}.{encoded_sig}"


def verify_session_token_py(token: str, secret: str = SESSION_SECRET) -> Optional[dict]:
    """Validates signature and expiration of session token."""
    if not token or "." not in token:
        return None
    try:
        import base64

        encoded_payload, encoded_sig = token.split(".", 1)

        def pad_b64(s: str) -> bytes:
            return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

        expected_sig = hmac.new(secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).digest()
        actual_sig = pad_b64(encoded_sig)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_bytes = pad_b64(encoded_payload)
        payload = json.loads(payload_bytes.decode("utf-8"))
        now = int(datetime.now(timezone.utc).timestamp())
        if "exp" in payload and payload["exp"] < now:
            return None
        return payload
    except Exception:
        return None
