"""
Theater Amenity Discovery Service

Discovers and maintains theater-level amenity information:
- Premium format availability (IMAX, Dolby, 4DX, etc.)
- Screen count estimation from overlapping showtimes
- Seating features (recliners, reserved seating)

The key insight for screen count: if a theater has 2 IMAX shows starting
at the same time (or within 5 minutes), they must have 2 IMAX screens.
"""

import logging
from datetime import datetime, date, timedelta, time, UTC
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import and_, func, distinct
from sqlalchemy.orm import Session

from app.db_session import get_session
from app.db_models import Showing, TheaterAmenities, Price, Film

logger = logging.getLogger(__name__)

# Formats that are considered "premium large format" (PLF)
PLF_FORMATS = {
    'IMAX', 'IMAX 3D', 'IMAX with Laser', 'IMAX HFR 3D', 'Laser IMAX',
    'Dolby Cinema', 'Dolby Atmos', 'Dolby Vision',
    'RPX', 'XD', 'BigD', 'UltraScreen', 'GTX', 'UltraAVX',
    '4DX', 'MX4D',
    'D-BOX',
    'ScreenX',
    'PLF', 'Premium Large Format',
}

# Map format names to amenity boolean fields
FORMAT_TO_AMENITY = {
    'IMAX': 'has_imax',
    'IMAX 3D': 'has_imax',
    'IMAX with Laser': 'has_imax',
    'IMAX HFR 3D': 'has_imax',
    'Laser IMAX': 'has_imax',
    'Dolby Cinema': 'has_dolby_cinema',
    'Dolby Atmos': 'has_dolby_atmos',
    'Dolby Vision': 'has_dolby_cinema',
    'RPX': 'has_rpx',
    '4DX': 'has_4dx',
    'MX4D': 'has_4dx',
    'ScreenX': 'has_screenx',
    'D-BOX': 'has_dbox',
}

# Categories of formats for grouping
FORMAT_CATEGORIES = {
    'imax': ['IMAX', 'IMAX 3D', 'IMAX with Laser', 'IMAX HFR 3D', 'Laser IMAX'],
    'dolby': ['Dolby Cinema', 'Dolby Atmos', 'Dolby Vision'],
    '3d': ['3D', 'RealD 3D', 'Digital 3D', 'IMAX 3D'],
    '4dx': ['4DX', 'MX4D'],
    'dbox': ['D-BOX'],
    'screenx': ['ScreenX'],
    'rpx': ['RPX'],
    'plf_other': ['XD', 'BigD', 'UltraScreen', 'GTX', 'UltraAVX', 'PLF', 'Premium Large Format'],
    # Generic "Premium Format" from Fandango - we can count overlaps but can't identify type
    'premium_generic': ['Premium Format'],
}


def parse_showtime(showtime_str: str) -> Optional[time]:
    """Parse a showtime string to a time object."""
    if not showtime_str:
        return None

    try:
        # Clean up the string
        s = showtime_str.strip().lower().replace('.', '')

        # Handle various formats
        if s.endswith('p'):
            s = s[:-1] + 'pm'
        if s.endswith('a'):
            s = s[:-1] + 'am'
        s = s.replace('p.m.', 'pm').replace('a.m.', 'am')

        # Try parsing
        for fmt in ['%I:%M%p', '%I:%M %p', '%H:%M']:
            try:
                return datetime.strptime(s, fmt).time()
            except ValueError:
                continue

        return None
    except Exception:
        return None


def showtimes_overlap(time1: time, time2: time, threshold_minutes: int = 10) -> bool:
    """
    Check if two showtimes overlap (start within threshold_minutes of each other).

    Two shows starting within 10 minutes of each other on the same format
    must be in different auditoriums.
    """
    if not time1 or not time2:
        return False

    # Convert to minutes since midnight for easy comparison
    mins1 = time1.hour * 60 + time1.minute
    mins2 = time2.hour * 60 + time2.minute

    return abs(mins1 - mins2) <= threshold_minutes


def count_overlapping_shows(showtimes: List[time], threshold_minutes: int = 10) -> int:
    """
    Count the maximum number of overlapping showtimes (simple start-time based).

    This gives us the minimum screen count for a format.

    Algorithm: For each showtime, count how many other showtimes are within
    the threshold. The maximum count + 1 (for itself) = screen count.
    """
    if not showtimes:
        return 0

    if len(showtimes) == 1:
        return 1

    # Sort showtimes by minutes since midnight
    sorted_times = sorted(showtimes, key=lambda t: t.hour * 60 + t.minute if t else 0)

    max_overlap = 1

    for i, t1 in enumerate(sorted_times):
        if not t1:
            continue

        overlap_count = 1  # Count itself
        t1_mins = t1.hour * 60 + t1.minute

        for j, t2 in enumerate(sorted_times):
            if i == j or not t2:
                continue

            t2_mins = t2.hour * 60 + t2.minute

            if abs(t1_mins - t2_mins) <= threshold_minutes:
                overlap_count += 1

        max_overlap = max(max_overlap, overlap_count)

    return max_overlap


def parse_runtime(runtime_str: Optional[str], min_runtime: int = 60) -> int:
    """
    Parse a runtime string like '135 min' to minutes.
    Returns default of 120 minutes if parsing fails or value is below minimum.

    Args:
        runtime_str: Runtime string like "135 min" or "2h 15m"
        min_runtime: Minimum valid runtime (default 60 min) - values below this
                    are treated as bad data and get the default

    Returns:
        Runtime in minutes (clamped to minimum)
    """
    DEFAULT_RUNTIME = 120  # 2 hours

    if not runtime_str:
        return DEFAULT_RUNTIME

    try:
        # Handle formats like "135 min", "2h 15m", "135"
        runtime_str = runtime_str.lower().strip()

        if 'min' in runtime_str:
            # "135 min" format
            match = runtime_str.replace('min', '').strip()
            result = int(match)
        elif 'h' in runtime_str:
            # "2h 15m" format
            parts = runtime_str.replace('h', ' ').replace('m', ' ').split()
            hours = int(parts[0]) if len(parts) > 0 else 0
            mins = int(parts[1]) if len(parts) > 1 else 0
            result = hours * 60 + mins
        else:
            # Just a number
            result = int(runtime_str)

        # Sanity check - films shorter than min_runtime are probably bad data
        if result < min_runtime:
            return DEFAULT_RUNTIME

        return result
    except (ValueError, IndexError):
        return DEFAULT_RUNTIME


def count_screens_with_runtime(
    showings: List[Tuple[time, int]],
    buffer_minutes: int = 35
) -> int:
    """
    Count screens considering actual screen occupancy based on runtime.

    Args:
        showings: List of (start_time, runtime_minutes) tuples
        buffer_minutes: Extra time between shows (default 35 min)
                       - 15-20 min for cleaning
                       - 15-20 min for seating/trailers

    Returns:
        Maximum number of concurrent screen occupancies

    This is more accurate than start-time overlap for theaters where
    a 7:00 PM 2-hour movie still occupies the screen during an 8:30 PM start.
    """
    if not showings:
        return 0

    if len(showings) == 1:
        return 1

    # Convert to (start_mins, end_mins) intervals
    intervals = []
    for start_time, runtime in showings:
        if not start_time:
            continue
        start_mins = start_time.hour * 60 + start_time.minute
        # Screen occupied from start to end + buffer
        end_mins = start_mins + runtime + buffer_minutes
        intervals.append((start_mins, end_mins))

    if not intervals:
        return 1

    # Sort by start time
    intervals.sort(key=lambda x: x[0])

    # Sweep line algorithm: count max overlapping intervals
    events = []
    for start, end in intervals:
        events.append((start, 1))   # Start event (+1 screen)
        events.append((end, -1))    # End event (-1 screen)

    # Sort events by time, with ends before starts at same time
    events.sort(key=lambda x: (x[0], x[1]))

    max_screens = 0
    current_screens = 0

    for _, delta in events:
        current_screens += delta
        max_screens = max(max_screens, current_screens)

    return max_screens


class TheaterAmenityDiscoveryService:
    """Service for discovering theater amenities from showings data."""

    def __init__(self, company_id: int):
        self.company_id = company_id

    def discover_theater_formats(
        self,
        theater_name: str,
        lookback_days: int = 30
    ) -> Dict[str, List[str]]:
        """
        Discover what formats a theater offers.

        Returns:
            Dict mapping format categories to list of specific formats seen
        """
        cutoff_date = date.today() - timedelta(days=lookback_days)

        with get_session() as session:
            formats = session.query(distinct(Showing.format)).filter(
                and_(
                    Showing.company_id == self.company_id,
                    Showing.theater_name == theater_name,
                    Showing.play_date >= cutoff_date,
                    Showing.format.isnot(None),
                    Showing.format != ''
                )
            ).all()

            format_list = [f[0] for f in formats if f[0]]

            # Categorize formats
            result = defaultdict(list)
            for fmt in format_list:
                categorized = False
                for category, category_formats in FORMAT_CATEGORIES.items():
                    if fmt in category_formats:
                        result[category].append(fmt)
                        categorized = True
                        break

                if not categorized:
                    # Check if it's a standard format
                    fmt_lower = fmt.lower()
                    if any(x in fmt_lower for x in ['2d', 'digital', 'standard']):
                        result['standard'].append(fmt)
                    else:
                        result['other'].append(fmt)

            return dict(result)

    def estimate_screen_counts(
        self,
        theater_name: str,
        target_date: Optional[date] = None,
        lookback_days: int = 14
    ) -> Dict[str, int]:
        """
        Estimate screen counts per format by analyzing overlapping showtimes.

        For best accuracy, use a date with full programming (Saturday typically).

        Returns:
            Dict mapping format category to estimated screen count
        """
        if target_date is None:
            # Default to the most recent Saturday with data
            target_date = self._find_best_analysis_date(theater_name, lookback_days)

        if target_date is None:
            logger.warning(f"No suitable date found for {theater_name}")
            return {}

        with get_session() as session:
            # Get all showtimes for this theater on the target date
            showings = session.query(
                Showing.format,
                Showing.showtime
            ).filter(
                and_(
                    Showing.company_id == self.company_id,
                    Showing.theater_name == theater_name,
                    Showing.play_date == target_date,
                    Showing.format.isnot(None)
                )
            ).all()

            # Group by format category
            category_showtimes = defaultdict(list)

            for showing in showings:
                fmt = showing.format
                showtime = parse_showtime(showing.showtime)

                if not showtime:
                    continue

                # Find category
                for category, category_formats in FORMAT_CATEGORIES.items():
                    if fmt in category_formats:
                        category_showtimes[category].append(showtime)
                        break

            # Count overlaps for each category
            screen_counts = {}

            for category, times in category_showtimes.items():
                if times:
                    count = count_overlapping_shows(times)
                    screen_counts[category] = count
                    logger.info(
                        f"{theater_name}: {category} has {len(times)} showtimes, "
                        f"estimated {count} screen(s)"
                    )

            return screen_counts

    def get_detailed_plf_screens(
        self,
        theater_name: str,
        circuit_name: Optional[str] = None,
        lookback_days: int = 14
    ) -> Dict[str, any]:
        """
        Get detailed PLF screen information including:
        - Screen counts per format type (e.g., 2 IMAX, 1 Dolby)
        - Circuit-branded PLF (e.g., Marcus SuperScreen)
        - Generic "Premium Format" screen count (when format isn't specific)

        Returns:
            Dict with:
              - plf_screens: {format_type: count} (e.g., {"imax": 2, "dolby": 1})
              - circuit_plf: {brand_name: full_label} (e.g., {"superscreen": "Marcus SuperScreen DLX"})
              - generic_plf_count: int (count of generic "Premium Format" screens)
              - total_plf_screens: int
        """
        screen_counts = self.estimate_screen_counts(theater_name, lookback_days=lookback_days)

        # Detect circuit-branded PLF from theater name
        circuit_plf = self._detect_circuit_plf(theater_name, circuit_name)

        # Separate generic PLF count from specific formats
        generic_count = screen_counts.pop('premium_generic', 0)

        # Calculate total (specific PLF + generic, not double-counting circuit PLF)
        total_plf = sum(screen_counts.values()) + generic_count

        return {
            'plf_screens': screen_counts,
            'circuit_plf': circuit_plf,
            'generic_plf_count': generic_count,
            'total_plf_screens': total_plf,
        }

    def _detect_circuit_plf(
        self,
        theater_name: str,
        circuit_name: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Detect circuit-branded PLF formats from theater name.

        For example:
        - "Marcus Ronnie's Cinema + IMAX" with Marcus circuit → check for SuperScreen
        - Theater may have SuperScreen even if not in name (check showings data)

        Returns:
            Dict mapping brand key to full label (e.g., {"superscreen": "Marcus SuperScreen DLX"})
        """
        detected = {}
        name_lower = theater_name.lower()

        # Determine circuit from theater name if not provided
        if not circuit_name:
            for circuit in CIRCUIT_PLF_BRANDS.keys():
                if circuit in name_lower:
                    circuit_name = circuit
                    break

        if not circuit_name:
            return detected

        circuit_lower = circuit_name.lower()

        # Check if this circuit has branded PLF formats
        if circuit_lower in CIRCUIT_PLF_BRANDS:
            brands = CIRCUIT_PLF_BRANDS[circuit_lower]

            # Check theater name for each branded format
            for brand_key, brand_label in brands.items():
                if brand_key in name_lower:
                    detected[brand_key] = brand_label

            # Also check showings data for circuit PLF formats
            # (theater may have SuperScreen shows even if not in name)
            detected.update(self._detect_circuit_plf_from_showings(theater_name, circuit_lower))

        return detected

    def _detect_circuit_plf_from_showings(
        self,
        theater_name: str,
        circuit: str,
        lookback_days: int = 30
    ) -> Dict[str, str]:
        """Check showings data for circuit-branded PLF format names."""
        cutoff_date = date.today() - timedelta(days=lookback_days)
        detected = {}

        if circuit not in CIRCUIT_PLF_BRANDS:
            return detected

        brands = CIRCUIT_PLF_BRANDS[circuit]

        with get_session() as session:
            # Get all unique formats for this theater
            formats = session.query(distinct(Showing.format)).filter(
                and_(
                    Showing.company_id == self.company_id,
                    Showing.theater_name == theater_name,
                    Showing.play_date >= cutoff_date,
                    Showing.format.isnot(None)
                )
            ).all()

            format_list = [f[0].lower() for f in formats if f[0]]

            # Check each brand
            for brand_key, brand_label in brands.items():
                for fmt in format_list:
                    if brand_key in fmt or brand_label.lower() in fmt:
                        detected[brand_key] = brand_label
                        break

        return detected

    def analyze_plf_price_tiers(
        self,
        theater_name: str,
        ticket_type: str = 'Adult',
        lookback_days: int = 30,
        price_threshold: float = 1.50
    ) -> Dict[str, any]:
        """
        Analyze Premium Format pricing to detect distinct PLF types.

        When Fandango returns generic "Premium Format", different PLF types
        often have different prices (e.g., IMAX $18, SuperScreen $15).
        This method clusters PLF showings by price to identify distinct formats.

        Args:
            theater_name: Name of the theater
            ticket_type: Ticket type to analyze (default 'Adult')
            lookback_days: Days of data to analyze
            price_threshold: Minimum price difference to consider distinct tiers ($1.50 default)

        Returns:
            Dict with:
              - tiers: List of {price, count, screen_count, sample_films}
              - needs_verification: bool (True if multiple tiers found)
              - suggested_assignments: Dict mapping tier to likely format
        """
        cutoff_date = date.today() - timedelta(days=lookback_days)

        with get_session() as session:
            # Get all Premium Format showings with prices (join Showing + Price tables)
            showings = session.query(
                Price.price,
                Showing.showtime,
                Showing.play_date,
                Showing.film_title
            ).join(
                Price, Showing.showing_id == Price.showing_id
            ).filter(
                and_(
                    Showing.company_id == self.company_id,
                    Showing.theater_name == theater_name,
                    Showing.play_date >= cutoff_date,
                    Showing.format == 'Premium Format',
                    Price.ticket_type == ticket_type,
                    Price.price.isnot(None)
                )
            ).all()

            if not showings:
                return {
                    'tiers': [],
                    'needs_verification': False,
                    'suggested_assignments': {}
                }

            # Group by price (rounded to nearest $0.50 to handle minor variations)
            price_groups = defaultdict(list)
            for showing in showings:
                price = float(showing.price) if showing.price else 0
                # Round to nearest $0.50
                rounded_price = round(price * 2) / 2
                price_groups[rounded_price].append(showing)

            # Merge groups that are within threshold
            sorted_prices = sorted(price_groups.keys())
            merged_tiers = []
            current_tier = None

            for price in sorted_prices:
                if current_tier is None or (price - current_tier['max_price']) > price_threshold:
                    # Start new tier
                    current_tier = {
                        'min_price': price,
                        'max_price': price,
                        'prices': [price],
                        'showings': price_groups[price]
                    }
                    merged_tiers.append(current_tier)
                else:
                    # Merge into current tier
                    current_tier['max_price'] = price
                    current_tier['prices'].append(price)
                    current_tier['showings'].extend(price_groups[price])

            # Analyze each tier
            tiers = []
            for i, tier in enumerate(merged_tiers):
                # Calculate average price for this tier
                avg_price = sum(tier['prices']) / len(tier['prices'])

                # Count screen count by analyzing overlapping showtimes on best date
                screen_count = self._count_screens_for_price_tier(
                    theater_name, tier['min_price'], tier['max_price'], lookback_days
                )

                # Get sample films
                sample_films = list(set(s.film_title for s in tier['showings'][:5]))

                tiers.append({
                    'tier_id': i + 1,
                    'price': round(avg_price, 2),
                    'price_range': f"${tier['min_price']:.2f}-${tier['max_price']:.2f}",
                    'showing_count': len(tier['showings']),
                    'screen_count': screen_count,
                    'sample_films': sample_films[:3]
                })

            # Sort by price descending (highest = premium tier like IMAX)
            tiers.sort(key=lambda t: t['price'], reverse=True)

            # Suggest assignments based on price (higher price = IMAX, lower = circuit PLF)
            suggested = {}
            name_inferred = infer_plf_from_theater_name(theater_name)

            if len(tiers) >= 1 and name_inferred.get('has_imax'):
                suggested['tier_1'] = 'IMAX'
            if len(tiers) >= 2:
                # Check for circuit-branded PLF
                circuit_plf = self._detect_circuit_plf(theater_name, None)
                if circuit_plf:
                    brand_name = list(circuit_plf.values())[0]
                    suggested['tier_2'] = brand_name
                else:
                    suggested['tier_2'] = 'Premium Large Format'

            return {
                'tiers': tiers,
                'needs_verification': len(tiers) > 1,
                'suggested_assignments': suggested
            }

    def _count_screens_for_price_tier(
        self,
        theater_name: str,
        min_price: float,
        max_price: float,
        lookback_days: int
    ) -> int:
        """Count screens for a specific price tier using showtime overlap analysis."""
        target_date = self._find_best_analysis_date(theater_name, lookback_days)
        if not target_date:
            return 1

        with get_session() as session:
            # Get showtimes in this price range on the target date (join with Price)
            showings = session.query(Showing.showtime).join(
                Price, Showing.showing_id == Price.showing_id
            ).filter(
                and_(
                    Showing.company_id == self.company_id,
                    Showing.theater_name == theater_name,
                    Showing.play_date == target_date,
                    Showing.format == 'Premium Format',
                    Price.price >= min_price - 0.50,
                    Price.price <= max_price + 0.50
                )
            ).distinct().all()

            times = [parse_showtime(s[0]) for s in showings if s[0]]
            times = [t for t in times if t]

            if not times:
                return 1

            return count_overlapping_shows(times, threshold_minutes=10)

    def _find_best_analysis_date(
        self,
        theater_name: str,
        lookback_days: int
    ) -> Optional[date]:
        """Find the best date to analyze for screen counts (most showtimes)."""
        cutoff_date = date.today() - timedelta(days=lookback_days)

        with get_session() as session:
            # Build list of all PLF format names to search for
            # (Fandango often returns "Premium Format" which doesn't set is_plf flag)
            all_plf_formats = list(PLF_FORMATS) + ['Premium Format']

            # Find date with most premium format showtimes
            # Check both is_plf flag AND format name (to catch "Premium Format")
            from sqlalchemy import or_
            result = session.query(
                Showing.play_date,
                func.count(Showing.showing_id).label('count')
            ).filter(
                and_(
                    Showing.company_id == self.company_id,
                    Showing.theater_name == theater_name,
                    Showing.play_date >= cutoff_date,
                    or_(
                        Showing.is_plf == True,
                        Showing.format.in_(all_plf_formats)
                    )
                )
            ).group_by(
                Showing.play_date
            ).order_by(
                func.count(Showing.showing_id).desc()
            ).first()

            return result[0] if result else None

    def update_theater_amenities(
        self,
        theater_name: str,
        circuit_name: Optional[str] = None,
        lookback_days: int = 30
    ) -> TheaterAmenities:
        """
        Update or create theater amenities record from discovered data.

        Args:
            theater_name: Name of the theater
            circuit_name: Circuit name (e.g., "Marcus Theatres")
            lookback_days: How many days of data to analyze

        Returns:
            Updated TheaterAmenities record
        """
        # Discover formats
        formats = self.discover_theater_formats(theater_name, lookback_days)

        # Get detailed PLF screen counts (including circuit-branded PLF)
        detailed_plf = self.get_detailed_plf_screens(theater_name, circuit_name, lookback_days)
        plf_screens = detailed_plf.get('plf_screens', {})
        circuit_plf = detailed_plf.get('circuit_plf', {})
        generic_plf_count = detailed_plf.get('generic_plf_count', 0)

        with get_session() as session:
            # Get or create amenities record
            amenities = session.query(TheaterAmenities).filter(
                and_(
                    TheaterAmenities.company_id == self.company_id,
                    TheaterAmenities.theater_name == theater_name
                )
            ).first()

            if not amenities:
                amenities = TheaterAmenities(
                    company_id=self.company_id,
                    theater_name=theater_name
                )
                session.add(amenities)

            # Update circuit name if provided
            if circuit_name:
                amenities.circuit_name = circuit_name

            # Update format availability from showings data
            amenities.has_imax = 'imax' in formats
            amenities.has_dolby_cinema = 'dolby' in formats
            amenities.has_dolby_atmos = any('atmos' in f.lower() for f in formats.get('dolby', []))
            amenities.has_rpx = 'rpx' in formats
            amenities.has_4dx = '4dx' in formats
            amenities.has_screenx = 'screenx' in formats
            amenities.has_dbox = 'dbox' in formats

            # If no PLF detected from showings, infer from theater name
            # (Fandango often returns generic "Premium Format" instead of specific type)
            name_inferred = infer_plf_from_theater_name(theater_name)
            if not any([amenities.has_imax, amenities.has_dolby_cinema, amenities.has_rpx,
                        amenities.has_4dx, amenities.has_screenx, amenities.has_dbox]):
                amenities.has_imax = name_inferred.get('has_imax', False)
                amenities.has_dolby_cinema = name_inferred.get('has_dolby_cinema', False)
                amenities.has_dolby_atmos = name_inferred.get('has_dolby_atmos', False)
                amenities.has_rpx = name_inferred.get('has_rpx', False)
                amenities.has_4dx = name_inferred.get('has_4dx', False)
                amenities.has_screenx = name_inferred.get('has_screenx', False)
                amenities.has_dbox = name_inferred.get('has_dbox', False)
            else:
                # Still merge in name-inferred formats that weren't in showings
                # (theater may have IMAX even if no IMAX shows were scraped)
                if not amenities.has_imax and name_inferred.get('has_imax'):
                    amenities.has_imax = True
                if not amenities.has_dolby_cinema and name_inferred.get('has_dolby_cinema'):
                    amenities.has_dolby_cinema = True
                if not amenities.has_4dx and name_inferred.get('has_4dx'):
                    amenities.has_4dx = True
                if not amenities.has_screenx and name_inferred.get('has_screenx'):
                    amenities.has_screenx = True

            # Update per-format screen counts
            imax_count = plf_screens.get('imax', 0)
            dolby_count = plf_screens.get('dolby', 0)
            other_plf = sum(v for k, v in plf_screens.items() if k not in ('imax', 'dolby'))

            # If we have generic PLF but no specific counts, distribute them
            # based on what formats are available (name-inferred or detected)
            if generic_plf_count > 0 and imax_count == 0 and dolby_count == 0:
                if amenities.has_imax:
                    imax_count = max(1, generic_plf_count // 2)
                if amenities.has_dolby_cinema:
                    dolby_count = max(1, generic_plf_count // 2)
                # If neither specific PLF is detected, count as "other"
                if not amenities.has_imax and not amenities.has_dolby_cinema:
                    other_plf = generic_plf_count

            amenities.imax_screen_count = imax_count if imax_count > 0 else None
            amenities.dolby_screen_count = dolby_count if dolby_count > 0 else None
            amenities.plf_other_count = other_plf if other_plf > 0 else None

            # Store circuit-branded PLF info (as JSON string)
            amenities.set_circuit_plf(circuit_plf)

            # Total premium screen count (don't double-count generic PLF that was distributed)
            # If we distributed generic to specific formats, they're already counted
            if generic_plf_count > 0 and (imax_count > 0 or dolby_count > 0 or other_plf > 0):
                # Generic was distributed, don't add it again
                total_premium = imax_count + dolby_count + other_plf
            else:
                # Generic wasn't distributed or there was no generic
                total_premium = imax_count + dolby_count + other_plf + generic_plf_count
            amenities.premium_screen_count = total_premium if total_premium > 0 else None

            # Calculate rough total screen count from all showtimes
            total_screens = self._estimate_total_screens(theater_name, lookback_days)
            if total_screens:
                amenities.screen_count = total_screens

            # Update metadata
            amenities.source = 'scraped'
            amenities.last_verified = datetime.now(UTC)

            session.commit()
            session.refresh(amenities)

            logger.info(
                f"Updated amenities for {theater_name}: "
                f"IMAX={amenities.has_imax} (x{amenities.imax_screen_count or 0}), "
                f"Dolby={amenities.has_dolby_cinema} (x{amenities.dolby_screen_count or 0}), "
                f"4DX={amenities.has_4dx}, "
                f"circuit_plf={circuit_plf or 'none'}, "
                f"premium_screens={amenities.premium_screen_count}"
            )

            return amenities

    def _estimate_total_screens(
        self,
        theater_name: str,
        lookback_days: int
    ) -> Optional[int]:
        """
        Estimate total screen count considering film runtimes.

        Uses runtime-aware overlap calculation: a 2-hour film starting at 7:00 PM
        occupies that screen until ~9:20 PM (with trailers/cleanup buffer).

        Falls back to start-time overlap if no runtime data available.
        """
        target_date = self._find_best_analysis_date(theater_name, lookback_days)

        if not target_date:
            return None

        with get_session() as session:
            # Try to get showings with runtime from Film table
            # Join on film_title (normalized matching)
            from sqlalchemy import case, func as sqlfunc

            showings_with_runtime = session.query(
                Showing.showtime,
                Showing.film_title,
                Film.runtime
            ).outerjoin(
                Film,
                # Match on film title (case-insensitive)
                sqlfunc.lower(Showing.film_title).like(
                    sqlfunc.concat('%', sqlfunc.lower(Film.film_title), '%')
                )
            ).filter(
                and_(
                    Showing.company_id == self.company_id,
                    Showing.theater_name == theater_name,
                    Showing.play_date == target_date
                )
            ).all()

            if not showings_with_runtime:
                return None

            # Build list of (start_time, runtime) tuples
            showings_data = []
            has_runtime_data = False

            for showtime_str, film_title, runtime_str in showings_with_runtime:
                start_time = parse_showtime(showtime_str)
                if not start_time:
                    continue

                runtime_mins = parse_runtime(runtime_str)
                if runtime_str:  # We have actual runtime data
                    has_runtime_data = True

                showings_data.append((start_time, runtime_mins))

            if not showings_data:
                return None

            # Use runtime-aware calculation if we have runtime data
            if has_runtime_data:
                screen_count = count_screens_with_runtime(showings_data, buffer_minutes=20)
                logger.debug(
                    f"{theater_name}: Runtime-based screen estimate = {screen_count} "
                    f"({len(showings_data)} showings analyzed)"
                )
                return screen_count

            # Fall back to simple start-time overlap
            times = [s[0] for s in showings_data]
            return count_overlapping_shows(times, threshold_minutes=5)

    def discover_all_theaters(
        self,
        circuit_name: Optional[str] = None,
        lookback_days: int = 30
    ) -> List[TheaterAmenities]:
        """
        Discover amenities for all theaters (optionally filtered by circuit).

        Returns:
            List of updated TheaterAmenities records
        """
        with get_session() as session:
            # Find all theaters with recent data
            cutoff_date = date.today() - timedelta(days=lookback_days)

            query = session.query(distinct(Showing.theater_name)).filter(
                and_(
                    Showing.company_id == self.company_id,
                    Showing.play_date >= cutoff_date
                )
            )

            if circuit_name:
                # Filter by circuit name pattern
                query = query.filter(
                    Showing.theater_name.like(f"%{circuit_name}%")
                )

            theaters = [r[0] for r in query.all()]

        logger.info(f"Discovering amenities for {len(theaters)} theaters")

        results = []
        for theater in theaters:
            try:
                amenities = self.update_theater_amenities(
                    theater,
                    circuit_name=circuit_name,
                    lookback_days=lookback_days
                )
                results.append(amenities)
            except Exception as e:
                logger.error(f"Error updating amenities for {theater}: {e}")

        return results

    def get_format_summary(self, lookback_days: int = 30) -> Dict:
        """
        Get a summary of formats across all theaters.

        Returns:
            Dict with format statistics
        """
        cutoff_date = date.today() - timedelta(days=lookback_days)

        with get_session() as session:
            # Count theaters per format
            format_counts = session.query(
                Showing.format,
                func.count(distinct(Showing.theater_name)).label('theater_count')
            ).filter(
                and_(
                    Showing.company_id == self.company_id,
                    Showing.play_date >= cutoff_date,
                    Showing.format.isnot(None),
                    Showing.format != ''
                )
            ).group_by(
                Showing.format
            ).all()

            # Organize by category
            summary = {
                'by_format': {f[0]: f[1] for f in format_counts},
                'by_category': defaultdict(int),
                'total_theaters_with_plf': 0
            }

            plf_theaters = set()

            for fmt, count in format_counts:
                # Categorize
                for category, category_formats in FORMAT_CATEGORIES.items():
                    if fmt in category_formats:
                        summary['by_category'][category] += count
                        break

                # Track PLF
                if fmt in PLF_FORMATS:
                    # Get actual theater names with this format
                    theaters = session.query(distinct(Showing.theater_name)).filter(
                        and_(
                            Showing.company_id == self.company_id,
                            Showing.play_date >= cutoff_date,
                            Showing.format == fmt
                        )
                    ).all()
                    plf_theaters.update(t[0] for t in theaters)

            summary['total_theaters_with_plf'] = len(plf_theaters)
            summary['by_category'] = dict(summary['by_category'])

            return summary


# PLF patterns to detect from theater names
THEATER_NAME_PLF_PATTERNS = {
    'has_imax': ['imax', '+ imax', 'imax '],
    'has_dolby_cinema': ['dolby cinema', 'dolby'],
    'has_dolby_atmos': ['dolby atmos', 'atmos'],
    'has_rpx': ['rpx'],
    'has_4dx': ['4dx'],
    'has_screenx': ['screenx'],
    'has_dbox': ['d-box', 'dbox'],
    'has_xd': [' xd', 'and xd', '& xd'],  # Cinemark XD - be careful not to match random 'xd'
    'has_plf_generic': ['ultrascreen', 'bigscreen', 'gtx', 'ultravx', 'ultraavx', 'liemax'],
}

# Circuit-specific branded PLF formats
CIRCUIT_PLF_BRANDS = {
    'marcus': {
        'superscreen': 'Marcus SuperScreen DLX',
        'ultrascreen': 'Marcus UltraScreen',
        'take five': 'Marcus Take Five Lounge',
    },
    'cinemark': {
        'xd': 'Cinemark XD',
    },
    'amc': {
        'prime': 'AMC Prime',
        'dolby': 'AMC Dolby Cinema',
    },
    'regal': {
        'rpx': 'Regal Premium Experience',
    },
    'harkins': {
        'cine capri': 'Harkins Cine Capri',
        'ultimate': 'Harkins Ultimate',
    },
    'emagine': {
        'super emax': 'Emagine Super EMAX',
        'emax': 'Emagine EMAX',
    },
}


def infer_plf_from_theater_name(theater_name: str) -> Dict[str, bool]:
    """
    Infer PLF availability from theater name.

    Many theaters include their premium formats in the name:
    - "Marcus Ronnie's Cinema + IMAX"
    - "Regal Warrington Crossing ScreenX, 4DX & IMAX"
    - "Cinemark Century Aurora and XD"
    """
    name_lower = theater_name.lower()
    result = {}

    for field, patterns in THEATER_NAME_PLF_PATTERNS.items():
        result[field] = any(p in name_lower for p in patterns)

    return result


# Convenience function
def discover_theater_amenities(
    company_id: int,
    theater_name: str,
    lookback_days: int = 30
) -> TheaterAmenities:
    """Convenience function to discover amenities for a single theater."""
    service = TheaterAmenityDiscoveryService(company_id)
    return service.update_theater_amenities(theater_name, lookback_days=lookback_days)


def discover_all_amenities(
    company_id: int,
    circuit_name: Optional[str] = None,
    lookback_days: int = 30
) -> List[TheaterAmenities]:
    """Convenience function to discover amenities for all theaters."""
    service = TheaterAmenityDiscoveryService(company_id)
    return service.discover_all_theaters(circuit_name, lookback_days)
