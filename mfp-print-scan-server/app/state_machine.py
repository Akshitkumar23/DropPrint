"""
State Machine and Audit Logging for Print Jobs.
Enforces strict cash collection before approval, valid status transitions, and immutable audit logs.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Optional

from fastapi import HTTPException

ALLOWED_TRANSITIONS = {
    "UPLOADED": {"PENDING_PAYMENT", "CANCELLED"},
    "PENDING_PAYMENT": {"PAID", "REJECTED", "CANCELLED"},
    "PAID": {"APPROVED", "REJECTED", "CANCELLED"},
    "APPROVED": {"QUEUED", "PRINTING", "COMPLETED", "FAILED", "CANCELLED"},
    "QUEUED": {"PRINTING", "COMPLETED", "FAILED", "CANCELLED"},
    "PRINTING": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),
    "REJECTED": set(),
    "CANCELLED": set(),
    "FAILED": set(),
}


def validate_transition_py(current_status: str, target_status: str, payment_status: str = "UNPAID") -> None:
    """Validates state transitions and enforces the Cash-First Gate."""
    if current_status in {"COMPLETED", "REJECTED", "CANCELLED", "FAILED"}:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from terminal status '{current_status}' to '{target_status}'",
        )
    if target_status == "APPROVED" and (payment_status != "PAID" or current_status != "PAID"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Strict cash approval gate violated: job cannot be APPROVED without prior cash payment "
                f"(current status: {current_status}, payment_status: {payment_status})"
            ),
        )
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Illegal state transition from '{current_status}' to '{target_status}'",
        )


def record_job_event_py(
    conn: sqlite3.Connection,
    job_id: str,
    prev_status: Optional[str],
    new_status: str,
    actor_type: str,
    actor_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Appends an immutable audit event for the job."""
    conn.execute(
        """INSERT INTO print_job_events (id, job_id, previous_status, new_status, actor_type, actor_id, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (str(uuid.uuid4()), job_id, prev_status, new_status, actor_type, actor_id, notes),
    )
