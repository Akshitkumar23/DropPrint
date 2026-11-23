"""
Customer Self-Service API Endpoints (v1).
Handles document uploads, real-time pricing estimates, job submission, and tracking.
"""

from __future__ import annotations

import io
import json
import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from PIL import Image
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import JobNotFoundError, PricingError, ShopNotFoundError
from app.printing.convert import page_count as get_pdf_page_count
from app.printing.windows_print import parse_page_range
from app.services.converter import OFFICE_EXTENSIONS, convert_office_to_pdf
from app.services.pricing import PricingService
from app.state_machine import record_job_event_py

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customer", tags=["customer"])

UPLOAD_DIR = settings.uploads_dir
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class EstimateRequest(BaseModel):
    shop_id: str = "default"
    page_count: int = Field(1, ge=1)
    copies: int = Field(1, ge=1)
    color_mode: str = "bw"
    duplex_mode: str = "simplex"
    page_range: Optional[str] = None


class SubmitJobRequest(BaseModel):
    shop_id: str = "default"
    file_r2_key: str
    filename: str
    file_size: int
    page_count: int = Field(1, ge=1)
    copies: int = Field(1, ge=1)
    color_mode: str = "bw"
    duplex_mode: str = "simplex"
    paper_size: str = "A4"
    page_range: Optional[str] = "all"


CHUNK_SIZE = 64 * 1024


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def customer_upload(request: Request, file: UploadFile = File(...)):
    """Uploads customer document, verifying PDF or Image format and converting images to PDF."""
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum allowed size of {settings.max_upload_size_mb}MB",
                )
        except ValueError:
            pass

    content = bytearray()
    try:
        while chunk := await file.read(CHUNK_SIZE):
            content.extend(chunk)
            if len(content) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum allowed size of {settings.max_upload_size_mb}MB",
                )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to read uploaded file: %s", exc)
        raise HTTPException(status_code=400, detail="Could not read uploaded file")

    header = bytes(content[:5])

    file_id = str(uuid.uuid4())
    filename = Path(file.filename or "document.pdf").name
    suffix = Path(filename).suffix.lower()
    disk_path = UPLOAD_DIR / f"{file_id}.pdf"

    if header == b"%PDF-":
        disk_path.write_bytes(content)
    elif suffix in OFFICE_EXTENSIONS:
        temp_input = UPLOAD_DIR / f"temp_{file_id}{suffix}"
        try:
            temp_input.write_bytes(content)
            converted = convert_office_to_pdf(temp_input, disk_path)
            if not converted or not disk_path.exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not convert office document '{filename}' to PDF. Please ensure the file is valid or convert to PDF before uploading.",
                )
        finally:
            temp_input.unlink(missing_ok=True)
    else:
        try:
            img = Image.open(io.BytesIO(content)).convert("RGB")
            img.save(disk_path, "PDF")
        except Exception as exc:
            logger.warning("Unsupported file format upload attempted: %s", exc)
            raise HTTPException(
                status_code=400,
                detail="Invalid file type: File must be a valid PDF, Office Document, or Image",
            )

    return {
        "file_r2_key": f"uploads/{file_id}.pdf",
        "filename": filename,
        "file_size": len(content),
    }


@router.post("/estimate")
def customer_estimate(body: EstimateRequest, conn: sqlite3.Connection = Depends(get_db)):
    """Calculates price quote based on shop pricing rules."""
    cur = conn.cursor()
    cur.execute(
        "SELECT bw_per_page, color_per_page, duplex_discount, min_charge FROM pricing_rules WHERE shop_id = ?",
        (body.shop_id,),
    )
    row = cur.fetchone()
    rules = dict(row) if row else {
        "bw_per_page": settings.bw_rate,
        "color_per_page": settings.color_rate,
        "duplex_discount": settings.duplex_discount,
        "min_charge": settings.min_charge,
    }

    cur.execute("SELECT currency FROM shops WHERE id = ?", (body.shop_id,))
    shop_row = cur.fetchone()
    currency = shop_row["currency"] if shop_row else "INR"

    eff_page_count = body.page_count
    if body.page_range and body.page_range.strip().lower() not in ("all", "*", ""):
        selected_pages = parse_page_range(body.page_range, body.page_count)
        if selected_pages:
            eff_page_count = len(selected_pages)

    try:
        estimate = PricingService.calculate_price(
            page_count=eff_page_count,
            copies=body.copies,
            color_mode=body.color_mode,
            duplex_mode=body.duplex_mode,
            rules=rules,
        )
    except PricingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {**estimate, "currency": currency}


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
async def customer_create_job(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    file: Optional[UploadFile] = File(None),
    shop_id: Optional[str] = Form(None),
    copies: Optional[int] = Form(None),
    color_mode: Optional[str] = Form(None),
    duplex_mode: Optional[str] = Form(None),
    paper_size: Optional[str] = Form(None),
    page_count: Optional[int] = Form(None),
    pages: Optional[int] = Form(None),
    page_range: Optional[str] = Form(None),
):
    """
    Submits a print job awaiting cash counter payment.
    Accepts both multipart/form-data (with direct file upload) and application/json.
    """
    if copies is not None and copies < 1:
        raise HTTPException(status_code=422, detail="Copies must be at least 1")
    req_pages = pages if pages is not None else page_count
    if req_pages is not None and req_pages < 1:
        raise HTTPException(status_code=422, detail="Pages must be at least 1")

    target_shop_id = shop_id or "default"
    target_copies = copies if copies is not None else 1
    target_color_mode = "color" if color_mode == "color" else "bw"
    target_duplex_mode = "duplex" if duplex_mode == "duplex" else "simplex"
    target_paper_size = paper_size or "A4"
    target_page_count = req_pages or 1
    target_page_range = page_range or "all"
    target_filename = "document.pdf"
    file_r2_key = ""
    file_size = 0

    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            raw_body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        try:
            req_body = SubmitJobRequest(**raw_body)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        if req_body.file_size > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size of {settings.max_upload_size_mb}MB",
            )

        target_shop_id = req_body.shop_id
        target_copies = req_body.copies
        target_color_mode = "color" if req_body.color_mode == "color" else "bw"
        target_duplex_mode = "duplex" if req_body.duplex_mode == "duplex" else "simplex"
        target_paper_size = req_body.paper_size
        target_page_count = req_body.page_count
        target_page_range = req_body.page_range or "all"
        target_filename = req_body.filename
        file_r2_key = req_body.file_r2_key
        file_size = req_body.file_size

    elif file is not None:
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size of {settings.max_upload_size_mb}MB",
                    )
            except ValueError:
                pass

        content = bytearray()
        try:
            while chunk := await file.read(CHUNK_SIZE):
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size of {settings.max_upload_size_mb}MB",
                    )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Error reading file upload: %s", exc)
            raise HTTPException(status_code=400, detail="Failed to read file payload")

        header = bytes(content[:5])
        file_id = str(uuid.uuid4())
        target_filename = Path(file.filename or "document.pdf").name
        suffix = Path(target_filename).suffix.lower()
        disk_path = UPLOAD_DIR / f"{file_id}.pdf"
        file_size = len(content)

        if header == b"%PDF-":
            disk_path.write_bytes(content)
            try:
                detected_pages = get_pdf_page_count(disk_path)
                if detected_pages > 0 and (target_page_count is None or target_page_count == 1):
                    target_page_count = detected_pages
            except Exception as exc:
                logger.warning("Could not count pages via pypdfium2: %s", exc)
        elif suffix in OFFICE_EXTENSIONS:
            temp_input = UPLOAD_DIR / f"temp_{file_id}{suffix}"
            try:
                temp_input.write_bytes(content)
                converted = convert_office_to_pdf(temp_input, disk_path)
                if not converted or not disk_path.exists():
                    raise HTTPException(
                        status_code=400,
                        detail=f"Could not convert office document '{target_filename}' to PDF.",
                    )
                try:
                    detected_pages = get_pdf_page_count(disk_path)
                    if detected_pages > 0:
                        target_page_count = detected_pages
                except Exception as exc:
                    logger.warning("Could not count pages from converted PDF: %s", exc)
            finally:
                temp_input.unlink(missing_ok=True)
        else:
            try:
                img = Image.open(io.BytesIO(content)).convert("RGB")
                img.save(disk_path, "PDF")
                target_page_count = 1
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid file type: File must be a valid PDF, Office Document, or Image",
                )

        file_r2_key = f"uploads/{file_id}.pdf"

    if not file_r2_key:
        raise HTTPException(status_code=400, detail="Missing print file or file_r2_key")

    cur = conn.cursor()
    cur.execute("SELECT id, currency FROM shops WHERE id = ?", (target_shop_id,))
    shop = cur.fetchone()
    if not shop:
        raise HTTPException(status_code=404, detail=f"Shop '{target_shop_id}' not found")

    cur.execute(
        "SELECT bw_per_page, color_per_page, duplex_discount, min_charge FROM pricing_rules WHERE shop_id = ?",
        (target_shop_id,),
    )
    rules_row = cur.fetchone()
    rules = dict(rules_row) if rules_row else {
        "bw_per_page": settings.bw_rate,
        "color_per_page": settings.color_rate,
        "duplex_discount": settings.duplex_discount,
        "min_charge": settings.min_charge,
    }

    # If custom page_range is specified, calculate actual pages in that range
    if target_page_range and target_page_range.strip().lower() not in ("all", "*", ""):
        selected_pages = parse_page_range(target_page_range, target_page_count)
        if selected_pages:
            target_page_count = len(selected_pages)

    price_calc = PricingService.calculate_price(
        page_count=target_page_count,
        copies=target_copies,
        color_mode=target_color_mode,
        duplex_mode=target_duplex_mode,
        rules=rules,
    )

    job_id = str(uuid.uuid4())
    tracking_token = uuid.uuid4().hex[:16]
    short_code = f"PRN-{tracking_token[:4].upper()}"

    cur.execute(
        """INSERT INTO print_jobs (
            id, shop_id, tracking_token, short_code, filename, file_r2_key, file_size,
            page_count, copies, color_mode, duplex_mode, paper_size, page_range,
            total_price, currency, status, payment_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_PAYMENT', 'UNPAID', datetime('now'), datetime('now'))""",
        (
            job_id,
            target_shop_id,
            tracking_token,
            short_code,
            target_filename,
            file_r2_key,
            file_size,
            target_page_count,
            target_copies,
            target_color_mode,
            target_duplex_mode,
            target_paper_size,
            target_page_range,
            price_calc["total_price"],
            shop["currency"] or "INR",
        ),
    )

    record_job_event_py(
        conn,
        job_id,
        None,
        "PENDING_PAYMENT",
        "customer",
        notes="Customer submitted print job awaiting cash counter payment",
    )
    conn.commit()

    return {
        "id": job_id,
        "job_id": job_id,
        "short_code": short_code,
        "tracking_token": tracking_token,
        "status": "PENDING_PAYMENT",
        "payment_status": "UNPAID",
        "total_price": price_calc["total_price"],
        "currency": shop["currency"] or "INR",
        "filename": target_filename,
        "page_count": target_page_count,
        "page_range": target_page_range,
        "copies": target_copies,
    }


@router.get("/jobs/{job_id}/status")
@router.get("/jobs/{job_id}")
def customer_get_job(job_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """Polls real-time job status using the private tracking token, job_id, or short_code."""
    cur = conn.cursor()
    cur.execute(
        """SELECT id, tracking_token, short_code, filename, file_size, page_count, copies, color_mode, duplex_mode,
                  paper_size, page_range, total_price, currency, status, payment_status, spooler_job_id, error_message, created_at, updated_at
           FROM print_jobs WHERE tracking_token = ? OR id = ? OR short_code = ?""",
        (job_id, job_id, job_id),
    )
    job = cur.fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found with provided tracking token or id")
    d = dict(job)
    token = d.get("tracking_token") or d["id"]
    d["job_id"] = d["id"]
    if not d.get("short_code"):
        d["short_code"] = f"PRN-{token[:4].upper()}"
    return d
