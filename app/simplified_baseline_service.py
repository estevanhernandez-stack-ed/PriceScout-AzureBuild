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

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from app.db_models import (
    PriceBaseline, CompanyProfile, DiscountDayProgram,
    TheaterMetadata, EntTelligencePriceCache
)


# Known theater circuits for matching
KNOWN_CIRCUITS = [
    'Marcus', 'Movie Tavern', 'AMC', 'Regal', 'Cinemark',
    'B&B Theatres', 'LOOK Cinemas', 'Studio Movie Grill',
    'Alamo Drafthouse', 'Harkins', 'Landmark'
]


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

        Args:
            theater_name: Theater name
            ticket_type: Ticket type (Adult, Child, Senior, etc.)
            format_type: Format (Standard, IMAX, Dolby, etc.) or None
            daypart: Daypart (matinee, evening, late_night) or None

        Returns:
            Most specific matching PriceBaseline or None
        """
        base_query = self.session.query(PriceBaseline).filter(
            PriceBaseline.company_id == self.company_id,
            PriceBaseline.theater_name == theater_name,
            PriceBaseline.ticket_type == ticket_type,
            # Only consider active baselines (no end date or end date in future)
            or_(
                PriceBaseline.effective_to.is_(None),
                PriceBaseline.effective_to >= date.today()
            )
        )

        # Level 1: Exact match
        baseline = base_query.filter(
            PriceBaseline.format == format_type,
            PriceBaseline.daypart == daypart
        ).first()
        if baseline:
            return baseline

        # Level 2: Match format, any daypart
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

    def get_circuit_name(self, theater_name: str) -> Optional[str]:
        """
        Extract circuit name from theater name.

        First checks TheaterMetadata, then pattern matching.
        """
        # Check metadata first
        metadata = self.session.query(TheaterMetadata).filter(
            TheaterMetadata.company_id == self.company_id,
            TheaterMetadata.theater_name == theater_name
        ).first()

        if metadata and metadata.circuit_name:
            return metadata.circuit_name

        # Pattern matching fallback
        theater_lower = theater_name.lower()
        for circuit in KNOWN_CIRCUITS:
            if theater_lower.startswith(circuit.lower()):
                return circuit

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
        circuit_name = self.get_circuit_name(theater_name)
        if not circuit_name:
            return False, None

        day_of_week = check_date.weekday()  # 0=Monday, 6=Sunday

        # Find active discount program for this circuit and day
        program = self.session.query(DiscountDayProgram).filter(
            DiscountDayProgram.company_id == self.company_id,
            DiscountDayProgram.circuit_name == circuit_name,
            DiscountDayProgram.day_of_week == day_of_week,
            DiscountDayProgram.is_active == True
        ).first()

        if not program:
            return False, None

        # Check if program applies to the given parameters
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
            adjusted_baseline = self.adjust_for_tax_status(
                baseline.baseline_price, 'exclusive', 'inclusive'
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
