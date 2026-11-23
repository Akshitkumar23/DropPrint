"""
Unified APIRouter aggregating all v1 API modules:
- Customer Self-Service (/api/customer and /api/v1/customer)
- Shopkeeper Dashboard (/api/shop and /api/v1/shop)
- System Health & Telemetry (/api/health, /api/printers, /api/v1/...)
- Hardware Gateway (/api/gateway and /api/v1/gateway)
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.customer import router as customer_router
from app.api.v1.shop import router as shop_router
from app.api.v1.system import router as system_router
from app.gateway_routes import router as gateway_router

# Version 1 Router (prefix="/v1")
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(customer_router)
v1_router.include_router(shop_router)
v1_router.include_router(system_router)
v1_router.include_router(gateway_router)

# Unified Root API Router (/api) - maintaining 100% backward compatibility
api_router = APIRouter(prefix="/api")
# Backwards compatible direct /api routes:
api_router.include_router(customer_router)
api_router.include_router(shop_router)
api_router.include_router(system_router)
api_router.include_router(gateway_router)
# Versioned /api/v1 routes:
api_router.include_router(v1_router)

__all__ = ["api_router", "v1_router", "customer_router", "shop_router", "system_router", "gateway_router"]
