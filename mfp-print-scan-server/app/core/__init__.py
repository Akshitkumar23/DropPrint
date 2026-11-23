"""
Core Module for DropPrint Server.
Houses configuration, database management, and domain exceptions.
"""

from .config import settings, Settings
from .database import get_db, get_db_connection, init_db
from .exceptions import (
    DropPrintError,
    PricingError,
    SpoolerError,
    JobNotFoundError,
    ShopNotFoundError,
    InvalidTransitionError,
    AuthenticationError,
    register_exception_handlers,
)

__all__ = [
    "settings",
    "Settings",
    "get_db",
    "get_db_connection",
    "init_db",
    "DropPrintError",
    "PricingError",
    "SpoolerError",
    "JobNotFoundError",
    "ShopNotFoundError",
    "InvalidTransitionError",
    "AuthenticationError",
    "register_exception_handlers",
]
