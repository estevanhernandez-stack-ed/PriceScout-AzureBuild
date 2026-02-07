"""
EntTelligence Cache Service
Manages caching of EntTelligence pricing data for hybrid scrape optimization.

This service:
1. Syncs pricing data from EntTelligence API
2. Stores in local cache with expiration
3. Provides cache lookup for scrape optimization
"""

import os
import re
import sqlite3
from datetime import datetime, UTC, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

# Import the existing EntTelligence client
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from enttelligence_client import EntTelligenceClient

from app import config
from api.services.tax_estimation import state_from_dma


def normalize_film_title(title: str) -> str:
    """
    Normalize film title for matching.
    Strips year suffix like '(2026)' and extra whitespace.
    """
    if not title:
        return ""
    # Remove year suffix like (2026), (2025), etc.
    normalized = re.sub(r'\s*\(\d{4}\)\s*$', '', title)
    return normalized.strip()


def normalize_showtime(time_str: str) -> str:
    """
    Normalize showtime to 24-hour HH:MM format for matching.
    Converts '2:30PM' -> '14:30', '10:45AM' -> '10:45'
    """
    if not time_str:
        return ""

    time_str = time_str.strip().upper()

    # Already in 24-hour format (no AM/PM)
    if 'AM' not in time_str and 'PM' not in time_str:
        # Ensure HH:MM format
        parts = time_str.split(':')
        if len(parts) == 2:
            return f"{int(parts[0]):02d}:{parts[1][:2]}"
        return time_str

    # Parse 12-hour format
    match = re.match(r'(\d{1,2}):?(\d{2})?\s*(AM|PM)', time_str)
    if match:
        hour = int(match.group(1))
        minute = match.group(2) or '00'
        period = match.group(3)

        if period == 'PM' and hour != 12:
            hour += 12
        elif period == 'AM' and hour == 12:
            hour = 0

        return f"{hour:02d}:{minute}"

    return time_str


def _time_to_minutes(time_str: str) -> Optional[int]:
    """
    Convert HH:MM time string to minutes since midnight.
    Returns None if parsing fails.
    """
    if not time_str:
        return None
    try:
        # Normalize first in case it's in 12-hour format
        normalized = normalize_showtime(time_str)
        parts = normalized.split(':')
        if len(parts) >= 2:
            hours = int(parts[0])
            minutes = int(parts[1][:2])
            return hours * 60 + minutes
    except (ValueError, IndexError):
        pass
    return None


@dataclass
class CachedPrice:
    """Represents a cached price entry"""
    theater_name: str
    film_title: str
    play_date: str
    showtime: str
    format: Optional[str]
    ticket_type: str
    price: float
    source: str
    fetched_at: datetime
    expires_at: datetime
    circuit_name: Optional[str] = None


class EntTelligenceCacheService:
    """Service for managing EntTelligence price cache"""

    def __init__(self, db_path: Optional[str] = None, cache_max_age_hours: int = 6):
        """
        Initialize cache service.

        Args:
            db_path: Path to SQLite database (uses config default if not provided)
            cache_max_age_hours: Hours before cached data is considered stale
        """
        self.db_path = db_path or config.DB_FILE or os.path.join(config.PROJECT_DIR, 'pricescout.db')
        self.cache_max_age_hours = cache_max_age_hours
        self._client: Optional[EntTelligenceClient] = None

    def _get_client(self) -> EntTelligenceClient:
        """Get authenticated EntTelligence client (lazy initialization)"""
        if self._client is None:
            self._client = EntTelligenceClient(
                base_url=os.getenv('ENTTELLIGENCE_BASE_URL', 'http://23.20.236.151:7582')
            )
            token_name = os.getenv('ENTTELLIGENCE_TOKEN_NAME', 'PriceScoutAzure')
            token_secret = os.getenv('ENTTELLIGENCE_TOKEN_SECRET', '')

            if not token_secret:
                raise ValueError("ENTTELLIGENCE_TOKEN_SECRET environment variable not set")

            if not self._client.login(token_name, token_secret):
                raise RuntimeError("Failed to authenticate with EntTelligence API")

        return self._client

    def _get_db_connection(self) -> sqlite3.Connection:
        """Get database connection with WAL mode for concurrent access"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _update_theater_metadata(
        self,
        cursor: sqlite3.Cursor,
        company_id: int,
        theaters_data: Dict[str, Dict[str, str]]
    ) -> int:
        """
        Update theater_metadata table with DMA info from EntTelligence.

        Args:
            cursor: Database cursor
            company_id: Company ID
            theaters_data: Dict mapping theater_name -> {circuit_name, dma}

        Returns:
            Number of theaters updated
        """
        updated = 0
        for theater_name, data in theaters_data.items():
            circuit_name = data.get('circuit_name', '')
            dma = data.get('dma', '')

            if not theater_name or not dma:
                continue

            # Insert or update theater metadata
            # - dma column: EntTelligence DMA (system-defined, always updated)
            # - state column: derived from DMA, only set if currently NULL
            # - market column: Marcus-specific markets (admin-editable, preserved)
            derived_state = state_from_dma(dma) or ''
            cursor.execute("""
                INSERT INTO theater_metadata (company_id, theater_name, circuit_name, dma, state, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(company_id, theater_name) DO UPDATE SET
                    circuit_name = COALESCE(NULLIF(excluded.circuit_name, ''), theater_metadata.circuit_name),
                    dma = excluded.dma,
                    state = COALESCE(NULLIF(theater_metadata.state, ''), excluded.state)
            """, (company_id, theater_name, circuit_name, dma, derived_state))

            if cursor.rowcount > 0:
                updated += 1

        return updated

    def sync_prices_for_dates(
        self,
        company_id: int,
        start_date: str,
        end_date: Optional[str] = None,
        circuits: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Sync pricing data from EntTelligence for a date range.

        Args:
            company_id: Company ID for multi-tenancy
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD), defaults to start_date
            circuits: Optional list of circuits to filter (e.g., ['AMC', 'Regal'])

        Returns:
            Dict with sync statistics
        """
        end_date = end_date or start_date
        client = self._get_client()

        # Fetch programming audit data
        print(f"[EntCache] Fetching data from EntTelligence for {start_date} to {end_date}...")
        showtimes = client.get_programming_audit(start_date, end_date)
        print(f"[EntCache] Retrieved {len(showtimes)} showtime records")

        if not showtimes:
            return {
                "status": "completed",
                "records_fetched": 0,
                "records_cached": 0,
                "circuits": [],
                "errors": 0
            }

        # Filter by circuits if specified
        if circuits:
            showtimes = [s for s in showtimes if s.get('circuit_name') in circuits]
            print(f"[EntCache] Filtered to {len(showtimes)} records for circuits: {circuits}")

        # Prepare cache entries
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=self.cache_max_age_hours)

        cached_count = 0
        error_count = 0
        circuits_seen = set()
        theaters_metadata = {}  # Collect theater -> {circuit_name, dma} for metadata update

        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            for showtime in showtimes:
                try:
                    # Extract fields from EntTelligence record
                    # Field mapping: EntTelligence API uses these field names
                    theater_name = showtime.get('theater_name', '').strip()
                    film_title = showtime.get('title', '').strip()
                    play_date = showtime.get('date_sh', showtime.get('show_date', ''))
                    show_time = showtime.get('show_time', showtime.get('time_sh', '')).strip()
                    circuit_name = showtime.get('circuit_name', '')
                    price_adult = showtime.get('price_per_general', 0)
                    price_child = showtime.get('price_per_child', 0)
                    price_senior = showtime.get('price_per_senior', 0)
                    film_format = showtime.get('film_format', None)
                    dma = showtime.get('dma', '')  # Extract DMA/market from EntTelligence

                    # Capacity / sales data
                    capacity = showtime.get('capacity', None)
                    available_seats = showtime.get('available', None)
                    blocked_seats = showtime.get('blocked', None)

                    # Film & theater metadata
                    release_date = showtime.get('release_date', None)
                    imdb_id = showtime.get('imdb_id', None)
                    ent_movie_id = showtime.get('movie_id', None)
                    ent_theater_id = showtime.get('theater_id', None)

                    if not all([theater_name, film_title, play_date, show_time]):
                        continue

                    circuits_seen.add(circuit_name)

                    # Collect theater metadata for bulk update
                    if theater_name and theater_name not in theaters_metadata:
                        theaters_metadata[theater_name] = {
                            'circuit_name': circuit_name,
                            'dma': dma
                        }

                    # Build list of (ticket_type, price) pairs to cache
                    # Cache Adult always (even if 0, for completeness)
                    # Cache Child/Senior only if price > 0
                    price_rows = [('Adult', price_adult)]
                    if price_child and float(price_child) > 0:
                        price_rows.append(('Child', float(price_child)))
                    if price_senior and float(price_senior) > 0:
                        price_rows.append(('Senior', float(price_senior)))

                    # Upsert each ticket type into cache
                    for ticket_type, ticket_price in price_rows:
                        cursor.execute("""
                            INSERT OR REPLACE INTO enttelligence_price_cache (
                                company_id, play_date, theater_name, film_title, showtime,
                                format, ticket_type, price, source, fetched_at, expires_at,
                                circuit_name, created_at,
                                capacity, available, blocked,
                                release_date, imdb_id, movie_id, theater_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            company_id,
                            play_date,
                            theater_name,
                            film_title,
                            show_time,
                            film_format,
                            ticket_type,
                            ticket_price,
                            'enttelligence',
                            now.isoformat(),
                            expires_at.isoformat(),
                            circuit_name,
                            now.isoformat(),
                            capacity,
                            available_seats,
                            blocked_seats,
                            release_date,
                            imdb_id,
                            ent_movie_id,
                            ent_theater_id,
                        ))
                        cached_count += 1

                except Exception as e:
                    error_count += 1
                    if error_count <= 5:
                        print(f"[EntCache] Error caching record: {e}")

            # Update theater metadata with DMA info from EntTelligence
            theaters_updated = 0
            if theaters_metadata:
                theaters_updated = self._update_theater_metadata(cursor, company_id, theaters_metadata)
                if theaters_updated > 0:
                    print(f"[EntCache] Updated {theaters_updated} theater metadata records with DMA info")

            conn.commit()
            print(f"[EntCache] Cached {cached_count} price records")

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Failed to cache prices: {e}")
        finally:
            conn.close()

        return {
            "status": "completed",
            "records_fetched": len(showtimes),
            "records_cached": cached_count,
            "theaters_updated": theaters_updated,
            "circuits": list(circuits_seen),
            "errors": error_count
        }

    def lookup_cached_prices(
        self,
        showtime_keys: List[str],
        company_id: int = 1,
        max_age_hours: Optional[int] = None
    ) -> Dict[str, Optional[CachedPrice]]:
        """
        Look up cached prices for showtime keys.

        Args:
            showtime_keys: List of "date|theater|film|time" keys
            company_id: Company ID for filtering
            max_age_hours: Override for cache max age (uses default if not provided)

        Returns:
            Dict mapping showtime_key -> CachedPrice or None (cache miss)
        """
        if not showtime_keys:
            return {}

        max_age = max_age_hours or self.cache_max_age_hours
        min_fetched_at = datetime.now(UTC) - timedelta(hours=max_age)

        results: Dict[str, Optional[CachedPrice]] = {key: None for key in showtime_keys}

        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            for key in showtime_keys:
                parts = key.split('|')
                if len(parts) < 4:
                    continue

                play_date, theater_name, film_title, showtime = parts[:4]

                # Normalize for matching (handles Fandango vs EntTelligence differences)
                normalized_film = normalize_film_title(film_title)
                normalized_time = normalize_showtime(showtime)

                row = None

                # Strategy 1: Try exact match with normalized values
                cursor.execute("""
                    SELECT theater_name, film_title, play_date, showtime, format,
                           ticket_type, price, source, fetched_at, expires_at, circuit_name
                    FROM enttelligence_price_cache
                    WHERE company_id = ?
                      AND play_date = ?
                      AND theater_name = ?
                      AND film_title = ?
                      AND showtime = ?
                      AND fetched_at > ?
                    ORDER BY fetched_at DESC
                    LIMIT 1
                """, (company_id, play_date, theater_name, normalized_film, normalized_time, min_fetched_at.isoformat()))
                row = cursor.fetchone()

                # Strategy 2: If no exact match, find closest showtime for same film
                if not row:
                    cursor.execute("""
                        SELECT theater_name, film_title, play_date, showtime, format,
                               ticket_type, price, source, fetched_at, expires_at, circuit_name
                        FROM enttelligence_price_cache
                        WHERE company_id = ?
                          AND play_date = ?
                          AND theater_name = ?
                          AND film_title = ?
                          AND fetched_at > ?
                        ORDER BY fetched_at DESC
                    """, (company_id, play_date, theater_name, normalized_film, min_fetched_at.isoformat()))

                    candidates = cursor.fetchall()
                    if candidates:
                        # Find closest showtime - prefer within 60 min, but take any match for same film
                        target_minutes = _time_to_minutes(normalized_time)
                        if target_minutes is not None:
                            best_match = None
                            best_diff = float('inf')
                            for candidate in candidates:
                                candidate_minutes = _time_to_minutes(candidate['showtime'])
                                if candidate_minutes is not None:
                                    diff = abs(candidate_minutes - target_minutes)
                                    if diff < best_diff:
                                        best_diff = diff
                                        best_match = candidate
                            # Accept any match for same film (price is likely similar for same film)
                            row = best_match

                if row:
                    results[key] = CachedPrice(
                        theater_name=row['theater_name'],
                        film_title=row['film_title'],
                        play_date=row['play_date'],
                        showtime=row['showtime'],
                        format=row['format'],
                        ticket_type=row['ticket_type'],
                        price=float(row['price']),
                        source=row['source'],
                        fetched_at=datetime.fromisoformat(row['fetched_at']),
                        expires_at=datetime.fromisoformat(row['expires_at']),
                        circuit_name=row['circuit_name']
                    )

        finally:
            conn.close()

        return results

    def lookup_cached_prices_all_types(
        self,
        showtime_keys: List[str],
        company_id: int = 1,
        max_age_hours: Optional[int] = None
    ) -> Dict[str, List[CachedPrice]]:
        """
        Look up cached prices for showtime keys, returning ALL ticket types per key.

        Unlike lookup_cached_prices() which returns one CachedPrice per key,
        this returns a list of CachedPrice objects (one per ticket type: Adult, Child, Senior).

        Args:
            showtime_keys: List of "date|theater|film|time" keys
            company_id: Company ID for filtering
            max_age_hours: Override for cache max age (uses default if not provided)

        Returns:
            Dict mapping showtime_key -> List[CachedPrice] (empty list = cache miss)
        """
        if not showtime_keys:
            return {}

        max_age = max_age_hours or self.cache_max_age_hours
        min_fetched_at = datetime.now(UTC) - timedelta(hours=max_age)

        results: Dict[str, List[CachedPrice]] = {key: [] for key in showtime_keys}

        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            for key in showtime_keys:
                parts = key.split('|')
                if len(parts) < 4:
                    continue

                play_date, theater_name, film_title, showtime = parts[:4]

                # Normalize for matching
                normalized_film = normalize_film_title(film_title)
                normalized_time = normalize_showtime(showtime)

                rows = []

                # Strategy 1: Try exact match with normalized values (all ticket types)
                cursor.execute("""
                    SELECT theater_name, film_title, play_date, showtime, format,
                           ticket_type, price, source, fetched_at, expires_at, circuit_name
                    FROM enttelligence_price_cache
                    WHERE company_id = ?
                      AND play_date = ?
                      AND theater_name = ?
                      AND film_title = ?
                      AND showtime = ?
                      AND fetched_at > ?
                    ORDER BY fetched_at DESC
                """, (company_id, play_date, theater_name, normalized_film, normalized_time, min_fetched_at.isoformat()))
                rows = cursor.fetchall()

                # Strategy 2: If no exact match, find closest showtime for same film
                if not rows:
                    cursor.execute("""
                        SELECT theater_name, film_title, play_date, showtime, format,
                               ticket_type, price, source, fetched_at, expires_at, circuit_name
                        FROM enttelligence_price_cache
                        WHERE company_id = ?
                          AND play_date = ?
                          AND theater_name = ?
                          AND film_title = ?
                          AND fetched_at > ?
                        ORDER BY fetched_at DESC
                    """, (company_id, play_date, theater_name, normalized_film, min_fetched_at.isoformat()))

                    candidates = cursor.fetchall()
                    if candidates:
                        target_minutes = _time_to_minutes(normalized_time)
                        if target_minutes is not None:
                            # Group candidates by showtime to find closest
                            by_showtime: Dict[str, list] = {}
                            for c in candidates:
                                st = c['showtime']
                                if st not in by_showtime:
                                    by_showtime[st] = []
                                by_showtime[st].append(c)

                            # Find closest showtime
                            best_showtime = None
                            best_diff = float('inf')
                            for st in by_showtime:
                                st_minutes = _time_to_minutes(st)
                                if st_minutes is not None:
                                    diff = abs(st_minutes - target_minutes)
                                    if diff < best_diff:
                                        best_diff = diff
                                        best_showtime = st

                            if best_showtime is not None:
                                rows = by_showtime[best_showtime]

                # Deduplicate by ticket_type (take most recent per type)
                seen_types = set()
                for row in rows:
                    tt = row['ticket_type']
                    if tt in seen_types:
                        continue
                    seen_types.add(tt)
                    results[key].append(CachedPrice(
                        theater_name=row['theater_name'],
                        film_title=row['film_title'],
                        play_date=row['play_date'],
                        showtime=row['showtime'],
                        format=row['format'],
                        ticket_type=row['ticket_type'],
                        price=float(row['price']),
                        source=row['source'],
                        fetched_at=datetime.fromisoformat(row['fetched_at']),
                        expires_at=datetime.fromisoformat(row['expires_at']),
                        circuit_name=row['circuit_name']
                    ))

        finally:
            conn.close()

        return results

    def get_cached_showtimes_for_theater_dates(
        self,
        theater_names: List[str],
        play_dates: List[str],
        company_id: int = 1,
        max_age_hours: Optional[int] = None
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Get all cached showtime entries for given theaters and dates.

        Used by showtime verification to compare Fandango live showtimes
        against what's in the EntTelligence cache.

        Args:
            theater_names: List of theater names to query
            play_dates: List of play dates in YYYY-MM-DD format
            company_id: Company ID for filtering
            max_age_hours: Override for cache max age

        Returns:
            {date: {theater: [{film_title, showtime, format, adult_price, fetched_at}]}}
        """
        if not theater_names or not play_dates:
            return {}

        max_age = max_age_hours or self.cache_max_age_hours
        min_fetched_at = datetime.now(UTC) - timedelta(hours=max_age)

        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            # Build parameterized IN clauses
            date_placeholders = ','.join('?' for _ in play_dates)
            theater_placeholders = ','.join('?' for _ in theater_names)

            cursor.execute(f"""
                SELECT play_date, theater_name, film_title, showtime, format,
                       MAX(fetched_at) as latest_fetch,
                       COUNT(DISTINCT ticket_type) as ticket_type_count,
                       MAX(CASE WHEN ticket_type = 'Adult' THEN price ELSE NULL END) as adult_price
                FROM enttelligence_price_cache
                WHERE company_id = ?
                  AND play_date IN ({date_placeholders})
                  AND theater_name IN ({theater_placeholders})
                  AND fetched_at > ?
                GROUP BY play_date, theater_name, film_title, showtime, format
                ORDER BY play_date, theater_name, showtime
            """, [company_id] + play_dates + theater_names + [min_fetched_at.isoformat()])

            rows = cursor.fetchall()

            # Build nested dict: {date: {theater: [entries]}}
            results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
            for row in rows:
                date_str = str(row['play_date'])
                theater = row['theater_name']

                if date_str not in results:
                    results[date_str] = {}
                if theater not in results[date_str]:
                    results[date_str][theater] = []

                results[date_str][theater].append({
                    'film_title': row['film_title'],
                    'showtime': row['showtime'],
                    'format': row['format'],
                    'adult_price': float(row['adult_price']) if row['adult_price'] else None,
                    'ticket_type_count': row['ticket_type_count'],
                    'fetched_at': row['latest_fetch'],
                })

            return results

        finally:
            conn.close()

    def get_cache_stats(self, company_id: int = 1) -> Dict[str, Any]:
        """
        Get cache statistics.

        Args:
            company_id: Company ID for filtering

        Returns:
            Dict with cache statistics
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            now = datetime.now(UTC)

            # Total cached entries
            cursor.execute("""
                SELECT COUNT(*) as total FROM enttelligence_price_cache
                WHERE company_id = ?
            """, (company_id,))
            total = cursor.fetchone()['total']

            # Fresh entries (not expired)
            cursor.execute("""
                SELECT COUNT(*) as fresh FROM enttelligence_price_cache
                WHERE company_id = ? AND expires_at > ?
            """, (company_id, now.isoformat()))
            fresh = cursor.fetchone()['fresh']

            # Entries by circuit
            cursor.execute("""
                SELECT circuit_name, COUNT(*) as count
                FROM enttelligence_price_cache
                WHERE company_id = ?
                GROUP BY circuit_name
            """, (company_id,))
            by_circuit = {row['circuit_name']: row['count'] for row in cursor.fetchall()}

            # Most recent fetch
            cursor.execute("""
                SELECT MAX(fetched_at) as last_fetch
                FROM enttelligence_price_cache
                WHERE company_id = ?
            """, (company_id,))
            row = cursor.fetchone()
            last_fetch = row['last_fetch'] if row else None

            return {
                "total_entries": total,
                "fresh_entries": fresh,
                "stale_entries": total - fresh,
                "by_circuit": by_circuit,
                "last_fetch": last_fetch,
                "cache_max_age_hours": self.cache_max_age_hours
            }

        finally:
            conn.close()

    def cleanup_expired(self, company_id: int = 1) -> int:
        """
        Remove expired cache entries.

        Args:
            company_id: Company ID for filtering

        Returns:
            Number of entries removed
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            now = datetime.now(UTC)
            cursor.execute("""
                DELETE FROM enttelligence_price_cache
                WHERE company_id = ? AND expires_at < ?
            """, (company_id, now.isoformat()))
            deleted = cursor.rowcount
            conn.commit()
            print(f"[EntCache] Cleaned up {deleted} expired entries")
            return deleted

        finally:
            conn.close()


# Singleton instance for convenience
_cache_service: Optional[EntTelligenceCacheService] = None


def get_cache_service() -> EntTelligenceCacheService:
    """Get or create singleton cache service instance"""
    global _cache_service
    if _cache_service is None:
        _cache_service = EntTelligenceCacheService()
    return _cache_service
