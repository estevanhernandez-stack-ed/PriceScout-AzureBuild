"""
Market Baseline Scraping Service

Provides functionality to systematically scrape Fandango prices
market-by-market for baseline discovery.
"""
import json
import logging
import asyncio
import concurrent.futures
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

from app import config

logger = logging.getLogger(__name__)


def _run_async_in_new_loop(coro_func, *args, **kwargs):
    """
    Run an async coroutine in a new event loop in the current thread.
    This works around Python 3.13's asyncio subprocess issues on Windows
    by using ProactorEventLoop which supports subprocess creation.
    """
    import sys

    # On Windows with Python 3.13+, we need ProactorEventLoop for subprocess support
    # The default SelectorEventLoop doesn't support subprocess on Windows
    if sys.platform == 'win32':
        # Use ProactorEventLoop which supports subprocesses on Windows
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro_func(*args, **kwargs))
    finally:
        loop.close()


def _scrape_in_thread(scout, theaters, date_str, scrape_type="showings"):
    """
    Run scraper methods in a separate thread with a new event loop.
    This avoids Python 3.13 asyncio subprocess issues on Windows.
    """
    if scrape_type == "showings":
        return _run_async_in_new_loop(
            scout.get_all_showings_for_theaters,
            theaters,
            date_str
        )
    elif scrape_type == "details":
        # theaters is actually (theaters, showings) tuple for details
        theater_list, showings_list = theaters
        return _run_async_in_new_loop(
            scout.scrape_details,
            theater_list,
            showings_list,
            progress_callback=None
        )
    return None


@dataclass
class MarketScrapeResult:
    """Result of scraping a single market."""
    market: str
    theater_name: str
    circuit: str
    status: str  # 'completed', 'failed', 'timeout', 'skipped'
    records_count: int = 0
    error: Optional[str] = None


@dataclass
class MarketScrapeJob:
    """Tracks a market baseline scrape job."""
    job_id: str
    status: str = "pending"  # pending, running, completed, failed, cancelled
    total_markets: int = 0
    completed_markets: int = 0
    failed_markets: int = 0
    current_market: Optional[str] = None
    results: List[MarketScrapeResult] = field(default_factory=list)
    error: Optional[str] = None


# Global job tracker
_market_scrape_jobs: Dict[str, MarketScrapeJob] = {}


def load_markets_from_cache() -> Dict:
    """Load all markets and their theaters from the theater cache."""
    cache_path = Path(config.CACHE_FILE) if hasattr(config, 'CACHE_FILE') else Path("app/theater_cache.json")

    if not cache_path.exists():
        # Try alternate path
        cache_path = Path("app/theater_cache.json")

    if not cache_path.exists():
        logger.error(f"Theater cache not found at {cache_path}")
        return {}

    try:
        with open(cache_path, 'r') as f:
            cache = json.load(f)
        return cache.get("markets", {})
    except Exception as e:
        logger.error(f"Error loading theater cache: {e}")
        return {}


def select_representative_theater(theaters: List[Dict]) -> Optional[Dict]:
    """
    Select the best theater to represent a market.
    Prioritizes premium theaters (IMAX, Dolby) to capture more formats.
    """
    premium_keywords = ['IMAX', 'Dolby', 'DINE-IN', 'Dine-In', 'XD', 'Luxe', 'Prime', 'CineBistro', 'BigD']

    # First, look for premium theaters
    for theater in theaters:
        name = theater.get("name", "")
        if any(kw in name for kw in premium_keywords):
            return theater

    # Otherwise, pick the first one
    return theaters[0] if theaters else None


def build_market_scrape_plan(
    circuit_filter: Optional[str] = None,
    max_markets: Optional[int] = None
) -> List[Dict]:
    """
    Build a plan for which theaters to scrape across markets.

    Args:
        circuit_filter: Filter to specific circuit (e.g., "Marcus", "AMC")
        max_markets: Maximum number of markets to include

    Returns:
        List of dicts with market, theater, and circuit info
    """
    markets = load_markets_from_cache()
    if not markets:
        return []

    scrape_plan = []

    for market_name, market_data in markets.items():
        theaters = market_data.get("theaters", [])
        if not theaters:
            continue

        # Filter by circuit if specified
        if circuit_filter:
            theaters = [
                t for t in theaters
                if circuit_filter.lower() in t.get("company", "").lower()
            ]
            if not theaters:
                continue

        # Select representative theater
        theater = select_representative_theater(theaters)
        if theater:
            scrape_plan.append({
                "market": market_name,
                "theater_name": theater.get("name"),
                "theater_url": theater.get("url"),
                "circuit": theater.get("company", "Unknown")
            })

    # Limit if specified
    if max_markets and len(scrape_plan) > max_markets:
        scrape_plan = scrape_plan[:max_markets]

    return scrape_plan


def get_market_scrape_stats() -> Dict:
    """Get statistics about available markets for scraping."""
    markets = load_markets_from_cache()

    if not markets:
        return {"total_markets": 0, "circuits": {}}

    circuits = {}
    for market_name, market_data in markets.items():
        theaters = market_data.get("theaters", [])
        for theater in theaters:
            circuit = theater.get("company", "Unknown")
            if circuit not in circuits:
                circuits[circuit] = {"theaters": 0, "markets": set()}
            circuits[circuit]["theaters"] += 1
            circuits[circuit]["markets"].add(market_name)

    # Convert sets to counts
    circuit_stats = {
        name: {"theaters": data["theaters"], "markets": len(data["markets"])}
        for name, data in circuits.items()
    }

    return {
        "total_markets": len(markets),
        "circuits": circuit_stats
    }


async def run_market_baseline_scrape(
    job_id: str,
    scrape_plan: List[Dict],
    dates: List[date],
    company_id: int = 1,
    progress_callback: Optional[Callable] = None,
    resume: bool = False
) -> MarketScrapeJob:
    """
    Execute market baseline scrapes with checkpoint tracking and resume capability.

    Args:
        job_id: Unique job identifier
        scrape_plan: List of markets/theaters to scrape
        dates: Dates to scrape
        company_id: Company ID for data association
        progress_callback: Optional callback for progress updates
        resume: If True, skip theaters that have already been completed

    Returns:
        MarketScrapeJob with results
    """
    from app.scraper import Scraper
    from app.db_adapter import (
        save_prices, upsert_showings, create_scrape_run,
        create_checkpoint, complete_checkpoint, fail_checkpoint,
        get_completed_theaters, start_scrape_journal, update_theater_progress,
        complete_scrape_journal
    )

    job = MarketScrapeJob(
        job_id=job_id,
        status="running",
        total_markets=len(scrape_plan)
    )
    _market_scrape_jobs[job_id] = job

    # Initialize progress journal
    all_theater_names = [m["theater_name"] for m in scrape_plan]
    play_date = dates[0] if dates else date.today()

    if not resume:
        # Start fresh journal
        start_scrape_journal(
            job_id=job_id,
            theaters=all_theater_names,
            play_date=play_date,
            market=scrape_plan[0]["market"] if scrape_plan else None,
            company_id=company_id
        )
    else:
        # Check which theaters are already completed
        completed_theaters = get_completed_theaters(job_id, play_date, phase='prices')
        logger.info(f"Resume mode: {len(completed_theaters)} theaters already completed")

    scout = Scraper()

    try:
        for i, market_info in enumerate(scrape_plan):
            if job.status == "cancelled":
                break

            theater_name = market_info["theater_name"]

            # Skip if resuming and already completed
            if resume:
                completed = get_completed_theaters(job_id, play_date, phase='prices')
                if theater_name in completed:
                    logger.info(f"Skipping {theater_name} - already completed")
                    job.completed_markets = i + 1
                    continue

            job.current_market = market_info["market"]
            job.completed_markets = i

            if progress_callback:
                progress_callback(job)

            theater = {
                "name": theater_name,
                "url": market_info["theater_url"]
            }

            result = MarketScrapeResult(
                market=market_info["market"],
                theater_name=theater_name,
                circuit=market_info["circuit"],
                status="pending"
            )

            # Create a scrape run for this theater
            run_id = create_scrape_run(
                "baseline_discovery",
                context={"market": market_info["market"], "theater": theater_name},
                company_id=company_id
            )

            try:
                # Create checkpoint for showings phase
                create_checkpoint(
                    job_id=job_id,
                    run_id=run_id,
                    theater_name=theater_name,
                    play_date=play_date,
                    phase='showings',
                    company_id=company_id,
                    market=market_info["market"]
                )
                update_theater_progress(job_id, theater_name, 'showings', 'started')

                # Scrape showtimes for all dates using thread pool to avoid Python 3.13 asyncio issues
                all_showings = {}
                total_showings = 0
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    for scrape_date in dates:
                        date_str = scrape_date.strftime("%Y-%m-%d")
                        showings = await loop.run_in_executor(
                            executor,
                            _scrape_in_thread,
                            scout, [theater], date_str, "showings"
                        )
                        if showings:
                            all_showings[date_str] = showings
                            for t_showings in showings.values():
                                total_showings += len(t_showings)

                # Complete showings checkpoint
                complete_checkpoint(job_id, theater_name, play_date, 'showings',
                                   showings_count=total_showings)
                update_theater_progress(job_id, theater_name, 'showings', 'completed',
                                       showings=total_showings)

                if not all_showings:
                    result.status = "skipped"
                    result.error = "No showtimes found"
                    job.results.append(result)
                    continue

                # Flatten showings for price scraping
                showings_to_scrape = []
                for date_str, theaters_showings in all_showings.items():
                    for theater_name_inner, theater_showings in theaters_showings.items():
                        for showing in theater_showings:
                            showing['date'] = date_str
                            showing['theater_name'] = theater_name_inner
                            showings_to_scrape.append(showing)

                # Sample a subset of showtimes (max 10 per theater to avoid overload)
                if len(showings_to_scrape) > 10:
                    # Sample diverse formats
                    by_format = {}
                    for s in showings_to_scrape:
                        fmt = s.get('format', '2D')
                        if fmt not in by_format:
                            by_format[fmt] = []
                        by_format[fmt].append(s)

                    sampled = []
                    for fmt, fmt_showings in by_format.items():
                        sampled.extend(fmt_showings[:3])  # Up to 3 per format

                    showings_to_scrape = sampled[:10]

                # Convert flat showings list to the nested structure expected by scrape_details
                # Expected: {date: {theater_name: {film_title: {showtime: [showing_info]}}}}
                structured_showtimes = {}
                for showing in showings_to_scrape:
                    d = showing.get('date', 'unknown')
                    t = showing.get('theater_name', theater['name'])
                    f = showing.get('film_title', 'Unknown')
                    s = showing.get('showtime', 'Unknown')

                    if d not in structured_showtimes:
                        structured_showtimes[d] = {}
                    if t not in structured_showtimes[d]:
                        structured_showtimes[d][t] = {}
                    if f not in structured_showtimes[d][t]:
                        structured_showtimes[d][t][f] = {}
                    if s not in structured_showtimes[d][t][f]:
                        structured_showtimes[d][t][f][s] = []
                    structured_showtimes[d][t][f][s].append(showing)

                # Create checkpoint for prices phase
                create_checkpoint(
                    job_id=job_id,
                    run_id=run_id,
                    theater_name=theater_name,
                    play_date=play_date,
                    phase='prices',
                    company_id=company_id,
                    market=market_info["market"]
                )
                update_theater_progress(job_id, theater_name, 'prices', 'started')

                # Scrape prices using thread pool to avoid Python 3.13 asyncio issues
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    result_tuple = await loop.run_in_executor(
                        executor,
                        _scrape_in_thread,
                        scout, ([theater], structured_showtimes), None, "details"
                    )
                    price_data = result_tuple[0] if result_tuple else None

                if price_data:
                    # Save to database (now with batch commits)
                    import pandas as pd
                    df = pd.DataFrame(price_data)
                    save_prices(run_id, df, company_id, batch_size=50)

                    # Also save showings
                    for date_str, theaters_showings in all_showings.items():
                        for inner_theater_name, theater_showings in theaters_showings.items():
                            upsert_showings(theater_showings, date_str, company_id)

                    result.status = "completed"
                    result.records_count = len(price_data)

                    # Complete prices checkpoint
                    complete_checkpoint(job_id, theater_name, play_date, 'prices',
                                       prices_count=len(price_data))
                    update_theater_progress(job_id, theater_name, 'prices', 'completed',
                                           prices=len(price_data))
                else:
                    result.status = "completed"
                    result.records_count = 0
                    complete_checkpoint(job_id, theater_name, play_date, 'prices', prices_count=0)
                    update_theater_progress(job_id, theater_name, 'prices', 'completed', prices=0)

            except Exception as e:
                logger.exception(f"Error scraping market {market_info['market']}: {e}")
                result.status = "failed"
                result.error = str(e)[:200]
                job.failed_markets += 1

                # Mark checkpoint as failed
                fail_checkpoint(job_id, theater_name, play_date, 'prices', str(e)[:500])
                update_theater_progress(job_id, theater_name, 'prices', 'failed', error=str(e)[:200])

            job.results.append(result)

        job.completed_markets = len(scrape_plan)
        job.current_market = None
        job.status = "completed" if job.status != "cancelled" else "cancelled"

        # Complete the progress journal
        complete_scrape_journal(job_id, job.status)

    except Exception as e:
        logger.exception(f"Market baseline scrape job failed: {e}")
        job.status = "failed"
        job.error = str(e)
        complete_scrape_journal(job_id, 'failed')

    finally:
        await scout.close()

    return job


def get_market_scrape_job(job_id: str) -> Optional[MarketScrapeJob]:
    """Get a market scrape job by ID."""
    return _market_scrape_jobs.get(job_id)


def cancel_market_scrape_job(job_id: str) -> bool:
    """Cancel a running market scrape job."""
    job = _market_scrape_jobs.get(job_id)
    if job and job.status == "running":
        job.status = "cancelled"
        return True
    return False


def get_all_market_scrape_jobs() -> List[MarketScrapeJob]:
    """Get all market scrape jobs."""
    return list(_market_scrape_jobs.values())


def get_incomplete_jobs() -> List[Dict]:
    """Get list of incomplete scrape jobs that can be resumed.

    Returns:
        List of job info dicts with job_id, play_date, progress summary
    """
    from app.db_adapter import list_incomplete_jobs, read_progress_journal

    incomplete = []
    for job_id in list_incomplete_jobs():
        journal = read_progress_journal(job_id)
        if journal:
            incomplete.append({
                'job_id': job_id,
                'play_date': journal.get('play_date'),
                'market': journal.get('market'),
                'started_at': journal.get('started_at'),
                'summary': journal.get('summary', {}),
                'last_updated': journal.get('last_updated')
            })

    return incomplete


def get_job_resume_info(job_id: str) -> Dict:
    """Get detailed info about an incomplete job for resuming.

    Args:
        job_id: The job ID to check

    Returns:
        Dict with job details, completed theaters, and remaining theaters
    """
    from app.db_adapter import read_progress_journal, get_job_progress

    journal = read_progress_journal(job_id)
    db_progress = get_job_progress(job_id)

    if not journal:
        return {'error': 'Job not found'}

    theaters = journal.get('theaters', {})
    completed = [t for t, data in theaters.items() if data.get('prices_status') == 'completed']
    remaining = [t for t, data in theaters.items() if data.get('prices_status') != 'completed']
    failed = [t for t, data in theaters.items() if data.get('prices_status') == 'failed']

    return {
        'job_id': job_id,
        'play_date': journal.get('play_date'),
        'market': journal.get('market'),
        'started_at': journal.get('started_at'),
        'last_updated': journal.get('last_updated'),
        'total_theaters': len(theaters),
        'completed_theaters': len(completed),
        'remaining_theaters': len(remaining),
        'failed_theaters': len(failed),
        'completed_names': completed,
        'remaining_names': remaining,
        'failed_names': failed,
        'summary': journal.get('summary', {}),
        'db_progress': db_progress
    }
