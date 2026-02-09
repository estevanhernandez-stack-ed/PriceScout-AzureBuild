"""
Simplified Baseline Service

This service handles baseline operations using the simplified matching system
where day_of_week is NOT part of the baseline matching. Discount days are
handled separately via DiscountDayProgram linked to CompanyProfile.

Matching hierarchy (most specific to least):
1. theater + ticket_type + format + daypart (exact match)
2. theater + ticket_type + format + NULL daypart (any daypart)
3. theater + ticket_type + NULL format + NULL daypart (any format/daypart)

Usage:
    from app.simplified_baseline_service import SimplifiedBaselineService

    service = SimplifiedBaselineService(session, company_id)
    baseline = service.find_baseline('Marcus Cinema', 'Adult', 'Standard', 'evening')
    is_discount, program = service.check_discount_day('Marcus Cinema', date(2024, 1, 16))
"""

from datetime import date, datetime, UTC
from decimal import Decimal
from typing import Optional, Tuple, List, Dict, Any
from collections import defaultdict
import json
import re

from sqlalchemy import and_, or_, func, case
from sqlalchemy.orm import Session

from app.db_models import (
    PriceBaseline, CompanyProfile, DiscountDayProgram,
    TheaterMetadata, EntTelligencePriceCache
)
from api.services.tax_estimation import (
    get_tax_config as _get_tax_config,
    get_tax_rate_for_theater,
    get_theater_state,
)


# Known theater circuits for matching
KNOWN_CIRCUITS = [
    'Marcus', 'Movie Tavern', 'AMC', 'Regal', 'Cinemark',
    'B&B Theatres', 'LOOK Cinemas', 'Studio Movie Grill',
    'Alamo Drafthouse', 'Harkins', 'Landmark'
]

# Normalize full corporation names from EntTelligence metadata to the short
# circuit names used by discount programs and company profiles.  Movie Tavern
# is a Marcus brand and shares the same discount/baseline programs.
CIRCUIT_NAME_NORMALIZE: dict[str, str] = {
    'Marcus Theatres Corporation': 'Marcus',
    'AMC Entertainment Inc': 'AMC',
    'Regal Entertainment Group': 'Regal',
    'Cinemark Theatres': 'Cinemark',
    'B & B Theatres': 'B&B Theatres',
    'Emagine Entertainment': 'Emagine',
    'Harkins Theatres': 'Harkins',
    'Malco Theatres': 'Malco',
    'Galaxy Theatres': 'Galaxy',
    'Megaplex Theatres': 'Megaplex',
    'Classic Cinemas': 'Classic',
    'ShowBiz Cinemas': 'ShowBiz',
    'ACX Cinemas': 'ACX',
    'Landmark Theatres': 'Landmark',
    'Alamo Drafthouse': 'Alamo Drafthouse',
    'LOOK Cinemas': 'LOOK Cinemas',
    'Studio Movie Grill': 'Studio Movie Grill',
    'Flix Brewhouse': 'Flix Brewhouse',
    # Movie Tavern is a Marcus brand — same discount programs apply
    'Movie Tavern': 'Marcus',
}


# Normalize legacy / inconsistent daypart values to canonical forms.
# Canonical dayparts: Matinee, Twilight, Prime, Late Night
# NOTE: 'Standard' is NOT a real daypart — it means the theater has flat
# pricing with no time-based variation.  find_baseline() treats 'Standard'
# as a wildcard fallback (similar to NULL daypart).
DAYPART_NORMALIZE: dict[str, str] = {
    'evening': 'Prime',
    'prime': 'Prime',
    'matinee': 'Matinee',
    'late': 'Late Night',
    'late night': 'Late Night',
    'late_night': 'Late Night',
    'twilight': 'Twilight',
}


def normalize_daypart(raw: Optional[str]) -> Optional[str]:
    """Normalize a daypart value to the canonical form.

    Handles case-insensitive matching of legacy values like 'evening' → 'Prime'.
    Returns None unchanged.
    """
    if not raw:
        return raw
    return DAYPART_NORMALIZE.get(raw.lower(), raw)


def classify_daypart(time_str: str) -> Optional[str]:
    """Classify a showtime string into a canonical daypart.

    Parses time strings like '7:30PM', '2:00 PM', '19:30' and returns
    one of: 'Matinee', 'Twilight', 'Prime', 'Late Night'.

    Cutoffs (matching enttelligence_baseline_discovery.py):
    - Matinee: before 4:00 PM
    - Twilight: 4:00 PM - 6:00 PM
    - Prime: 6:00 PM - 9:00 PM
    - Late Night: 9:00 PM and after
    """
    if not time_str or not isinstance(time_str, str):
        return None
    try:
        from datetime import time as dt_time
        import re as _re

        cleaned = time_str.lower().strip().replace('.', '').replace(' ', '')
        # Fix truncated am/pm
        if cleaned.endswith('p') and not cleaned.endswith('pm'):
            cleaned = cleaned[:-1] + 'pm'
        elif cleaned.endswith('a') and not cleaned.endswith('am'):
            cleaned = cleaned[:-1] + 'am'
        # Zero-pad single-digit hours: "7:30pm" → "07:30pm"
        match = _re.match(r'^(\d):(\d{2}(?:am|pm))$', cleaned)
        if match:
            cleaned = f"0{match.group(1)}:{match.group(2)}"
        cleaned = cleaned.upper()

        # Try 12-hour format first, then 24-hour
        time_obj = None
        from datetime import datetime as _dt
        for fmt in ("%I:%M%p", "%H:%M"):
            try:
                time_obj = _dt.strptime(cleaned, fmt).time()
                break
            except ValueError:
                continue
        if time_obj is None:
            return None

        if time_obj < dt_time(16, 0):
            return 'Matinee'
        elif time_obj < dt_time(18, 0):
            return 'Twilight'
        elif time_obj < dt_time(21, 0):
            return 'Prime'
        else:
            return 'Late Night'
    except (ValueError, AttributeError):
        return None


# Normalize ticket type typos and case inconsistencies.
# Only normalizes clear-cut duplicates — does NOT merge Adult/General Admission
# as those have different price points at the same theater.
TICKET_TYPE_NORMALIZE: dict[str, str] = {
    'early bird': 'Early Bird',
    'early': 'Early Bird',
    'lfx early bird': 'Early Bird',
    'matine': 'Matinee',
    'matine prime': 'Matinee',
    'tues mat': 'Matinee',
    'wednesday 50off': 'Bargain Wednesday',
    'bargain wednesday': 'Bargain Wednesday',
    'general': 'General Admission',
}


def normalize_ticket_type(raw: str) -> str:
    """Normalize a ticket type to canonical form.

    Fixes typos and case inconsistencies. Does not merge semantically
    different types like Adult vs General Admission.
    """
    if not raw:
        return raw
    return TICKET_TYPE_NORMALIZE.get(raw.lower(), raw)


# Normalize format strings across sources.
# Showings table uses 'Standard'; EntTelligence and baselines use '2D'.
# Both mean the same thing — standard digital projection (not 3D, IMAX, etc.).
FORMAT_NORMALIZE: dict[str, str] = {
    'standard': '2D',
}


def normalize_format(raw: Optional[str]) -> Optional[str]:
    """Normalize a format value to the canonical form.

    'Standard' (from Fandango scraper) → '2D' (baseline canonical).
    Returns None unchanged.
    """
    if not raw:
        return raw
    return FORMAT_NORMALIZE.get(raw.lower(), raw)


# Common low-value terms stripped from theater names for fuzzy matching.
_THEATER_STRIP_TERMS = sorted([
    'cinemas', 'cinema', 'cine', 'movies', 'theatres', 'theatre', 'theater',
    'showplace', 'imax', 'dolby', 'ultrascreen', 'xd', 'superscreen',
    'dine-in',
], key=len, reverse=True)
_THEATER_STRIP_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(t) for t in _THEATER_STRIP_TERMS) + r')\b',
    re.IGNORECASE,
)


def normalize_theater_name(name: str) -> str:
    """Strip common cinema terms for fuzzy matching.

    Used as a fallback in find_baseline() when an exact theater name match
    fails — e.g. 'Marcus Arnold Cine' matches 'Marcus Arnold Cinemas'.
    """
    stripped = _THEATER_STRIP_PATTERN.sub('', name.lower())
    stripped = re.sub(r'[^\w\s/-]', '', stripped)
    return re.sub(r'\s+', ' ', stripped).strip()


def normalize_circuit_name(raw: str) -> str:
    """Normalize a circuit name to the canonical short form.

    Handles both full corporation names from EntTelligence metadata and
    brand prefixes from pattern matching.  Movie Tavern maps to Marcus.
    """
    if raw in CIRCUIT_NAME_NORMALIZE:
        return CIRCUIT_NAME_NORMALIZE[raw]
    return raw


class SimplifiedBaselineService:
    """
    Service for simplified baseline operations without day_of_week matching.

    Key features:
    - Baseline matching ignores day_of_week
    - Discount days checked via DiscountDayProgram
    - Tax status tracking for cross-source comparisons
    - Coverage indicators for onboarding
    """

    def __init__(self, session: Session, company_id: int):
        self.session = session
        self.company_id = company_id
        self._theater_norm_cache: Optional[Dict[str, str]] = None

    def _get_theater_norm_map(self) -> Dict[str, str]:
        """Build a map of normalized_name → canonical theater_name (lazy, cached)."""
        if self._theater_norm_cache is not None:
            return self._theater_norm_cache

        names = self.session.query(PriceBaseline.theater_name).filter(
            PriceBaseline.company_id == self.company_id,
        ).distinct().all()

        # Map: normalized → first theater name seen (canonical)
        self._theater_norm_cache = {}
        for (name,) in names:
            norm = normalize_theater_name(name)
            if norm not in self._theater_norm_cache:
                self._theater_norm_cache[norm] = name
        return self._theater_norm_cache

    # Source preference: Fandango prices are customer-facing (tax-inclusive,
    # format-aware) and should always be preferred over EntTelligence when
    # both exist for the same theater.  EntTelligence prices have estimated
    # tax applied which introduces ~10-20% systematic error.
    _SOURCE_PRIORITY = case(
        (PriceBaseline.source == 'fandango', 0),
        else_=1,
    )

    def _find_baseline_for_theater(
        self,
        theater_name: str,
        ticket_type: str,
        format_type: Optional[str],
        daypart: Optional[str],
    ) -> Optional[PriceBaseline]:
        """Run the matching hierarchy for a specific theater name.

        At each level, prefers Fandango baselines over EntTelligence when
        both sources provide a match for the same dimensions.
        """
        base_query = self.session.query(PriceBaseline).filter(
            PriceBaseline.company_id == self.company_id,
            PriceBaseline.theater_name == theater_name,
            PriceBaseline.ticket_type == ticket_type,
            or_(
                PriceBaseline.effective_to.is_(None),
                PriceBaseline.effective_to >= date.today()
            )
        ).order_by(self._SOURCE_PRIORITY)

        # Level 1: Exact match
        baseline = base_query.filter(
            PriceBaseline.format == format_type,
            PriceBaseline.daypart == daypart
        ).first()
        if baseline:
            return baseline

        # Level 2: Match format, any daypart (NULL = flat pricing / wildcard)
        baseline = base_query.filter(
            PriceBaseline.format == format_type,
            PriceBaseline.daypart.is_(None)
        ).first()
        if baseline:
            return baseline

        # Level 3: Any format, any daypart
        baseline = base_query.filter(
            PriceBaseline.format.is_(None),
            PriceBaseline.daypart.is_(None)
        ).first()
        if baseline:
            return baseline

        # Level 4: Match daypart, any format (less common case)
        baseline = base_query.filter(
            PriceBaseline.format.is_(None),
            PriceBaseline.daypart == daypart
        ).first()

        return baseline

    def find_baseline(
        self,
        theater_name: str,
        ticket_type: str,
        format_type: Optional[str] = None,
        daypart: Optional[str] = None
    ) -> Optional[PriceBaseline]:
        """
        Find the most specific matching baseline for the given parameters.

        Matching hierarchy (tries in order until found):
        1. Exact match: theater + ticket + format + daypart
        2. Any daypart: theater + ticket + format + NULL
        3. Any format/daypart: theater + ticket + NULL + NULL
        4. Match daypart, any format

        If no match on the exact theater name, falls back to a normalized
        name search (strips 'Cinema'/'Cinemas'/'Cine'/etc.) to handle
        cross-source naming differences.

        Args:
            theater_name: Theater name
            ticket_type: Ticket type (Adult, Child, Senior, etc.)
            format_type: Format (Standard, IMAX, Dolby, etc.) or None
            daypart: Daypart (Matinee, Prime, Late Night, Twilight) or None

        Returns:
            Most specific matching PriceBaseline or None
        """
        daypart = normalize_daypart(daypart)
        ticket_type = normalize_ticket_type(ticket_type)
        format_type = normalize_format(format_type)

        # Try exact theater name first
        baseline = self._find_baseline_for_theater(
            theater_name, ticket_type, format_type, daypart
        )
        if baseline:
            return baseline

        # Fallback: look up the normalized name to find a variant
        norm = normalize_theater_name(theater_name)
        norm_map = self._get_theater_norm_map()
        canonical = norm_map.get(norm)
        if canonical and canonical != theater_name:
            return self._find_baseline_for_theater(
                canonical, ticket_type, format_type, daypart
            )

        return None

    def get_circuit_name(self, theater_name: str) -> Optional[str]:
        """
        Extract circuit name from theater name.

        First checks TheaterMetadata, then pattern matching.
        Always normalizes to the canonical short form so that discount
        programs and company profiles match correctly.
        """
        # Check metadata first
        metadata = self.session.query(TheaterMetadata).filter(
            TheaterMetadata.company_id == self.company_id,
            TheaterMetadata.theater_name == theater_name
        ).first()

        if metadata and metadata.circuit_name:
            return normalize_circuit_name(metadata.circuit_name)

        # Pattern matching fallback
        theater_lower = theater_name.lower()
        for circuit in KNOWN_CIRCUITS:
            if theater_lower.startswith(circuit.lower()):
                return normalize_circuit_name(circuit)

        return None

    def check_discount_day(
        self,
        theater_name: str,
        check_date: date,
        ticket_type: Optional[str] = None,
        format_type: Optional[str] = None,
        daypart: Optional[str] = None
    ) -> Tuple[bool, Optional[DiscountDayProgram]]:
        """
        Check if a given date is a discount day for the theater's circuit.

        Args:
            theater_name: Theater name
            check_date: Date to check
            ticket_type: Optional ticket type to check applicability
            format_type: Optional format to check applicability
            daypart: Optional daypart to check applicability

        Returns:
            Tuple of (is_discount_day, program) where program is the
            DiscountDayProgram if applicable, None otherwise
        """
        daypart = normalize_daypart(daypart)
        circuit_name = self.get_circuit_name(theater_name)
        if not circuit_name:
            return False, None

        day_of_week = check_date.weekday()  # 0=Monday, 6=Sunday

        # Find active discount programs for this circuit and day (may be
        # multiple — e.g. AMC has separate programs for different dayparts).
        programs = self.session.query(DiscountDayProgram).filter(
            DiscountDayProgram.company_id == self.company_id,
            DiscountDayProgram.circuit_name == circuit_name,
            DiscountDayProgram.day_of_week == day_of_week,
            DiscountDayProgram.is_active == True
        ).all()

        if not programs:
            return False, None

        # Check each matching program — return the first one that applies
        for program in programs:
            if program.applies_to(ticket_type, format_type, daypart):
                return True, program

        return False, None

    def get_discount_price(self, program: DiscountDayProgram, regular_price: Decimal) -> Decimal:
        """
        Calculate the expected discount price based on the program type.

        Args:
            program: The DiscountDayProgram
            regular_price: The regular (non-discount) baseline price

        Returns:
            Expected discount price
        """
        if program.discount_type == 'flat_price':
            return program.discount_value
        elif program.discount_type == 'percentage_off':
            discount = regular_price * (program.discount_value / 100)
            return regular_price - discount
        elif program.discount_type == 'amount_off':
            return max(Decimal('0'), regular_price - program.discount_value)
        else:
            return regular_price

    def adjust_for_tax_status(
        self,
        price: Decimal,
        source_tax_status: str,
        target_tax_status: str,
        tax_rate: Decimal = Decimal('0.09')  # Default 9% tax
    ) -> Decimal:
        """
        Adjust a price when comparing sources with different tax inclusion.

        Args:
            price: The price to adjust
            source_tax_status: Tax status of the source ('inclusive', 'exclusive', 'unknown')
            target_tax_status: Tax status to convert to
            tax_rate: Tax rate to use (default 9%)

        Returns:
            Adjusted price
        """
        if source_tax_status == target_tax_status:
            return price

        if source_tax_status == 'exclusive' and target_tax_status == 'inclusive':
            # Add tax
            return price * (1 + tax_rate)
        elif source_tax_status == 'inclusive' and target_tax_status == 'exclusive':
            # Remove tax
            return price / (1 + tax_rate)

        return price

    def discover_simplified_baselines(
        self,
        theater_names: List[str],
        lookback_days: int = 30,
        min_samples: int = 5,
        source: str = 'enttelligence'
    ) -> List[Dict[str, Any]]:
        """
        Discover simplified baselines from price data.

        Aggregates prices across all days (excluding detected discount days)
        to create simplified baselines.

        Args:
            theater_names: List of theater names to discover baselines for
            lookback_days: Number of days to look back for price data
            min_samples: Minimum samples required to create a baseline
            source: Data source ('enttelligence' or 'fandango')

        Returns:
            List of discovered baseline dictionaries
        """
        from datetime import timedelta

        cutoff_date = date.today() - timedelta(days=lookback_days)
        discovered = []

        if source == 'enttelligence':
            # Query EntTelligence price cache
            prices = self.session.query(
                EntTelligencePriceCache.theater_name,
                EntTelligencePriceCache.ticket_type,
                EntTelligencePriceCache.format,
                EntTelligencePriceCache.play_date,
                EntTelligencePriceCache.price
            ).filter(
                EntTelligencePriceCache.company_id == self.company_id,
                EntTelligencePriceCache.theater_name.in_(theater_names),
                EntTelligencePriceCache.play_date >= cutoff_date
            ).all()
        else:
            # Would query Fandango data
            prices = []

        if not prices:
            return discovered

        # Group by theater/ticket/format
        groups = defaultdict(lambda: defaultdict(list))
        for p in prices:
            key = (p.theater_name, p.ticket_type, p.format or 'Standard')
            day_of_week = p.play_date.weekday()
            groups[key][day_of_week].append(float(p.price))

        # For each group, detect discount days and calculate simplified baseline
        for key, prices_by_day in groups.items():
            theater_name, ticket_type, format_type = key

            # Calculate overall stats
            all_prices = []
            for day_prices in prices_by_day.values():
                all_prices.extend(day_prices)

            if len(all_prices) < min_samples:
                continue

            overall_avg = sum(all_prices) / len(all_prices)

            # Detect discount days
            discount_days = []
            for day_num, day_prices in prices_by_day.items():
                if len(day_prices) < 3:
                    continue
                day_avg = sum(day_prices) / len(day_prices)
                day_variance = (max(day_prices) - min(day_prices)) / day_avg if day_avg > 0 else 0
                below_avg = (overall_avg - day_avg) / overall_avg if overall_avg > 0 else 0

                if day_variance <= 0.03 and below_avg >= 0.15:
                    discount_days.append(day_num)

            # Calculate baseline from non-discount days
            baseline_prices = []
            for day_num, day_prices in prices_by_day.items():
                if day_num not in discount_days:
                    baseline_prices.extend(day_prices)

            if not baseline_prices:
                baseline_prices = all_prices

            # Use 25th percentile as conservative baseline
            baseline_prices.sort()
            idx = max(0, int(len(baseline_prices) * 0.25) - 1)
            baseline_price = baseline_prices[idx]

            discovered.append({
                'theater_name': theater_name,
                'ticket_type': ticket_type,
                'format': format_type if format_type != 'Standard' else None,
                'daypart': None,  # Simplified - no daypart
                'baseline_price': round(baseline_price, 2),
                'sample_count': len(all_prices),
                'source': source,
                'tax_status': 'exclusive' if source == 'enttelligence' else 'inclusive',
                'discount_days_detected': discount_days
            })

        return discovered

    def get_coverage_indicators(self, theater_name: str) -> Dict[str, Any]:
        """
        Get coverage indicators for a theater's baselines.

        Returns information about what baselines exist and what's missing.
        """
        # Get existing baselines
        baselines = self.session.query(PriceBaseline).filter(
            PriceBaseline.company_id == self.company_id,
            PriceBaseline.theater_name == theater_name,
            or_(
                PriceBaseline.effective_to.is_(None),
                PriceBaseline.effective_to >= date.today()
            )
        ).all()

        # Extract discovered dimensions
        formats = set()
        ticket_types = set()
        dayparts = set()

        for b in baselines:
            if b.format:
                formats.add(b.format)
            if b.ticket_type:
                ticket_types.add(b.ticket_type)
            if b.daypart:
                dayparts.add(b.daypart)

        # Expected dimensions (can be customized per circuit)
        expected_formats = {'Standard', 'IMAX', 'Dolby Cinema', '3D'}
        expected_ticket_types = {'Adult', 'Child', 'Senior'}
        expected_dayparts = {'matinee', 'evening', 'late_night'}

        # Calculate coverage
        format_coverage = len(formats) / len(expected_formats) if expected_formats else 1.0
        ticket_coverage = len(ticket_types) / len(expected_ticket_types) if expected_ticket_types else 1.0
        daypart_coverage = len(dayparts) / len(expected_dayparts) if expected_dayparts else 1.0

        overall_score = (format_coverage + ticket_coverage + daypart_coverage) / 3

        return {
            'theater_name': theater_name,
            'baseline_count': len(baselines),
            'formats_discovered': list(formats),
            'formats_expected': list(expected_formats),
            'format_coverage': round(format_coverage, 2),
            'ticket_types_discovered': list(ticket_types),
            'ticket_types_expected': list(expected_ticket_types),
            'ticket_type_coverage': round(ticket_coverage, 2),
            'dayparts_discovered': list(dayparts),
            'dayparts_expected': list(expected_dayparts),
            'daypart_coverage': round(daypart_coverage, 2),
            'overall_score': round(overall_score, 2),
            'gaps': {
                'formats': list(expected_formats - formats),
                'ticket_types': list(expected_ticket_types - ticket_types),
                'dayparts': list(expected_dayparts - dayparts)
            }
        }

    def compare_to_baseline(
        self,
        theater_name: str,
        ticket_type: str,
        format_type: str,
        daypart: str,
        current_price: Decimal,
        play_date: date
    ) -> Dict[str, Any]:
        """
        Compare a current price to the baseline, accounting for discount days.

        Returns comparison result with surge detection.
        """
        # Check if it's a discount day
        is_discount, discount_program = self.check_discount_day(
            theater_name, play_date, ticket_type, format_type, daypart
        )

        # Find baseline
        baseline = self.find_baseline(theater_name, ticket_type, format_type, daypart)

        if not baseline:
            return {
                'has_baseline': False,
                'message': 'No baseline found for comparison'
            }

        # Adjust for tax status if needed
        adjusted_price = current_price
        if baseline.tax_status == 'exclusive' and baseline.source == 'enttelligence':
            # Assume current price is inclusive, convert baseline to inclusive for comparison
            # Use per-theater tax rate instead of hardcoded default
            tax_cfg = _get_tax_config(self.company_id)
            theater_st = get_theater_state(self.company_id, theater_name)
            theater_tax_rate = Decimal(str(get_tax_rate_for_theater(
                tax_cfg, theater_st, theater_name=theater_name
            )))
            if theater_tax_rate <= 0:
                theater_tax_rate = Decimal('0.075')
            adjusted_baseline = self.adjust_for_tax_status(
                baseline.baseline_price, 'exclusive', 'inclusive', tax_rate=theater_tax_rate
            )
        else:
            adjusted_baseline = baseline.baseline_price

        # Calculate difference
        if is_discount:
            # Compare to expected discount price
            expected_price = self.get_discount_price(discount_program, adjusted_baseline)
            difference = float(adjusted_price) - float(expected_price)
            difference_pct = (difference / float(expected_price)) * 100 if expected_price > 0 else 0
            comparison_type = 'discount_day'
        else:
            # Compare to regular baseline
            difference = float(adjusted_price) - float(adjusted_baseline)
            difference_pct = (difference / float(adjusted_baseline)) * 100 if adjusted_baseline > 0 else 0
            comparison_type = 'regular'

        return {
            'has_baseline': True,
            'comparison_type': comparison_type,
            'baseline_price': float(adjusted_baseline),
            'current_price': float(adjusted_price),
            'difference': round(difference, 2),
            'difference_pct': round(difference_pct, 1),
            'is_discount_day': is_discount,
            'discount_program': discount_program.program_name if discount_program else None,
            'baseline_source': baseline.source,
            'baseline_tax_status': baseline.tax_status,
            'is_surge': difference_pct >= 20.0 and not is_discount,
            'surge_multiplier': round(1 + (difference_pct / 100), 2) if difference_pct > 0 else 1.0
        }
