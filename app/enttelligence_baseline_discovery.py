"""
EntTelligence Baseline Discovery Service for PriceScout

Discovers and maintains price baselines from EntTelligence cached data.
This is separate from Fandango-based baseline discovery to allow comparison
between data sources and handle EntTelligence-specific fields (circuits, etc.).

Usage:
    from app.enttelligence_baseline_discovery import (
        discover_enttelligence_baselines,
        analyze_enttelligence_prices
    )

    # Discover baselines from EntTelligence data
    baselines = discover_enttelligence_baselines(company_id=1)

    # Analyze price patterns by circuit
    analysis = analyze_enttelligence_prices(company_id=1)
"""

from datetime import datetime, date, timedelta, UTC, time
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import statistics
import logging
import re

from sqlalchemy import and_, func, text
from sqlalchemy.orm import Session

from app.db_session import get_session
from app.db_models import EntTelligencePriceCache, PriceBaseline

logger = logging.getLogger(__name__)

# Daypart thresholds - aligned with Fandango scraper for consistency
# Matinee: Before 4:00 PM
# Twilight: 4:00 PM - 6:00 PM
# Prime: 6:00 PM - 9:00 PM
# Late Night: After 9:00 PM
MATINEE_CUTOFF = time(16, 0)   # 4:00 PM
TWILIGHT_CUTOFF = time(18, 0)  # 6:00 PM
PRIME_CUTOFF = time(21, 0)     # 9:00 PM

# Minimum price difference to consider dayparts distinct (in dollars)
DAYPART_PRICE_THRESHOLD = 0.50

# Premium formats (same as baseline_discovery.py for consistency)
PREMIUM_FORMATS = {
    'IMAX', 'IMAX 3D', 'IMAX with Laser', 'IMAX HFR 3D',
    'Dolby Cinema', 'Dolby Atmos', 'Dolby Vision',
    '3D', 'RealD 3D', 'Digital 3D',
    'PLF', 'Premium Large Format', 'XD', 'RPX', 'BigD',
    '4DX', 'D-BOX', 'ScreenX', 'MX4D',
    'Laser IMAX', 'GTX', 'UltraAVX',
}

# Event cinema / special presentations - prices set by distributor, not theater
# These should be excluded from baseline calculation but tracked separately
EVENT_CINEMA_KEYWORDS = [
    # Distributors
    'Fathom', 'Trafalgar',
    # Opera/Theatre broadcasts
    'Met Opera', 'NT Live', 'National Theatre', 'Bolshoi', 'Royal Opera',
    'Royal Ballet', 'Globe Theatre', 'Stratford Festival',
    # Concert/Music events
    'Concert', 'Live Event', 'Live in Concert', 'Tour Film',
    # Special presentations
    'TCM', 'Turner Classic', 'Anniversary', 'Encore',
    'Special Presentation', 'Special Event', 'Fan Event',
    'Marathon', 'Double Feature', 'Triple Feature',
    # Sports/other
    'WWE', 'UFC', 'Boxing', 'Wrestling',
    # Anime events (often Fathom distributed)
    'Crunchyroll', 'Funimation',
]


class EntTelligenceBaselineDiscoveryService:
    """Service for discovering price baselines from EntTelligence cached data."""

    def __init__(self, company_id: int):
        self.company_id = company_id

    def is_premium_format(self, format_name: str) -> bool:
        """Check if format is a known premium format."""
        if not format_name:
            return False
        format_upper = format_name.upper()
        return any(pf.upper() in format_upper for pf in PREMIUM_FORMATS)

    def is_event_cinema(self, film_title: str) -> bool:
        """
        Check if a film appears to be event cinema based on title keywords.

        Event cinema includes Fathom Events, opera broadcasts, concerts, etc.
        These have distributor-set pricing and should be tracked separately.
        """
        if not film_title:
            return False
        title_upper = film_title.upper()
        return any(kw.upper() in title_upper for kw in EVENT_CINEMA_KEYWORDS)

    def _get_day_type(self, play_date: date) -> str:
        """
        Determine day type from a date.
        Weekday = Monday-Thursday (0-3)
        Weekend = Friday-Sunday (4-6)
        """
        day_of_week = play_date.weekday()
        return 'weekend' if day_of_week >= 4 else 'weekday'

    def _normalize_time_string(self, time_str: str) -> str:
        """
        Normalize time string for parsing.
        e.g., '4:15p' -> '04:15PM', '10:30 AM' -> '10:30AM'
        """
        if not isinstance(time_str, str):
            return ""

        # General cleanup
        time_str = time_str.lower().strip().replace('.', '').replace(' ', '')

        # Handle single letter 'p' or 'a'
        if time_str.endswith('p'):
            time_str = time_str[:-1] + 'pm'
        elif time_str.endswith('a'):
            time_str = time_str[:-1] + 'am'

        # Add leading zero if needed (e.g., 4:15pm -> 04:15pm)
        match = re.match(r'^(\d):(\d{2}(?:am|pm))$', time_str)
        if match:
            time_str = f"0{match.group(1)}:{match.group(2)}"

        return time_str.upper()

    def _get_daypart(self, showtime: str) -> Optional[str]:
        """
        Determine daypart from showtime string.

        Uses same cutoffs as Fandango scraper for consistency:
        - Matinee: Before 4:00 PM
        - Twilight: 4:00 PM - 6:00 PM
        - Prime: 6:00 PM - 9:00 PM
        - Late Night: After 9:00 PM

        Returns None if showtime can't be parsed.
        """
        if not showtime:
            return None

        try:
            time_obj = None

            # First try 24-hour format (EntTelligence uses this: "13:30", "20:25")
            if re.match(r'^\d{1,2}:\d{2}$', showtime.strip()):
                time_obj = datetime.strptime(showtime.strip(), "%H:%M").time()
            else:
                # Try 12-hour format with AM/PM
                normalized = self._normalize_time_string(showtime)
                if normalized:
                    time_obj = datetime.strptime(normalized, "%I:%M%p").time()

            if time_obj is None:
                return None

            # Use same daypart names as Fandango scraper (title case)
            if time_obj < MATINEE_CUTOFF:
                return 'Matinee'
            elif time_obj < TWILIGHT_CUTOFF:
                return 'Twilight'
            elif time_obj < PRIME_CUTOFF:
                return 'Prime'
            else:
                return 'Late Night'
        except (ValueError, AttributeError) as e:
            logger.debug(f"Could not parse showtime '{showtime}': {e}")
            return None

    def _get_time_bucket(self, showtime: str) -> Optional[str]:
        """
        Get a coarse time bucket for price-based daypart analysis.
        Returns 'early' (before 4pm), 'mid' (4-9pm), or 'late' (after 9pm).
        """
        if not showtime:
            return None
        try:
            time_obj = None
            if re.match(r'^\d{1,2}:\d{2}$', showtime.strip()):
                time_obj = datetime.strptime(showtime.strip(), "%H:%M").time()
            else:
                normalized = self._normalize_time_string(showtime)
                if normalized:
                    time_obj = datetime.strptime(normalized, "%I:%M%p").time()

            if time_obj is None:
                return None

            if time_obj < MATINEE_CUTOFF:
                return 'early'
            elif time_obj < PRIME_CUTOFF:
                return 'mid'
            else:
                return 'late'
        except (ValueError, AttributeError):
            return None

    def discover_baselines(
        self,
        min_samples: int = 5,
        lookback_days: int = 30,
        percentile: int = 25,
        exclude_premium: bool = True,
        exclude_event_cinema: bool = True,
        circuit_filter: Optional[List[str]] = None,
        split_by_day_type: bool = False,
        split_by_daypart: bool = False,
        split_by_day_of_week: bool = False
    ) -> List[Dict]:
        """
        Discover baselines from EntTelligence cached price data.

        Args:
            min_samples: Minimum number of price samples required
            lookback_days: How many days of history to analyze
            percentile: Which percentile to use as baseline (lower = more conservative)
            exclude_premium: Whether to exclude premium formats from baseline calculation
            exclude_event_cinema: Whether to exclude event cinema (Fathom, operas, concerts)
                                  from baseline calculation. Recommended True to avoid
                                  distributor-set pricing inflating baselines.
            circuit_filter: Optional list of circuits to include (None = all)
            split_by_day_type: Whether to calculate separate weekday/weekend baselines
            split_by_daypart: Whether to calculate separate matinee/evening/late baselines
            split_by_day_of_week: Whether to calculate separate baselines for each day (Mon-Sun)
                                  Note: If True, day_type is ignored since day_of_week is more granular

        Returns:
            List of discovered baseline configurations
        """
        import sys
        sys.stderr.write(f"[DISCOVERY SERVICE] discover_baselines called: company_id={self.company_id}, split_day_type={split_by_day_type}, split_daypart={split_by_daypart}\n")
        sys.stderr.flush()

        discovered = []
        cutoff_date = date.today() - timedelta(days=lookback_days)

        with get_session() as session:
            if split_by_day_type or split_by_daypart or split_by_day_of_week:
                # Get all data and group in Python for flexible splitting
                discovered = self._discover_with_splits(
                    session, cutoff_date, min_samples, percentile,
                    exclude_premium, exclude_event_cinema, circuit_filter,
                    split_by_day_type, split_by_daypart, split_by_day_of_week
                )
            else:
                # Original logic - no splitting
                discovered = self._discover_without_day_type_split(
                    session, cutoff_date, min_samples, percentile,
                    exclude_premium, exclude_event_cinema, circuit_filter
                )

        logger.info(f"Discovered {len(discovered)} baselines from EntTelligence data for company {self.company_id}")
        return discovered

    def _discover_without_day_type_split(
        self,
        session: Session,
        cutoff_date: date,
        min_samples: int,
        percentile: int,
        exclude_premium: bool,
        exclude_event_cinema: bool,
        circuit_filter: Optional[List[str]]
    ) -> List[Dict]:
        """
        Discovery logic without day type or daypart splitting.

        Fetches all records, filters by premium/event cinema, then groups
        by theater/ticket/format/circuit to calculate baselines.
        """
        from collections import defaultdict
        discovered = []
        skipped_event_cinema = 0

        # Build base query - need film_title for event cinema filtering
        query = session.query(
            EntTelligencePriceCache.theater_name,
            EntTelligencePriceCache.ticket_type,
            EntTelligencePriceCache.format,
            EntTelligencePriceCache.circuit_name,
            EntTelligencePriceCache.film_title,
            EntTelligencePriceCache.price
        ).filter(
            and_(
                EntTelligencePriceCache.company_id == self.company_id,
                EntTelligencePriceCache.play_date >= cutoff_date,
                EntTelligencePriceCache.price > 0
            )
        )

        # Apply circuit filter if specified
        if circuit_filter:
            query = query.filter(
                EntTelligencePriceCache.circuit_name.in_(circuit_filter)
            )

        # Group data by (theater, ticket_type, format, circuit)
        grouped_data = defaultdict(list)

        for row in query.all():
            theater_name, ticket_type, format_type, circuit_name, film_title, price = row

            # Skip premium formats if requested
            if exclude_premium and self.is_premium_format(format_type):
                continue

            # Skip event cinema if requested
            if exclude_event_cinema and self.is_event_cinema(film_title):
                skipped_event_cinema += 1
                continue

            if not price or float(price) <= 0:
                continue

            key = (theater_name, ticket_type, format_type, circuit_name)
            grouped_data[key].append(float(price))

        if skipped_event_cinema > 0:
            logger.info(f"Excluded {skipped_event_cinema} event cinema price records from baseline calculation")

        logger.info(f"Found {len(grouped_data)} theater/ticket/format combinations")

        # Process each group
        for (theater_name, ticket_type, format_type, circuit_name), prices in grouped_data.items():
            if len(prices) < min_samples:
                continue

            prices_sorted = sorted(prices)
            baseline_price = self._percentile(prices_sorted, percentile)
            min_p = min(prices)
            max_p = max(prices)
            avg_p = sum(prices) / len(prices)
            price_range = max_p - min_p
            volatility = (price_range / avg_p * 100) if avg_p else 0

            discovered.append({
                'theater_name': theater_name,
                'ticket_type': ticket_type,
                'format': format_type,
                'circuit_name': circuit_name,
                'day_type': None,
                'day_of_week': None,
                'daypart': None,
                'baseline_price': round(baseline_price, 2),
                'sample_count': len(prices),
                'min_price': round(min_p, 2),
                'max_price': round(max_p, 2),
                'avg_price': round(avg_p, 2),
                'volatility_percent': round(volatility, 1),
                'is_premium': self.is_premium_format(format_type),
                'source': 'enttelligence'
            })

        return discovered

    def _discover_with_splits(
        self,
        session: Session,
        cutoff_date: date,
        min_samples: int,
        percentile: int,
        exclude_premium: bool,
        exclude_event_cinema: bool,
        circuit_filter: Optional[List[str]],
        split_by_day_type: bool,
        split_by_daypart: bool,
        split_by_day_of_week: bool = False
    ) -> List[Dict]:
        """
        Discovery logic with flexible splitting by day_type, daypart, and/or day_of_week.

        This unified method handles:
        - split_by_day_type only: weekday/weekend baselines
        - split_by_daypart only: matinee/evening/late baselines
        - split_by_day_of_week only: Mon/Tue/Wed/Thu/Fri/Sat/Sun baselines
        - combinations: full granularity (e.g., Monday_matinee, Friday_evening)

        Note: If split_by_day_of_week is True, day_type is ignored since
        day_of_week provides more granular information.
        """
        discovered = []

        # Build base query to get all records with play_date, showtime, and film_title
        query = session.query(
            EntTelligencePriceCache.theater_name,
            EntTelligencePriceCache.ticket_type,
            EntTelligencePriceCache.format,
            EntTelligencePriceCache.circuit_name,
            EntTelligencePriceCache.play_date,
            EntTelligencePriceCache.showtime,
            EntTelligencePriceCache.price,
            EntTelligencePriceCache.film_title
        ).filter(
            and_(
                EntTelligencePriceCache.company_id == self.company_id,
                EntTelligencePriceCache.play_date >= cutoff_date,
                EntTelligencePriceCache.price > 0
            )
        )

        # Apply circuit filter if specified
        if circuit_filter:
            query = query.filter(
                EntTelligencePriceCache.circuit_name.in_(circuit_filter)
            )

        # Group data by (theater, ticket_type, format, circuit, day_type, day_of_week, daypart)
        from collections import defaultdict
        grouped_data = defaultdict(list)
        skipped_unparseable = 0
        skipped_event_cinema = 0

        for row in query.all():
            theater_name, ticket_type, format_type, circuit_name, play_date, showtime, price, film_title = row

            # Skip premium formats if requested
            if exclude_premium and self.is_premium_format(format_type):
                continue

            # Skip event cinema if requested
            if exclude_event_cinema and self.is_event_cinema(film_title):
                skipped_event_cinema += 1
                continue

            if not price or float(price) <= 0:
                continue

            # Determine day_of_week (0=Monday, 6=Sunday) if splitting by day of week
            day_of_week_val = play_date.weekday() if split_by_day_of_week else None

            # Determine day type from play_date (only if splitting by day_type AND not by day_of_week)
            # If splitting by day_of_week, day_type is redundant
            day_type = None
            if split_by_day_type and not split_by_day_of_week:
                day_type = self._get_day_type(play_date)

            # Determine daypart from showtime (if splitting)
            daypart = None
            if split_by_daypart:
                daypart = self._get_daypart(showtime)
                if daypart is None:
                    # Skip records where we can't parse the showtime
                    skipped_unparseable += 1
                    continue

            key = (theater_name, ticket_type, format_type, circuit_name, day_type, day_of_week_val, daypart)
            grouped_data[key].append(float(price))

        if skipped_unparseable > 0:
            logger.warning(f"Skipped {skipped_unparseable} records with unparseable showtimes")

        if skipped_event_cinema > 0:
            logger.info(f"Excluded {skipped_event_cinema} event cinema price records from baseline calculation")

        split_desc = []
        if split_by_day_of_week:
            split_desc.append("day_of_week")
        elif split_by_day_type:
            split_desc.append("day_type")
        if split_by_daypart:
            split_desc.append("daypart")
        logger.info(f"Grouped into {len(grouped_data)} combinations (splitting by: {', '.join(split_desc) if split_desc else 'none'})")

        # Process each group
        for (theater_name, ticket_type, format_type, circuit_name, day_type, day_of_week_val, daypart), prices in grouped_data.items():
            if len(prices) < min_samples:
                continue

            prices_sorted = sorted(prices)
            baseline_price = self._percentile(prices_sorted, percentile)
            min_p = min(prices)
            max_p = max(prices)
            avg_p = sum(prices) / len(prices)
            price_range = max_p - min_p
            volatility = (price_range / avg_p * 100) if avg_p else 0

            discovered.append({
                'theater_name': theater_name,
                'ticket_type': ticket_type,
                'format': format_type,
                'circuit_name': circuit_name,
                'day_type': day_type,
                'day_of_week': day_of_week_val,
                'daypart': daypart,
                'baseline_price': round(baseline_price, 2),
                'sample_count': len(prices),
                'min_price': round(min_p, 2),
                'max_price': round(max_p, 2),
                'avg_price': round(avg_p, 2),
                'volatility_percent': round(volatility, 1),
                'is_premium': self.is_premium_format(format_type),
                'source': 'enttelligence'
            })

        return discovered

    def _percentile(self, data: List[float], p: int) -> float:
        """Calculate the p-th percentile of data."""
        if not data:
            return 0.0
        k = (len(data) - 1) * (p / 100)
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        return data[f] + (data[c] - data[f]) * (k - f)

    def _analyze_daypart_pricing(
        self,
        prices_by_bucket: Dict[str, List[float]],
        percentile: int = 25
    ) -> Dict[str, float]:
        """
        Analyze prices across time buckets and determine if dayparts are meaningful.

        If prices differ by more than DAYPART_PRICE_THRESHOLD across buckets,
        return separate daypart baselines. Otherwise, return a single 'Standard' baseline.

        Args:
            prices_by_bucket: Dict mapping time bucket ('early', 'mid', 'late') to price list
            percentile: Which percentile to use for baseline calculation

        Returns:
            Dict mapping daypart name to baseline price.
            Returns {'Standard': price} if all buckets have similar pricing.
        """
        # Calculate baseline for each bucket that has enough samples
        bucket_baselines = {}
        for bucket, prices in prices_by_bucket.items():
            if len(prices) >= 3:  # Need at least a few samples
                sorted_prices = sorted(prices)
                bucket_baselines[bucket] = self._percentile(sorted_prices, percentile)

        if not bucket_baselines:
            return {}

        # If only one bucket has data, return it as Standard
        if len(bucket_baselines) == 1:
            return {'Standard': list(bucket_baselines.values())[0]}

        # Check if prices differ meaningfully across buckets
        baseline_prices = list(bucket_baselines.values())
        price_range = max(baseline_prices) - min(baseline_prices)

        if price_range < DAYPART_PRICE_THRESHOLD:
            # Prices are similar - use single Standard baseline
            all_prices = []
            for prices in prices_by_bucket.values():
                all_prices.extend(prices)
            return {'Standard': self._percentile(sorted(all_prices), percentile)}

        # Prices differ - map buckets to proper daypart names
        result = {}
        bucket_to_daypart = {
            'early': 'Matinee',
            'mid': 'Prime',      # Combine Twilight+Prime into just 'Prime' for simplicity
            'late': 'Late Night'
        }
        for bucket, baseline in bucket_baselines.items():
            daypart_name = bucket_to_daypart.get(bucket, bucket)
            result[daypart_name] = baseline

        return result

    def discover_baselines_price_based(
        self,
        min_samples: int = 5,
        lookback_days: int = 30,
        percentile: int = 25,
        exclude_premium: bool = True,
        exclude_event_cinema: bool = True,
        circuit_filter: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Discover baselines using price-based daypart detection.

        Instead of blindly splitting by time, this method:
        1. Groups prices by theater/ticket/format
        2. Analyzes if prices differ across time periods
        3. Only creates separate dayparts if there's a meaningful price difference

        This produces cleaner baselines - e.g., if a theater charges the same
        price at 7pm and 11pm, they get a single 'Standard' daypart instead of
        separate 'Prime' and 'Late Night' entries.

        Returns:
            List of discovered baseline configurations
        """
        from collections import defaultdict
        discovered = []
        cutoff_date = date.today() - timedelta(days=lookback_days)

        with get_session() as session:
            # Get all records with showtime for time bucket analysis
            query = session.query(
                EntTelligencePriceCache.theater_name,
                EntTelligencePriceCache.ticket_type,
                EntTelligencePriceCache.format,
                EntTelligencePriceCache.circuit_name,
                EntTelligencePriceCache.showtime,
                EntTelligencePriceCache.price,
                EntTelligencePriceCache.film_title
            ).filter(
                and_(
                    EntTelligencePriceCache.company_id == self.company_id,
                    EntTelligencePriceCache.play_date >= cutoff_date,
                    EntTelligencePriceCache.price > 0
                )
            )

            if circuit_filter:
                query = query.filter(
                    EntTelligencePriceCache.circuit_name.in_(circuit_filter)
                )

            # Group by theater/ticket/format, then by time bucket
            # Structure: {(theater, ticket, format, circuit): {'early': [prices], 'mid': [...], 'late': [...]}}
            grouped_data = defaultdict(lambda: defaultdict(list))
            skipped_event_cinema = 0

            for row in query.all():
                theater_name, ticket_type, format_type, circuit_name, showtime, price, film_title = row

                if exclude_premium and self.is_premium_format(format_type):
                    continue

                if exclude_event_cinema and self.is_event_cinema(film_title):
                    skipped_event_cinema += 1
                    continue

                if not price or float(price) <= 0:
                    continue

                # Get time bucket for this showtime
                bucket = self._get_time_bucket(showtime)
                if bucket is None:
                    continue

                key = (theater_name, ticket_type, format_type, circuit_name)
                grouped_data[key][bucket].append(float(price))

            if skipped_event_cinema > 0:
                logger.info(f"Excluded {skipped_event_cinema} event cinema records")

            logger.info(f"Found {len(grouped_data)} theater/ticket/format combinations for price-based analysis")

            # Analyze each group and determine appropriate dayparts
            for (theater_name, ticket_type, format_type, circuit_name), prices_by_bucket in grouped_data.items():
                total_samples = sum(len(prices) for prices in prices_by_bucket.values())
                if total_samples < min_samples:
                    continue

                # Determine dayparts based on price differences
                daypart_baselines = self._analyze_daypart_pricing(prices_by_bucket, percentile)

                # Collect all prices for volatility calculation
                all_prices = []
                for prices in prices_by_bucket.values():
                    all_prices.extend(prices)

                min_p = min(all_prices) if all_prices else 0
                max_p = max(all_prices) if all_prices else 0
                avg_p = sum(all_prices) / len(all_prices) if all_prices else 0
                volatility = ((max_p - min_p) / avg_p * 100) if avg_p else 0

                for daypart, baseline_price in daypart_baselines.items():
                    discovered.append({
                        'theater_name': theater_name,
                        'ticket_type': ticket_type,
                        'format': format_type,
                        'circuit_name': circuit_name,
                        'day_type': None,
                        'day_of_week': None,
                        'daypart': daypart,
                        'baseline_price': round(baseline_price, 2),
                        'sample_count': total_samples,
                        'min_price': round(min_p, 2),
                        'max_price': round(max_p, 2),
                        'avg_price': round(avg_p, 2),
                        'volatility_percent': round(volatility, 1),
                        'is_premium': self.is_premium_format(format_type),
                        'source': 'enttelligence'
                    })

        logger.info(f"Discovered {len(discovered)} price-based baselines")
        return discovered

    def save_discovered_baselines(
        self,
        baselines: List[Dict],
        effective_from: date = None,
        overwrite: bool = False
    ) -> int:
        """
        Save discovered baselines to the database.

        Args:
            baselines: List of baseline dicts from discover_baselines()
            effective_from: Start date for baselines (default: today)
            overwrite: Whether to replace existing baselines

        Returns:
            Number of baselines saved
        """
        if effective_from is None:
            effective_from = date.today()

        saved_count = 0

        with get_session() as session:
            for baseline_data in baselines:
                # Skip premium formats
                if baseline_data.get('is_premium'):
                    continue

                day_type = baseline_data.get('day_type')
                day_of_week = baseline_data.get('day_of_week')
                daypart = baseline_data.get('daypart')

                # Build filter for existing baseline check
                # Include day_type, day_of_week, and daypart in the uniqueness check
                existing_filter = and_(
                    PriceBaseline.company_id == self.company_id,
                    PriceBaseline.theater_name == baseline_data['theater_name'],
                    PriceBaseline.ticket_type == baseline_data['ticket_type'],
                    PriceBaseline.format == baseline_data['format'],
                    PriceBaseline.effective_to.is_(None)  # Active baseline
                )

                # Add day_type to filter (handle NULL case)
                if day_type:
                    existing_filter = and_(existing_filter, PriceBaseline.day_type == day_type)
                else:
                    existing_filter = and_(existing_filter, PriceBaseline.day_type.is_(None))

                # Add day_of_week to filter (handle NULL case)
                if day_of_week is not None:
                    existing_filter = and_(existing_filter, PriceBaseline.day_of_week == day_of_week)
                else:
                    existing_filter = and_(existing_filter, PriceBaseline.day_of_week.is_(None))

                # Add daypart to filter (handle NULL case)
                if daypart:
                    existing_filter = and_(existing_filter, PriceBaseline.daypart == daypart)
                else:
                    existing_filter = and_(existing_filter, PriceBaseline.daypart.is_(None))

                existing = session.query(PriceBaseline).filter(existing_filter).first()

                if existing:
                    if overwrite:
                        # End the existing baseline
                        existing.effective_to = effective_from - timedelta(days=1)
                    else:
                        # Skip - baseline already exists
                        continue

                # Create new baseline
                new_baseline = PriceBaseline(
                    company_id=self.company_id,
                    theater_name=baseline_data['theater_name'],
                    ticket_type=baseline_data['ticket_type'],
                    format=baseline_data['format'],
                    day_type=day_type,
                    day_of_week=day_of_week,
                    daypart=daypart,
                    baseline_price=Decimal(str(baseline_data['baseline_price'])),
                    effective_from=effective_from,
                    effective_to=None  # Active
                )
                session.add(new_baseline)
                saved_count += 1

            session.flush()

        logger.info(f"Saved {saved_count} EntTelligence baselines for company {self.company_id}")
        return saved_count

    def analyze_event_cinema(
        self,
        lookback_days: int = 30,
        circuit_filter: Optional[List[str]] = None
    ) -> Dict:
        """
        Analyze event cinema pricing separately from regular films.

        Event cinema (Fathom, Met Opera, concerts, etc.) typically has:
        - Distributor-set pricing (same across theaters in a region)
        - Higher than regular ticket prices
        - Limited distribution (fewer circuits/theaters)

        Returns analysis including:
        - List of detected event cinema films with pricing
        - Price consistency across theaters/circuits
        - Distribution pattern (which circuits show it)
        """
        cutoff_date = date.today() - timedelta(days=lookback_days)

        analysis = {
            'event_films': [],
            'summary': {
                'total_event_cinema_records': 0,
                'unique_films': 0,
                'circuits_with_event_cinema': [],
                'avg_event_price': None,
                'avg_regular_price': None,
                'price_premium_percent': None,
            },
            'price_variations': [],  # Films with price differences across theaters
        }

        with get_session() as session:
            # Query all prices, identify event cinema by title
            query = session.query(
                EntTelligencePriceCache.film_title,
                EntTelligencePriceCache.theater_name,
                EntTelligencePriceCache.circuit_name,
                EntTelligencePriceCache.ticket_type,
                EntTelligencePriceCache.format,
                EntTelligencePriceCache.price,
                EntTelligencePriceCache.play_date
            ).filter(
                and_(
                    EntTelligencePriceCache.company_id == self.company_id,
                    EntTelligencePriceCache.play_date >= cutoff_date,
                    EntTelligencePriceCache.price > 0
                )
            )

            if circuit_filter:
                query = query.filter(
                    EntTelligencePriceCache.circuit_name.in_(circuit_filter)
                )

            from collections import defaultdict

            # Separate event cinema from regular films
            event_cinema_data = defaultdict(lambda: {
                'prices': [],
                'theaters': set(),
                'circuits': set(),
                'ticket_types': set(),
                'formats': set(),
                'play_dates': set()
            })
            regular_prices = []
            event_circuits = set()

            for row in query.all():
                film_title, theater_name, circuit_name, ticket_type, format_type, price, play_date = row

                if self.is_event_cinema(film_title):
                    data = event_cinema_data[film_title]
                    data['prices'].append(float(price))
                    data['theaters'].add(theater_name)
                    if circuit_name:
                        data['circuits'].add(circuit_name)
                        event_circuits.add(circuit_name)
                    data['ticket_types'].add(ticket_type or 'Unknown')
                    data['formats'].add(format_type or '2D')
                    data['play_dates'].add(str(play_date))
                else:
                    regular_prices.append(float(price))

            # Build event films list with pricing analysis
            total_event_records = 0
            for film_title, data in event_cinema_data.items():
                prices = data['prices']
                total_event_records += len(prices)

                if not prices:
                    continue

                min_p = min(prices)
                max_p = max(prices)
                avg_p = sum(prices) / len(prices)
                price_variation = max_p - min_p

                film_info = {
                    'film_title': film_title,
                    'record_count': len(prices),
                    'theater_count': len(data['theaters']),
                    'circuit_count': len(data['circuits']),
                    'circuits': sorted(data['circuits']),
                    'ticket_types': sorted(data['ticket_types']),
                    'formats': sorted(data['formats']),
                    'min_price': round(min_p, 2),
                    'max_price': round(max_p, 2),
                    'avg_price': round(avg_p, 2),
                    'price_variation': round(price_variation, 2),
                    'price_consistent': price_variation < 1.0,  # Less than $1 variation
                    'play_dates': sorted(data['play_dates'])[:5],  # First 5 dates
                }

                analysis['event_films'].append(film_info)

                # Track significant price variations
                if price_variation >= 1.0:
                    analysis['price_variations'].append({
                        'film_title': film_title,
                        'min_price': round(min_p, 2),
                        'max_price': round(max_p, 2),
                        'variation': round(price_variation, 2),
                        'theaters_involved': len(data['theaters']),
                        'circuits_involved': list(data['circuits'])
                    })

            # Sort event films by record count
            analysis['event_films'].sort(key=lambda x: x['record_count'], reverse=True)
            analysis['price_variations'].sort(key=lambda x: x['variation'], reverse=True)

            # Calculate summary stats
            avg_event = sum(
                sum(d['prices']) for d in event_cinema_data.values()
            ) / total_event_records if total_event_records > 0 else None

            avg_regular = sum(regular_prices) / len(regular_prices) if regular_prices else None

            analysis['summary'] = {
                'total_event_cinema_records': total_event_records,
                'total_regular_records': len(regular_prices),
                'unique_films': len(event_cinema_data),
                'circuits_with_event_cinema': sorted(event_circuits),
                'avg_event_price': round(avg_event, 2) if avg_event else None,
                'avg_regular_price': round(avg_regular, 2) if avg_regular else None,
                'price_premium_percent': round(
                    (avg_event - avg_regular) / avg_regular * 100, 1
                ) if avg_event and avg_regular else None,
            }

        return analysis

    def analyze_by_circuit(self, lookback_days: int = 30) -> Dict:
        """
        Analyze price patterns grouped by circuit.

        Returns analysis including:
        - Circuit-level pricing averages
        - Format distribution per circuit
        - Price ranges by circuit
        """
        cutoff_date = date.today() - timedelta(days=lookback_days)

        analysis = {
            'circuits': {},
            'format_breakdown': {},
            'overall_stats': {},
            'data_coverage': {}
        }

        with get_session() as session:
            # Circuit-level stats
            circuit_query = session.query(
                EntTelligencePriceCache.circuit_name,
                func.count(EntTelligencePriceCache.cache_id).label('record_count'),
                func.count(func.distinct(EntTelligencePriceCache.theater_name)).label('theater_count'),
                func.avg(EntTelligencePriceCache.price).label('avg_price'),
                func.min(EntTelligencePriceCache.price).label('min_price'),
                func.max(EntTelligencePriceCache.price).label('max_price')
            ).filter(
                and_(
                    EntTelligencePriceCache.company_id == self.company_id,
                    EntTelligencePriceCache.play_date >= cutoff_date,
                    EntTelligencePriceCache.price > 0
                )
            ).group_by(
                EntTelligencePriceCache.circuit_name
            ).order_by(
                func.count(EntTelligencePriceCache.cache_id).desc()
            )

            for row in circuit_query.all():
                circuit, count, theaters, avg_p, min_p, max_p = row
                if circuit:
                    analysis['circuits'][circuit] = {
                        'record_count': count,
                        'theater_count': theaters,
                        'avg_price': round(float(avg_p), 2) if avg_p else None,
                        'min_price': float(min_p) if min_p else None,
                        'max_price': float(max_p) if max_p else None,
                        'price_range': round(float(max_p) - float(min_p), 2) if max_p and min_p else None
                    }

            # Format breakdown
            format_query = session.query(
                EntTelligencePriceCache.format,
                func.count(EntTelligencePriceCache.cache_id).label('count'),
                func.avg(EntTelligencePriceCache.price).label('avg_price')
            ).filter(
                and_(
                    EntTelligencePriceCache.company_id == self.company_id,
                    EntTelligencePriceCache.play_date >= cutoff_date,
                    EntTelligencePriceCache.price > 0
                )
            ).group_by(
                EntTelligencePriceCache.format
            ).order_by(
                func.count(EntTelligencePriceCache.cache_id).desc()
            )

            for fmt, count, avg_p in format_query.all():
                format_name = fmt or '2D/Standard'
                analysis['format_breakdown'][format_name] = {
                    'count': count,
                    'avg_price': round(float(avg_p), 2) if avg_p else None,
                    'is_premium': self.is_premium_format(fmt)
                }

            # Overall stats
            overall = session.query(
                func.count(EntTelligencePriceCache.cache_id).label('total_records'),
                func.count(func.distinct(EntTelligencePriceCache.theater_name)).label('total_theaters'),
                func.count(func.distinct(EntTelligencePriceCache.circuit_name)).label('total_circuits'),
                func.min(EntTelligencePriceCache.play_date).label('min_date'),
                func.max(EntTelligencePriceCache.play_date).label('max_date'),
                func.avg(EntTelligencePriceCache.price).label('overall_avg_price')
            ).filter(
                and_(
                    EntTelligencePriceCache.company_id == self.company_id,
                    EntTelligencePriceCache.play_date >= cutoff_date,
                    EntTelligencePriceCache.price > 0
                )
            ).first()

            if overall:
                analysis['overall_stats'] = {
                    'total_records': overall.total_records,
                    'total_theaters': overall.total_theaters,
                    'total_circuits': overall.total_circuits,
                    'date_range': {
                        'min': str(overall.min_date) if overall.min_date else None,
                        'max': str(overall.max_date) if overall.max_date else None
                    },
                    'overall_avg_price': round(float(overall.overall_avg_price), 2) if overall.overall_avg_price else None
                }

            # Data coverage (days with data)
            coverage_query = session.query(
                EntTelligencePriceCache.play_date,
                func.count(EntTelligencePriceCache.cache_id).label('count')
            ).filter(
                and_(
                    EntTelligencePriceCache.company_id == self.company_id,
                    EntTelligencePriceCache.play_date >= cutoff_date
                )
            ).group_by(
                EntTelligencePriceCache.play_date
            ).order_by(
                EntTelligencePriceCache.play_date
            )

            analysis['data_coverage'] = {
                str(row.play_date): row.count for row in coverage_query.all()
            }

        return analysis

    def get_circuit_baselines(
        self,
        circuit_name: str,
        min_samples: int = 3,
        lookback_days: int = 30
    ) -> List[Dict]:
        """
        Get baselines for a specific circuit.

        Useful for comparing a specific theater chain's pricing patterns.
        """
        return self.discover_baselines(
            min_samples=min_samples,
            lookback_days=lookback_days,
            circuit_filter=[circuit_name]
        )


# Convenience functions for direct use

def discover_enttelligence_baselines(
    company_id: int,
    min_samples: int = 5,
    lookback_days: int = 30,
    save: bool = False,
    circuit_filter: Optional[List[str]] = None,
    split_by_day_type: bool = False,
    split_by_daypart: bool = False,
    split_by_day_of_week: bool = False,
    price_based_dayparts: bool = False
) -> List[Dict]:
    """
    Convenience function to discover baselines from EntTelligence data.

    Args:
        company_id: Company ID
        min_samples: Minimum samples required per combination
        lookback_days: Days of history to analyze
        save: Whether to save to database
        circuit_filter: Optional list of circuits to include
        split_by_day_type: Whether to split baselines by weekday/weekend
        split_by_daypart: Whether to split baselines by matinee/evening/late
        split_by_day_of_week: Whether to split baselines by each day (Mon-Sun)
                              Note: If True, day_type is ignored
        price_based_dayparts: Use price-based daypart detection (recommended).
                              Only creates separate dayparts if prices actually
                              differ across time periods. Ignores other split flags.

    Returns:
        List of discovered baselines
    """
    service = EntTelligenceBaselineDiscoveryService(company_id)

    if price_based_dayparts:
        # Use smart price-based daypart detection
        baselines = service.discover_baselines_price_based(
            min_samples=min_samples,
            lookback_days=lookback_days,
            circuit_filter=circuit_filter
        )
    else:
        # Use legacy time-based splitting
        baselines = service.discover_baselines(
            min_samples=min_samples,
            lookback_days=lookback_days,
            circuit_filter=circuit_filter,
            split_by_day_type=split_by_day_type,
            split_by_daypart=split_by_daypart,
            split_by_day_of_week=split_by_day_of_week
        )

    if save and baselines:
        service.save_discovered_baselines(baselines)

    return baselines


def analyze_enttelligence_prices(company_id: int, lookback_days: int = 30) -> Dict:
    """
    Analyze EntTelligence price patterns.

    Args:
        company_id: Company ID
        lookback_days: Days to analyze

    Returns:
        Analysis dict with circuit breakdowns, format comparisons, etc.
    """
    service = EntTelligenceBaselineDiscoveryService(company_id)
    return service.analyze_by_circuit(lookback_days=lookback_days)


def refresh_enttelligence_baselines(company_id: int) -> int:
    """
    Refresh baselines with latest EntTelligence data.

    Args:
        company_id: Company ID

    Returns:
        Number of baselines updated/added
    """
    service = EntTelligenceBaselineDiscoveryService(company_id)
    baselines = service.discover_baselines(min_samples=5, lookback_days=30)
    return service.save_discovered_baselines(baselines, overwrite=True)


def analyze_event_cinema(
    company_id: int,
    lookback_days: int = 30,
    circuit_filter: Optional[List[str]] = None
) -> Dict:
    """
    Analyze event cinema pricing (Fathom, Met Opera, concerts, etc.).

    Event cinema is excluded from baseline calculations but tracked separately
    to document pricing patterns and variations.

    Args:
        company_id: Company ID
        lookback_days: Days to analyze
        circuit_filter: Optional list of circuits to include

    Returns:
        Analysis dict with event films, price variations, and summary stats
    """
    service = EntTelligenceBaselineDiscoveryService(company_id)
    return service.analyze_event_cinema(
        lookback_days=lookback_days,
        circuit_filter=circuit_filter
    )


def get_event_cinema_keywords() -> List[str]:
    """Get the list of keywords used to identify event cinema."""
    return EVENT_CINEMA_KEYWORDS.copy()
