"""
System routes compatibility shim for DropPrint Server.
Re-exports system router and handlers from app.api.v1.system.
"""

from __future__ import annotations

from app.api.v1.system import (
    get_lan_ip,
    get_public_url,
    get_qr_info,
    get_system_network_info,
    health_check,
    list_printers,
    printer_status,
    qrcode_png,
    router,
)

__all__ = [
    "get_lan_ip",
    "get_public_url",
    "get_qr_info",
    "get_system_network_info",
    "health_check",
    "list_printers",
    "printer_status",
    "qrcode_png",
    "router",
]
