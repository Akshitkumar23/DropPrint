"""
Cleanup and Document Lifecycle compatibility shim for DropPrint Server.
Re-exports cleanup symbols from app.services.cleanup.
"""

from __future__ import annotations

from app.services.cleanup import (
    DEFAULT_ABANDONED_TTL_SECONDS as ABANDONED_TTL_SECONDS,
    DEFAULT_CLEANUP_DELAY_SECONDS as CLEANUP_DELAY_SECONDS,
    UPLOAD_DIR,
    DocumentCleanupService,
    background_sweeper_loop,
    schedule_file_cleanup,
    sweep_expired_files,
)

__all__ = [
    "ABANDONED_TTL_SECONDS",
    "CLEANUP_DELAY_SECONDS",
    "UPLOAD_DIR",
    "DocumentCleanupService",
    "background_sweeper_loop",
    "schedule_file_cleanup",
    "sweep_expired_files",
]
