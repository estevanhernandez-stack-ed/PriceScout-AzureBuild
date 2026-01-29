from fastapi import APIRouter, Security, HTTPException, BackgroundTasks, Depends
from api.routers.auth import get_current_user, User, require_operator
from api.telemetry import track_scrape_completed, track_event
from app.audit_service import audit_service
from app import db_adapter as database
from app import config
import pandas as pd
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import time
import asyncio
import sys
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


@router.get("/scrapes/active-theaters", tags=["Scrapes"])
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


@router.post("/scrapes/check-collision", tags=["Scrapes"])
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


@router.get("/scrapes/search-theaters/fandango", tags=["Scrapes"])
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
        else:
            results = await scout.live_search_by_name(query)
            
        # Convert dictionary to list for frontend
        return [{"name": name, "url": data["url"]} for name, data in results.items()]
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
                                except:
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
    background_tasks: BackgroundTasks,
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
        # Fallback to local background task
        background_tasks.add_task(
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

    def make_progress_callback(total_showings: int):
        """Create a progress callback for the current batch of showings."""
        def progress_callback(current: int, total: int):
            job["showings_completed"] = base_showings_completed + current
            job["showings_total"] = max(job.get("showings_total", 0), base_showings_completed + total)
            # Calculate overall progress based on showings
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

                                # Lookup all keys in cache
                                cache_lookup = cache_service.lookup_cached_prices(
                                    [k for k, _ in showtime_keys_for_cache],
                                    company_id=1,
                                    max_age_hours=cache_max_age_hours
                                )

                                for key, showing in showtime_keys_for_cache:
                                    cached = cache_lookup.get(key)
                                    if cached:
                                        # Cache hit - use cached price
                                        job["cache_hits"] = job.get("cache_hits", 0) + 1
                                        fmt = cached.format or showing.get("format")
                                        # Convert play_date to date object if it's a string
                                        play_date = cached.play_date
                                        if isinstance(play_date, str):
                                            play_date = datetime.strptime(play_date, "%Y-%m-%d").date()
                                        cached_results.append({
                                            # snake_case for React frontend
                                            "theater_name": cached.theater_name,
                                            "film_title": cached.film_title,
                                            "showtime": cached.showtime,
                                            "price": f"${cached.price:.2f}",
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
                                        })
                                    else:
                                        # Cache miss - need to scrape
                                        job["cache_misses"] = job.get("cache_misses", 0) + 1
                                        showings_to_scrape.append(showing)

                                print(f"  [SCRAPER] Cache: {job['cache_hits']} hits, {job['cache_misses']} misses for {theater['name']}")

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
