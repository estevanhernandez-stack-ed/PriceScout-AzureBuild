"""
Shared state and helper functions for scrape sub-modules.

All scrape endpoint modules import from here to share:
- _scrape_jobs: in-memory job storage dict
- _scrape_executor: thread pool for async-in-thread execution
- _job_counter: monotonic job ID counter
- Thread helpers for running async code in background threads
"""

import logging
import asyncio
import sys
import threading
import concurrent.futures
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Shared thread pool for scrape operations (prevents creating new pools constantly)
_scrape_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="scrape_worker")

# In-memory job storage (in production, use Redis or database)
_scrape_jobs: Dict[int, Dict[str, Any]] = {}
_job_counter = 0


def _run_async_in_thread_sync(coro):
    """
    Synchronous helper that runs an async coroutine in a new event loop.
    This is called from a thread pool executor.
    """
    # On Windows, we need ProactorEventLoop for subprocess support
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _run_async_in_thread(coro):
    """
    Run an async coroutine in a separate thread WITHOUT blocking the main event loop.
    This allows the API to remain responsive during long-running scrapes.

    Uses asyncio.get_event_loop().run_in_executor() to properly yield control
    back to the event loop while the thread does its work.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_scrape_executor, lambda: _run_async_in_thread_sync(coro))


def _run_async_in_thread_blocking(coro):
    """
    BLOCKING version - only use for synchronous endpoints like fetch-showtimes.
    For background tasks, use the async _run_async_in_thread() instead.
    """
    return _run_async_in_thread_sync(coro)


def _launch_in_thread(async_fn, *args, **kwargs):
    """
    Launch an async function in a completely separate thread with its own event loop.

    This prevents long-running jobs (scrapes, syncs) from blocking the main
    FastAPI event loop, keeping the API responsive for status checks and
    other requests while a scrape runs in the background.
    """
    def _thread_target():
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(async_fn(*args, **kwargs))
        except Exception as e:
            logger.error(f"Background job failed: {e}", exc_info=True)
        finally:
            loop.close()

    thread = threading.Thread(
        target=_thread_target,
        daemon=True,
        name=f"scrape-{threading.active_count()}"
    )
    thread.start()
    return thread


def _get_active_theater_urls() -> Dict[str, int]:
    """
    Get all theater URLs currently being scraped and their job IDs.
    Returns: {theater_url: job_id}
    """
    active_theaters = {}
    for job_id, job in _scrape_jobs.items():
        if job.get("status") in ["pending", "running"]:
            theaters = job.get("theaters", [])
            for theater in theaters:
                url = theater.get("url") if isinstance(theater, dict) else None
                if url:
                    active_theaters[url] = job_id
    return active_theaters


def _check_theater_collision(requested_theaters: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """
    Check if any requested theaters are already being scraped.

    Args:
        requested_theaters: List of theater dicts with 'name' and 'url' keys

    Returns:
        None if no collision, or dict with collision details:
        {
            "conflicting_theaters": [{"name": str, "url": str, "job_id": int}],
            "job_ids": [int]
        }
    """
    active_theaters = _get_active_theater_urls()

    if not active_theaters:
        return None

    conflicts = []
    job_ids = set()

    for theater in requested_theaters:
        url = theater.get("url")
        if url and url in active_theaters:
            job_id = active_theaters[url]
            conflicts.append({
                "name": theater.get("name", "Unknown"),
                "url": url,
                "job_id": job_id
            })
            job_ids.add(job_id)

    if conflicts:
        return {
            "conflicting_theaters": conflicts,
            "job_ids": list(job_ids)
        }

    return None
