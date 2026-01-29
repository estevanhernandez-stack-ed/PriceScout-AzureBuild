"""
Baseline Discovery Service for PriceScout

Automatically discovers and maintains price baselines from historical scrape data.
Distinguishes between premium formats (expected higher prices) and surge pricing.

Usage:
    from app.baseline_discovery import discover_baselines, refresh_baselines

    # Discover baselines for a company from historical data
    baselines = discover_baselines(company_id=1, min_samples=5)

    # Refresh baselines with latest data
    refresh_baselines(company_id=1)
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

# Premium formats that have inherently higher prices (not surge)
PREMIUM_FORMATS = {
    'IMAX', 'IMAX 3D', 'IMAX with Laser', 'IMAX HFR 3D',
    'Dolby Cinema', 'Dolby Atmos', 'Dolby Vision',
    '3D', 'RealD 3D', 'Digital 3D',
    'PLF', 'Premium Large Format', 'XD', 'RPX', 'BigD',
    '4DX', 'D-BOX', 'ScreenX', 'MX4D',
    'Laser IMAX', 'GTX', 'UltraAVX',
}

# Event cinema / special presentations (expected higher prices)
EVENT_CINEMA_KEYWORDS = [
    'Fathom', 'TCM', 'Met Opera', 'NT Live', 'National Theatre',
    'Bolshoi', 'Royal Opera', 'Concert', 'Live Event',
    'Anniversary', 'Encore', 'Special Presentation',
    'Fan Event', 'Marathon', 'Double Feature',
]


class BaselineDiscoveryService:
    """Service for discovering and managing price baselines from historical data."""

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
        min_samples: int = 5,
        lookback_days: int = 90,
        percentile: int = 25,  # Use 25th percentile as baseline (lower end of normal)
        exclude_premium: bool = True
    ) -> List[Dict]:
        """
        Discover baselines from historical price data.

        Args:
            min_samples: Minimum number of price samples required
            lookback_days: How many days of history to analyze
            percentile: Which percentile to use as baseline (lower = more conservative)
            exclude_premium: Whether to exclude premium formats from baseline calculation

        Returns:
            List of discovered baseline configurations
        """
        discovered = []
        cutoff_date = datetime.now(UTC) - timedelta(days=lookback_days)

        with get_session() as session:
            # Query all prices grouped by theater/ticket_type/format
            query = session.query(
                Showing.theater_name,
                Price.ticket_type,
                Showing.format,
                func.count(Price.price_id).label('sample_count'),
                func.min(Price.price).label('min_price'),
                func.max(Price.price).label('max_price'),
                func.avg(Price.price).label('avg_price')
            ).join(
                Showing, Price.showing_id == Showing.showing_id
            ).filter(
                and_(
                    Price.company_id == self.company_id,
                    Price.created_at >= cutoff_date
                )
            ).group_by(
                Showing.theater_name,
                Price.ticket_type,
                Showing.format
            ).having(
                func.count(Price.price_id) >= min_samples
            )

            results = query.all()

            for row in results:
                theater_name, ticket_type, format_type, count, min_p, max_p, avg_p = row

                # Skip premium formats if requested
                if exclude_premium and self.is_premium_format(format_type):
                    logger.debug(f"Skipping premium format: {theater_name} {format_type}")
                    continue

                # Get all prices for this combination to calculate percentile
                prices = session.query(Price.price).join(
                    Showing, Price.showing_id == Showing.showing_id
                ).filter(
                    and_(
                        Price.company_id == self.company_id,
                        Showing.theater_name == theater_name,
                        Price.ticket_type == ticket_type,
                        Showing.format == format_type,
                        Price.created_at >= cutoff_date
                    )
                ).all()

                price_values = sorted([float(p[0]) for p in prices if p[0]])

                if len(price_values) < min_samples:
                    continue

                # Calculate baseline as the specified percentile
                # This gives us the "normal" lower price, ignoring surge spikes
                baseline_price = self._percentile(price_values, percentile)

                # Calculate price range metrics
                price_range = max_p - min_p if max_p and min_p else 0
                volatility = (price_range / avg_p * 100) if avg_p else 0

                discovered.append({
                    'theater_name': theater_name,
                    'ticket_type': ticket_type,
                    'format': format_type,
                    'baseline_price': round(baseline_price, 2),
                    'sample_count': count,
                    'min_price': float(min_p) if min_p else None,
                    'max_price': float(max_p) if max_p else None,
                    'avg_price': float(avg_p) if avg_p else None,
                    'volatility_percent': round(float(volatility), 1),
                    'is_premium': self.is_premium_format(format_type),
                })

        logger.info(f"Discovered {len(discovered)} baselines for company {self.company_id}")
        return discovered

    def _percentile(self, data: List[float], p: int) -> float:
        """Calculate the p-th percentile of data."""
        if not data:
            return 0.0
        k = (len(data) - 1) * (p / 100)
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        return data[f] + (data[c] - data[f]) * (k - f)

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
                # Skip premium formats - they shouldn't have baselines for surge detection
                if baseline_data.get('is_premium'):
                    continue

                # Extract optional fields (may be None)
                day_of_week = baseline_data.get('day_of_week')
                daypart = baseline_data.get('daypart')
                day_type = baseline_data.get('day_type')

                # Build filter for existing baseline check - must match ALL key fields
                filters = [
                    PriceBaseline.company_id == self.company_id,
                    PriceBaseline.theater_name == baseline_data['theater_name'],
                    PriceBaseline.ticket_type == baseline_data['ticket_type'],
                    PriceBaseline.effective_to.is_(None)  # Active baseline
                ]

                # Handle nullable fields - compare with IS NULL when None
                if baseline_data.get('format') is None:
                    filters.append(PriceBaseline.format.is_(None))
                else:
                    filters.append(PriceBaseline.format == baseline_data['format'])

                if day_of_week is None:
                    filters.append(PriceBaseline.day_of_week.is_(None))
                else:
                    filters.append(PriceBaseline.day_of_week == day_of_week)

                if daypart is None:
                    filters.append(PriceBaseline.daypart.is_(None))
                else:
                    filters.append(PriceBaseline.daypart == daypart)

                if day_type is None:
                    filters.append(PriceBaseline.day_type.is_(None))
                else:
                    filters.append(PriceBaseline.day_type == day_type)

                existing = session.query(PriceBaseline).filter(and_(*filters)).first()

                if existing:
                    if overwrite:
                        # Update existing baseline price instead of creating new
                        existing.baseline_price = Decimal(str(baseline_data['baseline_price']))
                        existing.effective_from = effective_from
                        saved_count += 1
                    # Skip if not overwriting - baseline already exists
                    continue

                # Create new baseline with all fields
                new_baseline = PriceBaseline(
                    company_id=self.company_id,
                    theater_name=baseline_data['theater_name'],
                    ticket_type=baseline_data['ticket_type'],
                    format=baseline_data.get('format'),
                    daypart=daypart,
                    day_type=day_type,
                    day_of_week=day_of_week,
                    baseline_price=Decimal(str(baseline_data['baseline_price'])),
                    effective_from=effective_from,
                    effective_to=None  # Active
                )
                session.add(new_baseline)
                saved_count += 1

            session.flush()

        logger.info(f"Saved {saved_count} baselines for company {self.company_id}")
        return saved_count

    def analyze_price_patterns(self, lookback_days: int = 30) -> Dict:
        """
        Analyze price patterns to identify potential surge events.

        Returns analysis including:
        - Theaters with high price volatility
        - Formats with consistent premium pricing
        - Time-based patterns (weekend vs weekday)
        """
        cutoff_date = datetime.now(UTC) - timedelta(days=lookback_days)

        analysis = {
            'high_volatility_combinations': [],
            'premium_format_pricing': [],
            'theaters_by_avg_price': [],
            'format_price_comparison': {},
            'overall_stats': {
                'total_records': 0,
                'total_theaters': 0,
                'total_circuits': 0,
                'date_range': {'min': None, 'max': None},
                'overall_avg_price': None
            }
        }

        with get_session() as session:
            # Get overall stats for Fandango data
            stats_query = session.query(
                func.count(Price.price_id).label('total_records'),
                func.count(func.distinct(Showing.theater_name)).label('total_theaters'),
                func.min(Price.created_at).label('min_date'),
                func.max(Price.created_at).label('max_date'),
                func.avg(Price.price).label('avg_price')
            ).join(
                Showing, Price.showing_id == Showing.showing_id
            ).filter(
                and_(
                    Price.company_id == self.company_id,
                    Price.created_at >= cutoff_date
                )
            ).first()

            if stats_query and stats_query.total_records:
                analysis['overall_stats']['total_records'] = stats_query.total_records or 0
                analysis['overall_stats']['total_theaters'] = stats_query.total_theaters or 0
                analysis['overall_stats']['overall_avg_price'] = round(float(stats_query.avg_price), 2) if stats_query.avg_price else None
                analysis['overall_stats']['date_range']['min'] = stats_query.min_date.strftime('%Y-%m-%d') if stats_query.min_date else None
                analysis['overall_stats']['date_range']['max'] = stats_query.max_date.strftime('%Y-%m-%d') if stats_query.max_date else None

                # Count unique circuits (extract from theater names)
                circuits_query = session.query(
                    func.count(func.distinct(
                        func.substr(Showing.theater_name, 1, func.instr(Showing.theater_name, ' ') - 1)
                    ))
                ).join(
                    Price, Price.showing_id == Showing.showing_id
                ).filter(
                    and_(
                        Price.company_id == self.company_id,
                        Price.created_at >= cutoff_date
                    )
                ).scalar()
                analysis['overall_stats']['total_circuits'] = circuits_query or 0

            # Find high volatility combinations (potential surge candidates)
            volatility_query = session.query(
                Showing.theater_name,
                Price.ticket_type,
                Showing.format,
                func.count(Price.price_id).label('count'),
                func.min(Price.price).label('min_p'),
                func.max(Price.price).label('max_p'),
                func.avg(Price.price).label('avg_p')
            ).join(
                Showing, Price.showing_id == Showing.showing_id
            ).filter(
                and_(
                    Price.company_id == self.company_id,
                    Price.created_at >= cutoff_date
                )
            ).group_by(
                Showing.theater_name,
                Price.ticket_type,
                Showing.format
            ).having(
                func.count(Price.price_id) >= 3
            )

            for row in volatility_query.all():
                theater, ticket, fmt, count, min_p, max_p, avg_p = row
                # Convert Decimal to float for arithmetic
                min_p_f = float(min_p) if min_p else 0
                max_p_f = float(max_p) if max_p else 0
                avg_p_f = float(avg_p) if avg_p else 0
                if avg_p_f > 0:
                    volatility = (max_p_f - min_p_f) / avg_p_f * 100
                    if volatility > 15:  # More than 15% price range
                        analysis['high_volatility_combinations'].append({
                            'theater': theater,
                            'ticket_type': ticket,
                            'format': fmt,
                            'volatility_percent': round(volatility, 1),
                            'price_range': f"${min_p_f:.2f} - ${max_p_f:.2f}",
                            'is_premium': self.is_premium_format(fmt)
                        })

            # Compare format pricing
            format_query = session.query(
                Showing.format,
                func.avg(Price.price).label('avg_price'),
                func.count(Price.price_id).label('count')
            ).join(
                Showing, Price.showing_id == Showing.showing_id
            ).filter(
                and_(
                    Price.company_id == self.company_id,
                    Price.created_at >= cutoff_date
                )
            ).group_by(Showing.format).having(
                func.count(Price.price_id) >= 5
            )

            for fmt, avg_p, count in format_query.all():
                analysis['format_price_comparison'][fmt or '2D'] = {
                    'avg_price': round(float(avg_p), 2),
                    'sample_count': count,
                    'is_premium': self.is_premium_format(fmt)
                }

        # Sort high volatility by volatility descending
        analysis['high_volatility_combinations'].sort(
            key=lambda x: x['volatility_percent'], reverse=True
        )

        return analysis


def discover_baselines(
    company_id: int,
    min_samples: int = 5,
    lookback_days: int = 90,
    save: bool = False
) -> List[Dict]:
    """
    Convenience function to discover baselines.

    Args:
        company_id: Company ID
        min_samples: Minimum samples required per combination
        lookback_days: Days of history to analyze
        save: Whether to save to database

    Returns:
        List of discovered baselines
    """
    service = BaselineDiscoveryService(company_id)
    baselines = service.discover_baselines(
        min_samples=min_samples,
        lookback_days=lookback_days
    )

    if save and baselines:
        service.save_discovered_baselines(baselines)

    return baselines


def refresh_baselines(company_id: int) -> int:
    """
    Refresh baselines with latest data (updates existing, adds new).

    Args:
        company_id: Company ID

    Returns:
        Number of baselines updated/added
    """
    service = BaselineDiscoveryService(company_id)
    baselines = service.discover_baselines(min_samples=5, lookback_days=60)
    return service.save_discovered_baselines(baselines, overwrite=True)


def analyze_prices(company_id: int) -> Dict:
    """
    Analyze price patterns for a company.

    Args:
        company_id: Company ID

    Returns:
        Analysis dict with volatility, format comparisons, etc.
    """
    service = BaselineDiscoveryService(company_id)
    return service.analyze_price_patterns()
