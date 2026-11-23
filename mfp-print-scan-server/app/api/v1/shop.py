"""
Shopkeeper Dashboard and Hardware Spooling Endpoints (v1).
Handles authentication, real-time job queue filtering (60s auto-purge), cash collection,
atomic receive-and-print approval, pricing rule updates, and device management.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import (
    create_session_token_py,
    get_db,
    hash_token_py,
    verify_password_py,
    verify_session_token_py,
)
from app.core.exceptions import JobNotFoundError, PricingError
from app.services.spooler import spooler_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shop", tags=["shopkeeper"])


class ShopLoginRequest(BaseModel):
    username: str
    password: str
    shop_id: Optional[str] = None


class PricingUpdateRequest(BaseModel):
    bw_per_page: float = Field(..., ge=0.0)
    color_per_page: float = Field(..., ge=0.0)
    duplex_discount: float = Field(0.5, ge=0.0)
    min_charge: float = Field(0.0, ge=0.0)


class JobActionReason(BaseModel):
    reason: Optional[str] = None


def get_current_shopkeeper(request: Request) -> Dict[str, Any]:
    """Zero-barrier print shop counter: allows unauthenticated counter operator or verifies token if passed."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        payload = verify_session_token_py(token)
        if payload:
            return payload
    return {"sub": "admin", "username": "admin", "shop_id": "default", "role": "owner"}


def get_optional_shopkeeper(
    authorization: Optional[str] = Header(None),
    shop_id: Optional[str] = Query(None),
) -> Optional[Dict[str, Any]]:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        session = verify_session_token_py(token)
        if session:
            return session
    if shop_id:
        return {"sub": "anonymous", "shop_id": shop_id, "role": "customer"}
    return None


@router.post("/login")
def shop_login(body: ShopLoginRequest, conn: sqlite3.Connection = Depends(get_db)):
    """Authenticates shopkeeper operator and issues signed session token."""
    cur = conn.cursor()
    if body.shop_id:
        cur.execute(
            "SELECT id, shop_id, username, password_hash FROM shopkeepers WHERE username = ? AND shop_id = ?",
            (body.username, body.shop_id),
        )
    else:
        cur.execute(
            "SELECT id, shop_id, username, password_hash FROM shopkeepers WHERE username = ?",
            (body.username,),
        )
    row = cur.fetchone()

    if not row or not verify_password_py(body.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = create_session_token_py({
        "sub": row["id"],
        "shop_id": row["shop_id"],
        "username": row["username"],
    })
    return {
        "token": token,
        "shopkeeper": {
            "id": row["id"],
            "shop_id": row["shop_id"],
            "username": row["username"],
        },
    }


@router.get("/jobs")
def shop_list_jobs(
    status: Optional[str] = None,
    all_history: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Lists real queue of jobs from database sorted by created_at DESC.
    Includes today's aggregate statistics summary card values.
    By default, completed/terminal jobs older than 60 seconds are filtered out
    from the active counter view so the queue stays clean.
    """
    cur = conn.cursor()

    # Query today's aggregate statistics for metric cards
    cur.execute("""
        SELECT 
            COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as completed_today,
            COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN total_price ELSE 0 END), 0.0) as revenue_today,
            COUNT(CASE WHEN status IN ('PENDING_PAYMENT', 'UPLOADED') THEN 1 END) as pending_count,
            COALESCE(SUM(CASE WHEN status IN ('PENDING_PAYMENT', 'UPLOADED') THEN total_price ELSE 0 END), 0.0) as pending_cash
        FROM print_jobs
        WHERE date(created_at) = date('now')
    """)
    stats_row = cur.fetchone()
    stats = {
        "completed_today": stats_row["completed_today"] if stats_row else 0,
        "revenue_today": round(float(stats_row["revenue_today"] if stats_row else 0.0), 2),
        "pending_count": stats_row["pending_count"] if stats_row else 0,
        "pending_cash": round(float(stats_row["pending_cash"] if stats_row else 0.0), 2),
    }

    query = "SELECT * FROM print_jobs"
    params: List[Any] = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(query, tuple(params))
    rows = cur.fetchall()

    now_utc = datetime.now(timezone.utc)
    jobs = []
    for r in rows:
        d = dict(r)
        if not d.get("short_code"):
            token = d.get("tracking_token") or d["id"]
            d["short_code"] = f"PRN-{token[:4].upper()}"

        age_seconds = 0
        updated_str = d.get("updated_at") or d.get("created_at") or ""
        if updated_str:
            try:
                if "T" in updated_str:
                    dt = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                else:
                    dt = datetime.strptime(updated_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                age_seconds = max(0, int((now_utc - dt).total_seconds()))
            except Exception:
                age_seconds = 0

        d["age_seconds"] = age_seconds

        # Active queue filter: exclude terminal jobs > 60s and stale unprinted jobs > 10m unless all_history is requested
        if not all_history and not status:
            if d.get("status") in ("COMPLETED", "CANCELLED", "REJECTED", "FAILED") and age_seconds >= settings.retention_seconds:
                continue
            if d.get("status") in ("PENDING_PAYMENT", "UPLOADED") and age_seconds >= settings.abandoned_ttl_seconds:
                continue

        jobs.append(d)

    return {"jobs": jobs, "stats": stats}


@router.post("/jobs/{job_id}/mark-paid")
def shop_mark_paid(
    job_id: str,
    session: dict = Depends(get_current_shopkeeper),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Confirms cash payment received at the counter."""
    try:
        actor_id = session.get("sub", "admin")
        return spooler_service.mark_paid(conn=conn, job_id=job_id, actor_id=actor_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/jobs/{job_id}/approve")
def shop_approve_job(
    job_id: str,
    session: dict = Depends(get_current_shopkeeper),
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Strict Cash Approval Gate:
    Validates cash payment, marks job APPROVED, and immediately prints directly
    via WindowsPrintBackend on the local machine hardware spooler.
    """
    try:
        actor_id = session.get("sub", "admin")
        return spooler_service.approve_and_print(conn=conn, job_id=job_id, actor_id=actor_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/jobs/{job_id}/receive-and-print")
def shop_receive_and_print(
    job_id: str,
    session: dict = Depends(get_current_shopkeeper),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Marks cash payment received AND immediately approves and prints to local spooler in one atomic action."""
    try:
        actor_id = session.get("sub", "admin")
        return spooler_service.receive_and_print(conn=conn, job_id=job_id, actor_id=actor_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/jobs/{job_id}/reject")
def shop_reject_job(
    job_id: str,
    body: Optional[JobActionReason] = None,
    session: dict = Depends(get_current_shopkeeper),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Rejects a print job."""
    try:
        reason = body.reason if body and body.reason else "Rejected by shopkeeper"
        actor_id = session.get("sub", "admin")
        return spooler_service.reject_job(conn=conn, job_id=job_id, reason=reason, actor_id=actor_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/jobs/{job_id}/cancel")
def shop_cancel_job(
    job_id: str,
    body: Optional[JobActionReason] = None,
    session: dict = Depends(get_current_shopkeeper),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Cancels a print job."""
    try:
        reason = body.reason if body and body.reason else "Cancelled by shopkeeper"
        actor_id = session.get("sub", "admin")
        return spooler_service.cancel_job(conn=conn, job_id=job_id, reason=reason, actor_id=actor_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/pricing")
def shop_get_pricing(
    session: Optional[dict] = Depends(get_optional_shopkeeper),
    shop_id: Optional[str] = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Returns active pricing rules for the shop."""
    target_shop_id = (session["shop_id"] if session else None) or shop_id or "default"
    cur = conn.cursor()
    cur.execute("SELECT * FROM pricing_rules WHERE shop_id = ?", (target_shop_id,))
    row = cur.fetchone()
    if not row:
        return {
            "shop_id": target_shop_id,
            "bw_per_page": settings.bw_rate,
            "color_per_page": settings.color_rate,
            "duplex_discount": settings.duplex_discount,
            "min_charge": settings.min_charge,
            "currency": "INR",
        }
    res = dict(row)
    if "currency" not in res:
        res["currency"] = "INR"
    return res


@router.put("/pricing")
def shop_update_pricing(
    body: PricingUpdateRequest,
    session: dict = Depends(get_current_shopkeeper),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Updates shop pricing rules."""
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO pricing_rules (id, shop_id, bw_per_page, color_per_page, duplex_discount, min_charge, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(shop_id) DO UPDATE SET
             bw_per_page = excluded.bw_per_page,
             color_per_page = excluded.color_per_page,
             duplex_discount = excluded.duplex_discount,
             min_charge = excluded.min_charge,
             updated_at = datetime('now')""",
        (str(uuid.uuid4()), session["shop_id"], body.bw_per_page, body.color_per_page, body.duplex_discount, body.min_charge),
    )
    conn.commit()
    return {"status": "ok", "shop_id": session["shop_id"], **body.model_dump()}


@router.get("/devices")
def shop_list_devices(
    session: dict = Depends(get_current_shopkeeper),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Lists registered gateway devices."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, is_active, last_seen_at, created_at FROM shop_devices WHERE shop_id = ?",
        (session["shop_id"],),
    )
    return {"devices": [dict(r) for r in cur.fetchall()]}


@router.post("/devices", status_code=status.HTTP_201_CREATED)
def shop_create_device(
    payload: Dict[str, Any] = None,
    session: dict = Depends(get_current_shopkeeper),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Creates a new gateway device authorization token."""
    name = payload.get("name", "Hardware Spooler Gateway") if payload else "Hardware Spooler Gateway"
    raw_token = uuid.uuid4().hex + uuid.uuid4().hex
    tok_hash = hash_token_py(raw_token)
    device_id = str(uuid.uuid4())

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO shop_devices (id, shop_id, name, token_hash, is_active, created_at) VALUES (?, ?, ?, ?, 1, datetime('now'))",
        (device_id, session["shop_id"], name, tok_hash),
    )
    conn.commit()

    return {
        "device_id": device_id,
        "name": name,
        "token": raw_token,
        "message": "Save this token! It will not be shown again.",
    }
