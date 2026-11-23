"""
Shop routes compatibility shim for DropPrint Server.
Re-exports shopkeeper router and handlers from app.api.v1.shop.
"""

from __future__ import annotations

from app.api.v1.shop import (
    JobActionReason,
    PricingUpdateRequest,
    ShopLoginRequest,
    get_current_shopkeeper,
    get_optional_shopkeeper,
    router,
    shop_approve_job,
    shop_cancel_job,
    shop_create_device,
    shop_get_pricing,
    shop_list_devices,
    shop_list_jobs,
    shop_login,
    shop_mark_paid,
    shop_receive_and_print,
    shop_reject_job,
    shop_update_pricing,
)

__all__ = [
    "JobActionReason",
    "PricingUpdateRequest",
    "ShopLoginRequest",
    "get_current_shopkeeper",
    "get_optional_shopkeeper",
    "router",
    "shop_approve_job",
    "shop_cancel_job",
    "shop_create_device",
    "shop_get_pricing",
    "shop_list_devices",
    "shop_list_jobs",
    "shop_login",
    "shop_mark_paid",
    "shop_receive_and_print",
    "shop_reject_job",
    "shop_update_pricing",
]
