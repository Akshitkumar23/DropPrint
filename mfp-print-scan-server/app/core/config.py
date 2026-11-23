"""
Centralized Configuration Manager for DropPrint Server.
Loads environment variables from .env and settings from config.ini.
Supports dynamic port binding, pricing rates, customer privacy retention timers, and security.
"""

from __future__ import annotations

import base64
import configparser
import hashlib
import hmac
import logging
import os
import secrets
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Attempt to load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Search root and parent folders for .env
    _server_root = Path(__file__).resolve().parent.parent.parent
    _workspace_root = _server_root.parent
    if (_workspace_root / ".env").exists():
        load_dotenv(_workspace_root / ".env")
    if (_server_root / ".env").exists():
        load_dotenv(_server_root / ".env", override=True)
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Base directories
ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent.parent
)
CONFIG_PATH = Path(os.environ.get("MFP_CONFIG") or ROOT / "config.ini")
EXAMPLE_PATH = ROOT / "config.example.ini"
MAIN_SECTION = "main"

HASH_PREFIX = "pbkdf2_sha256"
HASH_ITERATIONS = 390_000


@dataclass
class Settings:
    # Server & Networking
    defaultlang: str = "en"
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "production"
    public_tunnel_url: str = ""
    lan_ip: str = ""
    ipp_port: int = 631
    ipp_printer: str = ""
    mdns: bool = True
    escl: bool = True
    escl_scanner: str = ""
    escl_port: int = 80
    ssl_certfile: Optional[Path] = None
    ssl_keyfile: Optional[Path] = None

    # Paths
    data_dir: Path = ROOT / "data"
    scans_dir: Path = ROOT / "scans"
    uploads_dir: Path = ROOT / "uploads"
    frontend_dir: Path = ROOT / "frontend"

    # Security & Auth
    auth: bool = False
    ipp_auth: bool = False
    escl_auth: bool = False
    session_days: int = 30
    session_secret: str = "shopkeeper-jwt-dev-secret-change-in-production-0987654321"
    users: dict[str, str] = field(default_factory=dict)
    admins: set[str] = field(default_factory=set)

    # Pricing Defaults (INR linear rates)
    bw_rate: float = 2.0
    color_rate: float = 10.0
    duplex_discount: float = 0.5
    min_charge: float = 0.0

    # Document Lifecycle & Customer Privacy Auto-Purge
    retention_seconds: int = 60  # Auto-purge printed customer file after 60s
    abandoned_ttl_seconds: int = 600  # Auto-purge unprinted files after 10 min
    sweeper_interval_seconds: int = 30  # Sweeper check cadence

    # Uploads & Limits
    max_upload_size_mb: int = 50
    tunnel_token: Optional[str] = None

    # Logging
    log_level: str = "INFO"


def _read_file() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(inline_comment_prefixes=(";", "#"), interpolation=None, allow_no_value=True)
    parser.optionxform = str
    if not CONFIG_PATH.exists() and EXAMPLE_PATH.exists() and "MFP_CONFIG" not in os.environ:
        shutil.copyfile(EXAMPLE_PATH, CONFIG_PATH)
        logger.info("Created %s from %s", CONFIG_PATH.name, EXAMPLE_PATH.name)
    if CONFIG_PATH.exists():
        parser.read_string(f"[{MAIN_SECTION}]\n" + CONFIG_PATH.read_text(encoding="utf-8-sig"))
    return parser


def _bool(value: str) -> bool:
    return value.strip().lower() in ("yes", "true", "on", "1", "basic")


def load() -> Settings:
    parser = _read_file()
    main = parser[MAIN_SECTION] if parser.has_section(MAIN_SECTION) else {}

    def get(key: str, env_vars: list[str] | str, default: str) -> str:
        if isinstance(env_vars, str):
            env_vars = [env_vars]
        for env in env_vars:
            val = os.environ.get(env)
            if val is not None and val.strip():
                return val.strip()
        return main.get(key, "").strip() or default

    def path(key: str, env_vars: list[str] | str, default: Path) -> Path:
        value = get(key, env_vars, "")
        if not value:
            return default
        p = Path(value)
        return p if p.is_absolute() else ROOT / p

    def opt_path(key: str, env_vars: list[str] | str) -> Optional[Path]:
        value = get(key, env_vars, "")
        if not value:
            return None
        p = Path(value)
        return p if p.is_absolute() else ROOT / p

    lang = get("defaultlang", ["MFP_LANG", "DEFAULT_LANG"], "en").lower()
    host = get("host", ["HOST"], "0.0.0.0")
    port = int(get("port", ["PORT", "MFP_PORT"], "8000"))
    environment = get("environment", ["ENVIRONMENT"], "production")
    public_tunnel_url = get("public_tunnel_url", ["PUBLIC_TUNNEL_URL", "PUBLIC_BASE_URL"], "")
    lan_ip = get("lan_ip", ["LAN_IP"], "")
    ipp_port = int(get("ipp_port", ["MFP_IPP_PORT"], "631"))
    escl_port = int(get("escl_port", ["MFP_ESCL_PORT"], "80"))

    # Resolve frontend directory (authoritative check: project root frontend)
    primary_frontend = ROOT.parent / "frontend"
    server_frontend = ROOT / "frontend"
    resolved_frontend = primary_frontend if primary_frontend.exists() else server_frontend

    settings = Settings(
        defaultlang=lang if lang in ("auto", "ru", "en") else "en",
        host=host,
        port=port,
        environment=environment,
        public_tunnel_url=public_tunnel_url,
        lan_ip=lan_ip,
        ipp_port=ipp_port,
        ipp_printer=get("ipp_printer", ["MFP_IPP_PRINTER"], ""),
        mdns=_bool(get("mdns", ["MFP_MDNS"], "yes")),
        escl=_bool(get("escl", ["MFP_ESCL"], "yes")),
        escl_scanner=get("escl_scanner", ["MFP_ESCL_SCANNER"], ""),
        escl_port=escl_port,
        ssl_certfile=opt_path("ssl_certfile", ["MFP_SSL_CERTFILE", "SSL_CERTFILE"]),
        ssl_keyfile=opt_path("ssl_keyfile", ["MFP_SSL_KEYFILE", "SSL_KEYFILE"]),
        data_dir=path("data_dir", ["MFP_DATA_DIR", "DATA_DIR"], ROOT / "data"),
        scans_dir=path("scans_dir", ["MFP_SCANS_DIR", "SCANS_DIR"], ROOT / "scans"),
        uploads_dir=path("uploads_dir", ["MFP_UPLOADS_DIR", "UPLOADS_DIR"], ROOT / "uploads"),
        frontend_dir=resolved_frontend,
        auth=_bool(get("auth", ["MFP_AUTH"], "none")),
        ipp_auth=_bool(get("ipp_auth", ["MFP_IPP_AUTH"], "no")),
        escl_auth=_bool(get("escl_auth", ["MFP_ESCL_AUTH"], "no")),
        session_days=int(get("session_days", ["MFP_SESSION_DAYS"], "30")),
        session_secret=get("session_secret", ["SESSION_SECRET"], "shopkeeper-jwt-dev-secret-change-in-production-0987654321"),
        users={name: pw.strip() for name, pw in parser["users"].items()} if parser.has_section("users") else {},
        admins=set(parser["admins"].keys()) if parser.has_section("admins") else set(),
        bw_rate=float(get("bw_rate", ["PRICE_BW_PER_PAGE", "BW_PER_PAGE", "PRICING_BW"], "2.0")),
        color_rate=float(get("color_rate", ["PRICE_COLOR_PER_PAGE", "COLOR_PER_PAGE", "PRICING_COLOR"], "10.0")),
        duplex_discount=float(get("duplex_discount", ["DUPLEX_DISCOUNT", "PRICING_DUPLEX_DISCOUNT"], "0.5")),
        min_charge=float(get("min_charge", ["MIN_CHARGE", "PRICING_MIN_CHARGE"], "0.0")),
        retention_seconds=int(get("retention_seconds", ["FILE_RETENTION_SECONDS", "RETENTION_SECONDS", "CLEANUP_DELAY_SECONDS"], "60")),
        abandoned_ttl_seconds=int(get("abandoned_ttl_seconds", ["ABANDONED_TTL_SECONDS"], "600")),
        sweeper_interval_seconds=int(get("sweeper_interval_seconds", ["SWEEPER_INTERVAL_SECONDS"], "30")),
        max_upload_size_mb=int(get("max_upload_size_mb", ["MAX_UPLOAD_SIZE_MB"], "50")),
        tunnel_token=get("tunnel_token", ["TUNNEL_TOKEN", "CLOUDFLARE_TUNNEL_TOKEN"], "") or None,
        log_level=get("log_level", ["LOG_LEVEL"], "INFO").upper(),
    )

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.scans_dir.mkdir(parents=True, exist_ok=True)

    if bool(settings.ssl_certfile) != bool(settings.ssl_keyfile):
        logger.error(
            "Both ssl_certfile and ssl_keyfile must be set to enable HTTPS in %s — ignoring, serving plain HTTP",
            CONFIG_PATH.name,
        )
        settings.ssl_certfile = settings.ssl_keyfile = None

    return settings


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, HASH_ITERATIONS)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"{HASH_PREFIX}${HASH_ITERATIONS}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith(HASH_PREFIX + "$"):
        try:
            _, iterations, salt, expected = stored.split("$")
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
            return hmac.compare_digest(digest, base64.b64decode(expected))
        except ValueError:
            return False
    return hmac.compare_digest(password.encode(), stored.encode())


settings = load()
