"""
API Services Package
Business logic services for the PriceScout API.
"""

import os
import sqlite3

from .enttelligence_cache_service import (
    EntTelligenceCacheService,
    get_cache_service,
    CachedPrice
)


def get_sqlite_connection() -> sqlite3.Connection:
    """Get a raw SQLite connection to the PriceScout database.

    Used by routers that query raw tables (circuit_benchmarks, presales, etc.)
    rather than going through the SQLAlchemy ORM layer.
    """
    from app import config
    db_path = config.DB_FILE or os.path.join(config.PROJECT_DIR, 'pricescout.db')
    return sqlite3.connect(db_path)


__all__ = [
    'EntTelligenceCacheService',
    'get_cache_service',
    'CachedPrice',
    'get_sqlite_connection',
]
