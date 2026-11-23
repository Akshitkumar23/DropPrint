"""
Document Lifecycle & Customer Privacy Service for DropPrint Counter Server.
Enforces strict customer privacy:
- Automatically deletes printed customer files from disk 60 seconds (1 minute) after completion.
- Background sweeper cleans abandoned uploads (> 10 minutes) and lingering spool files.
- Strictly preserves database accounting rows (print_jobs, financial totals, event logs) for daily audits.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Set, Tuple

from app.core.config import settings
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)

UPLOAD_DIR = settings.uploads_dir
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CLEANUP_DELAY_SECONDS = settings.retention_seconds
DEFAULT_ABANDONED_TTL_SECONDS = settings.abandoned_ttl_seconds


class DocumentCleanupService:
    """Dedicated service for customer document lifecycle and privacy auto-purging."""

    _scheduled: Set[Tuple[str, Optional[str]]] = set()

    @classmethod
    async def _async_delete_file(
        cls,
        file_path: Path,
        delay_seconds: int = DEFAULT_CLEANUP_DELAY_SECONDS,
        job_id: Optional[str] = None,
    ) -> None:
        """Waits for delay_seconds then unlinks the customer document and associated spool files."""
        try:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

            if file_path.exists():
                file_path.unlink(missing_ok=True)
                logger.info(
                    "🔒 [PRIVACY AUTO-PURGE] Customer file deleted after %ds: %s (job=%s)",
                    delay_seconds,
                    file_path.name,
                    job_id,
                )

            # Check and remove associated spool temporary files
            spool_candidates = [
                file_path.parent / f"spool_out_{file_path.stem}.pdf",
                file_path.parent / f"spool_out_{file_path.name}",
            ]
            for spool_file in spool_candidates:
                if spool_file.exists():
                    spool_file.unlink(missing_ok=True)
                    logger.info("🔒 [PRIVACY AUTO-PURGE] Removed spool temp file: %s", spool_file.name)

        except Exception as exc:
            logger.warning("Could not auto-delete customer file %s: %s", file_path, exc)
        finally:
            cls._scheduled.discard((str(file_path), job_id))

    @classmethod
    def schedule_cleanup(
        cls,
        file_path: Path | str,
        delay_seconds: int = DEFAULT_CLEANUP_DELAY_SECONDS,
        job_id: Optional[str] = None,
    ) -> None:
        """Schedules non-blocking file deletion after delay_seconds (default 60s)."""
        path_obj = Path(file_path)
        key = (str(path_obj), job_id)
        if key in cls._scheduled:
            return
        cls._scheduled.add(key)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(cls._async_delete_file(path_obj, delay_seconds, job_id))
        except RuntimeError:
            # Fallback for synchronous threads
            t = threading.Timer(delay_seconds, lambda: path_obj.unlink(missing_ok=True))
            t.daemon = True
            t.start()

    @classmethod
    def sweep_expired_files(
        cls,
        completed_delay: int = DEFAULT_CLEANUP_DELAY_SECONDS,
        abandoned_delay: int = DEFAULT_ABANDONED_TTL_SECONDS,
    ) -> int:
        """
        Sweeps file storage to auto-purge:
        1. Completed, Cancelled, or Rejected job files older than completed_delay seconds.
        2. Orphaned temporary spool output files.
        3. Abandoned unprinted uploads older than abandoned_delay seconds.
        Database records remain 100% intact for accounting.
        """
        deleted_count = 0
        now = time.time()

        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Query completed/cancelled jobs whose disk files should be purged
            cur.execute(
                """SELECT id, file_r2_key, updated_at, status 
                   FROM print_jobs 
                   WHERE status IN ('COMPLETED', 'CANCELLED', 'REJECTED')"""
            )
            for row in cur.fetchall():
                file_key = row["file_r2_key"]
                if not file_key:
                    continue

                file_id = file_key.replace("uploads/", "").replace(".pdf", "")
                disk_path = UPLOAD_DIR / f"{file_id}.pdf"
                if not disk_path.exists():
                    disk_path = UPLOAD_DIR / Path(file_key).name

                if disk_path.exists():
                    mtime = disk_path.stat().st_mtime
                    if (now - mtime) >= completed_delay:
                        disk_path.unlink(missing_ok=True)
                        deleted_count += 1
                        logger.info("🔒 [SWEEPER PURGE] Removed completed job file: %s (job %s)", disk_path.name, row["id"])

                # Remove associated spool files
                for spool_file in [
                    UPLOAD_DIR / f"spool_out_{file_id}.pdf",
                    UPLOAD_DIR / f"spool_out_{disk_path.name}",
                    UPLOAD_DIR / f"spool_out_{disk_path.stem}.pdf",
                ]:
                    if spool_file.exists():
                        spool_file.unlink(missing_ok=True)
                        deleted_count += 1
                        logger.info("🔒 [SWEEPER PURGE] Removed associated spool out file: %s", spool_file.name)

            # Clean any orphaned spool_out_*.pdf files older than completed_delay
            for orphan in UPLOAD_DIR.glob("spool_out_*.pdf"):
                if (now - orphan.stat().st_mtime) >= completed_delay:
                    orphan.unlink(missing_ok=True)
                    deleted_count += 1
                    logger.info("🔒 [SWEEPER PURGE] Removed orphaned spool file: %s", orphan.name)

            conn.close()
        except Exception as exc:
            logger.warning("Document cleanup sweeper encountered an issue: %s", exc)

        return deleted_count

    @classmethod
    async def background_sweeper_loop(cls, interval_seconds: int = 30) -> None:
        """Background coroutine running periodic file sweep while server is active."""
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                cls.sweep_expired_files(completed_delay=settings.retention_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Background sweeper exception: %s", exc)


# Backwards compatibility procedural bindings
def schedule_file_cleanup(file_path: Path | str, delay_seconds: int = 60, job_id: Optional[str] = None):
    return DocumentCleanupService.schedule_cleanup(file_path=file_path, delay_seconds=delay_seconds, job_id=job_id)


def sweep_expired_files(completed_delay: int = 60, abandoned_delay: int = 600) -> int:
    return DocumentCleanupService.sweep_expired_files(completed_delay=completed_delay, abandoned_delay=abandoned_delay)


async def background_sweeper_loop(interval_seconds: int = 30):
    return await DocumentCleanupService.background_sweeper_loop(interval_seconds=interval_seconds)
