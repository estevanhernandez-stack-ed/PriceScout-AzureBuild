"""
Fandango Baseline Discovery Service for PriceScout

Discovers and maintains price baselines from Fandango scraped data.
Uses the actual daypart values from Fandango (which reflect each theater's
pricing structure) rather than deriving daypart from showtime.

Baselines are per-theater with the following dimensions:
- theater_name: The specific theater
- ticket_type: Adult, Child, Senior, etc.
- format: 2D, IMAX, Dolby, etc.
- daypart: Matinee, Prime, Twilight, Late Night (from Fandango)
- day_of_week: 0=Monday through 6=Sunday (for discount day detection)

Usage:
    from app.fandango_baseline_discovery import (
        discover_fandango_baselines,
        analyze_theater_pricing,
        detect_discount_days
    )

    # Discover baselines from Fandango scraped data
    baselines = discover_fandango_baselines(company_id=1)

    # Analyze a specific theater's pricing structure
    analysis = analyze_theater_pricing(company_id=1, theater_name="AMC Empire 25")

    # Detect potential discount days for a theater
    discount_days = detect_discount_days(company_id=1, theater_name="AMC Empire 25")
"""

from datetime import datetime, date, timedelta, UTC
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import statistics
import logging

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.db_session import get_session
from app.db_models import Price, Showing, PriceBaseline

logger = logging.getLogger(__name__)

# Day names for display
DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
DAY_ABBREV = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

# Premium formats that have inherently higher prices
PREMIUM_FORMATS = {
    'IMAX', 'IMAX 3D', 'IMAX with Laser', 'IMAX HFR 3D',
    'Dolby Cinema', 'Dolby Atmos', 'Dolby Vision',
    '3D', 'RealD 3D', 'Digital 3D',
    'PLF', 'Premium Large Format', 'XD', 'RPX', 'BigD',
    '4DX', 'D-BOX', 'ScreenX', 'MX4D',
    'Laser IMAX', 'GTX', 'UltraAVX',
}

# Event cinema keywords (prices set by distributor)
EVENT_CINEMA_KEYWORDS = [
    'Fathom', 'Trafalgar', 'Met Opera', 'NT Live', 'National Theatre',
    'Bolshoi', 'Royal Opera', 'Concert', 'Live Event', 'TCM',
    'Anniversary', 'Encore', 'Special Presentation', 'Fan Event',
    'Marathon', 'Double Feature', 'WWE', 'UFC', 'Crunchyroll',
]


class FandangoBaselineDiscoveryService:
    """Service for discovering price baselines from Fandango scraped data."""

    def __init__(self, company_id: int):
        self.company_id = company_id

    def is_premium_format(self, format_name: str) -> bool:
        """Check if format is a known premium format."""
        if not format_name:
            return False
        format_upper = format_name.upper()
        return any(pf.upper() in format_upper for pf in PREMIUM_FORMATS)

    def is_event_cinema(self, film_title: str) -> bool:
        """Check if film appears to be event cinema based on title."""
        if not film_title:
            return False
        title_upper = film_title.upper()
        return any(kw.upper() in title_upper for kw in EVENT_CINEMA_KEYWORDS)

    def discover_baselines(
        self,
        min_samples: int = 3,
        lookback_days: int = 90,
        percentile: int = 25,
        exclude_premium: bool = False,
        exclude_event_cinema: bool = True,
        theater_filter: Optional[List[str]] = None,
        split_by_day_of_week: bool = True,
    ) -> List[Dict]:
        """
        Discover baselines from Fandango scraped price data.

        Args:
            min_samples: Minimum number of price samples required
            lookback_days: How many days of history to analyze
            percentile: Which percentile to use as baseline (lower = more conservative)
            exclude_premium: Whether to exclude premium formats
            exclude_event_cinema: Whether to exclude event cinema titles
            theater_filter: Optional list of theater names to include
            split_by_day_of_week: Whether to create separate baselines for each day

        Returns:
            List of discovered baseline configurations
        """
        discovered = []
        cutoff_date = datetime.now(UTC) - timedelta(days=lookback_days)

        with get_session() as session:
            # Query all prices with their showing info
            query = session.query(
                Showing.theater_name,
                Price.ticket_type,
                Showing.format,
                Showing.daypart,
                Showing.play_date,
                Showing.film_title,
                Price.price
            ).join(
                Showing, Price.showing_id == Showing.showing_id
            ).filter(
                and_(
                    Price.company_id == self.company_id,
                    Price.created_at >= cutoff_date,
                    Price.price > 0,
                    Showing.daypart.isnot(None),  # Must have daypart
                    Showing.daypart != ''
                )
            )

            # Apply theater filter if specified
            if theater_filter:
                query = query.filter(Showing.theater_name.in_(theater_filter))

            # Group data by dimensions
            # Key: (theater, ticket_type, format, daypart, day_of_week or None)
            grouped_data = defaultdict(list)
            skipped_event = 0
            skipped_premium = 0

            for row in query.all():
                theater_name, ticket_type, format_type, daypart, play_date, film_title, price = row

                # Skip premium formats if requested
                if exclude_premium and self.is_premium_format(format_type):
                    skipped_premium += 1
                    continue

                # Skip event cinema if requested
                if exclude_event_cinema and self.is_event_cinema(film_title):
                    skipped_event += 1
                    continue

                if not price or float(price) <= 0:
                    continue

                # Normalize daypart
                daypart_normalized = (daypart or '').strip()
                if not daypart_normalized:
                    continue

                # Get day of week if splitting
                day_of_week = None
                if split_by_day_of_week and play_date:
                    day_of_week = play_date.weekday()

                key = (theater_name, ticket_type, format_type or '2D', daypart_normalized, day_of_week)
                grouped_data[key].append(float(price))

            if skipped_event > 0:
                logger.info(f"Excluded {skipped_event} event cinema prices")
            if skipped_premium > 0:
                logger.info(f"Excluded {skipped_premium} premium format prices")

            logger.info(f"Found {len(grouped_data)} unique combinations")

            # Calculate baselines for each group
            for (theater_name, ticket_type, format_type, daypart, day_of_week), prices in grouped_data.items():
                if len(prices) < min_samples:
                    continue

                prices_sorted = sorted(prices)
                baseline_price = self._percentile(prices_sorted, percentile)
                min_p = min(prices)
                max_p = max(prices)
                avg_p = sum(prices) / len(prices)
                price_range = max_p - min_p
                volatility = (price_range / avg_p * 100) if avg_p else 0

                # Determine day_type from day_of_week
                day_type = None
                if day_of_week is not None:
                    day_type = 'weekend' if day_of_week >= 4 else 'weekday'

                discovered.append({
                    'theater_name': theater_name,
                    'ticket_type': ticket_type,
                    'format': format_type,
                    'daypart': daypart,
                    'day_of_week': day_of_week,
                    'day_of_week_name': DAY_NAMES[day_of_week] if day_of_week is not None else None,
                    'day_type': day_type,
                    'baseline_price': round(baseline_price, 2),
                    'sample_count': len(prices),
                    'min_price': round(min_p, 2),
                    'max_price': round(max_p, 2),
                    'avg_price': round(avg_p, 2),
                    'volatility_percent': round(volatility, 1),
                    'is_premium': self.is_premium_format(format_type),
                    'source': 'fandango'
                })

        logger.info(f"Discovered {len(discovered)} baselines from Fandango data")
        return discovered

    def _percentile(self, data: List[float], p: int) -> float:
        """Calculate the p-th percentile of data."""
        if not data:
            return 0.0
        k = (len(data) - 1) * (p / 100)
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        return data[f] + (data[c] - data[f]) * (k - f)

    def analyze_theater_pricing(
        self,
        theater_name: str,
        lookback_days: int = 90
    ) -> Dict:
        """
        Analyze a specific theater's pricing structure.

        Returns:
            Dict with pricing analysis including:
            - dayparts: List of dayparts with their price ranges
            - day_of_week_patterns: Pricing by day of week
            - potential_discount_days: Days with significantly lower prices
            - ticket_type_breakdown: Pricing by ticket type
        """
        cutoff_date = datetime.now(UTC) - timedelta(days=lookback_days)

        analysis = {
            'theater_name': theater_name,
            'dayparts': {},
            'day_of_week_patterns': {},
            'potential_discount_days': [],
            'ticket_type_breakdown': {},
            'format_breakdown': {},
        }

        with get_session() as session:
            # Get all prices for this theater
            query = session.query(
                Price.ticket_type,
                Showing.format,
                Showing.daypart,
                Showing.play_date,
                Price.price
            ).join(
                Showing, Price.showing_id == Showing.showing_id
            ).filter(
                and_(
                    Price.company_id == self.company_id,
                    Showing.theater_name == theater_name,
                    Price.created_at >= cutoff_date,
                    Price.price > 0
                )
            )

            # Collect data
            daypart_prices = defaultdict(list)
            dow_prices = defaultdict(list)
            ticket_prices = defaultdict(list)
            format_prices = defaultdict(list)
            dow_daypart_prices = defaultdict(lambda: defaultdict(list))

            for ticket_type, format_type, daypart, play_date, price in query.all():
                price_val = float(price)

                if daypart:
                    daypart_prices[daypart].append(price_val)

                if play_date:
                    dow = play_date.weekday()
                    dow_prices[dow].append(price_val)
                    if daypart:
                        dow_daypart_prices[dow][daypart].append(price_val)

                if ticket_type:
                    ticket_prices[ticket_type].append(price_val)

                format_key = format_type or '2D'
                format_prices[format_key].append(price_val)

            # Analyze dayparts
            for daypart, prices in daypart_prices.items():
                if prices:
                    analysis['dayparts'][daypart] = {
                        'min': round(min(prices), 2),
                        'max': round(max(prices), 2),
                        'avg': round(sum(prices) / len(prices), 2),
                        'count': len(prices)
                    }

            # Analyze day of week patterns
            for dow, prices in dow_prices.items():
                if prices:
                    analysis['day_of_week_patterns'][DAY_NAMES[dow]] = {
                        'day_of_week': dow,
                        'min': round(min(prices), 2),
                        'max': round(max(prices), 2),
                        'avg': round(sum(prices) / len(prices), 2),
                        'count': len(prices)
                    }

            # Detect potential discount days
            # Compare each day's average to the overall average
            if dow_prices:
                all_prices = [p for prices in dow_prices.values() for p in prices]
                overall_avg = sum(all_prices) / len(all_prices) if all_prices else 0

                for dow, prices in dow_prices.items():
                    day_avg = sum(prices) / len(prices) if prices else 0
                    if overall_avg > 0:
                        discount_percent = ((overall_avg - day_avg) / overall_avg) * 100
                        # If day is 15%+ cheaper than average, flag as potential discount day
                        if discount_percent >= 15:
                            analysis['potential_discount_days'].append({
                                'day_of_week': dow,
                                'day_name': DAY_NAMES[dow],
                                'avg_price': round(day_avg, 2),
                                'overall_avg': round(overall_avg, 2),
                                'discount_percent': round(discount_percent, 1)
                            })

            # Analyze ticket types
            for ticket_type, prices in ticket_prices.items():
                if prices:
                    analysis['ticket_type_breakdown'][ticket_type] = {
                        'min': round(min(prices), 2),
                        'max': round(max(prices), 2),
                        'avg': round(sum(prices) / len(prices), 2),
                        'count': len(prices)
                    }

            # Analyze formats
            for format_type, prices in format_prices.items():
                if prices:
                    analysis['format_breakdown'][format_type] = {
                        'min': round(min(prices), 2),
                        'max': round(max(prices), 2),
                        'avg': round(sum(prices) / len(prices), 2),
                        'count': len(prices),
                        'is_premium': self.is_premium_format(format_type)
                    }

        return analysis

    def detect_discount_days(
        self,
        theater_name: Optional[str] = None,
        threshold_percent: float = 15.0,
        min_samples: int = 5
    ) -> List[Dict]:
        """
        Detect potential discount days across theaters.

        Args:
            theater_name: Optional specific theater to analyze
            threshold_percent: Minimum discount percentage to flag (default 15%)
            min_samples: Minimum samples required per day

        Returns:
            List of detected discount day patterns
        """
        detected = []

        with get_session() as session:
            # Build query
            query = session.query(
                Showing.theater_name,
                Price.ticket_type,
                Showing.format,
                Showing.daypart,
                Showing.play_date,
                Price.price
            ).join(
                Showing, Price.showing_id == Showing.showing_id
            ).filter(
                and_(
                    Price.company_id == self.company_id,
                    Price.price > 0
                )
            )

            if theater_name:
                query = query.filter(Showing.theater_name == theater_name)

            # Group by theater -> day_of_week -> daypart -> ticket_type
            theater_data = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))

            for t_name, ticket_type, format_type, daypart, play_date, price in query.all():
                if not play_date or not daypart:
                    continue
                dow = play_date.weekday()
                theater_data[t_name][dow][daypart][ticket_type].append(float(price))

            # Analyze each theater
            for t_name, dow_data in theater_data.items():
                # For each daypart + ticket_type, compare days
                daypart_ticket_combos = defaultdict(lambda: defaultdict(list))

                for dow, daypart_data in dow_data.items():
                    for daypart, ticket_data in daypart_data.items():
                        for ticket_type, prices in ticket_data.items():
                            if len(prices) >= min_samples:
                                avg = sum(prices) / len(prices)
                                daypart_ticket_combos[(daypart, ticket_type)][dow] = {
                                    'avg': avg,
                                    'count': len(prices)
                                }

                # Find discount days for each combo
                for (daypart, ticket_type), dow_avgs in daypart_ticket_combos.items():
                    if len(dow_avgs) < 2:
                        continue

                    # Calculate overall average (excluding potential discount days)
                    all_avgs = [d['avg'] for d in dow_avgs.values()]
                    overall_avg = sum(all_avgs) / len(all_avgs)

                    for dow, data in dow_avgs.items():
                        discount_pct = ((overall_avg - data['avg']) / overall_avg) * 100
                        if discount_pct >= threshold_percent:
                            detected.append({
                                'theater_name': t_name,
                                'day_of_week': dow,
                                'day_name': DAY_NAMES[dow],
                                'daypart': daypart,
                                'ticket_type': ticket_type,
                                'avg_price': round(data['avg'], 2),
                                'overall_avg': round(overall_avg, 2),
                                'discount_percent': round(discount_pct, 1),
                                'sample_count': data['count']
                            })

        # Sort by discount percentage descending
        detected.sort(key=lambda x: x['discount_percent'], reverse=True)
        return detected

    def save_baselines(
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
                # Build filter for existing baseline
                filters = [
                    PriceBaseline.company_id == self.company_id,
                    PriceBaseline.theater_name == baseline_data['theater_name'],
                    PriceBaseline.ticket_type == baseline_data['ticket_type'],
                    PriceBaseline.effective_to.is_(None)  # Active baseline
                ]

                # Add optional dimension filters
                if baseline_data.get('format'):
                    filters.append(PriceBaseline.format == baseline_data['format'])
                else:
                    filters.append(PriceBaseline.format.is_(None))

                if baseline_data.get('daypart'):
                    filters.append(PriceBaseline.daypart == baseline_data['daypart'])
                else:
                    filters.append(PriceBaseline.daypart.is_(None))

                if baseline_data.get('day_of_week') is not None:
                    filters.append(PriceBaseline.day_of_week == baseline_data['day_of_week'])
                else:
                    filters.append(PriceBaseline.day_of_week.is_(None))

                # Check for existing
                existing = session.query(PriceBaseline).filter(and_(*filters)).first()

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
                    format=baseline_data.get('format'),
                    daypart=baseline_data.get('daypart'),
                    day_type=baseline_data.get('day_type'),
                    day_of_week=baseline_data.get('day_of_week'),
                    baseline_price=Decimal(str(baseline_data['baseline_price'])),
                    effective_from=effective_from,
                    effective_to=None  # Active
                )
                session.add(new_baseline)
                saved_count += 1

            session.flush()

        logger.info(f"Saved {saved_count} baselines for company {self.company_id}")
        return saved_count


# Convenience functions

def discover_fandango_baselines(
    company_id: int,
    min_samples: int = 3,
    lookback_days: int = 90,
    split_by_day_of_week: bool = True,
    save: bool = False
) -> List[Dict]:
    """
    Discover baselines from Fandango scraped data.

    Args:
        company_id: Company ID
        min_samples: Minimum samples required per combination
        lookback_days: Days of history to analyze
        split_by_day_of_week: Whether to split by day of week
        save: Whether to save to database

    Returns:
        List of discovered baselines
    """
    service = FandangoBaselineDiscoveryService(company_id)
    baselines = service.discover_baselines(
        min_samples=min_samples,
        lookback_days=lookback_days,
        split_by_day_of_week=split_by_day_of_week
    )

    if save and baselines:
        service.save_baselines(baselines)

    return baselines


def analyze_theater_pricing(company_id: int, theater_name: str) -> Dict:
    """
    Analyze a specific theater's pricing structure.

    Args:
        company_id: Company ID
        theater_name: Theater name to analyze

    Returns:
        Pricing analysis dict
    """
    service = FandangoBaselineDiscoveryService(company_id)
    return service.analyze_theater_pricing(theater_name)


def detect_discount_days(
    company_id: int,
    theater_name: Optional[str] = None,
    threshold_percent: float = 15.0
) -> List[Dict]:
    """
    Detect potential discount days.

    Args:
        company_id: Company ID
        theater_name: Optional theater to analyze (None = all)
        threshold_percent: Minimum discount to flag

    Returns:
        List of detected discount day patterns
    """
    service = FandangoBaselineDiscoveryService(company_id)
    return service.detect_discount_days(
        theater_name=theater_name,
        threshold_percent=threshold_percent
    )
