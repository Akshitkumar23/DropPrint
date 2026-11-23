"""
Dedicated Pricing Service for DropPrint Counter Server.
Enforces honest linear pricing without hidden fees or forced round-ups:
- Black & White: ₹2.00 / page
- Color: ₹10.00 / page
- Duplex discount: ₹0.50 / duplex sheet (pages // 2)
- Minimum charge: ₹0.00 (honest zero-base pricing)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.exceptions import PricingError

logger = logging.getLogger(__name__)


class PricingService:
    """Dedicated business logic service for print job pricing calculation."""

    DEFAULT_RULES: Dict[str, Any] = {
        "bw_per_page": 2.0,
        "color_per_page": 10.0,
        "duplex_discount": 0.5,
        "min_charge": 0.0,
    }

    @classmethod
    def calculate_price(
        cls,
        page_count: int,
        copies: int = 1,
        color_mode: str = "bw",
        duplex_mode: str = "simplex",
        rules: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates honest, linear price quotation for customer print jobs.
        
        Args:
            page_count: Number of pages in document (>= 1)
            copies: Number of copies requested (>= 1)
            color_mode: 'bw' (monochrome) or 'color'
            duplex_mode: 'simplex' (single-sided) or 'duplex' (double-sided)
            rules: Optional shop-specific pricing rules dictionary

        Returns:
            Dictionary containing itemized pricing breakdown and total_price.
        """
        if page_count < 1:
            raise PricingError("Page count must be at least 1")
        if copies < 1:
            raise PricingError("Copies must be at least 1")

        active_rules = dict(cls.DEFAULT_RULES)
        # Apply global settings if available
        active_rules["bw_per_page"] = settings.bw_rate
        active_rules["color_per_page"] = settings.color_rate
        active_rules["duplex_discount"] = settings.duplex_discount
        active_rules["min_charge"] = settings.min_charge

        if rules:
            active_rules.update(rules)

        color = "color" if color_mode == "color" else "bw"
        duplex = "duplex" if duplex_mode == "duplex" else "simplex"

        bw_rate = float(active_rules.get("bw_per_page", 2.0))
        color_rate = float(active_rules.get("color_per_page", 10.0))
        duplex_discount_rate = float(active_rules.get("duplex_discount", 0.5))
        min_charge = float(active_rules.get("min_charge", 0.0))

        rate = color_rate if color == "color" else bw_rate
        single_copy_base = page_count * rate

        duplex_sheets = (page_count // 2) if duplex == "duplex" else 0
        duplex_discount_total = duplex_sheets * duplex_discount_rate

        single_copy_total = max(0.0, single_copy_base - duplex_discount_total)
        subtotal = single_copy_total * copies
        total_price = round(max(min_charge, subtotal), 2)

        return {
            "page_count": page_count,
            "copies": copies,
            "color_mode": color,
            "duplex_mode": duplex,
            "rate_per_page": rate,
            "single_copy_base": round(single_copy_base, 2),
            "duplex_sheets": duplex_sheets,
            "duplex_discount_total": round(duplex_discount_total, 2),
            "subtotal": round(subtotal, 2),
            "min_charge": min_charge,
            "min_charge_applied": subtotal < min_charge,
            "total_price": total_price,
        }


def calculate_price_py(
    page_count: int,
    copies: int,
    color_mode: str,
    duplex_mode: str,
    rules: Dict[str, Any],
) -> Dict[str, Any]:
    """Backwards-compatible procedural wrapper delegating to PricingService."""
    return PricingService.calculate_price(
        page_count=page_count,
        copies=copies,
        color_mode=color_mode,
        duplex_mode=duplex_mode,
        rules=rules,
    )
