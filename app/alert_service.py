"""
Alert Service for PriceScout
Generates price change and surge pricing alerts after each scrape.

Enhanced with simplified baseline matching (no day_of_week) and
circuit-level discount day detection from Company Profiles.

Usage:
    from app.alert_service import generate_alerts_for_scrape

    # After saving prices from a scrape
    alerts = generate_alerts_for_scrape(company_id=1, run_id=123, prices_df=df)
"""

from datetime import datetime, date, UTC
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import logging

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from app.db_session import get_session
from app.db_models import (
    Price, Showing, PriceAlert, AlertConfiguration, PriceBaseline,
    DiscountProgram, DiscountDayProgram, TheaterMetadata
)
from app.simplified_baseline_service import SimplifiedBaselineService, KNOWN_CIRCUITS, normalize_circuit_name, normalize_daypart, normalize_ticket_type, normalize_format
from api.services.tax_estimation import (
    get_tax_config,
    get_tax_rate_for_theater,
    get_theater_state,
)

logger = logging.getLogger(__name__)


class AlertService:
    """Service for generating and managing price alerts.

    Enhanced with:
    - Simplified baseline matching (no day_of_week granularity)
    - Circuit-level discount day detection from DiscountDayProgram
    - Tax status adjustment for cross-source comparisons
    - Potential new pattern detection when confidence is low
    """

    def __init__(self, company_id: int):
        self.company_id = company_id
        self._config: Optional[AlertConfiguration] = None
        self._baselines_cache: Dict[str, PriceBaseline] = {}
        self._discount_programs_cache: Dict[str, List['DiscountProgram']] = {}  # theater_name -> list of programs
        # NEW: Circuit-level discount programs from Company Profiles
        self._circuit_discount_cache: Dict[str, List['DiscountDayProgram']] = {}  # circuit_name -> list of programs
        self._theater_circuit_cache: Dict[str, str] = {}  # theater_name -> circuit_name
        self._simplified_service: Optional[SimplifiedBaselineService] = None
        self._tax_config: Optional[Dict] = None
        self._theater_state_cache: Dict[str, Optional[str]] = {}

    def get_config(self, session: Session) -> AlertConfiguration:
        """Load or create default configuration for company."""
        if self._config is None:
            self._config = session.query(AlertConfiguration).filter(
                AlertConfiguration.company_id == self.company_id
            ).first()

            if not self._config:
                # Return default config (not persisted)
                self._config = AlertConfiguration(
                    company_id=self.company_id,
                    min_price_change_percent=Decimal('5.0'),
                    min_price_change_amount=Decimal('1.00'),
                    surge_threshold_percent=Decimal('20.0'),
                    alert_on_increase=True,
                    alert_on_decrease=True,
                    alert_on_new_offering=True,
                    alert_on_discontinued=False,
                    alert_on_surge=True,
                    notification_enabled=True
                )
        return self._config

    def process_scrape_results(self, run_id: int, prices_df) -> List[PriceAlert]:
        """
        Process newly scraped prices and generate alerts.

        Args:
            run_id: The scrape run ID
            prices_df: DataFrame of newly saved prices with columns:
                       Theater Name, Ticket Type, Format, Price, Film Title, play_date, Daypart

        Returns:
            List of generated PriceAlert objects
        """
        alerts = []

        if prices_df is None or len(prices_df) == 0:
            logger.debug("No prices to process for alerts")
            return alerts

        with get_session() as session:
            config = self.get_config(session)

            # Initialize SimplifiedBaselineService for enhanced matching
            self._simplified_service = SimplifiedBaselineService(session, self.company_id)

            # Pre-load discount programs FIRST so baseline cache can filter them out
            self._load_discount_programs_cache(session)

            # Pre-load circuit-level discount programs from Company Profiles
            self._load_circuit_discount_programs_cache(session)

            # Pre-load baselines AFTER discount programs (so we can exclude discount day baselines)
            self._load_baselines_cache(session)

            # Track unique theater/ticket_type/format combinations to avoid duplicate alerts
            processed_combinations = set()

            for _, row in prices_df.iterrows():
                theater_name = row.get('Theater Name', '')
                ticket_type = normalize_ticket_type(row.get('Ticket Type', '')) or ''
                format_type = self._normalize_format(row.get('Format', '2D') or '2D')

                # Parse price - handle both "$XX.XX" strings and numeric values
                price_val = row.get('Price', 0)
                if isinstance(price_val, str):
                    price_val = price_val.replace('$', '').replace(',', '')
                try:
                    new_price = Decimal(str(price_val))
                except (ValueError, TypeError, ArithmeticError):
                    logger.warning(f"Could not parse price: {price_val}")
                    continue

                play_date = row.get('play_date')
                film_title = row.get('Film Title', '')
                daypart = normalize_daypart(row.get('Daypart', '')) or ''

                # Create unique key for this combination (including daypart for apples-to-apples)
                combo_key = f"{theater_name}|{ticket_type}|{format_type}|{daypart}"

                # Skip if we've already processed this combination in this run
                if combo_key in processed_combinations:
                    continue
                processed_combinations.add(combo_key)

                # 1. Check for price change vs previous scrape
                price_change_alert = self._check_price_change(
                    session, config, theater_name, ticket_type, format_type,
                    daypart, new_price, film_title, play_date
                )
                if price_change_alert:
                    alerts.append(price_change_alert)
                    session.add(price_change_alert)

                # 2. Check for surge pricing
                surge_alert = self._check_surge_pricing(
                    session, config, theater_name, ticket_type, format_type,
                    daypart, new_price, film_title, play_date
                )
                if surge_alert:
                    alerts.append(surge_alert)
                    session.add(surge_alert)

            # Commit all alerts
            if alerts:
                session.flush()
                logger.info(f"Generated {len(alerts)} alerts for run {run_id}")

        return alerts

    def _is_discount_day_of_week(self, theater_name: str, day_of_week: int) -> bool:
        """Check if a day_of_week is a known discount day for this theater's circuit.

        Handles circuit name mismatches between metadata (e.g., 'Marcus Theatres Corporation')
        and discount program entries (e.g., 'Marcus') by trying both exact and pattern matches.
        """
        circuit = self._get_circuit_for_theater(theater_name)

        # Try exact match first
        if circuit:
            programs = self._circuit_discount_cache.get(circuit, [])
            if any(p.day_of_week == day_of_week for p in programs):
                return True

        # Try matching against all cached circuit names (handles short vs full name mismatches)
        theater_lower = theater_name.lower()
        for cached_circuit, programs in self._circuit_discount_cache.items():
            if theater_lower.startswith(cached_circuit.lower()):
                if any(p.day_of_week == day_of_week for p in programs):
                    return True

        return False

    @staticmethod
    def _normalize_format(fmt: str) -> str:
        """Delegate to the shared normalize_format function."""
        return normalize_format(fmt) or fmt

    def _load_baselines_cache(self, session: Session):
        """Pre-load all active baselines for this company.

        Baselines are keyed by: theater|ticket_type|format|daypart
        Discount day baselines are excluded from the normal cache so that
        normal-day prices are only compared to normal-day baselines.
        Discount days are handled separately via DiscountDayProgram.

        NOTE: _load_circuit_discount_programs_cache() MUST be called before this
        method so that discount day filtering works correctly.
        """
        today = date.today()
        baselines = session.query(PriceBaseline).filter(
            and_(
                PriceBaseline.company_id == self.company_id,
                PriceBaseline.effective_from <= today,
                or_(
                    PriceBaseline.effective_to.is_(None),
                    PriceBaseline.effective_to >= today
                )
            )
        ).all()

        skipped_discount = 0
        for baseline in baselines:
            # Skip baselines from known discount days - these should only be
            # compared to other discount day prices, not used as the baseline
            # for normal day surge detection
            if baseline.day_of_week is not None:
                if self._is_discount_day_of_week(baseline.theater_name, baseline.day_of_week):
                    skipped_discount += 1
                    continue

            # Normalize format: "Standard" → "2D" so both sources match
            fmt = self._normalize_format(baseline.format) or '*'
            key = f"{baseline.theater_name}|{baseline.ticket_type}|{fmt}|{baseline.daypart or '*'}"
            existing = self._baselines_cache.get(key)
            if not existing:
                self._baselines_cache[key] = baseline
            elif baseline.format and baseline.daypart:
                # When multiple non-discount baselines share the same key,
                # prefer the one with more samples (more reliable)
                if hasattr(baseline, 'sample_count') and hasattr(existing, 'sample_count'):
                    if (baseline.sample_count or 0) > (existing.sample_count or 0):
                        self._baselines_cache[key] = baseline
                elif existing.baseline_price < baseline.baseline_price:
                    self._baselines_cache[key] = baseline

        logger.info(f"Loaded {len(self._baselines_cache)} baselines into cache "
                    f"(skipped {skipped_discount} discount day baselines)")

    def _find_baseline(self, theater_name: str, ticket_type: str,
                       format_type: str, daypart: str,
                       day_of_week: Optional[int] = None) -> Optional[PriceBaseline]:
        """Find the most specific matching baseline from cache.

        SIMPLIFIED: day_of_week is no longer part of baseline matching.
        Discount days are handled separately via DiscountDayProgram.

        Matching priority (most specific to least):
        1. theater|ticket_type|format|daypart (exact match)
        2. theater|ticket_type|format|* (any daypart)
        3. theater|ticket_type|*|daypart (any format)
        4. theater|ticket_type|*|* (most general)

        NOTE: 3D and PLF are NOT interchangeable — they have different pricing.
        Only Fandango provides accurate PLF labels; EntTelligence lumps PLF
        into '2D'. Format normalization maps 'Standard' ↔ '2D' only.
        """
        # NOTE: day_of_week parameter kept for backward compatibility but not used

        # Normalize format: "Standard" → "2D"
        format_type = self._normalize_format(format_type)

        # Try most specific first, then fall back to more general
        keys_to_try = [
            # Exact match
            f"{theater_name}|{ticket_type}|{format_type}|{daypart}",
            # Wildcard daypart
            f"{theater_name}|{ticket_type}|{format_type}|*",
            # Wildcard format
            f"{theater_name}|{ticket_type}|*|{daypart}",
            # Most general
            f"{theater_name}|{ticket_type}|*|*",
        ]

        for key in keys_to_try:
            if key in self._baselines_cache:
                return self._baselines_cache[key]

        return None

    def _load_discount_programs_cache(self, session: Session):
        """Pre-load all active discount programs for this company (legacy theater-level)."""
        programs = session.query(DiscountProgram).filter(
            and_(
                DiscountProgram.company_id == self.company_id,
                DiscountProgram.is_active == True
            )
        ).all()

        for program in programs:
            theater = program.theater_name
            if theater not in self._discount_programs_cache:
                self._discount_programs_cache[theater] = []
            self._discount_programs_cache[theater].append(program)

    def _load_circuit_discount_programs_cache(self, session: Session):
        """Pre-load circuit-level discount programs from Company Profiles.

        These are the new DiscountDayProgram entries linked to circuits,
        which handle discount days like "$5 Tuesdays" at the chain level.
        """
        # Load all active circuit discount programs
        programs = session.query(DiscountDayProgram).filter(
            and_(
                DiscountDayProgram.company_id == self.company_id,
                DiscountDayProgram.is_active == True
            )
        ).all()

        for program in programs:
            circuit = program.circuit_name
            if circuit not in self._circuit_discount_cache:
                self._circuit_discount_cache[circuit] = []
            self._circuit_discount_cache[circuit].append(program)

        logger.debug(f"Loaded {len(programs)} circuit-level discount programs")

        # Load theater -> circuit mappings from TheaterMetadata
        metadata = session.query(TheaterMetadata).filter(
            TheaterMetadata.company_id == self.company_id
        ).all()

        for m in metadata:
            if m.circuit_name:
                self._theater_circuit_cache[m.theater_name] = normalize_circuit_name(m.circuit_name)

        # Also detect circuits from theater names for theaters not in metadata
        # This ensures we can match even without explicit metadata entries
        logger.debug(f"Loaded {len(self._theater_circuit_cache)} theater-circuit mappings")

    def _get_circuit_for_theater(self, theater_name: str) -> Optional[str]:
        """Get the circuit name for a theater.

        First checks metadata cache, then falls back to pattern matching.
        """
        # Check cache first (already normalized during load)
        if theater_name in self._theater_circuit_cache:
            return self._theater_circuit_cache[theater_name]

        # Pattern matching fallback — normalize to canonical short form
        theater_lower = theater_name.lower()
        for circuit in KNOWN_CIRCUITS:
            if theater_lower.startswith(circuit.lower()):
                normalized = normalize_circuit_name(circuit)
                self._theater_circuit_cache[theater_name] = normalized
                return normalized

        return None

    def _check_discount_day_from_profile(
        self,
        theater_name: str,
        play_date,
        ticket_type: Optional[str] = None,
        format_type: Optional[str] = None,
        daypart: Optional[str] = None
    ) -> Tuple[bool, Optional[DiscountDayProgram], Optional[Decimal]]:
        """Check if a date is a circuit-level discount day from Company Profiles.

        This is the NEW method that checks DiscountDayProgram entries linked
        to circuits (chains) rather than individual theaters.

        Args:
            theater_name: Theater name to check
            play_date: Date to check
            ticket_type: Optional ticket type for applicability check
            format_type: Optional format for applicability check
            daypart: Optional daypart for applicability check

        Returns:
            Tuple of (is_discount_day, matching_program, expected_discount_price)
        """
        if play_date is None:
            return False, None, None

        # Get day of week (0=Monday, 6=Sunday)
        if not hasattr(play_date, 'weekday'):
            return False, None, None
        day_of_week = play_date.weekday()

        # Get the circuit for this theater
        circuit = self._get_circuit_for_theater(theater_name)
        if not circuit:
            return False, None, None

        # Check circuit discount programs
        programs = self._circuit_discount_cache.get(circuit, [])

        for program in programs:
            if program.day_of_week != day_of_week:
                continue

            # Check applicability using the program's applies_to method
            if not program.applies_to(ticket_type, format_type, daypart):
                continue

            # Calculate expected discount price if we have baseline context
            expected_price = None
            if program.discount_type == 'flat_price':
                expected_price = program.discount_value

            return True, program, expected_price

        return False, None, None

    def _is_discount_day(self, theater_name: str, play_date, ticket_type: str = None,
                         format_type: str = None, daypart: str = None) -> Tuple[bool, Optional[object]]:
        """
        Check if a play_date falls on a known discount day for the theater.

        Checks both:
        1. Circuit-level discount programs (DiscountDayProgram from Company Profiles) - NEW
        2. Theater-level discount programs (DiscountProgram - legacy)

        Args:
            theater_name: Theater name to check
            play_date: The date to check (date or datetime object)
            ticket_type: Optional - check if program applies to this ticket type
            format_type: Optional - check if program applies to this format
            daypart: Optional - check if program applies to this daypart

        Returns:
            Tuple of (is_discount_day: bool, matching_program: DiscountProgram or DiscountDayProgram or None)
        """
        if play_date is None:
            return False, None

        # Get day of week (0=Monday, 6=Sunday)
        if hasattr(play_date, 'weekday'):
            day_of_week = play_date.weekday()
        else:
            return False, None

        # FIRST: Check circuit-level discount programs (preferred - from Company Profiles)
        is_circuit_discount, circuit_program, _ = self._check_discount_day_from_profile(
            theater_name, play_date, ticket_type, format_type, daypart
        )
        if is_circuit_discount:
            return True, circuit_program

        # FALLBACK: Check theater-level discount programs (legacy)
        programs = self._discount_programs_cache.get(theater_name, [])

        for program in programs:
            if program.day_of_week != day_of_week:
                continue

            # Check ticket type applicability (if specified)
            if ticket_type and program.ticket_types:
                applicable_types = [t.strip().lower() for t in program.ticket_types.split(',')]
                if ticket_type.lower() not in applicable_types:
                    continue

            # Check format applicability (if specified)
            if format_type and program.formats:
                applicable_formats = [f.strip().lower() for f in program.formats.split(',')]
                if format_type.lower() not in applicable_formats:
                    continue

            # Found a matching discount program
            return True, program

        return False, None

    # Valid daypart values (lowercase) - must match to compare apples-to-apples.
    # Dayparts are normalized at entry via normalize_daypart() to canonical forms:
    #   Matinee, Twilight, Prime, Late Night
    # NOTE: 'Standard' is NOT valid here — it's a flat-pricing marker in baselines,
    # not a daypart that should appear in incoming scrape data.
    VALID_DAYPARTS = {'Matinee', 'Twilight', 'Prime', 'Late Night'}

    # Keywords that indicate special events (Fathom, marathons, re-releases, etc.)
    # These should not be compared against standard releases
    SPECIAL_EVENT_KEYWORDS = {
        'fathom', 'marathon', 'anniversary', '50th', '25th', '20th', '10th',
        'remaster', 're-release', 'rerelease', 'classic', 'throwback',
        'double feature', 'trilogy', 'extended', 'director\'s cut',
        'imax experience', 'special presentation', 'one night', 'limited engagement'
    }

    # Price threshold - films priced above this are likely special events
    SPECIAL_EVENT_PRICE_THRESHOLD = Decimal('15.00')

    # Keywords that indicate loyalty/AC ticket types
    # These are discounted from original price, not from flat discount day price
    LOYALTY_AC_KEYWORDS = {'ac ', ' ac', 'loyalty', 'alternative content', 'a-list', 'stubs'}

    # Day of week categories for pricing comparison
    # 0=Monday, 1=Tuesday, ... 6=Sunday
    WEEKDAY_DAYS = {0, 1, 2, 3}  # Monday-Thursday
    WEEKEND_DAYS = {4, 5, 6}     # Friday-Sunday

    def _get_day_category(self, play_date) -> str:
        """Get the day category (weekday/weekend) for a date."""
        if play_date is None:
            return 'unknown'

        # Handle both date and datetime objects
        if hasattr(play_date, 'weekday'):
            day_num = play_date.weekday()
        else:
            return 'unknown'

        if day_num in self.WEEKDAY_DAYS:
            return 'weekday'
        elif day_num in self.WEEKEND_DAYS:
            return 'weekend'
        return 'unknown'

    def _is_special_event(self, film_title: str, price: Decimal) -> bool:
        """Check if a film/price combination indicates a special event."""
        # Check price threshold
        if price >= self.SPECIAL_EVENT_PRICE_THRESHOLD:
            return True

        # Check for special event keywords in title
        title_lower = (film_title or '').lower()
        for keyword in self.SPECIAL_EVENT_KEYWORDS:
            if keyword in title_lower:
                return True

        return False

    def _is_loyalty_or_ac_ticket(self, ticket_type: str) -> bool:
        """Check if ticket type is a loyalty/AC type discounted from original price.

        Loyalty and alternative content tickets use a different discount model:
        they are discounted from the regular ticket price, not from the flat
        discount day price. For example, if "$5 Tuesdays" sets Adult to $5,
        an "AC Loyalty Member" ticket at $10 (discounted from $13 regular)
        should NOT be flagged as a discount day violation.
        """
        if not ticket_type:
            return False
        ticket_lower = ticket_type.lower()
        return any(kw in ticket_lower for kw in self.LOYALTY_AC_KEYWORDS)

    def _check_price_change(
        self, session: Session, config: AlertConfiguration,
        theater_name: str, ticket_type: str, format_type: str,
        daypart: str, new_price: Decimal, film_title: str, play_date
    ) -> Optional[PriceAlert]:
        """Check if price changed from previous scrape.

        Compares standard releases against each other to detect surge pricing.
        Special events (Fathom, marathons, high-priced screenings) are excluded.

        Compares apples-to-apples by matching on:
        - theater_name: Same theater
        - ticket_type: Same ticket type (Adult, Senior, Child, etc.)
        - format: Same format (2D, IMAX, Dolby, etc.)
        - daypart: Same daypart (matinee, evening, late_night) - prevents comparing cheap matinee to evening
        """

        # CRITICAL: Skip if daypart is missing or invalid - cannot compare apples-to-apples
        # daypart is already normalized at the entry point (normalize_daypart())
        daypart_canonical = (daypart or '').strip()
        if not daypart_canonical or daypart_canonical not in self.VALID_DAYPARTS:
            logger.debug(f"Skipping alert check - invalid or missing daypart '{daypart}' for {theater_name}")
            return None

        # Skip special events - they shouldn't be compared against standard releases
        if self._is_special_event(film_title, new_price):
            logger.debug(f"Skipping alert check - '{film_title}' at ${new_price} appears to be a special event")
            return None

        # Get day category for the current price (weekday vs weekend)
        current_day_category = self._get_day_category(play_date)
        if current_day_category == 'unknown':
            logger.debug(f"Skipping alert check - unknown day category for play_date {play_date}")
            return None

        # Check if this is a known discount day - skip to avoid false alerts
        # Discount days (e.g., "$5 Tuesdays") have artificially low prices that
        # shouldn't trigger "price decrease" alerts when comparing to normal days
        # Now checks BOTH circuit-level (DiscountDayProgram) and theater-level (DiscountProgram)
        is_discount, discount_program = self._is_discount_day(
            theater_name, play_date, ticket_type, format_type, daypart_canonical
        )
        if is_discount:
            program_name = getattr(discount_program, 'program_name', 'unknown')
            logger.debug(f"Skipping alert check - {play_date} is a discount day "
                        f"({program_name}) for {theater_name}")
            return None

        # Find previous prices for same theater/ticket_type/format/daypart
        # We'll filter by day category in Python since SQLite day functions differ
        prev_price_query = session.query(
            Price.price, Price.created_at, Showing.daypart, Showing.film_title, Showing.play_date
        ).join(
            Showing, Price.showing_id == Showing.showing_id
        ).filter(
            and_(
                Price.company_id == self.company_id,
                Showing.theater_name == theater_name,
                Price.ticket_type == ticket_type,
                Showing.format == format_type,
                Showing.daypart == daypart_canonical,  # Canonical daypart match
                Price.price < self.SPECIAL_EVENT_PRICE_THRESHOLD  # Exclude high-priced special events
            )
        ).order_by(Price.created_at.desc()).limit(20).all()  # Get more results to filter by day category

        # Filter by same day category (weekday vs weekend) AND exclude discount days
        matching_prices = []
        for row in prev_price_query:
            row_play_date = row[4]  # play_date
            # Must match day category (weekday vs weekend)
            if self._get_day_category(row_play_date) != current_day_category:
                continue
            # Exclude prices from known discount days
            is_discount, _ = self._is_discount_day(theater_name, row_play_date, ticket_type, format_type, daypart_canonical)
            if is_discount:
                continue
            matching_prices.append(row)

        if len(matching_prices) < 2:
            # Not enough history to compare - need at least 2 prices (current + previous)
            logger.debug(f"Not enough {current_day_category} price history for {theater_name} {ticket_type} {format_type} ({daypart_canonical})")
            return None

        # The most recent is the current price, the second is the previous
        # Query returns (price, created_at, daypart, film_title, play_date) tuples
        old_price = matching_prices[1][0]
        old_price_captured_at = matching_prices[1][1]
        old_daypart = matching_prices[1][2]
        old_film_title = matching_prices[1][3]
        old_play_date = matching_prices[1][4]

        # Log comparison details for debugging
        logger.debug(f"Comparing {current_day_category} prices at {theater_name} ({ticket_type}, {format_type}, {daypart_canonical}): "
                    f"'{old_film_title}' ${old_price} ({old_play_date}) vs '{film_title}' ${new_price} ({play_date})")

        if old_price == new_price:
            return None  # No change

        # Calculate change
        price_diff = new_price - old_price
        percent_change = (price_diff / old_price * 100) if old_price > 0 else Decimal('0')

        # Check thresholds
        min_percent = config.min_price_change_percent or Decimal('5.0')
        min_amount = config.min_price_change_amount or Decimal('1.00')

        meets_threshold = (
            abs(percent_change) >= min_percent or
            abs(price_diff) >= min_amount
        )

        if not meets_threshold:
            return None

        # Determine alert type
        if price_diff > 0:
            if not config.alert_on_increase:
                return None
            alert_type = 'price_increase'
        else:
            if not config.alert_on_decrease:
                return None
            alert_type = 'price_decrease'

        logger.info(f"Price change detected: {theater_name} {ticket_type} {format_type} ({daypart}): "
                   f"${old_price} -> ${new_price} ({percent_change:+.1f}%)")

        return PriceAlert(
            company_id=self.company_id,
            theater_name=theater_name,
            film_title=film_title,
            ticket_type=ticket_type,
            format=format_type,
            daypart=daypart,  # Include daypart for context
            alert_type=alert_type,
            old_price=old_price,
            new_price=new_price,
            price_change_percent=percent_change,
            play_date=play_date,
            triggered_at=datetime.now(UTC),
            old_price_captured_at=old_price_captured_at  # When the baseline price was recorded
        )

    def _check_surge_pricing(
        self, session: Session, config: AlertConfiguration,
        theater_name: str, ticket_type: str, format_type: str,
        daypart: str, current_price: Decimal, film_title: str, play_date
    ) -> Optional[PriceAlert]:
        """Check if current price exceeds baseline (surge detection).

        ENHANCED with:
        - Simplified baseline matching (no day_of_week granularity)
        - Circuit-level discount day checking from Company Profiles
        - Tax status adjustment for cross-source comparisons
        - Potential new pattern detection when confidence is low

        This is the primary method for detecting surge pricing - when a film
        is priced higher than the normal price for that theater's baseline.
        """

        if not config.alert_on_surge:
            return None

        # Get day of week from play_date (still useful for logging)
        day_of_week = None
        if play_date and hasattr(play_date, 'weekday'):
            day_of_week = play_date.weekday()

        # CHECK 1: Is this a circuit-level discount day?
        # If so, we need special handling - don't alert on expected discount prices
        is_discount, discount_program, expected_discount_price = self._check_discount_day_from_profile(
            theater_name, play_date, ticket_type, format_type, daypart
        )

        if is_discount and discount_program:
            # On discount days, we expect lower prices - don't flag as surge
            # But flag if price is HIGHER than expected discount (compliance violation)
            if expected_discount_price and current_price > expected_discount_price:
                # Skip special events - distributor-set pricing (Fathom, Met Opera, etc.)
                if self._is_special_event(film_title, current_price):
                    logger.debug(f"Discount day skip (special event): {film_title} at {theater_name}")
                    return None

                # Skip loyalty/AC tickets - discounted from original price, not flat discount
                if self._is_loyalty_or_ac_ticket(ticket_type):
                    logger.debug(f"Discount day skip (loyalty/AC): {ticket_type} for {film_title} at {theater_name}")
                    return None

                # Genuine discount day overcharge - generate alert with film name
                percent_over = ((current_price - expected_discount_price) / expected_discount_price * 100)
                logger.info(
                    f"Discount day overcharge: {film_title} at {theater_name} "
                    f"{ticket_type} {format_type}: ${current_price} vs expected "
                    f"${expected_discount_price} ({discount_program.program_name})"
                )
                return PriceAlert(
                    company_id=self.company_id,
                    theater_name=theater_name,
                    film_title=film_title,
                    ticket_type=ticket_type,
                    format=format_type,
                    daypart=daypart,
                    alert_type='discount_day_overcharge',
                    old_price=expected_discount_price,
                    new_price=current_price,
                    price_change_percent=percent_over,
                    play_date=play_date,
                    triggered_at=datetime.now(UTC),
                )
            return None

        # Find applicable baseline (SIMPLIFIED - no day_of_week matching)
        baseline = self._find_baseline(
            theater_name, ticket_type, format_type, daypart or '', day_of_week
        )

        if not baseline:
            # No baseline found - potential new pattern
            logger.debug(f"No baseline for surge check: {theater_name} {ticket_type} {format_type} {daypart}")
            return None

        # Adjust for tax status when comparing cross-source prices
        # EntTelligence prices are tax-exclusive, Fandango are tax-inclusive
        baseline_price = baseline.baseline_price
        if baseline_price <= 0:
            return None

        # If the baseline is from a different source with different tax treatment,
        # adjust to match current price's tax status (assume current is inclusive from scraper)
        adjusted_baseline = baseline_price
        if hasattr(baseline, 'tax_status') and baseline.tax_status == 'exclusive':
            # Baseline is tax-exclusive, current price likely tax-inclusive
            # Add estimated tax to baseline for fair comparison using per-theater rate
            if self._tax_config is None:
                self._tax_config = get_tax_config(self.company_id)
            if theater_name not in self._theater_state_cache:
                self._theater_state_cache[theater_name] = get_theater_state(self.company_id, theater_name)
            tax_rate = Decimal(str(get_tax_rate_for_theater(
                self._tax_config, self._theater_state_cache[theater_name], theater_name=theater_name
            )))
            if tax_rate <= 0:
                tax_rate = Decimal('0.075')  # Fallback for tax-inclusive circuits
            adjusted_baseline = baseline_price * (1 + tax_rate)
            logger.debug(f"Adjusted baseline from ${baseline_price} to ${adjusted_baseline} (tax rate {tax_rate}) for tax comparison")

        # Calculate surge against adjusted baseline
        surge_percent = ((current_price - adjusted_baseline) / adjusted_baseline * 100)
        surge_threshold = config.surge_threshold_percent or Decimal('20.0')

        if surge_percent < surge_threshold:
            return None

        surge_multiplier = current_price / adjusted_baseline

        # Check confidence level for potential new pattern detection
        low_confidence = False
        if hasattr(baseline, 'sample_count') and baseline.sample_count:
            if baseline.sample_count < 10:
                low_confidence = True
                logger.info(f"Low confidence baseline ({baseline.sample_count} samples) for {theater_name}")

        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        day_name = day_names[day_of_week] if day_of_week is not None else '?'

        # Determine alert type - could be surge or potential new pattern
        alert_type = 'surge_detected'
        if low_confidence:
            alert_type = 'potential_surge_low_confidence'

        logger.info(f"Surge pricing detected: {theater_name} {ticket_type} {format_type} ({daypart}, {day_name}): "
                   f"${current_price} vs baseline ${adjusted_baseline:.2f} ({surge_percent:.1f}% surge)"
                   f"{' [LOW CONFIDENCE]' if low_confidence else ''}")

        return PriceAlert(
            company_id=self.company_id,
            theater_name=theater_name,
            film_title=film_title,
            ticket_type=ticket_type,
            format=format_type,
            daypart=daypart,
            alert_type=alert_type,
            old_price=None,
            new_price=current_price,
            price_change_percent=surge_percent,
            baseline_price=adjusted_baseline,
            surge_multiplier=surge_multiplier,
            play_date=play_date,
            triggered_at=datetime.now(UTC)
        )


def generate_alerts_for_scrape(company_id: int, run_id: int, prices_df) -> List[PriceAlert]:
    """
    Convenience function to generate alerts after a scrape.
    Called from api/routers/scrapes.py post-save hook.

    Args:
        company_id: Company ID for multi-tenancy
        run_id: The scrape run ID
        prices_df: DataFrame of newly saved prices

    Returns:
        List of generated PriceAlert objects
    """
    try:
        service = AlertService(company_id)
        alerts = service.process_scrape_results(run_id, prices_df)
        return alerts
    except Exception as e:
        logger.exception(f"Error generating alerts for run {run_id}: {e}")
        return []


def get_alert_summary(company_id: int, days: int = 7) -> Dict:
    """
    Get summary statistics for alerts.

    Args:
        company_id: Company ID
        days: Number of days to include

    Returns:
        Dictionary with alert counts by type
    """
    from datetime import timedelta

    with get_session() as session:
        cutoff = datetime.now(UTC) - timedelta(days=days)

        # Count by type
        type_counts = session.query(
            PriceAlert.alert_type,
            func.count(PriceAlert.alert_id)
        ).filter(
            and_(
                PriceAlert.company_id == company_id,
                PriceAlert.triggered_at >= cutoff
            )
        ).group_by(PriceAlert.alert_type).all()

        # Count pending vs acknowledged
        status_counts = session.query(
            PriceAlert.is_acknowledged,
            func.count(PriceAlert.alert_id)
        ).filter(
            and_(
                PriceAlert.company_id == company_id,
                PriceAlert.triggered_at >= cutoff
            )
        ).group_by(PriceAlert.is_acknowledged).all()

        return {
            'by_type': {t: c for t, c in type_counts},
            'pending': next((c for ack, c in status_counts if not ack), 0),
            'acknowledged': next((c for ack, c in status_counts if ack), 0),
            'days': days
        }
