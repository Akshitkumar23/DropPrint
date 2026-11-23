"""
System Health, Telemetry, QR Code, and Printer Hardware Options Endpoints (v1).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import qrcode
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.exceptions import SpoolerError
from app.i18n import t
from app.mdns_util import local_ipv4_addresses
from app.models import (
    JobOut,
    JobStatus,
    OptionChoiceOut,
    PreviewOut,
    PrinterOptionOut,
)
from app.preview import PreviewUnavailable, render_preview
from app.printing.base import PrintError
from app.printing.layout import DEFAULT_LAYOUT
from app.services.spooler import spooler_service
from app.storage import job_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])

backend = spooler_service.get_backend_instance()
UPLOAD_DIR = settings.uploads_dir
MAX_FILE_SIZE = 100 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def get_lan_ip() -> str:
    """Finds configured or best local LAN IPv4 address."""
    if settings.lan_ip:
        return settings.lan_ip
    env_lan = os.environ.get("LAN_IP", "").strip()
    if env_lan:
        return env_lan
    for raw_addr in local_ipv4_addresses():
        ip = socket.inet_ntoa(raw_addr)
        if not ip.startswith("127.") and not ip.startswith("169.254."):
            return ip
    return "127.0.0.1"


@router.get("/health")
def health_check():
    """System health check endpoint."""
    return {
        "status": "ok",
        "service": "mfp-unified-print-scan-server",
        "name": "DropPrint-Counter-Server",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/system/public-url")
def get_public_url(request: Request, shop: str = "default"):
    """Returns dynamic LAN and public customer URLs for QR standee display."""
    lan_ip = get_lan_ip()
    port = request.url.port or settings.port or 8000
    scheme = request.url.scheme or "http"
    lan_base = f"{scheme}://{lan_ip}:{port}"

    public_base = (
        os.environ.get("PUBLIC_TUNNEL_URL", "").strip()
        or settings.public_tunnel_url
        or os.environ.get("PUBLIC_BASE_URL", "").strip()
    ).rstrip("/")
    if not public_base:
        public_base = lan_base

    return {
        "public_base_url": public_base,
        "customer_url": f"{public_base}/customer/?shop={shop}",
        "lan_url": f"{lan_base}/customer/?shop={shop}",
    }


@router.get("/system/status")
@router.get("/status")
@router.get("/system/network-info")
@router.get("/network-info")
def get_system_network_info(request: Request, shop: str = "default"):
    """Returns real-time network connectivity, LAN and tunnel URLs, and dual/lan active_mode."""
    lan_ip = get_lan_ip()
    port = request.url.port or settings.port or 8000
    scheme = request.url.scheme or "http"
    lan_base = f"{scheme}://{lan_ip}:{port}"

    tunnel_url = (
        os.environ.get("PUBLIC_TUNNEL_URL", "").strip()
        or settings.public_tunnel_url
        or os.environ.get("PUBLIC_BASE_URL", "").strip()
    ).rstrip("/")
    tunnel_active = bool(
        tunnel_url
        and not tunnel_url.startswith("http://127.0.0.1")
        and not tunnel_url.startswith("http://localhost")
    )
    active_mode = "dual" if (tunnel_url and tunnel_active) else "lan"

    customer_lan_url = f"{lan_base}/customer/?shop={shop}"
    customer_tunnel_url = f"{tunnel_url}/customer/?shop={shop}" if tunnel_url else customer_lan_url
    formatted_tunnel = f"{tunnel_url}/" if tunnel_url else None

    return {
        "status": "ok",
        "active_mode": active_mode,
        "lan_ip": lan_ip,
        "port": port,
        "lan_url": f"{lan_base}/",
        "tunnel_url": formatted_tunnel,
        "tunnel_active": tunnel_active,
        "tunnel_token_configured": bool(settings.tunnel_token or os.environ.get("TUNNEL_TOKEN") or os.environ.get("CLOUDFLARE_TUNNEL_TOKEN")),
        "customer_lan_url": customer_lan_url,
        "customer_tunnel_url": customer_tunnel_url,
        "customer_url": customer_tunnel_url if tunnel_active else customer_lan_url,
        "public_base_url": tunnel_url if tunnel_active else lan_base,
    }


@router.get("/system/qr-info")
@router.get("/qr-info")
def get_qr_info(request: Request, shop: str = "default"):
    """Returns QR code standee target metadata and customer URLs."""
    lan_ip = get_lan_ip()
    port = request.url.port or settings.port or 8000
    scheme = request.url.scheme or "http"
    lan_base = f"{scheme}://{lan_ip}:{port}"
    tunnel_url = (
        os.environ.get("PUBLIC_TUNNEL_URL", "").strip()
        or settings.public_tunnel_url
        or os.environ.get("PUBLIC_BASE_URL", "").strip()
    ).rstrip("/")

    tunnel_active = bool(
        tunnel_url
        and not tunnel_url.startswith("http://127.0.0.1")
        and not tunnel_url.startswith("http://localhost")
    )
    active_mode = "dual" if (tunnel_url and tunnel_active) else "lan"
    target_base = tunnel_url if (tunnel_url and tunnel_active) else lan_base
    return {
        "active_mode": active_mode,
        "lan_url": f"{lan_base}/customer/?shop={shop}",
        "tunnel_url": f"{tunnel_url}/customer/?shop={shop}" if tunnel_url else None,
        "target_customer_url": f"{target_base}/customer/?shop={shop}",
        "qr_code_url": f"/api/qrcode.png?shop={shop}",
    }


@router.get("/qrcode.png")
def qrcode_png(request: Request, url: Optional[str] = None, shop: str = "default"):
    """Generates PNG QR code for customer self-service access."""
    try:
        if not url:
            lan_ip = get_lan_ip()
            port = request.url.port or settings.port or 8000
            scheme = request.url.scheme or "http"
            public_base = (
                settings.public_tunnel_url
                or os.environ.get("PUBLIC_TUNNEL_URL", "")
                or os.environ.get("PUBLIC_BASE_URL", f"{scheme}://{lan_ip}:{port}")
            ).rstrip("/")
            target_url = f"{public_base}/customer/?shop={shop}"
        else:
            target_url = url

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as exc:
        logger.error("Failed to generate QR code: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate QR code image")


@router.get("/printers")
def list_printers():
    """Lists locally installed printers."""
    try:
        return spooler_service.list_printers()
    except SpoolerError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/printers/{printer_name}/status")
async def printer_status(printer_name: str):
    """Checks live hardware status for the given printer via WMI."""
    status_info = await run_in_threadpool(spooler_service.printer_status, printer_name)
    if status_info is None:
        return {"state": "idle", "accepting_jobs": True, "reasons": []}
    return status_info


@router.get("/printers/{printer_name}/options", response_model=List[PrinterOptionOut])
def list_printer_options(printer_name: str):
    """Retrieves supported hardware options for the specified printer."""
    try:
        options = backend.list_options(printer_name)
    except PrintError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return [
        PrinterOptionOut(
            key=o.key,
            label=o.label,
            choices=[OptionChoiceOut(value=c.value, label=c.label) for c in o.choices],
            default=o.default,
            limits=o.limits,
            fallbacks=o.fallbacks,
        )
        for o in options
    ]


@router.get("/printers/{printer_name}/maintenance")
async def list_maintenance(printer_name: str):
    """Lists available printer maintenance operations."""
    try:
        actions = await run_in_threadpool(backend.maintenance_actions, printer_name)
    except PrintError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return [{"id": a.id, "label": a.label, "description": a.description, "confirm": a.confirm} for a in actions]


@router.post("/printers/{printer_name}/maintenance/{action_id}", response_model=JobOut)
async def run_maintenance(printer_name: str, action_id: str):
    """Executes a printer maintenance action."""
    actions = {a.id: a for a in await run_in_threadpool(backend.maintenance_actions, printer_name)}
    if action_id not in actions:
        raise HTTPException(status_code=404, detail=t("err.action_unsupported"))
    job = JobOut(
        id=uuid.uuid4().hex,
        filename=actions[action_id].label,
        printer=printer_name,
        copies=1,
        options=None,
        status=JobStatus.QUEUED,
        error=None,
        created_at=datetime.now(),
    )
    job_store.add(job)
    try:
        await run_in_threadpool(backend.run_maintenance, printer_name, action_id)
        return job_store.update(job.id, status=JobStatus.SENT)
    except Exception as exc:
        return job_store.update(job.id, status=JobStatus.FAILED, error=str(exc))


def _parse_options(options: Optional[str]) -> dict[str, str]:
    if not options:
        return {}
    try:
        parsed = json.loads(options)
        if not isinstance(parsed, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail=t("err.bad_options"))
    return parsed


def _is_mono(options: dict[str, str]) -> bool:
    return options.get("color") == "mono" or options.get("ColorModel", "").lower() in ("gray", "grayscale")


async def _save_upload(file: UploadFile, dest: Path) -> None:
    size = 0
    with dest.open("wb") as f:
        while chunk := await file.read(CHUNK_SIZE):
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=t("err.file_too_large"))
            f.write(chunk)


@router.post("/preview", response_model=PreviewOut)
async def preview_file(
    file: UploadFile = File(...),
    printer: Optional[str] = Form(None),
    options: Optional[str] = Form(None),
):
    """Renders visual raster preview of document before printing."""
    parsed_options = _parse_options(options)
    dest = UPLOAD_DIR / f"preview_{uuid.uuid4().hex}_{Path(file.filename or 'doc').name}"
    await _save_upload(file, dest)
    try:
        layout = await run_in_threadpool(backend.page_layout, printer, parsed_options)
        exact = layout is not None
        layout = layout or DEFAULT_LAYOUT
        try:
            result = await run_in_threadpool(render_preview, dest, layout, _is_mono(parsed_options))
        except PreviewUnavailable:
            return PreviewOut(
                available=False,
                reason=t("err.no_preview", ext=Path(file.filename or '').suffix or t("err.this_type")),
            )
        except ValueError as exc:
            return PreviewOut(available=False, reason=str(exc))
        return PreviewOut(
            available=True,
            pages=["data:image/png;base64," + base64.b64encode(png).decode() for png in result.pages],
            total_pages=result.total_pages,
            paper_mm=(round(layout.paper_w, 1), round(layout.paper_h, 1)),
            exact_layout=exact,
        )
    finally:
        dest.unlink(missing_ok=True)
