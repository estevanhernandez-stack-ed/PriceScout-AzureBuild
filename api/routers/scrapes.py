"""
Scrapes API Router

Endpoints for managing Fandango web scraping operations: triggering scrapes,
monitoring job status, searching theaters, and saving results.

Endpoints:
    GET    /api/v1/scrapes/active-theaters       - List theaters currently being scraped
    POST   /api/v1/scrapes/check-collision       - Check if scrape would conflict
    GET    /api/v1/scrapes/jobs                   - List recent scrape jobs
    POST   /api/v1/scrapes/jobs/{job_id}/cancel   - Cancel a running scrape job
    GET    /api/v1/scrapes/search-theaters/fandango - Search Fandango for theaters
    GET    /api/v1/scrapes/search-theaters/cache    - Search local theater cache
    POST   /api/v1/scrapes/fetch-showtimes       - Fetch showtimes for a theater
    POST   /api/v1/scrapes/estimate-time         - Estimate scrape duration
    POST   /api/v1/scrapes/operating-hours       - Scrape operating hours data
    POST   /api/v1/scrapes/save                  - Save scraped data to database
    POST   /api/v1/scrape_runs                   - Create a scrape run record
    POST   /api/v1/scrapes/trigger               - Trigger a full scrape job
    GET    /api/v1/scrapes/{job_id}/status        - Get scrape job status
    POST   /api/v1/scrapes/{job_id}/cancel        - Cancel a scrape by job ID
    POST   /api/v1/scrapes/compare-counts        - Compare showtime counts across sources
    POST   /api/v1/scrapes/compare-showtimes     - Verify Fandango showtimes against EntTelligence cache
"""

from fastapi import APIRouter, Security, HTTPException, Depends
from api.routers.auth import get_current_user, User, require_operator
from api.telemetry import track_scrape_completed, track_event
from app.audit_service import audit_service
from app.simplified_baseline_service import normalize_theater_name
from app import db_adapter as database
from app import config
import pandas as pd
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import time
import asyncio
import sys
import threading
import concurrent.futures
from datetime import datetime, date

router = APIRouter()


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


# Shared thread pool for scrape operations (prevents creating new pools constantly)
_scrape_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="scrape_worker")


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
            print(f"[Thread] Background job failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            loop.close()

    thread = threading.Thread(
        target=_thread_target,
        daemon=True,
        name=f"scrape-{threading.active_count()}"
    )
    thread.start()
    return thread


# In-memory job storage (in production, use Redis or database)
_scrape_jobs: Dict[int, Dict[str, Any]] = {}
_job_counter = 0


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


class ScrapeData(BaseModel):
    run_id: int
    data: List[dict]


class TheaterRequest(BaseModel):
    name: str
    url: str


class TriggerScrapeRequest(BaseModel):
    mode: str  # 'market', 'compsnipe', or 'lineup'
    market: Optional[str] = None
    theaters: List[TheaterRequest]
    dates: List[str]  # YYYY-MM-DD format
    selected_showtimes: Optional[List[str]] = None  # List of "date|theater|film|time" keys
    # Cache options for hybrid scrape
    use_cache: bool = False  # Use EntTelligence cache when fresh
    cache_max_age_hours: int = 6  # Staleness threshold for cached data


class TriggerScrapeResponse(BaseModel):
    job_id: int
    status: str
    message: str


class FetchShowtimesRequest(BaseModel):
    theaters: List[TheaterRequest]
    dates: List[str]  # YYYY-MM-DD format


class TimeEstimateRequest(BaseModel):
    num_showings: int
    mode: Optional[str] = None


class TimeEstimateResponse(BaseModel):
    estimated_seconds: float
    formatted_time: str
    has_historical_data: bool


class ShowingData(BaseModel):
    film_title: str
    format: str
    showtime: str
    daypart: str
    ticket_url: Optional[str] = None
    is_plf: bool = False


class FetchShowtimesResponse(BaseModel):
    """Response containing showtimes grouped by date and theater"""
    showtimes: Dict[str, Dict[str, List[Dict[str, Any]]]]  # {date: {theater: [showings]}}
    duration_seconds: float


class ScrapeStatusResponse(BaseModel):
    job_id: int
    status: str  # 'pending', 'running', 'completed', 'failed', 'cancelled'
    progress: int
    theaters_completed: int
    theaters_total: int
    showings_completed: Optional[int] = 0
    showings_total: Optional[int] = 0
    current_theater: Optional[str] = None
    current_showing: Optional[str] = None
    duration_seconds: Optional[float] = None
    results: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    # Cache statistics
    use_cache: Optional[bool] = False
    cache_hits: Optional[int] = 0
    cache_misses: Optional[int] = 0


# ============================================================================
# Theater Search & Collision Check Models
# ============================================================================

class ActiveTheaterItem(BaseModel):
    """A theater currently being scraped."""
    url: str
    job_id: int


class ActiveTheatersResponse(BaseModel):
    """Response for active theaters query."""
    active_theater_count: int
    theaters: List[ActiveTheaterItem]


class CollisionCheckResponse(BaseModel):
    """Response for collision check - fields are optional when no collision."""
    has_collision: bool
    conflicting_theaters: Optional[List[str]] = None
    conflicting_job_ids: Optional[List[int]] = None


class FandangoTheaterSearchResult(BaseModel):
    """A theater found from Fandango search."""
    name: str
    url: str


# ============================================================================
# Operating Hours Models
# ============================================================================

class OperatingHoursRequest(BaseModel):
    theaters: List[TheaterRequest]
    start_date: str  # YYYY-MM-DD format
    end_date: str  # YYYY-MM-DD format


class OperatingHoursRecord(BaseModel):
    theater_name: str
    date: str
    open_time: str
    close_time: str
    first_showtime: Optional[str] = None
    last_showtime: Optional[str] = None
    duration_hours: float
    showtime_count: int


class WeekComparisonRecord(BaseModel):
    theater_name: str
    day_of_week: str
    prev_date: Optional[str] = None
    prev_open: Optional[str] = None
    prev_close: Optional[str] = None
    prev_first: Optional[str] = None
    prev_last: Optional[str] = None
    prev_duration: Optional[float] = None
    curr_date: str
    curr_open: str
    curr_close: str
    curr_first: Optional[str] = None
    curr_last: Optional[str] = None
    curr_duration: float
    status: str  # 'changed', 'no_change', 'new'


class OperatingHoursResponse(BaseModel):
    operating_hours: List[OperatingHoursRecord]
    comparison: Optional[List[WeekComparisonRecord]] = None
    summary: Dict[str, int]  # {'changed': 0, 'no_change': 0, 'new': 0}
    duration_seconds: float
    results: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


@router.get("/scrapes/active-theaters", tags=["Scrapes"], response_model=ActiveTheatersResponse)
async def get_active_theaters(current_user: User = Security(get_current_user, scopes=["read:scrapes"])):
    """
    Get list of theaters currently being scraped.

    Use this endpoint to check if specific theaters are already being scraped
    before starting a new scrape job. Returns theater URLs mapped to their job IDs.
    """
    active = _get_active_theater_urls()
    return {
        "active_theater_count": len(active),
        "theaters": [
            {"url": url, "job_id": job_id}
            for url, job_id in active.items()
        ]
    }


@router.post("/scrapes/check-collision", tags=["Scrapes"], response_model=CollisionCheckResponse)
async def check_theater_collision(
    theaters: List[TheaterRequest],
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Check if any theaters would conflict with active scrape jobs.

    Use this before triggering a scrape to warn users about potential conflicts.
    """
    theater_dicts = [{"name": t.name, "url": t.url} for t in theaters]
    collision = _check_theater_collision(theater_dicts)

    if collision:
        return {
            "has_collision": True,
            "conflicting_theaters": collision["conflicting_theaters"],
            "conflicting_job_ids": collision["job_ids"]
        }

    return {"has_collision": False}


@router.get("/scrapes/jobs", tags=["Scrapes"])
async def list_scrape_jobs(
    all_users: bool = False,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """List scrape jobs. By default only shows current user's jobs.

    Args:
        all_users: If True and user is admin, show all users' jobs
    """
    current_username = current_user.get("username")
    is_admin = current_user.get("role") == "admin"

    jobs = []
    for job_id, job_info in _scrape_jobs.items():
        # Filter by user unless admin requesting all
        job_username = job_info.get("username")
        if not (all_users and is_admin):
            if job_username and job_username != current_username:
                continue  # Skip jobs from other users

        job_summary = job_info.copy()
        job_summary['job_id'] = job_id  # Include job_id in response
        # Remove bulky results if present
        if 'results' in job_summary and job_summary['results']:
            job_summary['result_count'] = len(job_summary['results'])
            # Keep only first 2 results for preview if needed, or just remove
            if job_summary['status'] == 'completed':
                del job_summary['results']
        jobs.append(job_summary)

    # Sort by job_id descending
    jobs.sort(key=lambda x: x.get('job_id', 0), reverse=True)
    return jobs


@router.post("/scrapes/jobs/{job_id}/cancel", tags=["Scrapes"])
async def cancel_scrape_job(job_id: int, current_user: User = Security(get_current_user, scopes=["write:scrapes"])):
    """Cancel a running scrape job."""
    if job_id not in _scrape_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = _scrape_jobs[job_id]
    if job.get('status') in ['running', 'pending']:
        job['status'] = 'cancelled'
        job['message'] = "Job cancelled by user"
        return {"message": "Job cancelled"}
    
    return {"message": f"Job already in state: {job.get('status')}"}


@router.get("/scrapes/search-theaters/fandango", tags=["Scrapes"], response_model=List[FandangoTheaterSearchResult])
async def search_theaters_fandango(
    query: str,
    search_type: str = "name",  # 'name' or 'zip'
    date: Optional[str] = None,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Search for theaters on Fandango by name or ZIP code.
    """
    from app.scraper import Scraper
    scout = Scraper(headless=True)
    
    try:
        if search_type == "zip":
            if not date:
                from datetime import date as dt_date, timedelta
                date = (dt_date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
            results = await scout.live_search_by_zip(query, date)
            # Convert dictionary to list for frontend
            return [{"name": name, "url": data["url"]} for name, data in results.items()]
        else:
            # Use discover_theater_url (URL-based search) instead of live_search_by_name
            # (UI selector-based) which breaks when Fandango updates their site
            result = await scout.discover_theater_url(query)
            return [
                {"name": t["name"], "url": t["url"]}
                for t in result.get("all_results", [])
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scrapes/search-theaters/cache", tags=["Scrapes"])
async def search_theaters_cache(
    query: Optional[str] = None,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Search for theaters in the local markets cache.
    """
    try:
        import json
        import os
        from app import config
        
        if not os.path.exists(config.CACHE_FILE):
             # If cache file doesn't exist, return theaters from DB if any
             # For now, return empty or common markets
             return []
             
        with open(config.CACHE_FILE, 'r') as f:
            cache_data = json.load(f)
            
        all_theaters = []
        markets = cache_data.get("markets", {})
        for market_name, market_data in markets.items():
            for theater in market_data.get("theaters", []):
                all_theaters.append({
                    "name": theater["name"],
                    "url": theater["url"],
                    "market": market_name
                })
        
        # Deduplicate
        seen = set()
        unique_theaters = []
        for t in all_theaters:
            if t["url"] not in seen:
                seen.add(t["url"])
                unique_theaters.append(t)
                
        if query:
            query = query.lower()
            unique_theaters = [t for t in unique_theaters if query in t["name"].lower() or (t.get("market") and query in t["market"].lower())]
            
        return unique_theaters[:50]  # Limit results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrapes/fetch-showtimes", response_model=FetchShowtimesResponse, tags=["Scrapes"])
async def fetch_showtimes(
    request: FetchShowtimesRequest,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Fetch showtimes for specified theaters and dates.

    Returns showtimes grouped by date and theater for film/showtime selection UI.
    This is a synchronous call that returns when all showtimes are fetched.
    """
    start_time = time.time()

    try:
        from app.scraper import Scraper

        scout = Scraper(headless=True, devtools=False)
        all_showtimes: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

        for date_str in request.dates:
            all_showtimes[date_str] = {}

            # Build theater objects for scraper
            theater_objs = [{"name": t.name, "url": t.url} for t in request.theaters]

            try:
                # Run in separate thread with ProactorEventLoop for Windows compatibility
                # Using await to not block the event loop
                showings_by_theater = await _run_async_in_thread(
                    scout.get_all_showings_for_theaters(theater_objs, date_str)
                )

                for theater in request.theaters:
                    theater_showings = showings_by_theater.get(theater.name, [])
                    all_showtimes[date_str][theater.name] = theater_showings

            except Exception as e:
                print(f"Error fetching showtimes for {date_str}: {e}")
                import traceback
                traceback.print_exc()
                # Continue with other dates even if one fails
                for theater in request.theaters:
                    all_showtimes[date_str][theater.name] = []

        duration = time.time() - start_time

        # Count total showtimes for logging
        total_showtimes = sum(
            len(theater_showings)
            for date_data in all_showtimes.values()
            for theater_showings in date_data.values()
        )

        # Log runtime for time estimation
        try:
            from app.utils import log_runtime
            log_runtime("showtimes", len(request.theaters), total_showtimes, duration)
        except Exception as log_err:
            print(f"Warning: Failed to log runtime: {log_err}")

        track_event("PriceScout.Showtimes.Fetched", {
            "TheaterCount": len(request.theaters),
            "DateCount": len(request.dates),
            "ShowtimeCount": total_showtimes,
            "DurationSeconds": duration
        })

        return FetchShowtimesResponse(
            showtimes=all_showtimes,
            duration_seconds=duration
        )

    except Exception as e:
        track_event("PriceScout.Showtimes.Failed", {
            "Error": str(e)
        })
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrapes/estimate-time", response_model=TimeEstimateResponse, tags=["Scrapes"])
async def estimate_scrape_time(
    request: TimeEstimateRequest,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Estimate how long a scrape will take based on historical data.

    Uses the last 20 scrapes to calculate average time per showing.
    Falls back to default estimates if no historical data is available.
    """
    try:
        from app.utils import estimate_scrape_time as calc_estimate, format_time_to_human_readable

        estimated_seconds = calc_estimate(request.num_showings, request.mode)

        if estimated_seconds < 0:
            # Fallback estimates based on observed performance (seconds per showtime)
            # - showtimes mode: ~0.5-1 sec per showtime (fetching schedule data)
            # - market mode: ~1-2 sec per showtime (full price scraping)
            # - price mode: ~1.5 sec per showtime (ticket price checking)
            mode_lower = (request.mode or '').lower()
            if 'showtime' in mode_lower:
                avg_per_showing = 0.75  # Showtime fetching is faster
            elif 'market' in mode_lower or 'price' in mode_lower:
                avg_per_showing = 1.5   # Price scraping takes longer
            else:
                avg_per_showing = 1.0   # Default estimate

            fallback_seconds = avg_per_showing * request.num_showings

            return TimeEstimateResponse(
                estimated_seconds=fallback_seconds,
                formatted_time=f"~{format_time_to_human_readable(fallback_seconds)}",
                has_historical_data=True  # Set to True so UI shows the estimate
            )

        return TimeEstimateResponse(
            estimated_seconds=estimated_seconds,
            formatted_time=format_time_to_human_readable(estimated_seconds),
            has_historical_data=True
        )

    except Exception as e:
        # If estimation fails, return a default response
        return TimeEstimateResponse(
            estimated_seconds=-1,
            formatted_time="Unable to estimate",
            has_historical_data=False
        )


@router.post("/scrapes/operating-hours", response_model=OperatingHoursResponse, tags=["Scrapes"])
async def fetch_operating_hours(
    request: OperatingHoursRequest,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Fetch showtimes and calculate operating hours for specified theaters and date range.

    Returns operating hours (open/close times) derived from earliest/latest showtimes,
    plus week-over-week comparison if previous week data exists.
    """
    start_time = time.time()

    try:
        from app.scraper import Scraper
        from app.utils import normalize_time_string
        from datetime import datetime as dt, timedelta

        scout = Scraper(headless=True, devtools=False)
        operating_hours: List[OperatingHoursRecord] = []

        # Parse date range
        start = dt.strptime(request.start_date, "%Y-%m-%d")
        end = dt.strptime(request.end_date, "%Y-%m-%d")

        # Generate list of dates
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        # Build theater objects for scraper
        theater_objs = [{"name": t.name, "url": t.url} for t in request.theaters]

        # Fetch showtimes for each date
        for date_str in dates:
            try:
                showings_by_theater = await _run_async_in_thread(
                    scout.get_all_showings_for_theaters(theater_objs, date_str)
                )

                # Save showings to database for other data needs (films, amenities, times)
                if showings_by_theater:
                    try:
                        date_obj = dt.strptime(date_str, "%Y-%m-%d")
                        database.upsert_showings(showings_by_theater, date_obj)
                        print(f"[OperatingHours] Saved showings for {date_str}")
                    except Exception as e:
                        import traceback
                        print(f"[OperatingHours] Warning: Failed to save showings for {date_str}: {e}")
                        traceback.print_exc()

                for theater in request.theaters:
                    theater_showings = showings_by_theater.get(theater.name, [])

                    if theater_showings:
                        # Extract all showtime strings and parse to find min/max
                        times = []
                        for s in theater_showings:
                            showtime_str = s.get("showtime", "")
                            if showtime_str:
                                times.append(showtime_str)

                        if times:
                            # Parse times to find earliest and latest
                            def parse_time(t):
                                try:
                                    normalized = normalize_time_string(t)
                                    return dt.strptime(normalized, "%I:%M%p")
                                except Exception:
                                    return dt.strptime("12:00PM", "%I:%M%p")

                            parsed_times = [(t, parse_time(t)) for t in times]
                            parsed_times.sort(key=lambda x: x[1])

                            open_time = parsed_times[0][0]
                            close_time = parsed_times[-1][0]

                            # Calculate duration in hours
                            open_dt = parsed_times[0][1]
                            close_dt = parsed_times[-1][1]
                            duration = (close_dt - open_dt).seconds / 3600

                            operating_hours.append(OperatingHoursRecord(
                                theater_name=theater.name,
                                date=date_str,
                                open_time=open_time,
                                close_time=close_time,
                                first_showtime=open_time,
                                last_showtime=close_time,
                                duration_hours=round(duration, 1),
                                showtime_count=len(theater_showings)
                            ))
                    else:
                        # No showtimes found
                        operating_hours.append(OperatingHoursRecord(
                            theater_name=theater.name,
                            date=date_str,
                            open_time="N/A",
                            close_time="N/A",
                            duration_hours=0.0,
                            showtime_count=0
                        ))

            except Exception as e:
                print(f"Error fetching operating hours for {date_str}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # Build week-over-week comparison if we have 7+ days
        comparison: List[WeekComparisonRecord] = []
        summary = {"changed": 0, "no_change": 0, "new": 0}

        if len(dates) >= 7:
            # Group by theater and day of week for comparison
            prev_week_end = start - timedelta(days=1)
            prev_week_start = prev_week_end - timedelta(days=6)

            # Try to get previous week data from database
            try:
                prev_hours = database.get_operating_hours_for_theaters_and_dates(
                    [t.name for t in request.theaters],
                    prev_week_start.strftime("%Y-%m-%d"),
                    prev_week_end.strftime("%Y-%m-%d")
                )

                # Create lookup for previous week
                prev_lookup = {}
                if prev_hours is not None and not prev_hours.empty:
                    for _, record in prev_hours.iterrows():
                        key = (record['theater_name'], dt.strptime(str(record['scrape_date']), "%Y-%m-%d").strftime("%A"))
                        prev_lookup[key] = record

                # Build comparison records
                for oh in operating_hours:
                    date_obj = dt.strptime(oh.date, "%Y-%m-%d")
                    day_of_week = date_obj.strftime("%A")
                    key = (oh.theater_name, day_of_week)

                    prev = prev_lookup.get(key)

                    if prev is not None:
                        # Check if hours changed
                        if prev['open_time'] == oh.open_time and prev['close_time'] == oh.close_time:
                            status = "no_change"
                            summary["no_change"] += 1
                        else:
                            status = "changed"
                            summary["changed"] += 1

                        comparison.append(WeekComparisonRecord(
                            theater_name=oh.theater_name,
                            day_of_week=day_of_week,
                            prev_date=str(prev['scrape_date']),
                            prev_open=prev['open_time'],
                            prev_close=prev['close_time'],
                            prev_first=prev.get('first_showtime', None),
                            prev_last=prev.get('last_showtime', None),
                            prev_duration=prev['duration_hours'],
                            curr_date=oh.date,
                            curr_open=oh.open_time,
                            curr_close=oh.close_time,
                            curr_first=oh.first_showtime,
                            curr_last=oh.last_showtime,
                            curr_duration=oh.duration_hours,
                            status=status
                        ))
                    else:
                        # New - no previous week data
                        summary["new"] += 1
                        comparison.append(WeekComparisonRecord(
                            theater_name=oh.theater_name,
                            day_of_week=day_of_week,
                            curr_date=oh.date,
                            curr_open=oh.open_time,
                            curr_close=oh.close_time,
                            curr_first=oh.first_showtime,
                            curr_last=oh.last_showtime,
                            curr_duration=oh.duration_hours,
                            status="new"
                        ))

            except Exception as e:
                print(f"Error fetching previous week data: {e}")
                # Continue without comparison

        duration = time.time() - start_time

        # Save operating hours to database using merge logic (high water mark protection)
        try:
            # Convert to the format expected by save_full_operating_hours_run (list of dicts)
            # Note: We no longer delete first - save_operating_hours uses merge logic
            # to preserve the best data (earliest open, latest close)
            save_data = []
            for oh in operating_hours:
                if oh.open_time != "N/A":
                    save_data.append({
                        "Theater": oh.theater_name,
                        "Date": oh.date,
                        "Market": "",
                        "Showtime Range": f"{oh.open_time} - {oh.close_time}",
                        "Duration (hrs)": oh.duration_hours,
                        "First Showtime": oh.first_showtime,
                        "Last Showtime": oh.last_showtime,
                        "Showtime Count": oh.showtime_count
                    })
            
            if save_data:
                database.save_full_operating_hours_run(save_data, f"Fetch: {len(request.theaters)} theaters")
        except Exception as e:
            print(f"Error saving operating hours: {e}")

        track_event("PriceScout.OperatingHours.Fetched", {
            "TheaterCount": len(request.theaters),
            "DateCount": len(dates),
            "DurationSeconds": duration
        })

        return OperatingHoursResponse(
            operating_hours=operating_hours,
            comparison=comparison if comparison else None,
            summary=summary,
            duration_seconds=duration
        )

    except Exception as e:
        track_event("PriceScout.OperatingHours.Failed", {
            "Error": str(e)
        })
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrapes/save", tags=["Scrapes"])
async def save_scrape_data(scrape_data: ScrapeData, current_user: User = Security(get_current_user, scopes=["write:scrapes"])):
    """
    Saves scrape data to the database with telemetry tracking.
    """
    start_time = time.time()
    
    try:
        df = pd.DataFrame(scrape_data.data)
        database.save_prices(scrape_data.run_id, df)
        
        # Track scrape metrics
        duration = time.time() - start_time
        showing_count = len(scrape_data.data)
        price_count = showing_count  # Each showing has price data
        
        track_scrape_completed(
            theater_count=df['theater_name'].nunique() if 'theater_name' in df.columns else 0,
            showing_count=showing_count,
            price_count=price_count,
            duration_seconds=duration,
            success=True
        )
        
        return {"message": "Scrape data saved successfully.", "records": showing_count}
    except Exception as e:
        track_event("PriceScout.Scrape.Failed", {
            "RunId": str(scrape_data.run_id),
            "Error": str(e)
        })
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/scrape_runs", tags=["Scrapes"])
async def create_scrape_run(mode: str, context: str, current_user: User = Security(get_current_user, scopes=["write:scrapes"])):
    """
    Creates a new scrape run record with telemetry tracking.
    """
    try:
        run_id = database.create_scrape_run(mode, context)

        # Track scrape run creation
        track_event("PriceScout.ScrapeRun.Created", {
            "RunId": str(run_id),
            "Mode": mode,
            "Context": context
        })

        return {"run_id": run_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Market Mode Scraping API
# ============================================================================

@router.post("/scrapes/trigger", response_model=TriggerScrapeResponse, tags=["Scrapes"])
async def trigger_scrape(
    request: TriggerScrapeRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Trigger a new scrape job for specified theaters and dates.

    The scrape runs in the background and can be monitored via the status endpoint.

    **Theater Collision Prevention**: If any requested theaters are already being
    scraped by another job, this endpoint returns a 409 Conflict error with details
    about the conflicting theaters and job IDs.
    """
    global _job_counter

    # Check for theater collisions with active jobs
    theater_dicts = [{"name": t.name, "url": t.url} for t in request.theaters]
    collision = _check_theater_collision(theater_dicts)

    if collision:
        conflicting_names = [t["name"] for t in collision["conflicting_theaters"]]
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Cannot start scrape: {len(conflicting_names)} theater(s) are already being scraped",
                "conflicting_theaters": conflicting_names,
                "conflicting_job_ids": collision["job_ids"],
                "suggestion": "Wait for the existing scrape to complete, or cancel it first"
            }
        )

    _job_counter += 1
    job_id = _job_counter

    # Initialize job state (including theaters for collision detection)
    _scrape_jobs[job_id] = {
        "status": "pending",
        "progress": 0,
        "theaters_completed": 0,
        "theaters_total": len(request.theaters),
        "theaters": theater_dicts,  # Store for collision detection
        "showings_completed": 0,
        "showings_total": len(request.selected_showtimes) if request.selected_showtimes else 0,
        "current_theater": None,
        "current_showing": None,
        "started_at": datetime.now().isoformat(),
        "results": [],
        "error": None,
        "username": current_user.get("username"),  # Track who started this job
    }

    # If Celery is enabled, use it for distributed processing
    if config.USE_CELERY:
        from app.tasks.scrapes import run_scrape_task
        task = run_scrape_task.delay(
            mode=request.mode,
            market=request.market,
            theaters=[t.dict() for t in request.theaters],
            dates=request.dates,
            company_id=current_user.get("company_id") or 1,
            use_cache=request.use_cache
        )
        # Store Celery task ID in our job tracker
        _scrape_jobs[job_id]["celery_task_id"] = task.id
        _scrape_jobs[job_id]["status"] = "distributed"
    else:
        # Launch scrape in a separate thread so the API stays responsive
        _launch_in_thread(
            run_scrape_job,
            job_id,
            request.mode,
            request.market,
            [t.dict() for t in request.theaters],
            request.dates,
            request.selected_showtimes,
            request.use_cache,
            request.cache_max_age_hours
        )

    track_event("PriceScout.ScrapeJob.Started", {
        "JobId": str(job_id),
        "Mode": request.mode,
        "TheaterCount": len(request.theaters),
        "DateCount": len(request.dates),
        "UseCache": request.use_cache
    })

    # Audit scrape trigger
    audit_service.data_event(
        event_type="trigger_scrape",
        user_id=current_user.get("user_id"),
        username=current_user.get("username"),
        company_id=current_user.get("company_id") or 1,
        details={
            "job_id": job_id,
            "mode": request.mode,
            "theater_count": len(request.theaters),
            "date_count": len(request.dates),
            "use_cache": request.use_cache
        }
    )

    return TriggerScrapeResponse(
        job_id=job_id,
        status="pending",
        message=f"Scrape job started for {len(request.theaters)} theaters"
    )


@router.get("/scrapes/{job_id}/status", response_model=ScrapeStatusResponse, tags=["Scrapes"])
async def get_scrape_status(
    job_id: int,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Get the status of a scrape job.

    Poll this endpoint to track progress of a running scrape.
    """
    if job_id not in _scrape_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = _scrape_jobs[job_id].copy()
    
    # If it's a Celery task, check the async result
    if "celery_task_id" in job and config.USE_CELERY:
        try:
            from celery.result import AsyncResult
            from app.celery_app import app as celery_app
            
            res = AsyncResult(job["celery_task_id"], app=celery_app)
            
            if res.state == 'SUCCESS':
                result = res.result
                job["status"] = "completed"
                job["progress"] = 100
                job["records_found"] = result.get('records', 0)
                job["completed_at"] = datetime.now().isoformat()
                job["duration_seconds"] = result.get('duration_seconds')
            elif res.state == 'FAILURE':
                job["status"] = "failed"
                job["error"] = str(res.result)
            elif res.state == 'PROGRESS':
                job["status"] = "running"
                info = res.info or {}
                job["progress"] = info.get('progress', 0)
                job["current_theater"] = info.get('current_theater')
        except Exception as e:
            print(f"Error checking Celery task status: {e}")
            
    return ScrapeStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        theaters_completed=job.get("theaters_completed", 0),
        theaters_total=job.get("theaters_total", 0),
        showings_completed=job.get("showings_completed", 0),
        showings_total=job.get("showings_total", 0),
        current_theater=job.get("current_theater"),
        current_showing=job.get("current_showing"),
        duration_seconds=job.get("duration_seconds"),
        results=job.get("results") if job["status"] == "completed" else None,
        error=job.get("error"),
        use_cache=job.get("use_cache", False),
        cache_hits=job.get("cache_hits", 0),
        cache_misses=job.get("cache_misses", 0)
    )


@router.post("/scrapes/{job_id}/cancel", tags=["Scrapes"])
async def cancel_scrape(
    job_id: int,
    current_user: User = Security(get_current_user, scopes=["write:scrapes"])
):
    """
    Cancel a running scrape job.
    """
    if job_id not in _scrape_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = _scrape_jobs[job_id]

    if job["status"] not in ["pending", "running"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job['status']}'"
        )

    job["status"] = "cancelled"

    # Audit scrape cancellation
    audit_service.data_event(
        event_type="cancel_scrape",
        user_id=current_user.get("user_id"),
        username=current_user.get("username"),
        company_id=current_user.get("company_id") or 1,
        details={"job_id": job_id}
    )

    return {"message": f"Job {job_id} cancelled"}


async def run_scrape_job(
    job_id: int,
    mode: str,
    market: Optional[str],
    theaters: List[Dict[str, str]],
    dates: List[str],
    selected_showtime_keys: Optional[List[str]] = None,
    use_cache: bool = False,
    cache_max_age_hours: int = 6
):
    """
    Background task to run the actual scrape.

    DEBUG: Added explicit logging to trace execution flow.

    This function uses the Scraper class to fetch prices from Fandango.
    When use_cache=True, it first checks EntTelligence cache for prices.

    Args:
        selected_showtime_keys: Optional list of "date|theater|film|time" keys.
            If provided, only these showings will be scraped.
            If None, all showings for the theaters/dates will be scraped.
        use_cache: If True, check EntTelligence cache before scraping
        cache_max_age_hours: Max age (hours) for cached data to be considered fresh
    """
    print(f"\n{'='*60}")
    print(f"[SCRAPE JOB {job_id}] STARTED - mode={mode}, theaters={len(theaters)}, dates={dates}")
    print(f"[SCRAPE JOB {job_id}] Selected keys: {len(selected_showtime_keys) if selected_showtime_keys else 'None (all)'}")
    print(f"{'='*60}\n")

    # Convert keys to a set for fast lookup
    selected_keys_set = set(selected_showtime_keys) if selected_showtime_keys else None
    job = _scrape_jobs[job_id]
    job["status"] = "running"
    job["use_cache"] = use_cache
    job["cache_hits"] = 0
    job["cache_misses"] = 0
    company_id = config.DEFAULT_COMPANY_ID
    start_time = time.time()

    # Initialize cache service if using cache
    cache_service = None
    if use_cache:
        try:
            from api.services.enttelligence_cache_service import get_cache_service
            cache_service = get_cache_service()
            print(f"[SCRAPER] Cache enabled with {cache_max_age_hours}h max age")
        except Exception as e:
            print(f"[SCRAPER] Warning: Cache service unavailable: {e}")
            use_cache = False

    # Progress tracking variables
    base_showings_completed = 0  # Cumulative from previous theater/date batches

    # Lock the total when user provided explicit selections
    has_fixed_total = selected_keys_set is not None and len(selected_keys_set) > 0
    if has_fixed_total:
        job["showings_total"] = len(selected_keys_set)

    def make_progress_callback(total_showings: int):
        """Create a progress callback for the current batch of showings."""
        def progress_callback(current: int, total: int):
            job["showings_completed"] = base_showings_completed + current
            # Only update the total if the user didn't provide a fixed selection
            if not has_fixed_total:
                job["showings_total"] = max(job.get("showings_total", 0), base_showings_completed + total)
            if job["showings_total"] > 0:
                job["progress"] = int((job["showings_completed"] / job["showings_total"]) * 100)
            job["current_showing"] = f"{current}/{total}"
            print(f"  [JOB] Progress update: {job['showings_completed']}/{job['showings_total']} ({job['progress']}%)")
        return progress_callback

    try:
        # Import scraper here to avoid circular imports
        from app.scraper import Scraper

        scout = Scraper(headless=True, devtools=False)
        all_results = []

        for i, theater in enumerate(theaters):
            if job["status"] == "cancelled":
                break

            job["current_theater"] = theater["name"]
            job["theaters_completed"] = i

            try:
                # Build showtimes dict for this theater
                theater_obj = {"name": theater["name"], "url": theater["url"]}

                # Get showtimes for this theater across all dates
                for date_str in dates:
                    try:
                        # Fetch showtime data using the scraper method
                        # Run in separate thread with ProactorEventLoop for Windows compatibility
                        # get_all_showings_for_theaters returns {theater_name: [showings]}
                        # Phase 1: Fetch and save basic showtimes (for immediate UI results)
                        showtime_data_dict = await _run_async_in_thread(
                            scout.get_all_showings_for_theaters(
                                [theater_obj],
                                date_str
                            )
                        )
                        showtime_data = showtime_data_dict.get(theater['name'], [])
                        
                        if showtime_data:
                            print(f"  [JOB] Saving {len(showtime_data)} base showtimes for {theater['name']} on {date_str}")
                            # Set company ID for database operations (default to 1 for now)
                            from app import config
                            config.CURRENT_COMPANY_ID = 1 # Force to 1 for now, or use value from request
                            try:
                                database.upsert_showings(showtime_data_dict, date_str)
                                print(f"  [JOB] upsert_showings completed for {theater['name']}")
                            except Exception as upsert_err:
                                print(f"  [JOB] ERROR in upsert_showings: {upsert_err}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"  [JOB] No showtimes found for {theater['name']} on {date_str}")

                        if showtime_data:
                            # Filter showings based on user selection if provided
                            if selected_keys_set:
                                filtered_showtime_data = []
                                for showing in showtime_data:
                                    film = showing.get("film_title", "Unknown")
                                    showtime_str = showing.get("showtime", "")
                                    fmt = showing.get("format", "Standard")
                                    # Build key in same format as frontend: "date|theater|film|time|format"
                                    key = f"{date_str}|{theater['name']}|{film}|{showtime_str}|{fmt}"
                                    if key in selected_keys_set:
                                        filtered_showtime_data.append(showing)
                                showtime_data = filtered_showtime_data
                                print(f"  [SCRAPER] Filtered to {len(showtime_data)} selected showings for {theater['name']}")

                            if not showtime_data:
                                continue  # Skip if no showings match selection

                            # Update total showings estimate if not already known from selection
                            if not selected_keys_set:
                                job["showings_total"] = job.get("showings_total", 0) + len(showtime_data)

                            # Skip price scraping if we're only interested in the lineup
                            if mode == 'lineup':
                                print(f"  [JOB] Skipping price scraping for {theater['name']} due to 'lineup' mode")
                                job["showings_completed"] = job.get("showings_completed", 0) + len(showtime_data)
                                if job["showings_total"] > 0:
                                    job["progress"] = int((job["showings_completed"] / job["showings_total"]) * 100)
                                base_showings_completed = job.get("showings_completed", 0)
                                continue

                            # Check cache first if enabled
                            showings_to_scrape = []
                            cached_results = []

                            if use_cache and cache_service:
                                # Build showtime keys for cache lookup
                                showtime_keys_for_cache = []
                                for showing in showtime_data:
                                    film = showing.get("film_title", "Unknown")
                                    st = showing.get("showtime", "")
                                    fmt = showing.get("format", "Standard")
                                    key = f"{date_str}|{theater['name']}|{film}|{st}|{fmt}"
                                    showtime_keys_for_cache.append((key, showing))

                                # Lookup all keys in cache (returns all ticket types per key)
                                cache_lookup = cache_service.lookup_cached_prices_all_types(
                                    [k for k, _ in showtime_keys_for_cache],
                                    company_id=company_id,
                                    max_age_hours=cache_max_age_hours
                                )

                                for key, showing in showtime_keys_for_cache:
                                    cached_list = cache_lookup.get(key, [])
                                    if cached_list:
                                        # Cache hit - build one result per ticket type
                                        job["cache_hits"] = job.get("cache_hits", 0) + 1
                                        for cached in cached_list:
                                            fmt = cached.format or showing.get("format")
                                            # Convert play_date to date object if it's a string
                                            play_date = cached.play_date
                                            if isinstance(play_date, str):
                                                play_date = datetime.strptime(play_date, "%Y-%m-%d").date()
                                            # Build result with tax estimation
                                            result_entry = {
                                                # snake_case for React frontend
                                                "theater_name": cached.theater_name,
                                                "film_title": cached.film_title,
                                                "showtime": cached.showtime,
                                                "price": f"${cached.price:.2f}",
                                                "price_raw": cached.price,
                                                "ticket_type": cached.ticket_type,
                                                "format": fmt,
                                                "play_date": play_date,
                                                "source": "enttelligence_cache",
                                                "fetched_at": cached.fetched_at.isoformat(),
                                                # Title Case for backward compatibility with save_prices
                                                "Theater Name": cached.theater_name,
                                                "Film Title": cached.film_title,
                                                "Showtime": cached.showtime,
                                                "Price": f"${cached.price:.2f}",
                                                "Ticket Type": cached.ticket_type,
                                                "Format": fmt,
                                            }

                                            # Add tax estimation if available
                                            try:
                                                from api.services.tax_estimation import (
                                                    get_tax_config as _get_tax_cfg,
                                                    get_theater_state,
                                                    get_tax_rate_for_theater,
                                                    apply_estimated_tax,
                                                )
                                                tc = _get_tax_cfg(company_id)
                                                if tc.get("enabled"):
                                                    st = get_theater_state(company_id, cached.theater_name)
                                                    rate = get_tax_rate_for_theater(tc, st, theater_name=cached.theater_name)
                                                    adj = apply_estimated_tax(cached.price, rate)
                                                    result_entry["price_estimated_with_tax"] = adj
                                                    result_entry["tax_rate"] = rate
                                            except Exception:
                                                pass  # Tax estimation is optional

                                            cached_results.append(result_entry)
                                    else:
                                        # Cache miss - need to scrape
                                        job["cache_misses"] = job.get("cache_misses", 0) + 1
                                        showings_to_scrape.append(showing)

                                print(f"  [SCRAPER] Cache: {job['cache_hits']} hits ({len(cached_results)} prices incl. Child/Senior), {job['cache_misses']} misses for {theater['name']}")

                                # Add cached results immediately and update progress
                                if cached_results:
                                    all_results.extend(cached_results)
                                    job["showings_completed"] = job.get("showings_completed", 0) + len(cached_results)
                                    if job.get("showings_total", 0) > 0:
                                        job["progress"] = int((job["showings_completed"] / job["showings_total"]) * 100)
                            else:
                                # No cache - scrape all
                                showings_to_scrape = showtime_data

                            # Only scrape if there are uncached showings
                            if showings_to_scrape:
                                # Update base for the callback to include anything already completed (like cache hits)
                                base_showings_completed = job.get("showings_completed", 0)

                                # Build selected_showtimes structure for uncached showings
                                selected_showtimes = {}
                                for showing in showings_to_scrape:
                                    film = showing.get("film_title", "Unknown")
                                    showtime = showing.get("showtime", "")

                                    if date_str not in selected_showtimes:
                                        selected_showtimes[date_str] = {}
                                    if theater["name"] not in selected_showtimes[date_str]:
                                        selected_showtimes[date_str][theater["name"]] = {}
                                    if film not in selected_showtimes[date_str][theater["name"]]:
                                        selected_showtimes[date_str][theater["name"]][film] = {}

                                    selected_showtimes[date_str][theater["name"]][film][showtime] = [showing]

                                # Create progress callback for this batch
                                callback = make_progress_callback(len(showings_to_scrape))

                                # Scrape prices using scraper method in separate thread
                                result, _ = await _run_async_in_thread(
                                    scout.scrape_details(
                                        [theater_obj],
                                        selected_showtimes,
                                        progress_callback=callback
                                    )
                                )

                                if result:
                                    # Mark results as from fandango and add play_date
                                    # Convert date_str to date object for SQLite
                                    play_date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                                    for r in result:
                                        r["source"] = "fandango"
                                        r["play_date"] = play_date_obj
                                    all_results.extend(result)

                            # Update base for next batch
                            base_showings_completed = job.get("showings_completed", 0)
                    except Exception as e:
                        print(f"Error scraping {theater['name']} for {date_str}: {e}")
                        import traceback
                        traceback.print_exc()
                        continue

            except Exception as e:
                print(f"Error processing theater {theater['name']}: {e}")
                continue

        # Job completed
        job["status"] = "completed"
        job["theaters_completed"] = len(theaters)
        job["progress"] = 100
        job["results"] = all_results
        job["duration_seconds"] = time.time() - start_time
        job["current_theater"] = None

        # Log runtime for time estimation
        try:
            from app.utils import log_runtime
            num_showings = job.get("showings_completed", 0) or len(all_results)
            log_runtime(mode, len(theaters), num_showings, job["duration_seconds"])
            print(f"[SCRAPE JOB {job_id}] Logged runtime: {mode}, {len(theaters)} theaters, {num_showings} showings, {job['duration_seconds']:.1f}s")
        except Exception as log_err:
            print(f"Warning: Failed to log runtime: {log_err}")

        # Save to database
        if all_results:
            try:
                print(f"\n[SCRAPE JOB {job_id}] SAVING RESULTS - {len(all_results)} price records")
                # Set company ID for database operations (default to 1 for now)
                from app import config
                config.CURRENT_COMPANY_ID = 1

                run_id = database.create_scrape_run(mode, f"Market: {market or 'N/A'}")
                print(f"[SCRAPE JOB {job_id}] Created scrape run with ID: {run_id}")
                df = pd.DataFrame(all_results)
                print(f"[SCRAPE JOB {job_id}] DataFrame columns: {list(df.columns)}")
                print(f"[SCRAPE JOB {job_id}] DataFrame sample row: {df.iloc[0].to_dict() if len(df) > 0 else 'empty'}")
                database.save_prices(run_id, df)
                database.update_scrape_run_status(run_id, 'completed', len(all_results))
                print(f"[SCRAPE JOB {job_id}] Successfully saved {len(all_results)} price records to database (run_id: {run_id})")

                # Generate price alerts after saving prices
                try:
                    from app.alert_service import generate_alerts_for_scrape
                    from app.notification_service import dispatch_alerts_sync

                    company_id = getattr(config, 'CURRENT_COMPANY_ID', 1)
                    alerts = generate_alerts_for_scrape(company_id, run_id, df)

                    if alerts:
                        print(f"Generated {len(alerts)} price alerts")
                        # Dispatch notifications synchronously (we're already in a background thread)
                        dispatch_alerts_sync(company_id, alerts)
                except Exception as alert_err:
                    print(f"Warning: Alert generation failed: {alert_err}")
                    # Don't fail the scrape if alerts fail
                    import traceback
                    traceback.print_exc()

                # Auto-refresh baselines with drift protection
                try:
                    from app.baseline_guard import trigger_post_scrape_refresh

                    company_id = getattr(config, 'CURRENT_COMPANY_ID', 1)
                    refresh_result = trigger_post_scrape_refresh(company_id, source="fandango")
                    applied = refresh_result.get("applied", 0)
                    new = refresh_result.get("new", 0)
                    flagged = refresh_result.get("flagged", 0)
                    if applied or new or flagged:
                        print(
                            f"[SCRAPE JOB {job_id}] Baseline auto-refresh: "
                            f"{applied} updated, {new} new, {flagged} flagged for review"
                        )
                except Exception as refresh_err:
                    print(f"Warning: Baseline auto-refresh failed: {refresh_err}")

            except Exception as e:
                print(f"Error saving results to database: {e}")
                import traceback
                traceback.print_exc()
                # Mark scrape run as failed if we have a run_id
                if 'run_id' in locals():
                    database.update_scrape_run_status(run_id, 'failed', 0, str(e))

        track_scrape_completed(
            theater_count=len(theaters),
            showing_count=len(all_results),
            price_count=len(all_results),
            duration_seconds=job["duration_seconds"],
            success=True
        )

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["duration_seconds"] = time.time() - start_time

        track_event("PriceScout.ScrapeJob.Failed", {
            "JobId": str(job_id),
            "Error": str(e)
        })


# ============================================================================
# Fandango Verification (Spot-Check EntTelligence + Tax vs Fandango)
# ============================================================================

class VerifyPricesRequest(BaseModel):
    theaters: List[Dict[str, str]]  # Same format as trigger scrape: [{name, url}]
    dates: List[str]  # YYYY-MM-DD
    selected_showtimes: Optional[List[str]] = None  # Optional "date|theater|film|time|format" keys
    market: Optional[str] = None


class PriceVerificationItem(BaseModel):
    theater_name: str
    film_title: str
    showtime: str
    format: Optional[str] = None
    ticket_type: str
    fandango_price: float
    enttelligence_price: float
    tax_rate: float
    enttelligence_with_tax: float
    difference: float
    difference_percent: float
    match_status: str  # 'exact' (<$0.01), 'close' (<2%), 'divergent' (>2%)


class VerificationSummary(BaseModel):
    total_verified: int
    exact_matches: int
    close_matches: int
    divergent: int
    avg_difference_percent: float


class VerificationResponse(BaseModel):
    job_id: int
    status: str
    summary: Optional[VerificationSummary] = None
    comparisons: Optional[List[PriceVerificationItem]] = None
    fandango_only: Optional[int] = None  # Prices scraped from Fandango with no cache match
    error: Optional[str] = None


@router.post("/scrapes/verify-prices", tags=["Scrapes"])
async def verify_prices(
    request: VerifyPricesRequest,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Run a Fandango verification scrape: scrapes Fandango live, then compares
    each price against EntTelligence cache + estimated tax.

    This is a spot-check tool to validate that EntTelligence + tax estimation
    matches real Fandango prices.

    Returns a job ID; poll /scrapes/{job_id}/status for results.
    """
    if not request.theaters:
        raise HTTPException(status_code=400, detail="No theaters specified")
    if not request.dates:
        raise HTTPException(status_code=400, detail="No dates specified")

    # Create verification job (reuses scrape job infrastructure)
    job_id = int(time.time() * 1000) % 1000000
    _scrape_jobs[job_id] = {
        "job_id": job_id,
        "mode": "verification",
        "status": "pending",
        "theaters_total": len(request.theaters),
        "theaters_completed": 0,
        "showings_total": 0,
        "showings_completed": 0,
        "progress": 0,
        "results": [],
        "market": request.market,
        "current_theater": None,
        "verification_results": None,
    }

    # Audit
    audit_service.data_event(
        event_type="verify_prices",
        user_id=current_user.get("user_id"),
        username=current_user.get("username"),
        company_id=current_user.get("company_id") or 1,
        details={
            "job_id": job_id,
            "theater_count": len(request.theaters),
            "dates": request.dates,
        }
    )

    # Launch verification in a separate thread so the API stays responsive
    _launch_in_thread(
        run_verification_job,
        job_id=job_id,
        theaters=request.theaters,
        dates=request.dates,
        selected_showtime_keys=request.selected_showtimes,
        market=request.market,
    )

    return {"job_id": job_id, "status": "pending", "message": "Verification job started"}


async def run_verification_job(
    job_id: int,
    theaters: List[Dict[str, str]],
    dates: List[str],
    selected_showtime_keys: Optional[List[str]] = None,
    market: Optional[str] = None,
):
    """
    Background task: scrape Fandango (never cache), then compare each price
    against EntTelligence cache + tax estimation.
    """
    job = _scrape_jobs[job_id]
    job["status"] = "running"
    company_id = config.DEFAULT_COMPANY_ID
    start_time = time.time()

    try:
        # Step 1: Run a full Fandango scrape (use_cache=False)
        # We'll reuse the same scraper infrastructure
        from app.scraper import Scraper
        scout = Scraper()

        selected_keys_set = set(selected_showtime_keys) if selected_showtime_keys else None
        all_fandango_results = []

        for theater in theaters:
            if job.get("status") == "cancelled":
                break

            job["current_theater"] = theater["name"]

            try:
                theater_obj = type('Theater', (), {'name': theater["name"], 'url': theater.get("url", "")})()

                for date_str in dates:
                    if job.get("status") == "cancelled":
                        break

                    # Fetch showtimes
                    showtime_data = await _run_async_in_thread(
                        scout.fetch_showtimes(theater_obj, date_str)
                    )
                    if not showtime_data:
                        continue

                    # Filter by selected keys if provided
                    if selected_keys_set:
                        filtered = []
                        for showing in showtime_data:
                            film = showing.get("film_title", "Unknown")
                            st = showing.get("showtime", "")
                            fmt = showing.get("format", "Standard")
                            key = f"{date_str}|{theater['name']}|{film}|{st}|{fmt}"
                            if key in selected_keys_set:
                                filtered.append(showing)
                        showtime_data = filtered

                    if not showtime_data:
                        continue

                    job["showings_total"] = job.get("showings_total", 0) + len(showtime_data)

                    # Build selected_showtimes for scraper
                    selected_showtimes = {}
                    for showing in showtime_data:
                        film = showing.get("film_title", "Unknown")
                        showtime = showing.get("showtime", "")
                        if date_str not in selected_showtimes:
                            selected_showtimes[date_str] = {}
                        if theater["name"] not in selected_showtimes[date_str]:
                            selected_showtimes[date_str][theater["name"]] = {}
                        if film not in selected_showtimes[date_str][theater["name"]]:
                            selected_showtimes[date_str][theater["name"]][film] = {}
                        selected_showtimes[date_str][theater["name"]][film][showtime] = [showing]

                    # Scrape from Fandango (never cache)
                    result, _ = await _run_async_in_thread(
                        scout.scrape_details([theater_obj], selected_showtimes)
                    )

                    if result:
                        play_date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                        for r in result:
                            r["source"] = "fandango"
                            r["play_date"] = play_date_obj
                        all_fandango_results.extend(result)

                    job["showings_completed"] = job.get("showings_completed", 0) + len(showtime_data)
                    if job["showings_total"] > 0:
                        job["progress"] = int((job["showings_completed"] / job["showings_total"]) * 100)

                job["theaters_completed"] = job.get("theaters_completed", 0) + 1

            except Exception as e:
                print(f"[VERIFY] Error processing {theater['name']}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # Step 2: Look up EntTelligence cache prices for the same showings
        verification_items = []
        fandango_only_count = 0

        try:
            from api.services.enttelligence_cache_service import get_cache_service
            cache_service = get_cache_service()
        except Exception as e:
            print(f"[VERIFY] Cache service unavailable: {e}")
            cache_service = None

        # Load tax config once
        tax_config = None
        try:
            from api.services.tax_estimation import (
                get_tax_config as _get_tax_cfg,
                get_theater_state,
                get_tax_rate_for_theater,
                apply_estimated_tax,
            )
            tax_config = _get_tax_cfg(company_id)
        except Exception:
            pass

        if cache_service and all_fandango_results:
            # Build cache lookup keys from Fandango results
            from api.services.enttelligence_cache_service import normalize_film_title, normalize_showtime

            fandango_by_key = {}
            cache_keys = []
            for r in all_fandango_results:
                theater_name = r.get("theater_name") or r.get("Theater Name", "")
                film_title = r.get("film_title") or r.get("Film Title", "")
                showtime = r.get("showtime") or r.get("Showtime", "")
                play_date = r.get("play_date")
                ticket_type = r.get("ticket_type") or r.get("Ticket Type", "Adult")
                fandango_price_str = r.get("price_raw") or r.get("price") or r.get("Price", "0")

                if isinstance(fandango_price_str, str):
                    fandango_price_str = fandango_price_str.replace("$", "").strip()
                fandango_price = float(fandango_price_str) if fandango_price_str else 0

                if isinstance(play_date, date):
                    date_str = play_date.strftime("%Y-%m-%d")
                else:
                    date_str = str(play_date) if play_date else ""

                key = f"{date_str}|{theater_name}|{film_title}|{showtime}"
                cache_keys.append(key)
                if key not in fandango_by_key:
                    fandango_by_key[key] = []
                fandango_by_key[key].append({
                    "theater_name": theater_name,
                    "film_title": film_title,
                    "showtime": showtime,
                    "format": r.get("format") or r.get("Format"),
                    "ticket_type": ticket_type,
                    "fandango_price": fandango_price,
                })

            # Deduplicate cache keys
            unique_keys = list(set(cache_keys))

            # Lookup all ticket types from cache
            cache_results = cache_service.lookup_cached_prices_all_types(
                unique_keys, company_id=company_id
            )

            # Compare each Fandango result against cache
            for key, fandango_items in fandango_by_key.items():
                cached_list = cache_results.get(key, [])

                # Build dict of cached prices by ticket type
                cached_by_type = {c.ticket_type: c for c in cached_list}

                for fitem in fandango_items:
                    tt = fitem["ticket_type"]
                    cached = cached_by_type.get(tt)

                    if not cached:
                        fandango_only_count += 1
                        continue

                    # Get tax rate for this theater
                    tax_rate = 0.0
                    ent_with_tax = cached.price
                    if tax_config and tax_config.get("enabled"):
                        try:
                            st = get_theater_state(company_id, fitem["theater_name"])
                            tax_rate = get_tax_rate_for_theater(tax_config, st, theater_name=fitem["theater_name"])
                            ent_with_tax = apply_estimated_tax(cached.price, tax_rate)
                        except Exception:
                            pass

                    diff = ent_with_tax - fitem["fandango_price"]
                    diff_pct = (diff / fitem["fandango_price"] * 100) if fitem["fandango_price"] > 0 else 0

                    # Determine match status
                    if abs(diff) < 0.01:
                        match_status = "exact"
                    elif abs(diff_pct) < 2.0:
                        match_status = "close"
                    else:
                        match_status = "divergent"

                    verification_items.append(PriceVerificationItem(
                        theater_name=fitem["theater_name"],
                        film_title=fitem["film_title"],
                        showtime=fitem["showtime"],
                        format=fitem.get("format"),
                        ticket_type=tt,
                        fandango_price=fitem["fandango_price"],
                        enttelligence_price=cached.price,
                        tax_rate=tax_rate,
                        enttelligence_with_tax=round(ent_with_tax, 2),
                        difference=round(diff, 2),
                        difference_percent=round(diff_pct, 1),
                        match_status=match_status,
                    ))

        # Build summary
        exact = sum(1 for v in verification_items if v.match_status == "exact")
        close = sum(1 for v in verification_items if v.match_status == "close")
        divergent = sum(1 for v in verification_items if v.match_status == "divergent")
        avg_diff_pct = (
            sum(abs(v.difference_percent) for v in verification_items) / len(verification_items)
            if verification_items else 0
        )

        summary = VerificationSummary(
            total_verified=len(verification_items),
            exact_matches=exact,
            close_matches=close,
            divergent=divergent,
            avg_difference_percent=round(avg_diff_pct, 1),
        )

        job["status"] = "completed"
        job["progress"] = 100
        job["current_theater"] = None
        job["duration_seconds"] = time.time() - start_time
        job["results"] = all_fandango_results
        job["verification_results"] = VerificationResponse(
            job_id=job_id,
            status="completed",
            summary=summary,
            comparisons=verification_items,
            fandango_only=fandango_only_count,
        ).model_dump()

        print(f"[VERIFY JOB {job_id}] Complete: {len(verification_items)} comparisons, "
              f"{exact} exact, {close} close, {divergent} divergent, "
              f"{fandango_only_count} fandango-only")

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["duration_seconds"] = time.time() - start_time
        print(f"[VERIFY JOB {job_id}] Failed: {e}")
        import traceback
        traceback.print_exc()


@router.get("/scrapes/{job_id}/verification", tags=["Scrapes"])
async def get_verification_results(
    job_id: int,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """Get verification results for a completed verification job."""
    if job_id not in _scrape_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _scrape_jobs[job_id]
    if job.get("mode") != "verification":
        raise HTTPException(status_code=400, detail="Not a verification job")

    if job["status"] != "completed":
        return {"job_id": job_id, "status": job["status"], "progress": job.get("progress", 0)}

    return job.get("verification_results", {"job_id": job_id, "status": "completed", "comparisons": []})


# ============================================================================
# Showtime Count Comparison (Weather/Closure Monitoring)
# ============================================================================

class TheaterCountComparison(BaseModel):
    theater_name: str
    play_date: str
    current_count: int
    previous_count: int
    delta: int
    delta_percent: float
    status: str  # 'normal', 'reduced', 'closed', 'increased', 'no_previous'
    current_scrape_time: Optional[str] = None
    previous_scrape_time: Optional[str] = None


class ShowtimeComparisonRequest(BaseModel):
    theaters: List[str]
    play_dates: List[str]  # YYYY-MM-DD format
    # Nested dict: theater_name -> play_date -> count (from fresh scrape)
    current_counts: Optional[Dict[str, Dict[str, int]]] = None


class ShowtimeComparisonResponse(BaseModel):
    comparisons: List[TheaterCountComparison]
    current_time: str
    filter_applied: str  # Description of time filter


def _parse_showtime_to_minutes(showtime_str: str) -> Optional[int]:
    """
    Parse a showtime string like '10:30 AM' or '2:15 PM' to minutes since midnight.
    Returns None if parsing fails.
    """
    import re
    if not showtime_str:
        return None

    # Try various formats
    patterns = [
        r'(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)',  # 10:30 AM
        r'(\d{1,2}):(\d{2})',  # 10:30 (24-hour or needs context)
    ]

    for pattern in patterns:
        match = re.match(pattern, showtime_str.strip())
        if match:
            groups = match.groups()
            hour = int(groups[0])
            minute = int(groups[1])

            if len(groups) > 2:
                # Has AM/PM
                meridiem = groups[2].upper()
                if meridiem == 'PM' and hour != 12:
                    hour += 12
                elif meridiem == 'AM' and hour == 12:
                    hour = 0

            return hour * 60 + minute

    return None


@router.post("/scrapes/compare-counts", response_model=ShowtimeComparisonResponse, tags=["Scrapes"])
async def compare_showtime_counts(
    request: ShowtimeComparisonRequest,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Compare showtime counts between current scrape and previous database records.

    When `current_counts` is provided, uses those values as the "current" data
    (from fresh scrape in frontend). This handles the case where theaters with
    0 showtimes have nothing stored in the database.

    **Use Case:** Weather closure monitoring - identify theaters with significant
    drops in showtime counts that may indicate partial or full closure.

    **Status Values:**
    - `normal`: Delta within ±10% or ±3 showtimes
    - `reduced`: Down 10-50% (possible partial closure)
    - `closed`: Down >50% or zero showtimes (likely closed)
    - `increased`: Up >10% (unusual, may indicate data issue)
    - `no_previous`: No previous scrape data to compare
    """
    from app.db_session import get_session
    from sqlalchemy import text
    from datetime import datetime, timedelta

    # Get current time for filtering
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    current_time_str = now.strftime("%I:%M %p")

    comparisons = []

    # Helper to count future showtimes
    def count_future_showtimes(showtimes: List[str]) -> int:
        count = 0
        for st in showtimes:
            minutes = _parse_showtime_to_minutes(st)
            if minutes is not None and minutes >= current_minutes:
                count += 1
            elif minutes is None:
                # If we can't parse, include it to be safe
                count += 1
        return count

    with get_session() as session:
        for theater_name in request.theaters:
            for play_date in request.play_dates:
                # Get current count from request if provided (per theater AND date)
                current_count_from_request = None
                if request.current_counts:
                    theater_counts = request.current_counts.get(theater_name, {})
                    if play_date in theater_counts:
                        current_count_from_request = theater_counts[play_date]
                # Query previous showings from database
                query = text("""
                    SELECT showtime, created_at
                    FROM showings
                    WHERE theater_name = :theater_name
                      AND play_date = :play_date
                    ORDER BY created_at DESC
                """)

                rows = session.execute(query, {
                    "theater_name": theater_name,
                    "play_date": play_date
                }).fetchall()

                # If current_counts provided, use that as source of truth for current
                if current_count_from_request is not None:
                    current_count = current_count_from_request

                    # Find previous count from database (most recent scrape)
                    if not rows:
                        previous_count = 0
                        previous_run = None
                    else:
                        # Group by scrape run to find the most recent one
                        scrape_runs = {}
                        for row in rows:
                            showtime = row[0]
                            created_at = row[1]
                            if isinstance(created_at, str):
                                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            run_key = created_at.replace(minute=0, second=0, microsecond=0)
                            if run_key not in scrape_runs:
                                scrape_runs[run_key] = []
                            scrape_runs[run_key].append(showtime)

                        sorted_runs = sorted(scrape_runs.keys(), reverse=True)
                        if sorted_runs:
                            previous_run = sorted_runs[0]
                            previous_showtimes = scrape_runs[previous_run]
                            previous_count = count_future_showtimes(previous_showtimes)
                        else:
                            previous_count = 0
                            previous_run = None

                    current_scrape_time = now.strftime("%Y-%m-%d %H:%M")
                    previous_scrape_time = previous_run.strftime("%Y-%m-%d %H:%M") if previous_run else None

                else:
                    # No current_counts provided - use database for both current and previous
                    if not rows:
                        comparisons.append(TheaterCountComparison(
                            theater_name=theater_name,
                            play_date=play_date,
                            current_count=0,
                            previous_count=0,
                            delta=0,
                            delta_percent=0.0,
                            status="no_previous"
                        ))
                        continue

                    # Group by scrape run
                    scrape_runs = {}
                    for row in rows:
                        showtime = row[0]
                        created_at = row[1]
                        if isinstance(created_at, str):
                            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        run_key = created_at.replace(minute=0, second=0, microsecond=0)
                        if run_key not in scrape_runs:
                            scrape_runs[run_key] = []
                        scrape_runs[run_key].append(showtime)

                    sorted_runs = sorted(scrape_runs.keys(), reverse=True)
                    if len(sorted_runs) < 1:
                        comparisons.append(TheaterCountComparison(
                            theater_name=theater_name,
                            play_date=play_date,
                            current_count=0,
                            previous_count=0,
                            delta=0,
                            delta_percent=0.0,
                            status="no_previous"
                        ))
                        continue

                    current_run = sorted_runs[0]
                    current_showtimes = scrape_runs[current_run]
                    current_count = count_future_showtimes(current_showtimes)

                    previous_run = sorted_runs[1] if len(sorted_runs) > 1 else None
                    previous_showtimes = scrape_runs[previous_run] if previous_run else []
                    previous_count = count_future_showtimes(previous_showtimes) if previous_showtimes else 0

                    current_scrape_time = current_run.strftime("%Y-%m-%d %H:%M")
                    previous_scrape_time = previous_run.strftime("%Y-%m-%d %H:%M") if previous_run else None

                # Calculate delta
                delta = current_count - previous_count
                if previous_count > 0:
                    delta_percent = (delta / previous_count) * 100
                else:
                    delta_percent = 0.0 if current_count == 0 else 100.0

                # Determine status
                if previous_count == 0 and current_count == 0:
                    status = "no_previous"
                elif previous_count == 0:
                    status = "no_previous"
                elif current_count == 0:
                    status = "closed"
                elif delta_percent <= -50:
                    status = "closed"
                elif delta_percent <= -10 or delta <= -3:
                    status = "reduced"
                elif delta_percent >= 10:
                    status = "increased"
                else:
                    status = "normal"

                comparisons.append(TheaterCountComparison(
                    theater_name=theater_name,
                    play_date=play_date,
                    current_count=current_count,
                    previous_count=previous_count,
                    delta=delta,
                    delta_percent=round(delta_percent, 1),
                    status=status,
                    current_scrape_time=current_scrape_time,
                    previous_scrape_time=previous_scrape_time
                ))

    return ShowtimeComparisonResponse(
        comparisons=comparisons,
        current_time=current_time_str,
        filter_applied=f"Only counting showtimes >= {current_time_str}"
    )


# =============================================================================
# SHOWTIME VERIFICATION (Fandango vs EntTelligence Cache)
# =============================================================================


class ShowtimeMatchItem(BaseModel):
    date: str
    theater_name: str
    film_title: str
    showtime: str  # Original Fandango format ("7:30pm")
    format: str
    status: str  # 'cached' | 'new' | 'missing_from_fandango'
    cached_price: Optional[float] = None
    cache_age_minutes: Optional[int] = None


class TheaterVerificationSummary(BaseModel):
    theater_name: str
    cached_count: int
    new_count: int
    missing_count: int
    total_fandango: int
    total_cached: int
    closure_warning: bool = False
    closure_reason: Optional[str] = None


class CompareShowtimesRequest(BaseModel):
    theaters: List[str]
    play_dates: List[str]  # YYYY-MM-DD format
    fandango_showtimes: Dict[str, Dict[str, List[Dict[str, Any]]]]
    # Shape: {date: {theater: [{film_title, format, showtime, ...}]}}
    company_id: Optional[int] = 1


class CompareShowtimesResponse(BaseModel):
    summary: Dict[str, Any]  # {cached, new, missing, closure_warnings}
    by_theater: List[TheaterVerificationSummary]
    matches: List[ShowtimeMatchItem]
    cache_freshness: Optional[str] = None


@router.post("/scrapes/compare-showtimes", response_model=CompareShowtimesResponse, tags=["Scrapes"])
async def compare_showtimes(
    request: CompareShowtimesRequest,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Compare Fandango live showtimes against EntTelligence cache.

    After fetching showtimes from Fandango, this endpoint checks which showtimes
    have cached pricing (no scrape needed), which are new (need scraping), and
    which are missing from Fandango (possible closure/cancellation).
    """
    from api.services.enttelligence_cache_service import (
        EntTelligenceCacheService, normalize_film_title, normalize_showtime
    )

    company_id = request.company_id or 1
    cache_service = EntTelligenceCacheService()

    # 1. Get all cached showtimes for these theaters/dates
    cached_data = cache_service.get_cached_showtimes_for_theater_dates(
        theater_names=request.theaters,
        play_dates=request.play_dates,
        company_id=company_id,
    )

    # 2. Build normalized lookup from cache entries
    # Key: "date|theater|normalized_film|normalized_time"
    cache_lookup: Dict[str, Dict[str, Any]] = {}
    cache_matched: set = set()  # Track which cache entries get matched

    for date_str, theaters in cached_data.items():
        for theater_name, entries in theaters.items():
            for entry in entries:
                norm_film = normalize_film_title(entry['film_title'])
                norm_time = normalize_showtime(entry['showtime'])
                key = f"{date_str}|{theater_name}|{norm_film}|{norm_time}"
                cache_lookup[key] = entry

    # 3. Compare Fandango showtimes against cache
    matches: List[ShowtimeMatchItem] = []
    now = datetime.now()

    for date_str, theaters in request.fandango_showtimes.items():
        for theater_name, showings in theaters.items():
            for showing in showings:
                film_title = showing.get('film_title', '')
                showtime_str = showing.get('showtime', '')
                fmt = showing.get('format', '')

                norm_film = normalize_film_title(film_title)
                norm_time = normalize_showtime(showtime_str)
                key = f"{date_str}|{theater_name}|{norm_film}|{norm_time}"

                if key in cache_lookup:
                    cache_entry = cache_lookup[key]
                    cache_matched.add(key)

                    # Calculate cache age in minutes
                    age_minutes = None
                    fetched_at = cache_entry.get('fetched_at')
                    if fetched_at:
                        try:
                            fetched_dt = datetime.fromisoformat(str(fetched_at))
                            age_minutes = int((now - fetched_dt.replace(tzinfo=None)).total_seconds() / 60)
                        except (ValueError, TypeError):
                            pass

                    matches.append(ShowtimeMatchItem(
                        date=date_str,
                        theater_name=theater_name,
                        film_title=film_title,
                        showtime=showtime_str,
                        format=fmt,
                        status='cached',
                        cached_price=cache_entry.get('adult_price'),
                        cache_age_minutes=age_minutes,
                    ))
                else:
                    matches.append(ShowtimeMatchItem(
                        date=date_str,
                        theater_name=theater_name,
                        film_title=film_title,
                        showtime=showtime_str,
                        format=fmt,
                        status='new',
                    ))

    # 4. Find cache entries missing from Fandango
    for key, entry in cache_lookup.items():
        if key not in cache_matched:
            parts = key.split('|')
            if len(parts) >= 4:
                matches.append(ShowtimeMatchItem(
                    date=parts[0],
                    theater_name=parts[1],
                    film_title=entry['film_title'],
                    showtime=entry['showtime'],
                    format=entry.get('format') or '',
                    status='missing_from_fandango',
                    cached_price=entry.get('adult_price'),
                ))

    # 5. Build per-theater summaries with closure detection
    theater_summaries: Dict[str, TheaterVerificationSummary] = {}

    for theater_name in request.theaters:
        # Count Fandango showtimes for this theater
        fandango_count = 0
        for date_str, theaters in request.fandango_showtimes.items():
            fandango_count += len(theaters.get(theater_name, []))

        # Count cached showtimes for this theater
        cached_count = 0
        for date_str, theaters in cached_data.items():
            cached_count += len(theaters.get(theater_name, []))

        # Count match statuses for this theater
        theater_cached = sum(1 for m in matches if m.theater_name == theater_name and m.status == 'cached')
        theater_new = sum(1 for m in matches if m.theater_name == theater_name and m.status == 'new')
        theater_missing = sum(1 for m in matches if m.theater_name == theater_name and m.status == 'missing_from_fandango')

        # Closure detection
        closure_warning = False
        closure_reason = None
        if cached_count >= 5 and fandango_count == 0:
            closure_warning = True
            closure_reason = f"No Fandango showtimes but {cached_count} cached entries — possible closure"
        elif cached_count >= 5 and fandango_count > 0 and fandango_count < (cached_count * 0.3):
            closure_warning = True
            closure_reason = f"Only {fandango_count} Fandango showtimes vs {cached_count} cached — significant reduction"

        theater_summaries[theater_name] = TheaterVerificationSummary(
            theater_name=theater_name,
            cached_count=theater_cached,
            new_count=theater_new,
            missing_count=theater_missing,
            total_fandango=fandango_count,
            total_cached=cached_count,
            closure_warning=closure_warning,
            closure_reason=closure_reason,
        )

    # 6. Build overall summary
    total_cached = sum(1 for m in matches if m.status == 'cached')
    total_new = sum(1 for m in matches if m.status == 'new')
    total_missing = sum(1 for m in matches if m.status == 'missing_from_fandango')
    closure_warnings = sum(1 for t in theater_summaries.values() if t.closure_warning)

    # Cache freshness: oldest cache entry age
    cache_ages = [m.cache_age_minutes for m in matches if m.cache_age_minutes is not None]
    cache_freshness = None
    if cache_ages:
        oldest_minutes = max(cache_ages)
        if oldest_minutes < 60:
            cache_freshness = f"{oldest_minutes}m ago"
        else:
            cache_freshness = f"{oldest_minutes // 60}h {oldest_minutes % 60}m ago"

    return CompareShowtimesResponse(
        summary={
            'cached': total_cached,
            'new': total_new,
            'missing': total_missing,
            'closure_warnings': closure_warnings,
        },
        by_theater=list(theater_summaries.values()),
        matches=matches,
        cache_freshness=cache_freshness,
    )


# =============================================================================
# ZERO SHOWTIME ANALYSIS
# =============================================================================

class ZeroShowtimeRequest(BaseModel):
    theater_names: Optional[List[str]] = None
    lookback_days: int = 30

class ZeroShowtimeTheaterResult(BaseModel):
    theater_name: str
    total_scrapes: int
    zero_count: int
    last_nonzero_date: Optional[str] = None
    consecutive_zeros: int
    last_scrape_date: Optional[str] = None
    classification: str  # "likely_off_fandango" | "warning" | "normal"

class ZeroShowtimeAnalysisResponse(BaseModel):
    theaters: List[ZeroShowtimeTheaterResult]
    summary: Dict[str, int]

@router.post("/scrapes/zero-showtime-analysis", tags=["Scrapes"])
async def analyze_zero_showtimes(
    request: ZeroShowtimeRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Analyze operating hours history to find theaters consistently returning
    zero showtimes from Fandango. Helps identify theaters that may have moved
    to their own ticketing sites.

    Classifications:
    - likely_off_fandango: 3+ consecutive zero-showtime scrapes
    - warning: 2 consecutive zero-showtime scrapes
    - normal: 0-1 zeros (could be weather/holiday)
    """
    from app.zero_showtime_service import ZeroShowtimeService

    company_id = current_user.get("company_id", 1)
    service = ZeroShowtimeService(company_id)

    theater_names = request.theater_names or []
    if not theater_names:
        return ZeroShowtimeAnalysisResponse(theaters=[], summary={
            "likely_off_fandango": 0, "warning": 0, "normal": 0
        })

    results = service.analyze_theaters(theater_names, request.lookback_days)

    summary = {"likely_off_fandango": 0, "warning": 0, "normal": 0}
    theater_results = []
    for r in results:
        summary[r.classification] = summary.get(r.classification, 0) + 1
        theater_results.append(ZeroShowtimeTheaterResult(
            theater_name=r.theater_name,
            total_scrapes=r.total_scrapes,
            zero_count=r.zero_count,
            last_nonzero_date=r.last_nonzero_date,
            consecutive_zeros=r.consecutive_zeros,
            last_scrape_date=r.last_scrape_date,
            classification=r.classification,
        ))

    return ZeroShowtimeAnalysisResponse(theaters=theater_results, summary=summary)


class MarkTheaterStatusRequest(BaseModel):
    theater_name: str
    market: str
    status: str  # "not_on_fandango" | "closed" | "active"
    external_url: Optional[str] = None  # Theater's own ticketing site URL
    reason: Optional[str] = None

class MarkTheaterStatusResponse(BaseModel):
    success: bool
    theater_name: str
    new_status: str

@router.post("/scrapes/mark-theater-status", tags=["Scrapes"])
async def mark_theater_status(
    request: MarkTheaterStatusRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update a theater's Fandango availability status in the theater cache.

    Statuses:
    - not_on_fandango: Theater uses its own ticketing site (optionally provide external_url)
    - closed: Theater is permanently closed
    - active: Re-enable a previously flagged theater
    """
    import json
    import os
    import shutil
    from app.config import CACHE_FILE

    if not os.path.exists(CACHE_FILE):
        raise HTTPException(status_code=404, detail="Theater cache file not found")

    try:
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)

        markets = cache_data.get('markets', {})
        if request.market not in markets:
            raise HTTPException(status_code=404, detail=f"Market '{request.market}' not found")

        market_data = markets[request.market]
        theater_found = False

        status_req_norm = normalize_theater_name(request.theater_name)
        for theater in market_data.get('theaters', []):
            if theater.get('name') == request.theater_name or normalize_theater_name(theater.get('name', '')) == status_req_norm:
                theater_found = True

                if request.status == 'not_on_fandango':
                    theater['not_on_fandango'] = True
                    if request.external_url:
                        theater['url'] = request.external_url
                elif request.status == 'closed':
                    theater['name'] = f"{request.theater_name} (Permanently Closed)"
                    theater['url'] = "N/A"
                    if 'not_on_fandango' in theater:
                        del theater['not_on_fandango']
                elif request.status == 'active':
                    if 'not_on_fandango' in theater:
                        del theater['not_on_fandango']
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid status: '{request.status}'. Use 'not_on_fandango', 'closed', or 'active'."
                    )
                break

        if not theater_found:
            raise HTTPException(
                status_code=404,
                detail=f"Theater '{request.theater_name}' not found in market '{request.market}'"
            )

        # Backup and save
        backup_path = CACHE_FILE + ".bak"
        if os.path.exists(CACHE_FILE):
            shutil.copy2(CACHE_FILE, backup_path)

        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)

        # Audit log
        try:
            audit_service.log(
                company_id=current_user.get("company_id", 1),
                user_id=current_user.get("user_id"),
                event_type="theater_status_changed",
                category="configuration",
                details={
                    "theater_name": request.theater_name,
                    "market": request.market,
                    "new_status": request.status,
                    "reason": request.reason,
                }
            )
        except Exception:
            pass  # Don't fail the request if audit logging fails

        return MarkTheaterStatusResponse(
            success=True,
            theater_name=request.theater_name,
            new_status=request.status,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating theater status: {str(e)}")
