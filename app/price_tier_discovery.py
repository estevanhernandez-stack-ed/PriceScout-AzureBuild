"""
Price Tier Discovery Service for PriceScout

Discovers theater-specific pricing tiers from historical Fandango scrape data.
Instead of relying on Fandango's daypart labels (which may not match theater pricing),
this service analyzes actual prices to find natural price breaks.

Features:
- Auto-detects discount days (e.g., "$5 Tuesdays") by identifying days with flat pricing
- Creates separate baselines for discount days vs regular days
- Recommends additional scrapes needed for better tier accuracy

Example: If Movie Tavern charges $7.58 before 4pm and $11.91 after, we discover:
  - Tier 1 (Matinee): $7.58, shows before 4:00 PM
  - Tier 2 (Evening): $11.91, shows 4:00 PM and after
  - Discount Day (Tuesday): $7.58 flat all day

Usage:
    from app.price_tier_discovery import PriceTierDiscoveryService

    service = PriceTierDiscoveryService(company_id=1)

    # Discover tiers for a theater (auto-detects discount days)
    result = service.discover_tiers_for_theater("Movie Tavern Hulen")

    # Get scrape recommendations
    recs = service.get_scrape_recommendations()
"""

from datetime import datetime, time, timedelta, UTC
from decimal import Decimal
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict
import logging
import statistics

from sqlalchemy import and_, func, distinct
from sqlalchemy.orm import Session

from app.db_session import get_session
from app.db_models import Price, Showing, PriceBaseline

logger = logging.getLogger(__name__)


class DiscountDay:
    """Represents a detected discount day for a theater."""

    DOW_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def __init__(
        self,
        day_of_week: int,  # 0=Monday, 6=Sunday
        price: Decimal,
        sample_count: int,
        price_variance: float = 0.0,
        program_name: Optional[str] = None  # e.g., "$5 Tuesdays"
    ):
        self.day_of_week = day_of_week
        self.day_name = self.DOW_NAMES[day_of_week]
        self.price = price
        self.sample_count = sample_count
        self.price_variance = price_variance
        self.program_name = program_name or f"Discount {self.day_name}"

    def to_dict(self) -> Dict:
        return {
            'day_of_week': self.day_of_week,
            'day_name': self.day_name,
            'price': float(self.price),
            'sample_count': self.sample_count,
            'price_variance': round(self.price_variance, 2),
            'program_name': self.program_name,
        }


class PriceTier:
    """Represents a discovered price tier for a theater."""

    def __init__(
        self,
        tier_name: str,
        price: Decimal,
        start_time: time,
        end_time: time,
        sample_count: int,
        price_variance: float = 0.0
    ):
        self.tier_name = tier_name
        self.price = price
        self.start_time = start_time
        self.end_time = end_time
        self.sample_count = sample_count
        self.price_variance = price_variance  # How much prices vary within this tier

    def to_dict(self) -> Dict:
        return {
            'tier_name': self.tier_name,
            'price': float(self.price),
            'start_time': self.start_time.strftime('%H:%M') if self.start_time else None,
            'end_time': self.end_time.strftime('%H:%M') if self.end_time else None,
            'sample_count': self.sample_count,
            'price_variance': round(self.price_variance, 2),
        }


class TheaterPricingProfile:
    """Complete pricing profile for a theater."""

    def __init__(
        self,
        theater_name: str,
        ticket_type: str,
        format_type: str,
        tiers: List[PriceTier],
        discount_days: Optional[List[DiscountDay]] = None,
        regular_day_count: int = 0,
        total_samples: int = 0
    ):
        self.theater_name = theater_name
        self.ticket_type = ticket_type
        self.format_type = format_type
        self.tiers = tiers
        self.discount_days = discount_days or []
        self.regular_day_count = regular_day_count
        self.total_samples = total_samples

    def to_dict(self) -> Dict:
        return {
            'theater_name': self.theater_name,
            'ticket_type': self.ticket_type,
            'format': self.format_type,
            'tiers': [t.to_dict() for t in self.tiers],
            'tier_count': len(self.tiers),
            'discount_days': [d.to_dict() for d in self.discount_days],
            'has_discount_days': len(self.discount_days) > 0,
            'regular_day_count': self.regular_day_count,
            'total_samples': self.total_samples,
        }

    def get_tier_for_time(self, showtime: time) -> Optional[PriceTier]:
        """Find which tier a showtime falls into."""
        for tier in self.tiers:
            if tier.start_time <= showtime < tier.end_time:
                return tier
        return None

    def get_discount_day(self, day_of_week: int) -> Optional[DiscountDay]:
        """Check if a day of week is a discount day."""
        for dd in self.discount_days:
            if dd.day_of_week == day_of_week:
                return dd
        return None


class PriceTierDiscoveryService:
    """Service for discovering price tiers from historical data."""

    # Minimum price difference to consider it a new tier (as percentage)
    MIN_TIER_DIFFERENCE_PERCENT = 5.0

    # Minimum absolute price difference
    MIN_TIER_DIFFERENCE_DOLLARS = 0.50

    # Discount day detection: max variance allowed for "flat" pricing
    DISCOUNT_DAY_MAX_VARIANCE_PERCENT = 3.0  # If prices vary less than 3%, it's flat

    # Minimum samples per day to consider for discount day detection
    MIN_SAMPLES_FOR_DISCOUNT_DETECTION = 3

    # Time parsing formats
    TIME_FORMATS = ['%I:%M%p', '%I:%M %p', '%H:%M']

    # Day of week names
    DOW_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def __init__(self, company_id: int):
        self.company_id = company_id

    def detect_discount_days(
        self,
        theater_name: str,
        ticket_type: str = 'Adult',
        format_type: str = 'Standard'
    ) -> Tuple[List[DiscountDay], List[int]]:
        """
        Detect discount days for a theater based on flat pricing patterns.

        A discount day is detected when:
        - All prices for that day of week are the same (or within 3% variance)
        - The price is lower than the average of other days

        Returns:
            Tuple of (list of DiscountDay objects, list of non-discount day_of_week values)
        """
        discount_days = []
        regular_days = []

        with get_session() as session:
            # Get all prices grouped by day of week
            results = session.query(
                Price.price,
                Showing.play_date
            ).join(
                Showing, Price.showing_id == Showing.showing_id
            ).filter(
                and_(
                    Price.company_id == self.company_id,
                    Showing.theater_name == theater_name,
                    Price.ticket_type == ticket_type,
                    Showing.format == format_type
                )
            ).all()

            if not results:
                return [], list(range(7))

            # Group prices by day of week
            dow_prices: Dict[int, List[float]] = defaultdict(list)
            for price, play_date in results:
                if price and play_date:
                    dow = play_date.weekday()
                    dow_prices[dow].append(float(price))

            # Calculate overall average (for comparison)
            all_prices = [p for prices in dow_prices.values() for p in prices]
            overall_avg = statistics.mean(all_prices) if all_prices else 0

            # Check each day of week for discount day pattern
            for dow, prices in dow_prices.items():
                if len(prices) < self.MIN_SAMPLES_FOR_DISCOUNT_DETECTION:
                    regular_days.append(dow)
                    continue

                avg_price = statistics.mean(prices)
                min_price = min(prices)
                max_price = max(prices)

                # Calculate variance as percentage of average
                price_range = max_price - min_price
                variance_percent = (price_range / avg_price * 100) if avg_price > 0 else 0

                # Check if this is a discount day:
                # 1. Low variance (flat pricing)
                # 2. Below average pricing
                is_flat = variance_percent <= self.DISCOUNT_DAY_MAX_VARIANCE_PERCENT
                is_discounted = avg_price < (overall_avg * 0.85)  # At least 15% below average

                if is_flat and is_discounted:
                    # Detect program name based on price
                    price_rounded = round(avg_price)
                    program_name = f"${price_rounded} {self.DOW_NAMES[dow]}s"

                    discount_days.append(DiscountDay(
                        day_of_week=dow,
                        price=Decimal(str(round(avg_price, 2))),
                        sample_count=len(prices),
                        price_variance=variance_percent,
                        program_name=program_name
                    ))
                    logger.info(f"Detected discount day: {theater_name} - {program_name} (${avg_price:.2f}, {len(prices)} samples)")
                else:
                    regular_days.append(dow)

            # Add days with no data to regular days
            for dow in range(7):
                if dow not in dow_prices:
                    regular_days.append(dow)

        return discount_days, sorted(set(regular_days))

    def parse_showtime(self, showtime_str: str) -> Optional[time]:
        """Parse a showtime string into a time object."""
        if not showtime_str:
            return None

        # Normalize the string
        showtime_str = showtime_str.strip().upper().replace(' ', '')

        for fmt in self.TIME_FORMATS:
            try:
                dt = datetime.strptime(showtime_str, fmt.replace(' ', ''))
                return dt.time()
            except ValueError:
                continue

        # Try with space
        showtime_str_spaced = showtime_str[:-2] + ' ' + showtime_str[-2:]
        for fmt in self.TIME_FORMATS:
            try:
                dt = datetime.strptime(showtime_str_spaced, fmt)
                return dt.time()
            except ValueError:
                continue

        logger.warning(f"Could not parse showtime: {showtime_str}")
        return None

    def discover_tiers_for_theater(
        self,
        theater_name: str,
        ticket_type: str = 'Adult',
        format_type: str = 'Standard',
        min_samples: int = 5
    ) -> Optional[TheaterPricingProfile]:
        """
        Discover price tiers for a specific theater/ticket_type/format combination.

        Automatically detects and separates discount days from regular pricing tiers.

        Args:
            theater_name: Theater name to analyze
            ticket_type: Ticket type (Adult, Senior, Child, etc.)
            format_type: Format (Standard, IMAX, Dolby, etc.)
            min_samples: Minimum prices required for analysis

        Returns:
            TheaterPricingProfile with discovered tiers and discount days, or None if insufficient data
        """
        # First, detect discount days
        discount_days, regular_day_dows = self.detect_discount_days(
            theater_name, ticket_type, format_type
        )

        with get_session() as session:
            # Build query for prices
            query = session.query(
                Price.price,
                Showing.showtime,
                Showing.play_date
            ).join(
                Showing, Price.showing_id == Showing.showing_id
            ).filter(
                and_(
                    Price.company_id == self.company_id,
                    Showing.theater_name == theater_name,
                    Price.ticket_type == ticket_type,
                    Showing.format == format_type
                )
            )

            results = query.all()
            total_samples = len(results)

            if total_samples < min_samples:
                logger.debug(f"Insufficient data for {theater_name} {ticket_type} {format_type}: {total_samples} < {min_samples}")
                return None

            # Filter out discount days for tier discovery
            discount_day_dows = {dd.day_of_week for dd in discount_days}
            regular_results = []
            regular_dates = set()

            for price, showtime, play_date in results:
                if play_date:
                    dow = play_date.weekday()
                    if dow not in discount_day_dows:
                        regular_results.append((price, showtime, play_date))
                        regular_dates.add(play_date)

            regular_day_count = len(regular_dates)

            if len(regular_results) < min_samples:
                # Not enough regular day data, but we might still have discount day info
                if discount_days:
                    return TheaterPricingProfile(
                        theater_name=theater_name,
                        ticket_type=ticket_type,
                        format_type=format_type,
                        tiers=[],  # No tiers discovered
                        discount_days=discount_days,
                        regular_day_count=regular_day_count,
                        total_samples=total_samples
                    )
                return None

            # Group prices by showtime (regular days only)
            time_prices: Dict[time, List[Decimal]] = defaultdict(list)

            for price, showtime_str, play_date in regular_results:
                t = self.parse_showtime(showtime_str)
                if t and price:
                    time_prices[t].append(Decimal(str(price)))

            if not time_prices:
                if discount_days:
                    return TheaterPricingProfile(
                        theater_name=theater_name,
                        ticket_type=ticket_type,
                        format_type=format_type,
                        tiers=[],
                        discount_days=discount_days,
                        regular_day_count=regular_day_count,
                        total_samples=total_samples
                    )
                return None

            # Calculate average price for each time slot
            time_avg_prices: List[Tuple[time, Decimal, int]] = []
            for t, prices in sorted(time_prices.items()):
                avg_price = Decimal(str(statistics.mean([float(p) for p in prices])))
                time_avg_prices.append((t, avg_price, len(prices)))

            # Find natural price breaks (tiers)
            tiers = self._find_price_tiers(time_avg_prices)

            return TheaterPricingProfile(
                theater_name=theater_name,
                ticket_type=ticket_type,
                format_type=format_type,
                tiers=tiers,
                discount_days=discount_days,
                regular_day_count=regular_day_count,
                total_samples=total_samples
            )

    def _find_price_tiers(
        self,
        time_avg_prices: List[Tuple[time, Decimal, int]]
    ) -> List[PriceTier]:
        """
        Find natural price tiers from time-sorted price data.

        Uses a simple algorithm:
        1. Sort by time
        2. Group consecutive times with similar prices
        3. When price jumps significantly, start a new tier
        """
        if not time_avg_prices:
            return []

        tiers = []
        current_tier_times = [time_avg_prices[0][0]]
        current_tier_prices = [time_avg_prices[0][1]]
        current_tier_samples = time_avg_prices[0][2]

        for i in range(1, len(time_avg_prices)):
            t, price, samples = time_avg_prices[i]
            prev_price = current_tier_prices[-1]

            # Calculate price difference
            price_diff = abs(float(price) - float(prev_price))
            price_diff_percent = (price_diff / float(prev_price)) * 100 if prev_price > 0 else 0

            # Check if this is a new tier
            is_new_tier = (
                price_diff >= self.MIN_TIER_DIFFERENCE_DOLLARS and
                price_diff_percent >= self.MIN_TIER_DIFFERENCE_PERCENT
            )

            if is_new_tier:
                # Save current tier
                avg_price = Decimal(str(statistics.mean([float(p) for p in current_tier_prices])))
                variance = statistics.stdev([float(p) for p in current_tier_prices]) if len(current_tier_prices) > 1 else 0

                tier = PriceTier(
                    tier_name=self._get_tier_name(len(tiers)),
                    price=avg_price,
                    start_time=current_tier_times[0],
                    end_time=t,  # End at start of next tier
                    sample_count=current_tier_samples,
                    price_variance=variance
                )
                tiers.append(tier)

                # Start new tier
                current_tier_times = [t]
                current_tier_prices = [price]
                current_tier_samples = samples
            else:
                # Add to current tier
                current_tier_times.append(t)
                current_tier_prices.append(price)
                current_tier_samples += samples

        # Save final tier
        avg_price = Decimal(str(statistics.mean([float(p) for p in current_tier_prices])))
        variance = statistics.stdev([float(p) for p in current_tier_prices]) if len(current_tier_prices) > 1 else 0

        tier = PriceTier(
            tier_name=self._get_tier_name(len(tiers)),
            price=avg_price,
            start_time=current_tier_times[0],
            end_time=time(23, 59),  # End of day
            sample_count=current_tier_samples,
            price_variance=variance
        )
        tiers.append(tier)

        return tiers

    def _get_tier_name(self, tier_index: int) -> str:
        """Get a descriptive name for a tier based on its index."""
        names = ['Matinee', 'Twilight', 'Prime', 'Evening', 'Late Night']
        if tier_index < len(names):
            return names[tier_index]
        return f'Tier {tier_index + 1}'

    def discover_all_theater_tiers(
        self,
        min_prices: int = 20,
        ticket_types: Optional[List[str]] = None
    ) -> List[TheaterPricingProfile]:
        """
        Discover price tiers for all theaters with sufficient data.

        Args:
            min_prices: Minimum prices required per theater
            ticket_types: List of ticket types to analyze (default: Adult only)

        Returns:
            List of TheaterPricingProfile objects
        """
        if ticket_types is None:
            ticket_types = ['Adult']

        profiles = []

        with get_session() as session:
            # Get theaters with enough data
            theater_counts = session.query(
                Showing.theater_name,
                Showing.format,
                func.count(Price.price_id).label('price_count')
            ).join(
                Price, Price.showing_id == Showing.showing_id
            ).filter(
                Price.company_id == self.company_id
            ).group_by(
                Showing.theater_name,
                Showing.format
            ).having(
                func.count(Price.price_id) >= min_prices
            ).all()

        for theater_name, format_type, count in theater_counts:
            for ticket_type in ticket_types:
                profile = self.discover_tiers_for_theater(
                    theater_name=theater_name,
                    ticket_type=ticket_type,
                    format_type=format_type or 'Standard',
                    min_samples=min_prices // 2  # Lower threshold per type
                )
                if profile:
                    profiles.append(profile)

        logger.info(f"Discovered {len(profiles)} pricing profiles for company {self.company_id}")
        return profiles

    def analyze_theater_pricing(self, theater_name: str) -> Dict[str, Any]:
        """
        Get a detailed pricing analysis for a theater.

        Returns breakdown by ticket type, format, and time.
        """
        analysis = {
            'theater_name': theater_name,
            'ticket_types': {},
            'formats': {},
            'price_by_time': [],
            'summary': {}
        }

        with get_session() as session:
            # Get all prices for this theater
            results = session.query(
                Price.price,
                Price.ticket_type,
                Showing.showtime,
                Showing.format,
                Showing.daypart,
                Showing.play_date
            ).join(
                Showing, Price.showing_id == Showing.showing_id
            ).filter(
                and_(
                    Price.company_id == self.company_id,
                    Showing.theater_name == theater_name
                )
            ).all()

            if not results:
                return analysis

            # Aggregate by ticket type
            ticket_prices: Dict[str, List[float]] = defaultdict(list)
            format_prices: Dict[str, List[float]] = defaultdict(list)
            time_prices: Dict[str, List[Tuple[str, float]]] = defaultdict(list)  # time -> [(ticket_type, price)]

            for price, ticket_type, showtime, fmt, daypart, play_date in results:
                if price:
                    ticket_prices[ticket_type].append(float(price))
                    format_prices[fmt or 'Standard'].append(float(price))

                    t = self.parse_showtime(showtime)
                    if t:
                        time_key = t.strftime('%H:%M')
                        time_prices[time_key].append((ticket_type, float(price)))

            # Calculate stats by ticket type
            for ttype, prices in ticket_prices.items():
                analysis['ticket_types'][ttype] = {
                    'min': min(prices),
                    'max': max(prices),
                    'avg': round(statistics.mean(prices), 2),
                    'count': len(prices)
                }

            # Calculate stats by format
            for fmt, prices in format_prices.items():
                analysis['formats'][fmt] = {
                    'min': min(prices),
                    'max': max(prices),
                    'avg': round(statistics.mean(prices), 2),
                    'count': len(prices)
                }

            # Price by time (for Adult tickets)
            for time_key in sorted(time_prices.keys()):
                adult_prices = [p for tt, p in time_prices[time_key] if tt == 'Adult']
                if adult_prices:
                    analysis['price_by_time'].append({
                        'time': time_key,
                        'avg_price': round(statistics.mean(adult_prices), 2),
                        'sample_count': len(adult_prices)
                    })

            # Summary
            all_prices = [float(p) for p, _, _, _, _, _ in results if p]
            analysis['summary'] = {
                'total_prices': len(all_prices),
                'min_price': min(all_prices) if all_prices else None,
                'max_price': max(all_prices) if all_prices else None,
                'avg_price': round(statistics.mean(all_prices), 2) if all_prices else None,
                'price_range': round(max(all_prices) - min(all_prices), 2) if all_prices else None
            }

        return analysis

    def get_scrape_recommendations(
        self,
        target_samples_per_theater: int = 50,
        target_days_per_theater: int = 5
    ) -> Dict[str, Any]:
        """
        Get recommendations for additional scrapes needed to improve tier discovery.

        Args:
            target_samples_per_theater: Target number of prices per theater
            target_days_per_theater: Target number of unique days per theater

        Returns:
            Dict with recommendations by theater
        """
        recommendations = {
            'theaters_needing_data': [],
            'theaters_ready': [],
            'summary': {
                'total_theaters': 0,
                'theaters_ready': 0,
                'theaters_needing_data': 0,
            }
        }

        with get_session() as session:
            # Get current data status by theater
            theater_stats = session.query(
                Showing.theater_name,
                func.count(Price.price_id).label('price_count'),
                func.count(distinct(Showing.play_date)).label('date_count'),
                func.min(Showing.play_date).label('min_date'),
                func.max(Showing.play_date).label('max_date')
            ).join(
                Price, Price.showing_id == Showing.showing_id
            ).filter(
                Price.company_id == self.company_id
            ).group_by(
                Showing.theater_name
            ).all()

            for theater_name, price_count, date_count, min_date, max_date in theater_stats:
                recommendations['summary']['total_theaters'] += 1

                # Check which days we have data for
                days_with_data = session.query(
                    distinct(func.strftime('%w', Showing.play_date))
                ).join(
                    Price, Price.showing_id == Showing.showing_id
                ).filter(
                    and_(
                        Price.company_id == self.company_id,
                        Showing.theater_name == theater_name
                    )
                ).all()

                days_covered = [int(d[0]) for d in days_with_data if d[0]]
                # SQLite %w: 0=Sunday, 1=Monday, etc. Convert to Python: 0=Monday
                days_covered_python = [(d - 1) % 7 for d in days_covered]

                missing_days = [self.DOW_NAMES[d] for d in range(7) if d not in days_covered_python]

                if price_count >= target_samples_per_theater and date_count >= target_days_per_theater:
                    recommendations['theaters_ready'].append({
                        'theater_name': theater_name,
                        'price_count': price_count,
                        'date_count': date_count,
                        'date_range': f"{min_date} to {max_date}",
                        'status': 'ready'
                    })
                    recommendations['summary']['theaters_ready'] += 1
                else:
                    needed_prices = max(0, target_samples_per_theater - price_count)
                    needed_days = max(0, target_days_per_theater - date_count)

                    recommendations['theaters_needing_data'].append({
                        'theater_name': theater_name,
                        'current_prices': price_count,
                        'current_days': date_count,
                        'needed_prices': needed_prices,
                        'needed_days': needed_days,
                        'missing_days_of_week': missing_days,
                        'date_range': f"{min_date} to {max_date}",
                        'priority': 'high' if price_count < 20 else 'medium',
                        'recommendation': self._get_scrape_recommendation(
                            price_count, date_count, missing_days
                        )
                    })
                    recommendations['summary']['theaters_needing_data'] += 1

        # Sort by priority
        recommendations['theaters_needing_data'].sort(
            key=lambda x: (x['priority'] == 'high', -x['current_prices']),
            reverse=True
        )

        return recommendations

    def _get_scrape_recommendation(
        self,
        price_count: int,
        date_count: int,
        missing_days: List[str]
    ) -> str:
        """Generate a human-readable scrape recommendation."""
        if price_count < 20:
            return f"Need more data. Scrape at least 2-3 more days, prioritize: {', '.join(missing_days[:3]) or 'any days'}"
        elif date_count < 3:
            return f"Need more date variety. Scrape different days: {', '.join(missing_days[:3]) or 'any days'}"
        elif missing_days:
            return f"Good progress. Fill in missing days: {', '.join(missing_days)}"
        else:
            return "Nearly ready. One more scrape should complete the profile."

    def save_tiers_as_baselines(
        self,
        profiles: List[TheaterPricingProfile],
        overwrite: bool = False
    ) -> Dict[str, int]:
        """
        Save discovered tiers and discount days as PriceBaseline records.

        Args:
            profiles: List of TheaterPricingProfile to save
            overwrite: If True, replace existing baselines

        Returns:
            Dict with counts: {'tiers_saved': N, 'discount_days_saved': N}
        """
        from datetime import date

        tiers_saved = 0
        discount_days_saved = 0
        today = date.today()

        with get_session() as session:
            for profile in profiles:
                # Save regular tiers
                for tier in profile.tiers:
                    # Check for existing baseline
                    existing = session.query(PriceBaseline).filter(
                        and_(
                            PriceBaseline.company_id == self.company_id,
                            PriceBaseline.theater_name == profile.theater_name,
                            PriceBaseline.ticket_type == profile.ticket_type,
                            PriceBaseline.format == profile.format_type,
                            PriceBaseline.daypart == tier.tier_name,
                            PriceBaseline.day_of_week.is_(None),  # Regular tier, not day-specific
                            PriceBaseline.effective_to.is_(None)  # Active baseline
                        )
                    ).first()

                    if existing:
                        if overwrite:
                            existing.effective_to = today - timedelta(days=1)
                        else:
                            continue

                    # Create new baseline
                    baseline = PriceBaseline(
                        company_id=self.company_id,
                        theater_name=profile.theater_name,
                        ticket_type=profile.ticket_type,
                        format=profile.format_type,
                        daypart=tier.tier_name,
                        day_type=None,  # Applies to regular days
                        day_of_week=None,
                        baseline_price=tier.price,
                        effective_from=today
                    )
                    session.add(baseline)
                    tiers_saved += 1

                # Save discount days as separate baselines
                for discount_day in profile.discount_days:
                    existing = session.query(PriceBaseline).filter(
                        and_(
                            PriceBaseline.company_id == self.company_id,
                            PriceBaseline.theater_name == profile.theater_name,
                            PriceBaseline.ticket_type == profile.ticket_type,
                            PriceBaseline.format == profile.format_type,
                            PriceBaseline.day_of_week == discount_day.day_of_week,
                            PriceBaseline.effective_to.is_(None)
                        )
                    ).first()

                    if existing:
                        if overwrite:
                            existing.effective_to = today - timedelta(days=1)
                        else:
                            continue

                    # Create discount day baseline with "Discount" daypart
                    baseline = PriceBaseline(
                        company_id=self.company_id,
                        theater_name=profile.theater_name,
                        ticket_type=profile.ticket_type,
                        format=profile.format_type,
                        daypart=discount_day.program_name,  # e.g., "$8 Tuesdays"
                        day_type='discount',
                        day_of_week=discount_day.day_of_week,
                        baseline_price=discount_day.price,
                        effective_from=today
                    )
                    session.add(baseline)
                    discount_days_saved += 1

            session.flush()

        logger.info(f"Saved {tiers_saved} tier baselines and {discount_days_saved} discount day baselines")
        return {'tiers_saved': tiers_saved, 'discount_days_saved': discount_days_saved}


# Convenience functions

def discover_price_tiers(
    company_id: int,
    theater_name: str,
    ticket_type: str = 'Adult',
    format_type: str = 'Standard'
) -> Optional[TheaterPricingProfile]:
    """
    Discover price tiers for a specific theater.

    Automatically detects and separates discount days.

    Args:
        company_id: Company ID
        theater_name: Theater name
        ticket_type: Ticket type (default: Adult)
        format_type: Format (default: Standard)

    Returns:
        TheaterPricingProfile with tiers and discount_days, or None if insufficient data
    """
    service = PriceTierDiscoveryService(company_id)
    return service.discover_tiers_for_theater(
        theater_name=theater_name,
        ticket_type=ticket_type,
        format_type=format_type
    )


def discover_all_tiers(company_id: int, min_prices: int = 20) -> List[TheaterPricingProfile]:
    """
    Discover price tiers for all theaters with sufficient data.

    Args:
        company_id: Company ID
        min_prices: Minimum prices required per theater

    Returns:
        List of TheaterPricingProfile objects
    """
    service = PriceTierDiscoveryService(company_id)
    return service.discover_all_theater_tiers(min_prices=min_prices)


def analyze_theater(company_id: int, theater_name: str) -> Dict[str, Any]:
    """
    Get pricing analysis for a theater.

    Args:
        company_id: Company ID
        theater_name: Theater name

    Returns:
        Analysis dict with price breakdowns
    """
    service = PriceTierDiscoveryService(company_id)
    return service.analyze_theater_pricing(theater_name)


def get_scrape_recommendations(company_id: int) -> Dict[str, Any]:
    """
    Get recommendations for which theaters need more scrape data.

    Args:
        company_id: Company ID

    Returns:
        Dict with theaters_ready, theaters_needing_data, and recommendations
    """
    service = PriceTierDiscoveryService(company_id)
    return service.get_scrape_recommendations()


def detect_discount_days(
    company_id: int,
    theater_name: str,
    ticket_type: str = 'Adult',
    format_type: str = 'Standard'
) -> List[DiscountDay]:
    """
    Detect discount days for a theater.

    Args:
        company_id: Company ID
        theater_name: Theater name
        ticket_type: Ticket type (default: Adult)
        format_type: Format (default: Standard)

    Returns:
        List of DiscountDay objects
    """
    service = PriceTierDiscoveryService(company_id)
    discount_days, _ = service.detect_discount_days(theater_name, ticket_type, format_type)
    return discount_days
