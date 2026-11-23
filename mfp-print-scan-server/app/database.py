"""
Database compatibility shim for DropPrint Server.
Re-exports database symbols from app.core.database.
"""

from __future__ import annotations

from app.core.database import (
    DATA_DIR,
    DB_PATH,
    PBKDF2_ITERATIONS,
    SESSION_SECRET,
    create_session_token_py,
    get_db,
    get_db_connection,
    hash_password_py,
    hash_token_py,
    init_db,
    seed_default_data,
    verify_password_py,
    verify_session_token_py,
)

__all__ = [
    "DATA_DIR",
    "DB_PATH",
    "PBKDF2_ITERATIONS",
    "SESSION_SECRET",
    "create_session_token_py",
    "get_db",
    "get_db_connection",
    "hash_password_py",
    "hash_token_py",
    "init_db",
    "seed_default_data",
    "verify_password_py",
    "verify_session_token_py",
]
