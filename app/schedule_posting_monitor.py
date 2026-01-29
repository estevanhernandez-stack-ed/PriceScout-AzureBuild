"""
Schedule Posting Monitor Service

Lightweight Fandango checks to detect when theaters post new schedules.
Unlike the full scraper, this only checks IF schedules exist - not prices.

Use cases:
- Detect same-day schedule postings (before EntTelligence 2 AM refresh)
- Monitor high-priority dates (release weekends, major posting days)
- Alert when competitors post schedules before Marcus

This is designed to be:
- Fast: Only checks for schedule existence, not prices
- Lightweight: Can run hourly without heavy resource usage
- Targeted: Focus on specific theaters and dates
"""

import asyncio
import logging
import sqlite3
import os
from datetime import datetime, date, timedelta, UTC
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from app import config

logger = logging.getLogger(__name__)


@dataclass
class SchedulePostingStatus:
    """Represents the schedule posting status for a theater/date"""
    theater_name: str
    theater_url: str
    play_date: str
    has_schedule: bool
    film_count: int
    showtime_count: int
    checked_at: str
    is_new_posting: bool  # True if this is newly detected


class SchedulePostingMonitor:
    """
    Monitor for detecting when theaters post schedules on Fandango.

    This is a lightweight alternative to full scraping - it only checks
    IF schedules exist, not the detailed pricing information.
    """

    def __init__(self, company_id: int):
        self.company_id = company_id
        self.db_path = getattr(config, 'DB_FILE', None) or os.path.join(config.PROJECT_DIR, 'pricescout.db')
        self._ensure_table_exists()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table_exists(self):
        """Create the schedule_posting_status table if it doesn't exist"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schedule_posting_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    theater_name TEXT NOT NULL,
                    theater_url TEXT,
                    play_date TEXT NOT NULL,
                    has_schedule INTEGER DEFAULT 0,
                    film_count INTEGER DEFAULT 0,
                    showtime_count INTEGER DEFAULT 0,
                    first_detected_at TEXT,
                    last_checked_at TEXT,
                    check_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                    UNIQUE(company_id, theater_name, play_date)
                )
            """)

            # Index for quick lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_schedule_posting_lookup
                ON schedule_posting_status(company_id, play_date, has_schedule)
            """)

            conn.commit()
        finally:
            conn.close()

    def get_posting_status(
        self,
        theater_name: str,
        play_date: str
    ) -> Optional[Dict[str, Any]]:
        """Get current posting status for a theater/date"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM schedule_posting_status
                WHERE company_id = ? AND theater_name = ? AND play_date = ?
            """, (self.company_id, theater_name, play_date))

            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_pending_dates(self, days_ahead: int = 14) -> List[str]:
        """Get dates that need schedule posting checks (dates without known schedules)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            today = date.today()
            dates = []

            for i in range(days_ahead):
                check_date = today + timedelta(days=i)
                dates.append(check_date.isoformat())

            # Find dates where we DON'T have schedule postings recorded
            placeholders = ','.join(['?' for _ in dates])
            cursor.execute(f"""
                SELECT DISTINCT play_date
                FROM schedule_posting_status
                WHERE company_id = ?
                  AND play_date IN ({placeholders})
                  AND has_schedule = 1
            """, [self.company_id] + dates)

            covered_dates = {row['play_date'] for row in cursor.fetchall()}
            pending_dates = [d for d in dates if d not in covered_dates]

            return pending_dates
        finally:
            conn.close()

    def get_theaters_to_check(self, circuit_filter: Optional[List[str]] = None) -> List[Dict[str, str]]:
        """Get list of theaters to check for schedule postings.

        Uses the theater_cache to get theater URLs, prioritizing:
        1. Marcus theaters (our theaters)
        2. Major competitor circuits (AMC, Regal, Cinemark)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get theaters from the market cache
            cursor.execute("""
                SELECT DISTINCT
                    t.value->>'name' as name,
                    t.value->>'url' as url,
                    t.value->>'company' as company
                FROM theater_cache,
                     json_each(json_extract(cache_data, '$.markets')) as m,
                     json_each(json_extract(m.value, '$.theaters')) as t
                WHERE t.value->>'url' IS NOT NULL
                  AND t.value->>'not_on_fandango' IS NOT 'true'
                ORDER BY
                    CASE
                        WHEN t.value->>'company' = 'Marcus' THEN 1
                        WHEN t.value->>'company' IN ('AMC', 'Regal', 'Cinemark') THEN 2
                        ELSE 3
                    END,
                    t.value->>'name'
            """)

            theaters = []
            for row in cursor.fetchall():
                if row['name'] and row['url']:
                    company = row['company'] or 'Unknown'
                    if circuit_filter is None or company in circuit_filter:
                        theaters.append({
                            'name': row['name'],
                            'url': row['url'],
                            'company': company
                        })

            return theaters
        except Exception as e:
            logger.warning(f"Could not get theaters from cache: {e}")
            return []
        finally:
            conn.close()

    async def _check_theater_schedule_async(
        self,
        theater: Dict[str, str],
        play_date: str
    ) -> SchedulePostingStatus:
        """Check if a theater has posted a schedule for a date (async).

        This is a lightweight check - it just looks for the presence of
        showtimes, not the full details.
        """
        from playwright.async_api import async_playwright

        theater_name = theater['name']
        theater_url = theater['url']

        # Build the Fandango URL for this date
        if '?' in theater_url:
            check_url = f"{theater_url}&date={play_date}"
        else:
            check_url = f"{theater_url}?date={play_date}"

        has_schedule = False
        film_count = 0
        showtime_count = 0

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = await context.new_page()

                try:
                    # Load the page with a shorter timeout for quick checks
                    await page.goto(check_url, timeout=15000, wait_until='domcontentloaded')

                    # Wait briefly for dynamic content
                    await page.wait_for_timeout(2000)

                    # Check for movie listings using Fandango's structure
                    # Look for film containers or showtime elements
                    film_elements = await page.query_selector_all('[class*="movie"], [class*="film"], [data-movie]')
                    showtime_elements = await page.query_selector_all('[class*="showtime"], [class*="time-btn"], [data-showtime]')

                    film_count = len(film_elements)
                    showtime_count = len(showtime_elements)
                    has_schedule = film_count > 0 or showtime_count > 0

                    # Alternative check: look for "no showtimes" message
                    no_showtimes = await page.query_selector('[class*="no-showtimes"], [class*="no-movies"]')
                    if no_showtimes:
                        has_schedule = False
                        film_count = 0
                        showtime_count = 0

                except Exception as e:
                    logger.debug(f"Error checking {theater_name} for {play_date}: {e}")

                await context.close()
                await browser.close()

        except Exception as e:
            logger.error(f"Playwright error checking {theater_name}: {e}")

        return SchedulePostingStatus(
            theater_name=theater_name,
            theater_url=theater_url,
            play_date=play_date,
            has_schedule=has_schedule,
            film_count=film_count,
            showtime_count=showtime_count,
            checked_at=datetime.now(UTC).isoformat(),
            is_new_posting=False  # Will be set by save_posting_status
        )

    def _run_async(self, coro):
        """Run an async coroutine in a new event loop (for sync contexts)"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def check_theater_schedule(
        self,
        theater: Dict[str, str],
        play_date: str
    ) -> SchedulePostingStatus:
        """Check if a theater has posted a schedule (sync wrapper)"""
        return self._run_async(
            self._check_theater_schedule_async(theater, play_date)
        )

    def save_posting_status(self, status: SchedulePostingStatus) -> bool:
        """Save posting status and detect if this is a new posting.

        Returns True if this is a newly detected schedule posting.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = datetime.now(UTC).isoformat()

            # Check if we already knew about this schedule
            cursor.execute("""
                SELECT has_schedule, first_detected_at, check_count
                FROM schedule_posting_status
                WHERE company_id = ? AND theater_name = ? AND play_date = ?
            """, (self.company_id, status.theater_name, status.play_date))

            existing = cursor.fetchone()
            is_new_posting = False

            if existing:
                # Update existing record
                was_posted = existing['has_schedule']
                check_count = (existing['check_count'] or 0) + 1

                # Detect newly posted schedule
                if status.has_schedule and not was_posted:
                    is_new_posting = True
                    first_detected = now
                else:
                    first_detected = existing['first_detected_at']

                cursor.execute("""
                    UPDATE schedule_posting_status
                    SET has_schedule = ?,
                        film_count = ?,
                        showtime_count = ?,
                        last_checked_at = ?,
                        first_detected_at = COALESCE(first_detected_at, ?),
                        check_count = ?
                    WHERE company_id = ? AND theater_name = ? AND play_date = ?
                """, (
                    1 if status.has_schedule else 0,
                    status.film_count,
                    status.showtime_count,
                    now,
                    first_detected if is_new_posting else None,
                    check_count,
                    self.company_id, status.theater_name, status.play_date
                ))
            else:
                # Insert new record
                is_new_posting = status.has_schedule

                cursor.execute("""
                    INSERT INTO schedule_posting_status
                    (company_id, theater_name, theater_url, play_date,
                     has_schedule, film_count, showtime_count,
                     first_detected_at, last_checked_at, check_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    self.company_id,
                    status.theater_name,
                    status.theater_url,
                    status.play_date,
                    1 if status.has_schedule else 0,
                    status.film_count,
                    status.showtime_count,
                    now if status.has_schedule else None,
                    now
                ))

            conn.commit()
            status.is_new_posting = is_new_posting
            return is_new_posting

        finally:
            conn.close()

    def create_schedule_alert(self, status: SchedulePostingStatus) -> int:
        """Create a schedule alert for a new posting detection"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = datetime.now(UTC).isoformat()

            cursor.execute("""
                INSERT INTO schedule_alerts
                (company_id, theater_name, film_title, play_date, alert_type,
                 old_value, new_value, change_details, source,
                 triggered_at, detected_at, is_acknowledged)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                self.company_id,
                status.theater_name,
                None,  # film_title - general schedule posting
                status.play_date,
                'new_schedule',
                None,
                f'{{"film_count": {status.film_count}, "showtime_count": {status.showtime_count}}}',
                f"Schedule posted for {status.play_date}: {status.film_count} films, {status.showtime_count} showtimes",
                'fandango_check',  # Different source to distinguish from EntTelligence
                now,
                now
            ))

            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def run_check(
        self,
        theaters: Optional[List[Dict[str, str]]] = None,
        play_dates: Optional[List[str]] = None,
        max_theaters: int = 20,
        circuit_filter: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Run schedule posting checks for specified theaters and dates.

        Args:
            theaters: Specific theaters to check (or None to auto-select)
            play_dates: Specific dates to check (or None to check pending dates)
            max_theaters: Maximum theaters to check per run (to limit load)
            circuit_filter: Only check theaters from these circuits

        Returns:
            Dict with check results
        """
        start_time = datetime.now(UTC)

        # Get theaters to check
        if theaters is None:
            theaters = self.get_theaters_to_check(circuit_filter)[:max_theaters]

        # Get dates to check
        if play_dates is None:
            play_dates = self.get_pending_dates(days_ahead=7)

        if not theaters:
            return {
                'status': 'skipped',
                'message': 'No theaters to check',
                'theaters_checked': 0,
                'dates_checked': 0,
                'new_postings': 0
            }

        if not play_dates:
            return {
                'status': 'skipped',
                'message': 'No pending dates to check',
                'theaters_checked': 0,
                'dates_checked': len(play_dates),
                'new_postings': 0
            }

        logger.info(f"Schedule posting check: {len(theaters)} theaters, {len(play_dates)} dates")

        results = {
            'status': 'completed',
            'theaters_checked': 0,
            'dates_checked': len(play_dates),
            'checks_performed': 0,
            'new_postings': 0,
            'alerts_created': 0,
            'postings': [],
            'errors': []
        }

        # Check each theater/date combination
        for theater in theaters:
            results['theaters_checked'] += 1

            for play_date in play_dates:
                try:
                    status = self.check_theater_schedule(theater, play_date)
                    results['checks_performed'] += 1

                    # Save and check if new
                    is_new = self.save_posting_status(status)

                    if status.has_schedule:
                        posting_info = {
                            'theater': status.theater_name,
                            'date': status.play_date,
                            'films': status.film_count,
                            'showtimes': status.showtime_count,
                            'is_new': is_new
                        }
                        results['postings'].append(posting_info)

                        if is_new:
                            results['new_postings'] += 1
                            alert_id = self.create_schedule_alert(status)
                            results['alerts_created'] += 1
                            logger.info(f"New schedule posting: {status.theater_name} for {status.play_date} (alert {alert_id})")

                except Exception as e:
                    error_msg = f"Error checking {theater['name']} for {play_date}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)

        duration = (datetime.now(UTC) - start_time).total_seconds()
        results['duration_seconds'] = duration

        logger.info(
            f"Schedule posting check complete: {results['checks_performed']} checks, "
            f"{results['new_postings']} new postings in {duration:.1f}s"
        )

        return results

    def get_posting_summary(self, days_ahead: int = 14) -> Dict[str, Any]:
        """Get summary of schedule posting status across all theaters"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            today = date.today()
            end_date = today + timedelta(days=days_ahead)

            # Overall counts
            cursor.execute("""
                SELECT
                    COUNT(*) as total_checks,
                    SUM(CASE WHEN has_schedule = 1 THEN 1 ELSE 0 END) as posted_count,
                    COUNT(DISTINCT theater_name) as theaters,
                    COUNT(DISTINCT play_date) as dates
                FROM schedule_posting_status
                WHERE company_id = ?
                  AND play_date >= ?
                  AND play_date <= ?
            """, (self.company_id, today.isoformat(), end_date.isoformat()))

            totals = dict(cursor.fetchone())

            # By date
            cursor.execute("""
                SELECT
                    play_date,
                    SUM(CASE WHEN has_schedule = 1 THEN 1 ELSE 0 END) as posted_count,
                    COUNT(*) as checked_count
                FROM schedule_posting_status
                WHERE company_id = ?
                  AND play_date >= ?
                  AND play_date <= ?
                GROUP BY play_date
                ORDER BY play_date
            """, (self.company_id, today.isoformat(), end_date.isoformat()))

            by_date = {row['play_date']: {
                'posted': row['posted_count'],
                'checked': row['checked_count']
            } for row in cursor.fetchall()}

            # Recent new postings (last 24 hours)
            yesterday = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
            cursor.execute("""
                SELECT theater_name, play_date, film_count, showtime_count, first_detected_at
                FROM schedule_posting_status
                WHERE company_id = ?
                  AND first_detected_at >= ?
                  AND has_schedule = 1
                ORDER BY first_detected_at DESC
                LIMIT 20
            """, (self.company_id, yesterday))

            recent_postings = [dict(row) for row in cursor.fetchall()]

            return {
                **totals,
                'by_date': by_date,
                'recent_postings': recent_postings
            }

        finally:
            conn.close()


def get_schedule_posting_monitor(company_id: int) -> SchedulePostingMonitor:
    """Factory function to get a SchedulePostingMonitor instance"""
    return SchedulePostingMonitor(company_id)
