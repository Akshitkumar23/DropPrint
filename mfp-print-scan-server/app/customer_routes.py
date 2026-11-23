"""
Customer routes compatibility shim for DropPrint Server.
Re-exports customer router and handlers from app.api.v1.customer.
"""

from __future__ import annotations

from app.api.v1.customer import (
    EstimateRequest,
    SubmitJobRequest,
    UPLOAD_DIR,
    customer_create_job,
    customer_estimate,
    customer_get_job,
    customer_upload,
    router,
)

__all__ = [
    "EstimateRequest",
    "SubmitJobRequest",
    "UPLOAD_DIR",
    "customer_create_job",
    "customer_estimate",
    "customer_get_job",
    "customer_upload",
    "router",
]
