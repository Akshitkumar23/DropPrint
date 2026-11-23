"""
Configuration compatibility shim for DropPrint Server.
Re-exports configuration symbols from app.core.config.
"""

from __future__ import annotations

from app.core.config import (
    CONFIG_PATH,
    EXAMPLE_PATH,
    HASH_ITERATIONS,
    HASH_PREFIX,
    MAIN_SECTION,
    ROOT,
    Settings,
    hash_password,
    load,
    settings,
    verify_password,
)

__all__ = [
    "CONFIG_PATH",
    "EXAMPLE_PATH",
    "HASH_ITERATIONS",
    "HASH_PREFIX",
    "MAIN_SECTION",
    "ROOT",
    "Settings",
    "hash_password",
    "load",
    "settings",
    "verify_password",
]
