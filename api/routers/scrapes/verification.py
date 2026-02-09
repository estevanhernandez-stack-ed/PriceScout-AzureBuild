"""
Verification & QA endpoints: price verification, showtime comparison,
zero-showtime analysis, theater status management.

Endpoints:
    POST   /scrapes/verify-prices           - Verify prices against EntTelligence cache
    GET    /scrapes/{job_id}/verification    - Get verification results
    POST   /scrapes/compare-counts          - Compare showtime counts across sources
    POST   /scrapes/compare-showtimes       - Compare Fandango vs EntTelligence showtimes
    POST   /scrapes/zero-showtime-analysis  - Analyze theaters with zero showtimes
    POST   /scrapes/mark-theater-status     - Update theater Fandango availability
"""

from fastapi import APIRouter, Security, HTTPException, Depends
from api.routers.auth import get_current_user, User
from api.telemetry import track_event
from app.audit_service import audit_service
from app.simplified_baseline_service import normalize_theater_name
from app import db_adapter as database
from app import config
import logging
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import time
from datetime import datetime, date

from ._shared import (
    _scrape_jobs,
    _run_async_in_thread,
    _launch_in_thread,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Price Verification Models
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


# ============================================================================
# Showtime Count Comparison Models
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


# ============================================================================
# Showtime Verification Models
# ============================================================================

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


# ============================================================================
# Zero Showtime Analysis Models
# ============================================================================

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


# ============================================================================
# Theater Status Models
# ============================================================================

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


# ============================================================================
# Helper functions
# ============================================================================

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


# ============================================================================
# Endpoints
# ============================================================================

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
                logger.error(f"Verify error processing {theater['name']}: {e}", exc_info=True)
                continue

        # Step 2: Look up EntTelligence cache prices for the same showings
        verification_items = []
        fandango_only_count = 0

        try:
            from api.services.enttelligence_cache_service import get_cache_service
            cache_service = get_cache_service()
        except Exception as e:
            logger.warning(f"Cache service unavailable for verification: {e}")
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

        logger.info(f"Verify job {job_id} complete: {len(verification_items)} comparisons, "
                    f"{exact} exact, {close} close, {divergent} divergent, "
                    f"{fandango_only_count} fandango-only")

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["duration_seconds"] = time.time() - start_time
        logger.error(f"Verify job {job_id} failed: {e}", exc_info=True)


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
    - `normal`: Delta within +/-10% or +/-3 showtimes
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
        EntTelligenceCacheService, normalize_film_title, normalize_showtime,
        normalize_theater_name
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
    # Key: "date|normalized_theater|normalized_film|normalized_time"
    # Theater names are normalized so Fandango ("Marcus Cape West Cinema")
    # matches EntTelligence ("Marcus Cape West Cine").
    cache_lookup: Dict[str, Dict[str, Any]] = {}
    cache_matched: set = set()  # Track which cache entries get matched

    for date_str, theaters in cached_data.items():
        for theater_name, entries in theaters.items():
            norm_theater = normalize_theater_name(theater_name)
            for entry in entries:
                norm_film = normalize_film_title(entry['film_title'])
                norm_time = normalize_showtime(entry['showtime'])
                key = f"{date_str}|{norm_theater}|{norm_film}|{norm_time}"
                cache_lookup[key] = entry

    # 3. Compare Fandango showtimes against cache
    matches: List[ShowtimeMatchItem] = []
    now = datetime.now()

    for date_str, theaters in request.fandango_showtimes.items():
        for theater_name, showings in theaters.items():
            norm_theater = normalize_theater_name(theater_name)
            for showing in showings:
                film_title = showing.get('film_title', '')
                showtime_str = showing.get('showtime', '')
                fmt = showing.get('format', '')

                norm_film = normalize_film_title(film_title)
                norm_time = normalize_showtime(showtime_str)
                key = f"{date_str}|{norm_theater}|{norm_film}|{norm_time}"

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
                    theater_name=parts[1],  # normalized name
                    film_title=entry['film_title'],
                    showtime=entry['showtime'],
                    format=entry.get('format') or '',
                    status='missing_from_fandango',
                    cached_price=entry.get('adult_price'),
                ))

    # 5. Build per-theater summaries with closure detection
    # Map normalized names to Fandango names for consistent matching
    norm_to_fandango = {normalize_theater_name(t): t for t in request.theaters}
    theater_summaries: Dict[str, TheaterVerificationSummary] = {}

    for theater_name in request.theaters:
        norm_name = normalize_theater_name(theater_name)

        # Count Fandango showtimes for this theater
        fandango_count = 0
        for date_str, theaters in request.fandango_showtimes.items():
            fandango_count += len(theaters.get(theater_name, []))

        # Count cached showtimes for this theater (cache uses EntTelligence names)
        cached_count = 0
        for date_str, theaters in cached_data.items():
            for ent_name, entries in theaters.items():
                if normalize_theater_name(ent_name) == norm_name:
                    cached_count += len(entries)

        # Count match statuses for this theater (matches use normalized names)
        theater_cached = sum(1 for m in matches if m.theater_name == theater_name and m.status == 'cached')
        theater_new = sum(1 for m in matches if m.theater_name == theater_name and m.status == 'new')
        # Missing entries use normalized theater name from cache key
        theater_missing = sum(1 for m in matches if m.theater_name == norm_name and m.status == 'missing_from_fandango')

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
        except Exception as e:
            logger.debug("Audit log failed for theater status change: %s", e)

        return MarkTheaterStatusResponse(
            success=True,
            theater_name=request.theater_name,
            new_status=request.status,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating theater status: {str(e)}")
