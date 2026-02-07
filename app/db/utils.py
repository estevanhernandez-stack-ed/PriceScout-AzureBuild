"""
Database Utilities Module
PriceScout Database Adapter Layer

Provides:
- Async execution helpers
- Raw SQL execution
- Time parsing utilities
"""

import re
import asyncio
import concurrent.futures
import pandas as pd
from app.db_session import get_session, get_engine


def _parse_time_to_minutes(time_str):
    """
    Parse time string like '10:30 AM' or '10:30am' to minutes since midnight.
    Used for comparing operating hours in high water mark logic.
    """
    if not time_str or time_str in ('N/A', 'N\\A', None):
        return None
    match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?', str(time_str).strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    meridiem = match.group(3)
    if meridiem:
        meridiem = meridiem.upper()
        if meridiem == 'PM' and hour != 12:
            hour += 12
        elif meridiem == 'AM' and hour == 12:
            hour = 0
    return hour * 60 + minute


def run_async_safe(coro):
    """
    Safely runs an async coroutine from a synchronous context.
    Works inside FastAPI (which has a running loop) and outside (e.g., Streamlit).
    """
    try:
        # Check if we are in an event loop
        loop = asyncio.get_running_loop()
        # If we are, we must run it in a separate thread to avoid
        # "RuntimeError: asyncio.run() cannot be called from a running event loop"
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    except (RuntimeError, ValueError):
        # No loop running, asyncio.run is safe
        return asyncio.run(coro)


def execute_raw_sql(query, params=None):
    """
    Execute a raw SQL query and return results as list of dicts.
    Useful for complex queries not easily expressible in ORM.
    """
    from sqlalchemy import text
    with get_session() as session:
        result = session.execute(text(query), params or {})
        if result.returns_rows:
            columns = result.keys()
            return [dict(zip(columns, row)) for row in result.fetchall()]
        return []


def execute_raw_sql_pandas(query, params=None):
    """
    Execute a raw SQL query and return results as a pandas DataFrame.
    """
    from sqlalchemy import text
    engine = get_engine()
    return pd.read_sql(text(query), engine, params=params or {})


def update_database_schema():
    """Alias for init_database to handle schema updates"""
    from app.db.core import init_database
    init_database()


def migrate_schema():
    """Run schema migrations (placeholder for future Alembic integration)"""
    from app.db.core import init_database
    init_database()
