"""
DropPrint Counter Server - Main Application Entrypoint.
Orchestrates FastAPI application, API routing (/api, /api/v1), static frontend delivery,
IPP driverless printing, hardware scanner services, and customer privacy document lifecycles.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app.api.v1.router import api_router
from app.core.config import ROOT, settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers
from app.escl.mdns import EsclMdnsAnnouncer
from app.escl.server import EsclScanner
from app.escl_routes import create_router as create_escl_router
from app.i18n import t
from app.ipp.mdns import MdnsAnnouncer
from app.ipp.printer import IppPrinter, is_supported as ipp_supported
from app.scan_routes import create_router as create_scan_router
from app.scanning.factory import get_scan_backend
from app.services.cleanup import background_sweeper_loop
from app.services.spooler import spooler_service

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = settings.frontend_dir
UPLOAD_DIR = settings.uploads_dir

WEB_PORT = settings.port
WEB_SCHEME = "https" if settings.ssl_certfile and settings.ssl_keyfile else "http"

backend = spooler_service.get_backend_instance()
scan_backend = get_scan_backend()
ipp_printer = IppPrinter(backend, UPLOAD_DIR) if ipp_supported() else None
mdns_announcer = MdnsAnnouncer() if ipp_printer and settings.mdns and settings.ipp_port else None
escl_scanner = EsclScanner(scan_backend) if settings.escl else None
escl_mdns = EsclMdnsAnnouncer() if escl_scanner and settings.mdns else None

_lifespan_servers = 0
_sweeper_task = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Manages application startup and graceful shutdown."""
    global _lifespan_servers, _sweeper_task
    _lifespan_servers += 1
    if _lifespan_servers == 1:
        # Initialize SQLite database schema and seed default data
        init_db()

        # Start periodic background sweeper loop (customer privacy auto-purge)
        _sweeper_task = asyncio.create_task(
            background_sweeper_loop(interval_seconds=settings.sweeper_interval_seconds)
        )

        # Warm up printer hardware driver
        if ipp_printer:
            ipp_printer.warm_up()
        if mdns_announcer:
            mdns_announcer.start(ipp_printer, settings.ipp_port, WEB_PORT)
        if escl_mdns:
            escl_mdns.start(escl_scanner, WEB_PORT)

    try:
        yield
    finally:
        _lifespan_servers -= 1
        if _lifespan_servers == 0:
            if _sweeper_task:
                _sweeper_task.cancel()
            if mdns_announcer:
                mdns_announcer.stop()
            if escl_mdns:
                escl_mdns.stop()


# ---------------------------------------------------------------------------
# FastAPI Initialization
# ---------------------------------------------------------------------------
app = FastAPI(
    title="DropPrint Counter Server",
    version="2.0.0",
    description="Scalable, zero-barrier counter print server for express copy shops.",
    lifespan=lifespan,
)

# Register custom exception handlers for structured JSON responses
register_exception_handlers(app)

# Allow Cross-Origin Requests from mobile browsers and tunnel proxies
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routing Architecture
# ---------------------------------------------------------------------------
# Mount unified API router providing both /api (legacy) and /api/v1 (RESTful)
app.include_router(api_router)

# Mount hardware scanning routes
app.include_router(create_scan_router(backend, scan_backend, settings.scans_dir))
if escl_scanner:
    app.include_router(create_escl_router(escl_scanner, WEB_PORT))

# Mount static frontend directories
if FRONTEND_DIR.exists():
    if (FRONTEND_DIR / "shared").exists():
        app.mount("/shared", StaticFiles(directory=str(FRONTEND_DIR / "shared")), name="shared")
    if (FRONTEND_DIR / "customer").exists():
        app.mount("/customer", StaticFiles(directory=str(FRONTEND_DIR / "customer"), html=True), name="customer")
    if (FRONTEND_DIR / "shopkeeper").exists():
        app.mount("/shopkeeper", StaticFiles(directory=str(FRONTEND_DIR / "shopkeeper"), html=True), name="shopkeeper")


# Mount legacy static files if directory exists
if (BASE_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Portal Landing & Direct Asset Delivery
# ---------------------------------------------------------------------------
@app.get("/login")
@app.post("/login")
def login_redirect():
    """Zero-barrier print shop: redirects /login straight to the shopkeeper counter."""
    return RedirectResponse("/shopkeeper", status_code=303)


@app.get("/logout")
@app.post("/logout")
def logout_redirect():
    """Redirects /logout to shopkeeper counter."""
    return RedirectResponse("/shopkeeper", status_code=303)


@app.get("/", response_class=HTMLResponse)
def root_portal():
    """Root URL directly serves the Customer Mobile Upload Web App."""
    customer_index = FRONTEND_DIR / "customer" / "index.html"
    if customer_index.exists():
        return HTMLResponse(customer_index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>DropPrint Customer Mobile Page</h1>")


@app.get("/customer")
def customer_redirect():
    return RedirectResponse("/customer/", status_code=307)


@app.get("/customer/", response_class=HTMLResponse)
def customer_page():
    customer_index = FRONTEND_DIR / "customer" / "index.html"
    if customer_index.exists():
        return HTMLResponse(customer_index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>DropPrint Customer Mobile Page</h1>")


@app.get("/shopkeeper")
def shopkeeper_redirect():
    return RedirectResponse("/shopkeeper/", status_code=307)


@app.get("/shopkeeper/", response_class=HTMLResponse)
def shopkeeper_page():
    shop_index = FRONTEND_DIR / "shopkeeper" / "index.html"
    if shop_index.exists():
        return HTMLResponse(shop_index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>DropPrint Shopkeeper Counter Dashboard</h1>")


@app.get("/shopkeeper/style.css")
def shopkeeper_style_css():
    css_file = FRONTEND_DIR / "shopkeeper" / "style.css"
    if css_file.exists():
        return FileResponse(css_file, media_type="text/css")
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/shopkeeper/dashboard.js")
def shopkeeper_dashboard_js():
    js_file = FRONTEND_DIR / "shopkeeper" / "dashboard.js"
    if js_file.exists():
        return FileResponse(js_file, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/dashboard.js")
def shopkeeper_root_dashboard_js():
    js_file = FRONTEND_DIR / "shopkeeper" / "dashboard.js"
    if js_file.exists():
        return FileResponse(js_file, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/app.js")
def customer_root_app_js():
    js_file = FRONTEND_DIR / "customer" / "app.js"
    if js_file.exists():
        return FileResponse(js_file, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/style.css")
def customer_root_style_css():
    css_file = FRONTEND_DIR / "customer" / "style.css"
    if css_file.exists():
        return FileResponse(css_file, media_type="text/css")
    raise HTTPException(status_code=404, detail="File not found")


# ---------------------------------------------------------------------------
# IPP Driverless Printing Endpoint
# ---------------------------------------------------------------------------
IPP_PATHS = ("/", "/ipp", "/ipp/", "/ipp/print", "/ipp/print/", "/ipp/printer", "/ipp/printer/")


async def ipp_endpoint(request: Request):
    """Handles standard IPP binary POST requests for driverless network printing."""
    if ipp_printer is None:
        raise HTTPException(status_code=501, detail=t("err.ipp_windows_only"))
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/ipp":
        raise HTTPException(status_code=415, detail=t("err.expect_ipp"))
    host = request.headers.get("host") or f"{request.url.hostname}:{request.url.port}"
    printer_uri = f"ipp://{host}{request.url.path.rstrip('/')}"
    more_info = f"{WEB_SCHEME}://{host.rsplit(':', 1)[0]}:{WEB_PORT}/"
    body = await request.body()
    response = await run_in_threadpool(ipp_printer.handle, body, printer_uri, more_info)
    return Response(content=response, media_type="application/ipp")


for ipp_path in IPP_PATHS:
    app.add_api_route(ipp_path, ipp_endpoint, methods=["POST"], include_in_schema=False)
