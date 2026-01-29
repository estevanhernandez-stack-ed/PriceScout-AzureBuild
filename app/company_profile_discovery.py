"""
Company Profile Discovery Service for PriceScout

Discovers and maintains pricing profiles for theater circuits/companies.
Analyzes scraped price data to understand each circuit's unique pricing structure:
- Ticket type inventory (age-based vs daypart-based)
- Daypart scheme (ticket-type-based vs time-based)
- Discount days (e.g., "$5 Tuesdays")
- Premium formats and surcharges

Usage:
    from app.company_profile_discovery import (
        CompanyProfileDiscoveryService,
        discover_company_profile,
    )

    # Discover profile for a circuit
    service = CompanyProfileDiscoveryService(company_id=1)
    profile = service.discover_profile("Marcus Theatres")
"""

from datetime import datetime, date, timedelta, UTC
from decimal import Decimal
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
import statistics
import logging
import json

from sqlalchemy import and_, func, distinct
from sqlalchemy.orm import Session

from app.db_session import get_session
from app.db_models import Price, Showing, CompanyProfile

logger = logging.getLogger(__name__)

# Day names for display
DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

# Known age-based ticket types
AGE_BASED_TICKET_TYPES = {
    'adult', 'child', 'senior', 'student', 'military', 'teen',
    'adult 3d', 'child 3d', 'senior 3d', 'student 3d',
    'adult imax', 'child imax', 'senior imax',
    'adult dolby', 'child dolby', 'senior dolby',
}

# Known daypart-based ticket types (flat price regardless of age)
DAYPART_TICKET_TYPES = {
    'matinee', 'early bird', 'twilight', 'super saver', 'bargain',
    'discount', 'value', 'morning', 'afternoon',
}

# Premium formats
PREMIUM_FORMATS = {
    'IMAX', 'IMAX 3D', 'IMAX with Laser', 'IMAX HFR 3D',
    'Dolby Cinema', 'Dolby Atmos', 'Dolby Vision',
    '3D', 'RealD 3D', 'Digital 3D',
    'PLF', 'Premium Large Format', 'XD', 'RPX', 'BigD',
    '4DX', 'D-BOX', 'ScreenX', 'MX4D',
    'Laser IMAX', 'GTX', 'UltraAVX', 'UltraScreen',
}


class CompanyProfileDiscoveryService:
    """Service for discovering pricing profiles for theater circuits."""

    def __init__(self, company_id: int):
        self.company_id = company_id

    def discover_profile(
        self,
        circuit_name: str,
        theater_names: Optional[List[str]] = None,
        lookback_days: int = 90,
        min_samples: int = 10,
    ) -> Optional[CompanyProfile]:
        """
        Discover or update a pricing profile for a theater circuit.

        Args:
            circuit_name: Name of the circuit (e.g., "Marcus Theatres", "AMC")
            theater_names: Optional list of theaters to analyze (defaults to all matching circuit)
            lookback_days: How many days of history to analyze
            min_samples: Minimum samples required for reliable detection

        Returns:
            CompanyProfile with discovered pricing characteristics
        """
        cutoff_date = datetime.now(UTC) - timedelta(days=lookback_days)

        with get_session() as session:
            # Build theater filter
            if theater_names:
                theaters = theater_names
            else:
                # Find all theaters matching circuit name pattern
                theaters = self._find_circuit_theaters(session, circuit_name)

            if not theaters:
                logger.warning(f"No theaters found for circuit: {circuit_name}")
                return None

            # Gather all price data for these theaters
            price_data = self._gather_price_data(session, theaters, cutoff_date)

            if not price_data:
                logger.warning(f"No price data found for circuit: {circuit_name}")
                return None

            # Analyze the data
            ticket_types = self._discover_ticket_types(price_data)
            daypart_scheme, daypart_boundaries, has_flat_matinee = self._analyze_daypart_scheme(price_data)
            discount_days, has_discount_days = self._detect_discount_days(price_data, min_samples)
            premium_formats, premium_surcharges = self._analyze_premium_formats(price_data)

            # Calculate data quality metrics
            theater_count = len(theaters)
            sample_count = len(price_data)
            date_range = self._get_date_range(price_data)
            confidence = self._calculate_confidence(sample_count, theater_count, len(ticket_types), price_data)

            # Create or update profile
            profile = session.query(CompanyProfile).filter(
                and_(
                    CompanyProfile.company_id == self.company_id,
                    CompanyProfile.circuit_name == circuit_name
                )
            ).first()

            if not profile:
                profile = CompanyProfile(
                    company_id=self.company_id,
                    circuit_name=circuit_name
                )
                session.add(profile)

            # Update profile fields
            profile.ticket_types = json.dumps(ticket_types)
            profile.daypart_scheme = daypart_scheme
            profile.daypart_boundaries = json.dumps(daypart_boundaries)
            profile.has_flat_matinee = has_flat_matinee
            profile.has_discount_days = has_discount_days
            profile.discount_days = json.dumps(discount_days)
            profile.premium_formats = json.dumps(premium_formats)
            profile.premium_surcharges = json.dumps(premium_surcharges)
            profile.theater_count = theater_count
            profile.sample_count = sample_count
            profile.date_range_start = date_range[0]
            profile.date_range_end = date_range[1]
            profile.confidence_score = Decimal(str(confidence))
            profile.last_updated_at = datetime.now(UTC)

            session.commit()

            # Refresh to get the committed data
            session.refresh(profile)
            return profile

    def _find_circuit_theaters(self, session: Session, circuit_name: str) -> List[str]:
        """Find all theaters matching a circuit name pattern."""
        # Common circuit prefixes - map circuit name to ALL theater name patterns
        # Note: Marcus owns Movie Tavern, so they should be grouped together
        circuit_patterns = {
            'marcus': ['Marcus %', 'Marcus Theatres %', 'Movie Tavern %'],
            'amc': ['AMC %'],
            'regal': ['Regal %'],
            'cinemark': ['Cinemark %', 'Century %'],  # Century is owned by Cinemark
        }

        circuit_lower = circuit_name.lower()

        # Check if it's a known circuit
        for circuit_key, patterns in circuit_patterns.items():
            if circuit_key in circuit_lower:
                theaters = []
                for pattern in patterns:
                    results = session.query(distinct(Showing.theater_name)).filter(
                        and_(
                            Showing.company_id == self.company_id,
                            Showing.theater_name.like(pattern)
                        )
                    ).all()
                    theaters.extend([r[0] for r in results])
                return theaters

        # Generic pattern matching
        results = session.query(distinct(Showing.theater_name)).filter(
            and_(
                Showing.company_id == self.company_id,
                Showing.theater_name.like(f"%{circuit_name}%")
            )
        ).all()
        return [r[0] for r in results]

    def _gather_price_data(
        self,
        session: Session,
        theaters: List[str],
        cutoff_date: datetime
    ) -> List[Dict]:
        """Gather all price data for specified theaters."""
        query = session.query(
            Showing.theater_name,
            Price.ticket_type,
            Showing.format,
            Showing.daypart,
            Showing.play_date,
            Showing.showtime,
            Price.price
        ).join(
            Showing, Price.showing_id == Showing.showing_id
        ).filter(
            and_(
                Price.company_id == self.company_id,
                Price.created_at >= cutoff_date,
                Price.price > 0,
                Showing.theater_name.in_(theaters)
            )
        )

        return [
            {
                'theater_name': r[0],
                'ticket_type': r[1],
                'format': r[2] or 'Standard',
                'daypart': r[3] or 'Unknown',
                'play_date': r[4],
                'showtime': r[5],
                'price': float(r[6]),
                'day_of_week': r[4].weekday() if r[4] else None
            }
            for r in query.all()
        ]

    def _discover_ticket_types(self, price_data: List[Dict]) -> List[str]:
        """Discover all unique ticket types used by the circuit."""
        ticket_types = set()
        for row in price_data:
            if row['ticket_type']:
                ticket_types.add(row['ticket_type'])
        return sorted(list(ticket_types))

    def _analyze_daypart_scheme(self, price_data: List[Dict]) -> Tuple[str, Dict, bool]:
        """
        Analyze how the circuit handles dayparts.

        Returns:
            Tuple of (scheme, boundaries, has_flat_matinee)
            - scheme: "ticket-type-based", "time-based", or "hybrid"
            - boundaries: Dict mapping daypart -> description
            - has_flat_matinee: True if matinee prices are flat regardless of age
        """
        # Check for matinee ticket types
        matinee_prices = defaultdict(list)
        adult_matinee_prices = []
        child_matinee_prices = []
        senior_matinee_prices = []

        for row in price_data:
            ticket_type_lower = (row['ticket_type'] or '').lower()
            daypart_lower = (row['daypart'] or '').lower()

            # Check if "matinee" is in the ticket type itself
            if 'matinee' in ticket_type_lower:
                matinee_prices['matinee_ticket'].append(row['price'])
                # Check for age splits within matinee ticket type
                if 'adult' in ticket_type_lower:
                    adult_matinee_prices.append(row['price'])
                elif 'child' in ticket_type_lower:
                    child_matinee_prices.append(row['price'])
                elif 'senior' in ticket_type_lower:
                    senior_matinee_prices.append(row['price'])
                else:
                    # Plain "Matinee" without age qualifier
                    matinee_prices['flat_matinee'].append(row['price'])

            # Check if daypart is matinee with age-based ticket type
            elif 'matinee' in daypart_lower:
                if 'adult' in ticket_type_lower:
                    adult_matinee_prices.append(row['price'])
                elif 'child' in ticket_type_lower:
                    child_matinee_prices.append(row['price'])
                elif 'senior' in ticket_type_lower:
                    senior_matinee_prices.append(row['price'])

        # Determine if they have flat matinee pricing
        has_flat_matinee = len(matinee_prices['flat_matinee']) > 0

        # Determine the scheme
        ticket_type_based_indicators = 0
        time_based_indicators = 0

        # If we see "Matinee" as a ticket type without age, it's ticket-type-based
        if has_flat_matinee:
            ticket_type_based_indicators += 2

        # If we see Adult Matinee / Child Matinee / Senior Matinee, check if prices differ
        if adult_matinee_prices and child_matinee_prices:
            adult_avg = statistics.mean(adult_matinee_prices)
            child_avg = statistics.mean(child_matinee_prices)
            if abs(adult_avg - child_avg) > 1.0:  # More than $1 difference
                time_based_indicators += 1
            else:
                ticket_type_based_indicators += 1

        # Analyze daypart patterns from the data
        daypart_boundaries = {}
        dayparts_seen = set()
        daypart_times = defaultdict(list)

        for row in price_data:
            daypart = row['daypart']
            showtime = row['showtime']
            if daypart and showtime:
                dayparts_seen.add(daypart)
                daypart_times[daypart].append(showtime)

        # Try to determine time boundaries for each daypart
        for daypart, times in daypart_times.items():
            if times:
                # Sort and get range
                sorted_times = sorted(set(times))
                if len(sorted_times) >= 2:
                    daypart_boundaries[daypart] = f"{sorted_times[0]} - {sorted_times[-1]}"
                else:
                    daypart_boundaries[daypart] = sorted_times[0]

        # Determine final scheme
        if ticket_type_based_indicators > time_based_indicators:
            scheme = "ticket-type-based"
        elif time_based_indicators > ticket_type_based_indicators:
            scheme = "time-based"
        else:
            scheme = "hybrid"

        return scheme, daypart_boundaries, has_flat_matinee

    def _detect_discount_days(
        self,
        price_data: List[Dict],
        min_samples: int = 10
    ) -> Tuple[List[Dict], bool]:
        """
        Detect discount days (e.g., "$5 Tuesdays").

        Detection methods:
        1. Look for day-specific discount ticket types (loyalty, bargain, etc.)
        2. Look for days where adult prices are significantly lower

        A discount day is detected when:
        - All prices for that day are nearly identical (≤8% variance or ≤$1.50 range)
        - The price is significantly lower than other days (≥8% below average)

        Adaptive behavior for sparse data:
        - If fewer than min_samples on a day, uses adaptive threshold (min 3 samples)
        - If only 2 weekdays available, still attempts detection with lower confidence
        - Results include confidence indicators based on sample size

        Returns:
            Tuple of (discount_days_list, has_discount_days)
        """
        discount_days = []
        discount_days_found = set()  # Track day_of_week to avoid duplicates

        # Known discount ticket type patterns
        DISCOUNT_TICKET_PATTERNS = {
            'loyalty', 'bargain', 'value', 'discount', 'special', 'deal',
            'super saver', 'value pricing', 'discount pricing'
        }

        # Method 1: Detect discount-specific ticket types that appear on specific days
        discount_ticket_prices = defaultdict(lambda: defaultdict(list))
        for row in price_data:
            if row['day_of_week'] is not None and row['ticket_type']:
                ticket_lower = row['ticket_type'].lower()
                # Check if this is a discount ticket type
                for pattern in DISCOUNT_TICKET_PATTERNS:
                    if pattern in ticket_lower:
                        discount_ticket_prices[ticket_lower][row['day_of_week']].append(row['price'])
                        break

        # Check if any discount ticket types appear primarily on one day
        for ticket_type, day_data in discount_ticket_prices.items():
            if not day_data:
                continue

            # Find which day has the most samples
            max_day = max(day_data.keys(), key=lambda d: len(day_data[d]))
            max_day_count = len(day_data[max_day])
            total_count = sum(len(prices) for prices in day_data.values())

            # If >70% of samples are on one day, it's likely a day-specific discount
            if total_count >= min_samples and max_day_count / total_count >= 0.7:
                prices = day_data[max_day]
                if prices:
                    day_avg = statistics.mean(prices)
                    day_name = DAY_NAMES[max_day]
                    discount_price = round(day_avg, 2)

                    # Generate program name from ticket type
                    program_name = ticket_type.title()
                    if discount_price == int(discount_price):
                        program_name = f"${discount_price:.0f} {day_name}s ({ticket_type.title()})"
                    else:
                        program_name = f"${discount_price:.2f} {day_name}s ({ticket_type.title()})"

                    discount_days.append({
                        'day_of_week': max_day,
                        'day': day_name,
                        'price': discount_price,
                        'program': program_name,
                        'sample_count': len(prices),
                        'variance_pct': 0.0,
                        'below_avg_pct': 0.0,
                        'detection_method': 'discount_ticket_type'
                    })
                    discount_days_found.add(max_day)

        # Log discount ticket type detection results
        if discount_ticket_prices:
            logger.info(f"Discount ticket types found: {list(discount_ticket_prices.keys())}")
            for ticket_type, day_data in discount_ticket_prices.items():
                logger.info(f"  {ticket_type}: {dict((DAY_NAMES[d], len(p)) for d, p in day_data.items())}")

        # Method 2: Look for days where ADULT ticket prices are flat AND lower
        # Key insight: On discount days, adult tickets are the SAME price all day
        # (across all dayparts), and that price is lower than other weekdays.
        #
        # We focus on:
        # - Adult tickets only (biggest discount signal)
        # - Standard format only (exclude premium formats)
        # - Compare weekdays to weekdays (Mon-Thu typically same, discount day stands out)

        day_prices = defaultdict(list)

        for row in price_data:
            if row['day_of_week'] is not None:
                format_name = (row['format'] or '').lower()
                ticket_type = (row['ticket_type'] or '').lower()

                # Only consider standard format
                is_standard = 'standard' in format_name or format_name in ['', '2d', 'digital']

                # ONLY adult tickets - they show the clearest discount signal
                # Exclude matinee ticket types (which are daypart-priced) and discount types
                is_adult = (
                    'adult' in ticket_type
                    and 'matinee' not in ticket_type
                    and not any(p in ticket_type for p in DISCOUNT_TICKET_PATTERNS)
                )

                if is_standard and is_adult:
                    day_prices[row['day_of_week']].append(row['price'])

        if day_prices:
            # Count how many weekdays we have data for
            weekdays_with_data = [d for d in range(5) if d in day_prices and len(day_prices[d]) >= 3]
            logger.info(f"Weekdays with sufficient data: {[DAY_NAMES[d] for d in weekdays_with_data]}")

            # Calculate weekday average (Mon=0 through Thu=3) excluding already-found discount days
            # This gives us a baseline of "normal weekday pricing"
            weekday_prices = []
            for day in range(4):  # Mon, Tue, Wed, Thu
                if day not in discount_days_found and day in day_prices:
                    weekday_prices.extend(day_prices[day])

            # If not enough weekday data, fall back to all days except weekends
            if len(weekday_prices) < min_samples:
                weekday_prices = []
                for day in range(5):  # Mon through Fri
                    if day not in discount_days_found and day in day_prices:
                        weekday_prices.extend(day_prices[day])

            # Adaptive: if still sparse, include weekend data as last resort
            # This helps when only 1-2 weekdays are available
            if len(weekday_prices) < 5 and len(weekdays_with_data) < 2:
                logger.info("Sparse weekday data - including all days for baseline calculation")
                weekday_prices = []
                for day in range(7):
                    if day not in discount_days_found and day in day_prices:
                        weekday_prices.extend(day_prices[day])

            if weekday_prices:
                weekday_avg = statistics.mean(weekday_prices)
                logger.info(f"Baseline average adult price: ${weekday_avg:.2f} (from {len(weekday_prices)} samples)")

                # Adaptive min_samples based on data availability
                # If we have limited data, lower the threshold but track confidence
                adaptive_min = min_samples
                if len(weekdays_with_data) <= 3:
                    adaptive_min = max(3, min_samples // 3)  # At least 3 samples
                    logger.info(f"Using adaptive min_samples: {adaptive_min} (limited day coverage)")

                # Now check each weekday for discount day pattern
                for day_of_week in range(5):  # Mon through Fri (weekdays only)
                    if day_of_week in discount_days_found:
                        continue

                    prices = day_prices.get(day_of_week, [])
                    if len(prices) < adaptive_min:
                        if len(prices) > 0:
                            logger.debug(f"  {DAY_NAMES[day_of_week]}: skipped (only {len(prices)} samples, need {adaptive_min})")
                        continue

                    day_avg = statistics.mean(prices)
                    day_std = statistics.stdev(prices) if len(prices) > 1 else 0
                    day_min = min(prices)
                    day_max = max(prices)

                    # Calculate variance as percentage of mean
                    variance_pct = (day_std / day_avg * 100) if day_avg > 0 else 0

                    # Calculate price range (max - min) as indicator of "flat pricing"
                    price_range = day_max - day_min

                    # Calculate how much below weekday average this day is
                    below_avg_pct = ((weekday_avg - day_avg) / weekday_avg * 100) if weekday_avg > 0 else 0

                    # Discount day detection criteria:
                    # 1. Price is relatively flat across all dayparts (low variance OR small price range)
                    # 2. Price is notably lower than other weekdays
                    #
                    # A "flat" day means all adult tickets cost the same regardless of showtime
                    is_flat_pricing = variance_pct <= 8.0 or price_range <= 1.50
                    is_discounted = below_avg_pct >= 8.0

                    if is_flat_pricing and is_discounted:
                        day_name = DAY_NAMES[day_of_week]
                        # Use the mode (most common price) or min price as the discount price
                        discount_price = round(day_min, 2)

                        # Generate program name
                        if discount_price == int(discount_price):
                            program_name = f"${discount_price:.0f} {day_name}s"
                        else:
                            program_name = f"${discount_price:.2f} {day_name}s"

                        # Calculate confidence based on sample size
                        # High: 10+ samples, Medium: 5-9 samples, Low: 3-4 samples
                        if len(prices) >= 10:
                            confidence = 'high'
                        elif len(prices) >= 5:
                            confidence = 'medium'
                        else:
                            confidence = 'low'

                        discount_days.append({
                            'day_of_week': day_of_week,
                            'day': day_name,
                            'price': discount_price,
                            'program': program_name,
                            'sample_count': len(prices),
                            'variance_pct': round(variance_pct, 1),
                            'below_avg_pct': round(below_avg_pct, 1),
                            'price_range': round(price_range, 2),
                            'detection_method': 'adult_flat_pricing',
                            'confidence': confidence
                        })
                        logger.info(f"  Detected discount day: {day_name} at ${discount_price:.2f} "
                                   f"(var={variance_pct:.1f}%, range=${price_range:.2f}, below_avg={below_avg_pct:.1f}%, "
                                   f"confidence={confidence})")

        # Sort by day of week
        discount_days.sort(key=lambda d: d['day_of_week'])

        # Log day price analysis for debugging
        if day_prices:
            weekday_avg_val = weekday_avg if 'weekday_avg' in dir() else 0
            logger.info(f"Adult ticket day-by-day analysis (weekday_avg: ${weekday_avg_val:.2f}):")
            for day in range(7):
                prices = day_prices.get(day, [])
                if prices:
                    avg = statistics.mean(prices)
                    std = statistics.stdev(prices) if len(prices) > 1 else 0
                    var_pct = (std / avg * 100) if avg > 0 else 0
                    price_range = max(prices) - min(prices)
                    below_pct = ((weekday_avg_val - avg) / weekday_avg_val * 100) if weekday_avg_val > 0 else 0
                    is_flat = "FLAT" if (var_pct <= 8.0 or price_range <= 1.50) else ""
                    is_disc = "DISCOUNT" if below_pct >= 8.0 else ""
                    logger.info(f"  {DAY_NAMES[day]}: ${avg:.2f} (n={len(prices)}, "
                               f"range=${price_range:.2f}, var={var_pct:.1f}%, "
                               f"below_avg={below_pct:.1f}%) {is_flat} {is_disc}")

        has_discount_days = len(discount_days) > 0
        logger.info(f"Discount days detected: {[d['program'] for d in discount_days]}")
        return discount_days, has_discount_days

    def _analyze_premium_formats(self, price_data: List[Dict]) -> Tuple[List[str], Dict]:
        """
        Analyze premium formats and calculate surcharges.

        Returns:
            Tuple of (premium_formats_list, surcharges_dict)
        """
        # Group prices by format (Adult ticket type only)
        format_prices = defaultdict(list)

        for row in price_data:
            if row['format']:
                ticket_type = (row['ticket_type'] or '').lower()
                if 'adult' in ticket_type and 'matinee' not in ticket_type:
                    format_prices[row['format']].append(row['price'])

        if not format_prices:
            return [], {}

        # Identify standard format baseline
        standard_prices = []
        standard_format = None

        for format_name, prices in format_prices.items():
            format_lower = format_name.lower()
            if 'standard' in format_lower or format_lower in ['2d', 'digital', '']:
                standard_prices.extend(prices)
                standard_format = format_name

        if not standard_prices:
            # Use the format with lowest average as baseline
            format_avgs = {f: statistics.mean(p) for f, p in format_prices.items() if p}
            if format_avgs:
                standard_format = min(format_avgs, key=format_avgs.get)
                standard_prices = format_prices[standard_format]

        if not standard_prices:
            return [], {}

        standard_avg = statistics.mean(standard_prices)

        # Find premium formats and calculate surcharges
        premium_formats = []
        surcharges = {}

        for format_name, prices in format_prices.items():
            if format_name == standard_format:
                continue

            format_avg = statistics.mean(prices)
            surcharge = round(format_avg - standard_avg, 2)

            # Consider it premium if surcharge is at least $2
            if surcharge >= 2.0:
                premium_formats.append(format_name)
                surcharges[format_name] = surcharge

        return sorted(premium_formats), surcharges

    def _get_date_range(self, price_data: List[Dict]) -> Tuple[Optional[date], Optional[date]]:
        """Get the date range of the price data."""
        dates = [row['play_date'] for row in price_data if row['play_date']]
        if not dates:
            return None, None
        return min(dates), max(dates)

    def _calculate_confidence(
        self,
        sample_count: int,
        theater_count: int,
        ticket_type_count: int,
        price_data: Optional[List[Dict]] = None
    ) -> float:
        """
        Calculate a confidence score (0-1) for the profile.

        Based on:
        - Sample count (more samples = higher confidence)
        - Theater coverage (more theaters = better representation)
        - Ticket type diversity (more types = more complete picture)
        - Day coverage (more weekdays = better discount detection)
        """
        # Sample count factor: 0-0.3 (100 samples = 0.15, 500+ samples = 0.3)
        sample_factor = min(0.3, sample_count / 1667)

        # Theater count factor: 0-0.25 (1 theater = 0.1, 10+ theaters = 0.25)
        theater_factor = min(0.25, 0.1 + (theater_count - 1) * 0.015)

        # Ticket type factor: 0-0.25 (3 types = 0.125, 6+ types = 0.25)
        type_factor = min(0.25, ticket_type_count * 0.042)

        # Day coverage factor: 0-0.2 (based on how many weekdays have data)
        day_factor = 0.0
        if price_data:
            days_with_data = set()
            for row in price_data:
                if row.get('day_of_week') is not None:
                    days_with_data.add(row['day_of_week'])
            weekdays_covered = len([d for d in days_with_data if d < 5])  # Mon-Fri
            # 5 weekdays = 0.2, 3 weekdays = 0.12, 2 weekdays = 0.08
            day_factor = min(0.2, weekdays_covered * 0.04)

        confidence = sample_factor + theater_factor + type_factor + day_factor
        return round(min(1.0, confidence), 2)

    def get_profile(self, circuit_name: str) -> Optional[CompanyProfile]:
        """Get existing profile for a circuit."""
        with get_session() as session:
            return session.query(CompanyProfile).filter(
                and_(
                    CompanyProfile.company_id == self.company_id,
                    CompanyProfile.circuit_name == circuit_name
                )
            ).first()

    def list_profiles(self) -> List[CompanyProfile]:
        """List all profiles for the company."""
        with get_session() as session:
            return session.query(CompanyProfile).filter(
                CompanyProfile.company_id == self.company_id
            ).order_by(CompanyProfile.circuit_name).all()


# Convenience functions
def discover_company_profile(
    company_id: int,
    circuit_name: str,
    theater_names: Optional[List[str]] = None,
    lookback_days: int = 90,
) -> Optional[CompanyProfile]:
    """Discover a company profile for a circuit."""
    service = CompanyProfileDiscoveryService(company_id)
    return service.discover_profile(circuit_name, theater_names, lookback_days)


def get_company_profile(company_id: int, circuit_name: str) -> Optional[CompanyProfile]:
    """Get an existing company profile."""
    service = CompanyProfileDiscoveryService(company_id)
    return service.get_profile(circuit_name)
