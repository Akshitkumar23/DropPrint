"""
Dedicated Hardware Printing and Spooler Service for DropPrint Counter Server.
Interfaces directly with WindowsPrintBackend on Windows OS or fallback backend on POSIX.
Enforces strict cash approval gates, robust status transitions, and audit trail logging.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.exceptions import JobNotFoundError, SpoolerError
from app.printing.base import PrintError
from app.printing.factory import get_backend
from app.services.cleanup import DocumentCleanupService
from app.state_machine import record_job_event_py, validate_transition_py

logger = logging.getLogger(__name__)

UPLOAD_DIR = settings.uploads_dir


class SpoolerService:
    """Dedicated service for printer hardware communication and job spooling."""

    def __init__(self):
        self.backend = get_backend()

    def get_backend_instance(self):
        """Returns the active backend instance."""
        return self.backend

    def list_printers(self) -> List[Dict[str, Any]]:
        """Lists locally installed printers."""
        try:
            printers = self.backend.list_printers()
            return [{"name": p.name, "is_default": p.is_default} for p in printers]
        except PrintError as exc:
            logger.error("Failed to list printers: %s", exc)
            raise SpoolerError(f"Could not retrieve printer list: {exc}")

    def printer_status(self, printer_name: str) -> Optional[Dict[str, Any]]:
        """Queries live hardware status of printer via WMI."""
        try:
            status = self.backend.printer_status(printer_name)
            if status is None:
                return {"state": "idle", "accepting_jobs": True, "reasons": []}
            return {
                "state": status.state,
                "accepting_jobs": status.accepting_jobs,
                "reasons": status.reasons,
            }
        except Exception as exc:
            logger.warning("Failed to query printer status for %s: %s", printer_name, exc)
            return {"state": "unknown", "accepting_jobs": True, "reasons": [str(exc)]}

    def mark_paid(
        self,
        conn: sqlite3.Connection,
        job_id: str,
        actor_id: Optional[str] = "admin",
    ) -> Dict[str, Any]:
        """Confirms cash payment received at counter."""
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM print_jobs WHERE id = ? OR tracking_token = ? OR short_code = ?",
            (job_id, job_id, job_id),
        )
        job = cur.fetchone()
        if not job:
            raise JobNotFoundError(f"Job '{job_id}' not found")

        real_id = job["id"]
        validate_transition_py(job["status"], "PAID", "PAID")

        cur.execute(
            "SELECT id FROM shopkeepers WHERE id = ? OR username = ?",
            (actor_id, actor_id),
        )
        sk = cur.fetchone()
        resolved_actor_id = sk["id"] if sk else actor_id

        cur.execute(
            """UPDATE print_jobs
               SET status = 'PAID', payment_status = 'PAID', updated_at = datetime('now')
               WHERE id = ?""",
            (real_id,),
        )
        record_job_event_py(
            conn,
            real_id,
            job["status"],
            "PAID",
            "shopkeeper",
            actor_id=resolved_actor_id,
            notes="Shopkeeper confirmed cash payment in person at the counter",
        )
        conn.commit()

        return {"id": real_id, "status": "PAID", "payment_status": "PAID"}

    def approve_and_print(
        self,
        conn: sqlite3.Connection,
        job_id: str,
        actor_id: Optional[str] = "admin",
    ) -> Dict[str, Any]:
        """
        Strict Cash Approval Gate & Direct Spooler Printing:
        Validates cash payment, marks job APPROVED, and immediately prints directly
        via WindowsPrintBackend on the local machine hardware spooler.
        """
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM print_jobs WHERE id = ? OR tracking_token = ? OR short_code = ?",
            (job_id, job_id, job_id),
        )
        job = cur.fetchone()
        if not job:
            raise JobNotFoundError(f"Job '{job_id}' not found")

        real_id = job["id"]

        # Strict Cash Gate: Cannot approve unless payment_status is PAID
        validate_transition_py(job["status"], "APPROVED", job["payment_status"])

        # Resolve shopkeeper UUID for approved_by foreign key reference
        cur.execute(
            "SELECT id FROM shopkeepers WHERE id = ? OR username = ?",
            (actor_id, actor_id),
        )
        sk = cur.fetchone()
        resolved_actor_id = sk["id"] if sk else None

        cur.execute(
            """UPDATE print_jobs
               SET status = 'APPROVED', approved_by = ?, approved_at = datetime('now'), updated_at = datetime('now')
               WHERE id = ?""",
            (resolved_actor_id, real_id),
        )
        record_job_event_py(
            conn,
            real_id,
            job["status"],
            "APPROVED",
            "shopkeeper",
            actor_id=resolved_actor_id or actor_id,
            notes="Shopkeeper approved print job for spooling",
        )
        conn.commit()

        # Locate customer print file on disk
        file_key = job["file_r2_key"]
        file_id = file_key.replace("uploads/", "").replace(".pdf", "")
        disk_path = UPLOAD_DIR / f"{file_id}.pdf"
        if not disk_path.exists():
            candidate = UPLOAD_DIR / Path(file_key).name
            if candidate.exists():
                disk_path = candidate

        if not disk_path.exists():
            logger.error("Job %s print file missing on disk: %s", real_id, disk_path)
            cur.execute(
                "UPDATE print_jobs SET status = 'FAILED', error_message = ?, updated_at = datetime('now') WHERE id = ?",
                ("Uploaded PDF file not found on disk", real_id),
            )
            record_job_event_py(conn, real_id, "APPROVED", "FAILED", "system", notes="File missing on disk")
            conn.commit()
            raise JobNotFoundError("Print file missing on disk")

        # Map print settings
        page_range = "all"
        try:
            if "page_range" in job.keys() and job["page_range"]:
                page_range = job["page_range"]
        except Exception:
            page_range = "all"

        print_options = {
            "color": "mono" if job["color_mode"] == "bw" else "color",
            "duplex": "duplex_long" if job["duplex_mode"] == "duplex" else "simplex",
            "paper_size": job["paper_size"] or "A4",
            "quality": "normal",
            "page_range": page_range,
        }

        try:
            logger.info("Directly dispatching job %s to local print backend: %s", real_id, disk_path)
            result = self.backend.print_file(
                file_path=disk_path,
                printer_name=None,  # OS default printer
                copies=job["copies"],
                options=print_options,
            )

            spooler_job_id = None
            if result and result.job_id:
                try:
                    spooler_job_id = int(result.job_id)
                except (ValueError, TypeError):
                    spooler_job_id = None

            cur.execute(
                """UPDATE print_jobs
                   SET status = 'COMPLETED', spooler_job_id = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (spooler_job_id, real_id),
            )
            note = result.note if result else "Dispatched to local spooler"
            record_job_event_py(
                conn,
                real_id,
                "APPROVED",
                "COMPLETED",
                "shopkeeper",
                actor_id=actor_id,
                notes=f"Spooler job submitted successfully: {result.job_id if result else 'OK'} ({note})",
            )
            conn.commit()

            # Schedule document auto-purge 60s after print completion for customer privacy
            DocumentCleanupService.schedule_cleanup(
                disk_path,
                delay_seconds=settings.retention_seconds,
                job_id=real_id,
            )

            return {
                "id": real_id,
                "status": "COMPLETED",
                "spooler_job_id": result.job_id if result else None,
                "note": note,
                "approved_by": actor_id,
            }

        except Exception as exc:
            logger.exception("Hardware printing error for job %s: %s", real_id, exc)
            err_msg = str(exc)
            cur.execute(
                """UPDATE print_jobs
                   SET status = 'FAILED', error_message = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (err_msg, real_id),
            )
            record_job_event_py(
                conn,
                real_id,
                "APPROVED",
                "FAILED",
                "system",
                notes=f"Hardware spooler failure: {err_msg}",
            )
            conn.commit()
            return {
                "id": real_id,
                "status": "FAILED",
                "error_message": err_msg,
                "approved_by": actor_id,
            }

    def receive_and_print(
        self,
        conn: sqlite3.Connection,
        job_id: str,
        actor_id: Optional[str] = "admin",
    ) -> Dict[str, Any]:
        """Marks cash payment received AND immediately approves and prints to local spooler."""
        paid_res = self.mark_paid(conn=conn, job_id=job_id, actor_id=actor_id)
        return self.approve_and_print(conn=conn, job_id=paid_res["id"], actor_id=actor_id)

    def reject_job(
        self,
        conn: sqlite3.Connection,
        job_id: str,
        reason: str = "Rejected by shopkeeper",
        actor_id: Optional[str] = "admin",
    ) -> Dict[str, Any]:
        """Rejects a print job."""
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM print_jobs WHERE id = ? OR tracking_token = ? OR short_code = ?",
            (job_id, job_id, job_id),
        )
        job = cur.fetchone()
        if not job:
            raise JobNotFoundError(f"Job '{job_id}' not found")

        real_id = job["id"]
        validate_transition_py(job["status"], "REJECTED")

        cur.execute(
            "UPDATE print_jobs SET status = 'REJECTED', error_message = ?, updated_at = datetime('now') WHERE id = ?",
            (reason, real_id),
        )
        record_job_event_py(
            conn,
            real_id,
            job["status"],
            "REJECTED",
            "shopkeeper",
            actor_id=actor_id,
            notes=reason,
        )
        conn.commit()

        # Clean file after rejection
        file_key = job["file_r2_key"]
        if file_key:
            file_id = file_key.replace("uploads/", "").replace(".pdf", "")
            disk_path = UPLOAD_DIR / f"{file_id}.pdf"
            if disk_path.exists():
                DocumentCleanupService.schedule_cleanup(disk_path, delay_seconds=settings.retention_seconds, job_id=real_id)

        return {"id": real_id, "status": "REJECTED", "reason": reason}

    def cancel_job(
        self,
        conn: sqlite3.Connection,
        job_id: str,
        reason: str = "Cancelled by shopkeeper",
        actor_id: Optional[str] = "admin",
    ) -> Dict[str, Any]:
        """Cancels a print job."""
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM print_jobs WHERE id = ? OR tracking_token = ? OR short_code = ?",
            (job_id, job_id, job_id),
        )
        job = cur.fetchone()
        if not job:
            raise JobNotFoundError(f"Job '{job_id}' not found")

        real_id = job["id"]
        validate_transition_py(job["status"], "CANCELLED")

        cur.execute(
            "UPDATE print_jobs SET status = 'CANCELLED', error_message = ?, updated_at = datetime('now') WHERE id = ?",
            (reason, real_id),
        )
        record_job_event_py(
            conn,
            real_id,
            job["status"],
            "CANCELLED",
            "shopkeeper",
            actor_id=actor_id,
            notes=reason,
        )
        conn.commit()

        file_key = job["file_r2_key"]
        if file_key:
            file_id = file_key.replace("uploads/", "").replace(".pdf", "")
            disk_path = UPLOAD_DIR / f"{file_id}.pdf"
            if disk_path.exists():
                DocumentCleanupService.schedule_cleanup(disk_path, delay_seconds=settings.retention_seconds, job_id=real_id)

        return {"id": real_id, "status": "CANCELLED", "reason": reason}


# Singleton spooler service instance
spooler_service = SpoolerService()
