"""
Background scrape job execution.

Contains the long-running run_scrape_job() function that is launched
in a separate thread by the trigger endpoint in jobs.py.
"""

from api.telemetry import track_scrape_completed, track_event
from app import config
from app.db.showings import upsert_showings
from app.db.scrape_runs import create_scrape_run, update_scrape_run_status
from app.db.prices import save_prices
import logging
import pandas as pd
from typing import List, Dict, Any, Optional
import time
from datetime import datetime

from ._shared import _scrape_jobs

logger = logging.getLogger(__name__)


async def run_scrape_job(
    job_id: int,
    mode: str,
    market: Optional[str],
    theaters: List[Dict[str, str]],
    dates: List[str],
    selected_showtime_keys: Optional[List[str]] = None,
    use_cache: bool = False,
    cache_max_age_hours: int = 24
):
    """
    Background task to run the actual scrape.

    This function uses the Scraper class to fetch prices from Fandango.
    When use_cache=True, it first checks EntTelligence cache for prices.

    Args:
        selected_showtime_keys: Optional list of "date|theater|film|time" keys.
            If provided, only these showings will be scraped.
            If None, all showings for the theaters/dates will be scraped.
        use_cache: If True, check EntTelligence cache before scraping
        cache_max_age_hours: Max age (hours) for cached data to be considered fresh
    """
    logger.info(f"Scrape job {job_id} started - mode={mode}, theaters={len(theaters)}, dates={dates}")
    logger.info(f"Scrape job {job_id} selected keys: {len(selected_showtime_keys) if selected_showtime_keys else 'None (all)'}")

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
            logger.info(f"Cache enabled with {cache_max_age_hours}h max age")
        except Exception as e:
            logger.warning(f"Cache service unavailable: {e}")
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
            effective_total = job.get("showings_total", 0)
            if effective_total > 0:
                # Cap completed at total — scraper counts ticket types
                # (Adult/Child/Senior) while total counts unique showings
                job["showings_completed"] = min(job["showings_completed"], effective_total)
                job["progress"] = int((job["showings_completed"] / effective_total) * 100)
            job["current_showing"] = f"{current}/{total}"
            logger.debug(f"Progress update: {job['showings_completed']}/{job['showings_total']} ({job['progress']}%)")
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
                        # Phase 1: Fetch and save basic showtimes (for immediate UI results)
                        # Await directly — run_scrape_job already runs in its own
                        # thread with its own event loop (via _launch_in_thread),
                        # so no need for _run_async_in_thread which creates a nested
                        # thread+loop that hangs Playwright on Windows.
                        showtime_data_dict = await scout.get_all_showings_for_theaters(
                            [theater_obj],
                            date_str
                        )
                        showtime_data = showtime_data_dict.get(theater['name'], [])

                        if showtime_data:
                            logger.info(f"Saving {len(showtime_data)} base showtimes for {theater['name']} on {date_str}")
                            # Set company ID for database operations (default to 1 for now)
                            config.CURRENT_COMPANY_ID = 1 # Force to 1 for now, or use value from request
                            try:
                                upsert_showings(showtime_data_dict, date_str)
                                logger.info(f"upsert_showings completed for {theater['name']}")
                            except Exception as upsert_err:
                                logger.error(f"Error in upsert_showings: {upsert_err}")
                                import traceback
                                traceback.print_exc()
                        else:
                            logger.info(f"No showtimes found for {theater['name']} on {date_str}")

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
                                logger.debug(f"Filtered to {len(showtime_data)} selected showings for {theater['name']}")

                            if not showtime_data:
                                continue  # Skip if no showings match selection

                            # Update total showings estimate if not already known from selection
                            if not selected_keys_set:
                                job["showings_total"] = job.get("showings_total", 0) + len(showtime_data)

                            # Skip price scraping if we're only interested in the lineup
                            if mode == 'lineup':
                                logger.debug(f"Skipping price scraping for {theater['name']} due to 'lineup' mode")
                                job["showings_completed"] = job.get("showings_completed", 0) + len(showtime_data)
                                effective_total = job.get("showings_total", 0)
                                if effective_total > 0:
                                    job["showings_completed"] = min(job["showings_completed"], effective_total)
                                    job["progress"] = int((job["showings_completed"] / effective_total) * 100)
                                base_showings_completed = job.get("showings_completed", 0)
                                continue

                            # Check cache first if enabled
                            showings_to_scrape = []
                            cached_results = []

                            if use_cache and cache_service:
                                # Build showtime keys for cache lookup
                                batch_cache_hits = 0
                                showtime_keys_for_cache = []
                                for showing in showtime_data:
                                    film = showing.get("film_title", "Unknown")
                                    st = showing.get("showtime", "")
                                    fmt = showing.get("format", "Standard")
                                    key = f"{date_str}|{theater['name']}|{film}|{st}|{fmt}"
                                    showtime_keys_for_cache.append((key, showing))

                                # Lookup all keys in cache (returns all ticket types per key).
                                # max_age_hours=0 = "showtime-match mode": the live Fandango
                                # showtime match IS the freshness signal. If the same film is
                                # playing at the same time on the same date, the cached price
                                # is still valid regardless of when EntTelligence fetched it.
                                cache_lookup = cache_service.lookup_cached_prices_all_types(
                                    [k for k, _ in showtime_keys_for_cache],
                                    company_id=company_id,
                                    max_age_hours=0
                                )

                                for key, showing in showtime_keys_for_cache:
                                    cached_list = cache_lookup.get(key, [])
                                    if cached_list:
                                        # Cache hit - build one result per ticket type
                                        job["cache_hits"] = job.get("cache_hits", 0) + 1
                                        batch_cache_hits += 1
                                        for cached in cached_list:
                                            # Fandango format always wins — it knows PLF (Premium Format)
                                            # while EntTelligence only reports 2D/3D
                                            fmt = showing.get("format") or cached.format
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

                                logger.info(f"Cache: {job['cache_hits']} hits ({len(cached_results)} prices incl. Child/Senior), {job['cache_misses']} misses for {theater['name']}")

                                # Add cached results immediately and update progress
                                if cached_results:
                                    all_results.extend(cached_results)
                                    # Count unique showings, not ticket-type rows (Adult+Child+Senior = 1 showing)
                                    job["showings_completed"] = job.get("showings_completed", 0) + batch_cache_hits
                                    effective_total = job.get("showings_total", 0)
                                    if effective_total > 0:
                                        job["showings_completed"] = min(job["showings_completed"], effective_total)
                                        job["progress"] = int((job["showings_completed"] / effective_total) * 100)
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

                                # Scrape prices — await directly (same thread/loop rationale)
                                result, _ = await scout.scrape_details(
                                    [theater_obj],
                                    selected_showtimes,
                                    progress_callback=callback
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
                        logger.error(f"Error scraping {theater['name']} for {date_str}: {e}", exc_info=True)
                        continue

            except Exception as e:
                logger.error(f"Error processing theater {theater['name']}: {e}")
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
            logger.info(f"Scrape job {job_id} logged runtime: {mode}, {len(theaters)} theaters, {num_showings} showings, {job['duration_seconds']:.1f}s")
        except Exception as log_err:
            logger.warning(f"Failed to log runtime: {log_err}")

        # Save to database
        if all_results:
            try:
                logger.info(f"Scrape job {job_id} saving results - {len(all_results)} price records")
                # Set company ID for database operations (default to 1 for now)
                config.CURRENT_COMPANY_ID = 1

                run_id = create_scrape_run(mode, f"Market: {market or 'N/A'}")
                logger.info(f"Scrape job {job_id} created scrape run with ID: {run_id}")
                df = pd.DataFrame(all_results)
                logger.debug(f"Scrape job {job_id} DataFrame columns: {list(df.columns)}")
                logger.debug(f"Scrape job {job_id} DataFrame sample row: {df.iloc[0].to_dict() if len(df) > 0 else 'empty'}")
                save_prices(run_id, df)
                update_scrape_run_status(run_id, 'completed', len(all_results))
                logger.info(f"Scrape job {job_id} successfully saved {len(all_results)} price records to database (run_id: {run_id})")

                # Generate price alerts after saving prices
                try:
                    from app.alert_service import generate_alerts_for_scrape
                    from app.notification_service import dispatch_alerts_sync

                    company_id = getattr(config, 'CURRENT_COMPANY_ID', 1)
                    alerts = generate_alerts_for_scrape(company_id, run_id, df)

                    if alerts:
                        logger.info(f"Generated {len(alerts)} price alerts")
                        # Dispatch notifications synchronously (we're already in a background thread)
                        dispatch_alerts_sync(company_id, alerts)
                except Exception as alert_err:
                    logger.warning(f"Alert generation failed: {alert_err}", exc_info=True)
                    # Don't fail the scrape if alerts fail

                # Auto-refresh baselines with drift protection
                try:
                    from app.baseline_guard import trigger_post_scrape_refresh

                    company_id = getattr(config, 'CURRENT_COMPANY_ID', 1)
                    refresh_result = trigger_post_scrape_refresh(company_id, source="fandango")
                    applied = refresh_result.get("applied", 0)
                    new = refresh_result.get("new", 0)
                    flagged = refresh_result.get("flagged", 0)
                    if applied or new or flagged:
                        logger.info(
                            f"Scrape job {job_id} baseline auto-refresh: "
                            f"{applied} updated, {new} new, {flagged} flagged for review"
                        )
                except Exception as refresh_err:
                    logger.warning(f"Baseline auto-refresh failed: {refresh_err}")

            except Exception as e:
                logger.error(f"Error saving results to database: {e}", exc_info=True)
                # Mark scrape run as failed if we have a run_id
                if 'run_id' in locals():
                    update_scrape_run_status(run_id, 'failed', 0, str(e))

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
