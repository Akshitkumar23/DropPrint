"""
Gateway compatibility routes for remote/external Windows Print Gateways.
Supports polling, claiming, file downloading, and status reporting.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import ROOT
from .database import get_db, hash_token_py
from .state_machine import record_job_event_py, validate_transition_py

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gateway", tags=["gateway"])

UPLOAD_DIR = Path(ROOT) / "uploads"


class GatewayHeartbeatRequest(BaseModel):
    printer_name: Optional[str] = None
    printer_status: Optional[str] = "READY"
    accepting_jobs: int = 1
    error_state: Optional[str] = None


class GatewayStatusRequest(BaseModel):
    outcome: str
    spooler_job_id: Optional[int] = None
    error_message: Optional[str] = None


def get_current_gateway_device(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid gateway Authorization header")
    token = auth[7:].strip()
    tok_hash = hash_token_py(token)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, shop_id, name, is_active FROM shop_devices WHERE token_hash = ? AND is_active = 1",
        (tok_hash,),
    )
    device = cur.fetchone()
    if not device:
        raise HTTPException(status_code=401, detail="Invalid or inactive gateway device token")
    return dict(device)


@router.post("/heartbeat")
def gateway_heartbeat(
    body: GatewayHeartbeatRequest,
    device: dict = Depends(get_current_gateway_device),
    conn: sqlite3.Connection = Depends(get_db),
):
    cur = conn.cursor()
    cur.execute("UPDATE shop_devices SET last_seen_at = datetime('now') WHERE id = ?", (device["id"],))
    cur.execute(
        """INSERT INTO device_heartbeats (id, device_id, printer_name, printer_status, accepting_jobs, error_state, created_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
        (str(uuid.uuid4()), device["id"], body.printer_name, body.printer_status, body.accepting_jobs, body.error_state),
    )
    conn.commit()
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/jobs/pending")
def gateway_get_pending_jobs(
    device: dict = Depends(get_current_gateway_device),
    conn: sqlite3.Connection = Depends(get_db),
):
    cur = conn.cursor()
    cur.execute(
        """SELECT id, shop_id, tracking_token, filename, file_r2_key, file_size, page_count,
                  copies, color_mode, duplex_mode, paper_size, status, created_at
           FROM print_jobs
           WHERE shop_id = ? AND status IN ('APPROVED', 'QUEUED')
           ORDER BY created_at ASC""",
        (device["shop_id"],),
    )
    jobs_list = [dict(r) for r in cur.fetchall()]
    return {"pending_jobs": jobs_list, "jobs": jobs_list}


@router.post("/jobs/{job_id}/claim")
def gateway_claim_job(
    job_id: str,
    device: dict = Depends(get_current_gateway_device),
    conn: sqlite3.Connection = Depends(get_db),
):
    cur = conn.cursor()
    cur.execute(
        """UPDATE print_jobs
           SET status = 'PRINTING', gateway_device_id = ?, updated_at = datetime('now')
           WHERE id = ? AND shop_id = ? AND status IN ('APPROVED', 'QUEUED')""",
        (device["id"], job_id, device["shop_id"]),
    )
    if cur.rowcount == 0:
        cur.execute("SELECT id, status FROM print_jobs WHERE id = ? AND shop_id = ?", (job_id, device["shop_id"]))
        existing = cur.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Job not found")
        raise HTTPException(
            status_code=409,
            detail=f"Job cannot be claimed: current status is '{existing['status']}', already claimed or not approved",
        )

    record_job_event_py(
        conn,
        job_id,
        "APPROVED",
        "PRINTING",
        "gateway",
        actor_id=device["id"],
        notes=f"Gateway device '{device['name']}' claimed job for spooling",
    )
    conn.commit()

    return {"id": job_id, "status": "PRINTING", "gateway_device_id": device["id"]}


@router.get("/jobs/{job_id}/download")
def gateway_download_job(
    job_id: str,
    device: dict = Depends(get_current_gateway_device),
    conn: sqlite3.Connection = Depends(get_db),
):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, shop_id, file_r2_key, filename, status FROM print_jobs WHERE id = ? AND shop_id = ?",
        (job_id, device["shop_id"]),
    )
    job = cur.fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] not in ("APPROVED", "QUEUED", "PRINTING"):
        raise HTTPException(status_code=403, detail=f"File download not permitted for status '{job['status']}'")

    file_id = job["file_r2_key"].replace("uploads/", "").replace(".pdf", "")
    disk_path = UPLOAD_DIR / f"{file_id}.pdf"
    if not disk_path.exists():
        disk_path = UPLOAD_DIR / Path(job["file_r2_key"]).name
    if not disk_path.exists():
        raise HTTPException(status_code=404, detail="File not found in local storage")

    return FileResponse(
        path=str(disk_path),
        filename=job["filename"],
        media_type="application/pdf",
    )


@router.post("/jobs/{job_id}/status")
def gateway_update_status(
    job_id: str,
    body: GatewayStatusRequest,
    device: dict = Depends(get_current_gateway_device),
    conn: sqlite3.Connection = Depends(get_db),
):
    if body.outcome not in ("COMPLETED", "FAILED"):
        raise HTTPException(status_code=400, detail="outcome must be 'COMPLETED' or 'FAILED'")

    cur = conn.cursor()
    cur.execute("SELECT id, shop_id, status FROM print_jobs WHERE id = ? AND shop_id = ?", (job_id, device["shop_id"]))
    job = cur.fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    validate_transition_py(job["status"], body.outcome)

    cur.execute(
        """UPDATE print_jobs
           SET status = ?, spooler_job_id = ?, error_message = ?, updated_at = datetime('now')
           WHERE id = ?""",
        (body.outcome, body.spooler_job_id, body.error_message, job_id),
    )
    notes = (
        f"Spooler job ID {body.spooler_job_id} successfully completed"
        if body.outcome == "COMPLETED"
        else f"Print job failed: {body.error_message}"
    )
    record_job_event_py(conn, job_id, job["status"], body.outcome, "gateway", actor_id=device["id"], notes=notes)
    conn.commit()

    return {
        "id": job_id,
        "status": body.outcome,
        "spooler_job_id": body.spooler_job_id,
        "error_message": body.error_message,
    }
