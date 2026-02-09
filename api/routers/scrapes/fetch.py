"""
Theater search, showtime fetching, and data save endpoints.

Endpoints:
    GET    /scrapes/search-theaters/fandango  - Search Fandango for theaters
    GET    /scrapes/search-theaters/cache     - Search local theater cache
    POST   /scrapes/fetch-showtimes          - Fetch showtimes for theaters
    POST   /scrapes/estimate-time            - Estimate scrape duration
    POST   /scrapes/operating-hours          - Scrape operating hours data
    POST   /scrapes/save                     - Save scraped data to database
    POST   /scrape_runs                      - Create a scrape run record
"""

from fastapi import APIRouter, Security, HTTPException
from api.routers.auth import get_current_user, User
from api.telemetry import track_scrape_completed, track_event
from app import db_adapter as database
from app import config
import logging
import pandas as pd
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import time

from ._shared import _run_async_in_thread

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class TheaterRequest(BaseModel):
    name: str
    url: str


class ScrapeData(BaseModel):
    run_id: int
    data: List[dict]


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


class FandangoTheaterSearchResult(BaseModel):
    """A theater found from Fandango search."""
    name: str
    url: str


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


# ============================================================================
# Endpoints
# ============================================================================

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
                # Run in a separate thread with its own event loop.
                # fetch.py endpoints run on FastAPI's main event loop, so
                # Playwright needs _run_async_in_thread for isolation.
                # (execution.py uses direct await because _launch_in_thread
                # already provides its own thread+loop.)
                showings_by_theater = await _run_async_in_thread(
                    scout.get_all_showings_for_theaters(theater_objs, date_str)
                )

                for theater in request.theaters:
                    theater_showings = showings_by_theater.get(theater.name, [])
                    all_showtimes[date_str][theater.name] = theater_showings

            except Exception as e:
                logger.error(f"Error fetching showtimes for {date_str}: {e}", exc_info=True)
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
            logger.warning(f"Failed to log runtime: {log_err}")

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
                has_historical_data=True
            )

        return TimeEstimateResponse(
            estimated_seconds=estimated_seconds,
            formatted_time=format_time_to_human_readable(estimated_seconds),
            has_historical_data=True
        )

    except Exception as e:
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
                # Run in a separate thread — same pattern as fetch-showtimes
                showings_by_theater = await _run_async_in_thread(
                    scout.get_all_showings_for_theaters(theater_objs, date_str)
                )

                # Save showings to database for other data needs
                if showings_by_theater:
                    try:
                        date_obj = dt.strptime(date_str, "%Y-%m-%d")
                        database.upsert_showings(showings_by_theater, date_obj)
                        logger.info(f"Saved showings for {date_str}")
                    except Exception as e:
                        logger.warning(f"Failed to save showings for {date_str}: {e}", exc_info=True)

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
                        operating_hours.append(OperatingHoursRecord(
                            theater_name=theater.name,
                            date=date_str,
                            open_time="N/A",
                            close_time="N/A",
                            duration_hours=0.0,
                            showtime_count=0
                        ))

            except Exception as e:
                logger.error(f"Error fetching operating hours for {date_str}: {e}", exc_info=True)
                continue

        # Build week-over-week comparison if we have 7+ days
        comparison: List[WeekComparisonRecord] = []
        summary = {"changed": 0, "no_change": 0, "new": 0}

        if len(dates) >= 7:
            prev_week_end = start - timedelta(days=1)
            prev_week_start = prev_week_end - timedelta(days=6)

            try:
                prev_hours = database.get_operating_hours_for_theaters_and_dates(
                    [t.name for t in request.theaters],
                    prev_week_start.strftime("%Y-%m-%d"),
                    prev_week_end.strftime("%Y-%m-%d")
                )

                prev_lookup = {}
                if prev_hours is not None and not prev_hours.empty:
                    for _, record in prev_hours.iterrows():
                        key = (record['theater_name'], dt.strptime(str(record['scrape_date']), "%Y-%m-%d").strftime("%A"))
                        prev_lookup[key] = record

                for oh in operating_hours:
                    date_obj = dt.strptime(oh.date, "%Y-%m-%d")
                    day_of_week = date_obj.strftime("%A")
                    key = (oh.theater_name, day_of_week)

                    prev = prev_lookup.get(key)

                    if prev is not None:
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
                logger.error(f"Error fetching previous week data: {e}")

        duration = time.time() - start_time

        # Save operating hours to database
        try:
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
            logger.error(f"Error saving operating hours: {e}")

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

        duration = time.time() - start_time
        showing_count = len(scrape_data.data)
        price_count = showing_count

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

        track_event("PriceScout.ScrapeRun.Created", {
            "RunId": str(run_id),
            "Mode": mode,
            "Context": context
        })

        return {"run_id": run_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
