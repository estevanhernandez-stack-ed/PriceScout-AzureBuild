"""
Company Profiles API Router

Endpoints for discovering and managing company/circuit pricing profiles.

Endpoints:
    GET    /api/v1/company-profiles              - List all profiles
    GET    /api/v1/company-profiles/{circuit}    - Get profile for a circuit
    POST   /api/v1/company-profiles/discover     - Discover profile for a circuit
    DELETE /api/v1/company-profiles/{circuit}    - Delete a profile
"""

from datetime import datetime, date, timezone, UTC
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from api.routers.auth import get_current_user, require_operator
from app.db_session import get_session
from app.company_profile_discovery import CompanyProfileDiscoveryService
from app.db_models import CompanyProfile, DiscountDayProgram, CompanyProfileGap
from sqlalchemy import and_, or_, distinct
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/company-profiles", tags=["Company Profiles"])

# Log when this module is loaded to confirm endpoints are registered
logger.info("=== Company Profiles router loaded with cleanup-duplicates endpoint ===")


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class DiscountDayInfo(BaseModel):
    """Info about a detected discount day."""
    day_of_week: int
    day: str
    price: float
    program: str
    sample_count: int = 0
    variance_pct: float = 0.0
    below_avg_pct: float = 0.0


class CompanyProfileResponse(BaseModel):
    """Response model for a company profile."""
    profile_id: int
    circuit_name: str
    discovered_at: datetime
    last_updated_at: Optional[datetime] = None

    # Ticket types
    ticket_types: List[str] = []

    # Daypart scheme
    daypart_scheme: str = "unknown"
    daypart_boundaries: Dict[str, str] = {}
    has_flat_matinee: bool = False

    # Discount days
    has_discount_days: bool = False
    discount_days: List[DiscountDayInfo] = []

    # Premium formats
    premium_formats: List[str] = []
    premium_surcharges: Dict[str, float] = {}

    # Data quality
    theater_count: int = 0
    sample_count: int = 0
    date_range_start: Optional[date] = None
    date_range_end: Optional[date] = None
    confidence_score: float = 0.0


class DiscoverRequest(BaseModel):
    """Request model for discovering a profile."""
    circuit_name: str = Field(..., description="Circuit name (e.g., 'Marcus Theatres')")
    theater_names: Optional[List[str]] = Field(None, description="Specific theaters to analyze")
    lookback_days: int = Field(90, ge=7, le=365, description="Days of history to analyze")
    min_samples: int = Field(10, ge=5, le=100, description="Minimum samples for detection")


class DiscoverResponse(BaseModel):
    """Response model for discover operation."""
    profile: CompanyProfileResponse
    message: str


class ProfileListResponse(BaseModel):
    """Response model for list of profiles."""
    total: int
    profiles: List[CompanyProfileResponse]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _profile_to_response(profile: CompanyProfile) -> CompanyProfileResponse:
    """Convert a CompanyProfile ORM object to response model."""
    return CompanyProfileResponse(
        profile_id=profile.profile_id,
        circuit_name=profile.circuit_name,
        discovered_at=profile.discovered_at,
        last_updated_at=profile.last_updated_at,
        ticket_types=profile.ticket_types_list,
        daypart_scheme=profile.daypart_scheme,
        daypart_boundaries=profile.daypart_boundaries_dict,
        has_flat_matinee=profile.has_flat_matinee or False,
        has_discount_days=profile.has_discount_days or False,
        discount_days=[DiscountDayInfo(**dd) for dd in profile.discount_days_list],
        premium_formats=profile.premium_formats_list,
        premium_surcharges=profile.premium_surcharges_dict,
        theater_count=profile.theater_count or 0,
        sample_count=profile.sample_count or 0,
        date_range_start=profile.date_range_start,
        date_range_end=profile.date_range_end,
        confidence_score=float(profile.confidence_score or 0),
    )


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("", response_model=ProfileListResponse)
async def list_profiles(current_user: dict = Depends(get_current_user)):
    """
    List all discovered company profiles.

    Returns profiles for all circuits that have been analyzed.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        profiles = session.query(CompanyProfile).filter(
            CompanyProfile.company_id == company_id
        ).order_by(CompanyProfile.circuit_name).all()

        return ProfileListResponse(
            total=len(profiles),
            profiles=[_profile_to_response(p) for p in profiles]
        )


@router.get("/{circuit_name}", response_model=CompanyProfileResponse)
async def get_profile(
    circuit_name: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get a company profile for a specific circuit.

    Returns 404 if no profile exists for the circuit.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        profile = session.query(CompanyProfile).filter(
            and_(
                CompanyProfile.company_id == company_id,
                CompanyProfile.circuit_name == circuit_name
            )
        ).first()

        if not profile:
            raise HTTPException(
                status_code=404,
                detail=f"No profile found for circuit: {circuit_name}"
            )

        return _profile_to_response(profile)


@router.post("/discover", response_model=DiscoverResponse)
async def discover_profile(
    request: DiscoverRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Discover or update a pricing profile for a circuit.

    Analyzes scraped price data to determine:
    - Ticket type inventory (age-based vs daypart-based)
    - Daypart scheme (ticket-type-based vs time-based)
    - Discount days (e.g., "$5 Tuesdays")
    - Premium formats and surcharges

    This operation may take several seconds for circuits with many theaters.
    """
    company_id = current_user.get("company_id", 1)

    service = CompanyProfileDiscoveryService(company_id)

    try:
        profile = service.discover_profile(
            circuit_name=request.circuit_name,
            theater_names=request.theater_names,
            lookback_days=request.lookback_days,
            min_samples=request.min_samples,
        )

        if not profile:
            raise HTTPException(
                status_code=404,
                detail=f"No price data found for circuit: {request.circuit_name}. "
                       f"Ensure theaters have been scraped with price data."
            )

        return DiscoverResponse(
            profile=_profile_to_response(profile),
            message=f"Profile discovered for {request.circuit_name} with {profile.sample_count} samples from {profile.theater_count} theaters"
        )

    except Exception as e:
        logger.exception(f"Error discovering profile for {request.circuit_name}")
        raise HTTPException(
            status_code=500,
            detail=f"Error discovering profile: {str(e)}"
        )


@router.delete("/{circuit_name}")
async def delete_profile(
    circuit_name: str,
    current_user: dict = Depends(require_operator)
):
    """
    Delete a company profile.

    This does not delete any price data, only the discovered profile.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        profile = session.query(CompanyProfile).filter(
            and_(
                CompanyProfile.company_id == company_id,
                CompanyProfile.circuit_name == circuit_name
            )
        ).first()

        if not profile:
            raise HTTPException(
                status_code=404,
                detail=f"No profile found for circuit: {circuit_name}"
            )

        session.delete(profile)
        session.commit()

        return {"message": f"Profile deleted for circuit: {circuit_name}"}


@router.post("/cleanup-duplicates")
async def cleanup_duplicate_profiles(
    current_user: dict = Depends(require_operator)
):
    """
    Clean up duplicate circuit profiles by consolidating variants.

    Groups related circuits (e.g., Marcus, Marcus Theatres, Movie Tavern)
    and KEEPS the profile with the most theaters, deleting the others.
    """
    company_id = current_user.get("company_id", 1)

    # Define consolidation groups - profiles that should be merged
    # Each group will keep the profile with the most theaters
    consolidation_groups = [
        ['Marcus', 'Marcus Theatres', 'Movie Tavern'],  # All Marcus-owned
        # Add more groups as needed
    ]

    deleted = []
    kept = []
    existing_profiles = []

    with get_session() as session:
        # Log all existing profiles for debugging
        all_profiles = session.query(CompanyProfile).filter(
            CompanyProfile.company_id == company_id
        ).all()
        existing_profiles = [
            {"name": p.circuit_name, "theaters": p.theater_count or 0}
            for p in all_profiles
        ]
        logger.info(f"Existing profiles before cleanup: {existing_profiles}")

        for group in consolidation_groups:
            # Find all profiles in this consolidation group
            group_profiles = []
            for name in group:
                profile = session.query(CompanyProfile).filter(
                    CompanyProfile.company_id == company_id,
                    CompanyProfile.circuit_name.ilike(name)
                ).first()
                if profile:
                    group_profiles.append(profile)

            if len(group_profiles) <= 1:
                # No duplicates to clean up in this group
                if group_profiles:
                    kept.append(group_profiles[0].circuit_name)
                continue

            # Sort by theater_count descending - keep the one with most theaters
            group_profiles.sort(key=lambda p: p.theater_count or 0, reverse=True)

            # Keep the first one (most theaters), delete the rest
            keeper = group_profiles[0]
            to_delete = group_profiles[1:]

            logger.info(f"Consolidation group: {[p.circuit_name for p in group_profiles]}")
            logger.info(f"  Keeping: '{keeper.circuit_name}' ({keeper.theater_count} theaters)")

            kept.append(keeper.circuit_name)

            for profile in to_delete:
                logger.info(f"  Deleting: '{profile.circuit_name}' ({profile.theater_count} theaters)")

                # Delete related discount programs
                deleted_programs = session.query(DiscountDayProgram).filter(
                    DiscountDayProgram.profile_id == profile.profile_id
                ).delete()
                logger.info(f"    - Deleted {deleted_programs} discount programs")

                # Delete related gaps
                deleted_gaps = session.query(CompanyProfileGap).filter(
                    CompanyProfileGap.profile_id == profile.profile_id
                ).delete()
                logger.info(f"    - Deleted {deleted_gaps} gaps")

                # Delete the profile
                session.delete(profile)
                deleted.append(f"{profile.circuit_name} ({profile.theater_count} theaters)")

        if deleted:
            session.commit()
            logger.info(f"Committed deletion of {len(deleted)} profiles: {deleted}")

        # Get remaining profiles after cleanup
        remaining = session.query(CompanyProfile).filter(
            CompanyProfile.company_id == company_id
        ).all()
        remaining_names = [
            {"name": p.circuit_name, "theaters": p.theater_count or 0}
            for p in remaining
        ]
        logger.info(f"Remaining profiles after cleanup: {remaining_names}")

    return {
        "message": f"Deleted {len(deleted)} duplicate profiles, kept profiles with most theaters",
        "deleted": deleted,
        "kept": kept,
        "existing_before": existing_profiles,
        "remaining_after": remaining_names,
        "note": "Kept the profile with the most theaters in each consolidation group"
    }


@router.post("/discover-all", response_model=ProfileListResponse)
async def discover_all_profiles(
    lookback_days: int = Query(90, ge=7, le=365, description="Days of history"),
    min_samples: int = Query(10, ge=5, le=100, description="Minimum samples"),
    min_theaters: int = Query(2, ge=1, le=10, description="Minimum theaters to create profile"),
    current_user: dict = Depends(require_operator)
):
    """
    Discover profiles for ALL circuits found in scraped data.

    Dynamically finds all theater circuits by analyzing theater name prefixes,
    then creates a profile for each circuit that has enough data.
    """
    company_id = current_user.get("company_id", 1)

    service = CompanyProfileDiscoveryService(company_id)
    discovered_profiles = []

    with get_session() as session:
        from app.db_models import Showing, Price
        from sqlalchemy import distinct, func
        from collections import defaultdict

        # Get all theaters with their price counts
        theater_data = session.query(
            Showing.theater_name,
            func.count(Price.price_id).label('price_count')
        ).join(
            Price, Showing.showing_id == Price.showing_id
        ).filter(
            Showing.company_id == company_id
        ).group_by(
            Showing.theater_name
        ).all()

        # Group theaters by circuit prefix
        circuit_theaters = defaultdict(list)

        # Known multi-word circuit names that should be detected as a unit
        # All Marcus-owned theaters consolidate to "Marcus Theatres" (the main brand)
        multi_word_circuits = {
            ('Movie', 'Tavern'): 'Marcus Theatres',  # Movie Tavern is owned by Marcus
            ('Marcus', 'Theatres'): 'Marcus Theatres',  # Keep as Marcus Theatres
            ('Studio', 'Movie'): 'Studio Movie Grill',
            ('B&B', 'Theatres'): 'B&B Theatres',
            ('LOOK', 'Dine-in'): 'LOOK Cinemas',
        }

        # Circuit consolidation: map variant names to canonical circuit name
        # This prevents creating separate profiles for the same company
        # "Marcus Theatres" is the canonical name (has most theaters)
        circuit_consolidation = {
            'Marcus': 'Marcus Theatres',
            'Marcus Theatres': 'Marcus Theatres',
            'Movie Tavern': 'Marcus Theatres',
        }

        for theater_name, price_count in theater_data:
            words = theater_name.split()
            circuit = None

            # Check for multi-word circuits first
            if len(words) >= 2:
                for (w1, w2), circuit_name in multi_word_circuits.items():
                    if words[0] == w1 and words[1] == w2:
                        circuit = circuit_name
                        break

            # If not multi-word, use first word
            if not circuit and words:
                circuit = words[0]

            # Apply circuit consolidation
            if circuit and circuit in circuit_consolidation:
                circuit = circuit_consolidation[circuit]

            if circuit:
                circuit_theaters[circuit].append(theater_name)

        # First, clean up any duplicate profiles that should be consolidated
        # e.g., delete "Marcus" and "Movie Tavern" since they'll be merged into "Marcus Theatres"
        profiles_to_delete = []
        for variant, canonical in circuit_consolidation.items():
            if variant != canonical:
                # This is a variant that should be merged into the canonical name
                existing = session.query(CompanyProfile).filter(
                    CompanyProfile.company_id == company_id,
                    CompanyProfile.circuit_name == variant
                ).first()
                if existing:
                    profiles_to_delete.append(existing)
                    logger.info(f"Will delete duplicate profile '{variant}' (consolidating into '{canonical}')")

        for profile in profiles_to_delete:
            session.delete(profile)
        if profiles_to_delete:
            session.commit()
            logger.info(f"Deleted {len(profiles_to_delete)} duplicate circuit profiles")

        # Discover profile for each circuit with enough theaters
        for circuit_name, theaters in sorted(circuit_theaters.items(), key=lambda x: -len(x[1])):
            if len(theaters) < min_theaters:
                logger.debug(f"Skipping {circuit_name}: only {len(theaters)} theaters (min: {min_theaters})")
                continue

            try:
                profile = service.discover_profile(
                    circuit_name=circuit_name,
                    theater_names=theaters,
                    lookback_days=lookback_days,
                    min_samples=min_samples,
                )
                if profile:
                    discovered_profiles.append(_profile_to_response(profile))
                    logger.info(f"Discovered profile for {circuit_name}: {len(theaters)} theaters")
            except Exception as e:
                logger.warning(f"Failed to discover profile for {circuit_name}: {e}")

    return ProfileListResponse(
        total=len(discovered_profiles),
        profiles=discovered_profiles
    )


# ============================================================================
# DIAGNOSTIC ENDPOINTS
# ============================================================================

class DayPriceAnalysis(BaseModel):
    """Analysis of prices for a single day."""
    day_of_week: int
    day_name: str
    sample_count: int
    avg_price: float
    min_price: float
    max_price: float
    price_range: float = 0.0  # max - min, indicates if pricing is "flat"
    std_dev: float
    variance_pct: float
    below_avg_pct: float
    is_flat_pricing: bool = False  # True if variance <= 8% or range <= $1.50
    is_discounted: bool = False  # True if >= 8% below weekday average
    ticket_types_seen: List[str]


class DiscountDayDiagnostic(BaseModel):
    """Diagnostic info for discount day detection."""
    circuit_name: str
    theater_count: int
    total_samples: int
    overall_avg_price: float
    day_analysis: List[DayPriceAnalysis]
    discount_ticket_types_found: Dict[str, Dict[str, int]]  # ticket_type -> day -> count
    detected_discount_days: List[Dict]
    detection_thresholds: Dict[str, float]


@router.get("/{circuit_name}/discount-day-diagnostic", response_model=DiscountDayDiagnostic)
async def get_discount_day_diagnostic(
    circuit_name: str,
    lookback_days: int = Query(90, ge=7, le=365, description="Days of history"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get detailed diagnostic info about discount day detection for a circuit.

    Shows:
    - Day-by-day price analysis
    - Ticket types found (especially discount types like 'loyalty')
    - Why certain days were/weren't detected as discount days
    """
    import statistics
    from collections import defaultdict
    from datetime import timedelta

    company_id = current_user.get("company_id", 1)
    cutoff_date = datetime.now(UTC) - timedelta(days=lookback_days)

    with get_session() as session:
        from app.db_models import Showing, Price

        # Get all theaters for this circuit
        circuit_patterns = {
            'marcus': ['Marcus %', 'Movie Tavern %'],
            'amc': ['AMC %'],
            'regal': ['Regal %'],
            'cinemark': ['Cinemark %'],
        }

        circuit_lower = circuit_name.lower()
        theaters = []

        for circuit_key, patterns in circuit_patterns.items():
            if circuit_key in circuit_lower:
                for pattern in patterns:
                    results = session.query(distinct(Showing.theater_name)).filter(
                        and_(
                            Showing.company_id == company_id,
                            Showing.theater_name.like(pattern)
                        )
                    ).all()
                    theaters.extend([r[0] for r in results])
                break

        if not theaters:
            # Generic pattern matching
            results = session.query(distinct(Showing.theater_name)).filter(
                and_(
                    Showing.company_id == company_id,
                    Showing.theater_name.like(f"%{circuit_name}%")
                )
            ).all()
            theaters = [r[0] for r in results]

        if not theaters:
            raise HTTPException(status_code=404, detail=f"No theaters found for circuit: {circuit_name}")

        # Get price data
        query = session.query(
            Showing.theater_name,
            Price.ticket_type,
            Showing.format,
            Showing.play_date,
            Price.price
        ).join(
            Showing, Price.showing_id == Showing.showing_id
        ).filter(
            and_(
                Price.company_id == company_id,
                Price.created_at >= cutoff_date,
                Price.price > 0,
                Showing.theater_name.in_(theaters)
            )
        )

        price_data = [
            {
                'theater_name': r[0],
                'ticket_type': r[1],
                'format': r[2] or 'Standard',
                'play_date': r[3],
                'price': float(r[4]),
                'day_of_week': r[3].weekday() if r[3] else None
            }
            for r in query.all()
        ]

        # Analyze discount ticket types
        DISCOUNT_TICKET_PATTERNS = {
            'loyalty', 'bargain', 'value', 'discount', 'special', 'deal',
            'super saver', 'value pricing', 'discount pricing'
        }

        discount_ticket_types = defaultdict(lambda: defaultdict(int))
        DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        for row in price_data:
            if row['day_of_week'] is not None and row['ticket_type']:
                ticket_lower = row['ticket_type'].lower()
                for pattern in DISCOUNT_TICKET_PATTERNS:
                    if pattern in ticket_lower:
                        discount_ticket_types[row['ticket_type']][DAY_NAMES[row['day_of_week']]] += 1
                        break

        # Day-by-day analysis for ADULT tickets only (clearest discount signal)
        day_prices = defaultdict(list)
        day_ticket_types = defaultdict(set)

        for row in price_data:
            if row['day_of_week'] is not None:
                format_name = (row['format'] or '').lower()
                ticket_type = (row['ticket_type'] or '').lower()

                is_standard = 'standard' in format_name or format_name in ['', '2d', 'digital']
                # Focus on ADULT tickets only - they show the biggest discount
                is_adult = (
                    'adult' in ticket_type
                    and 'matinee' not in ticket_type
                    and not any(p in ticket_type for p in DISCOUNT_TICKET_PATTERNS)
                )

                if is_standard and is_adult:
                    day_prices[row['day_of_week']].append(row['price'])
                    day_ticket_types[row['day_of_week']].add(row['ticket_type'])

        # Calculate WEEKDAY average (Mon-Thu) - this is our baseline for "normal" pricing
        weekday_prices = []
        for day in range(4):  # Mon, Tue, Wed, Thu
            if day in day_prices:
                weekday_prices.extend(day_prices[day])

        overall_avg = statistics.mean(weekday_prices) if weekday_prices else 0

        # Build day analysis
        day_analysis = []
        detected_discount_days = []

        for day in range(7):
            prices = day_prices.get(day, [])
            if not prices:
                continue

            avg = statistics.mean(prices)
            std = statistics.stdev(prices) if len(prices) > 1 else 0
            variance_pct = (std / avg * 100) if avg > 0 else 0
            price_range = max(prices) - min(prices)
            below_avg_pct = ((overall_avg - avg) / overall_avg * 100) if overall_avg > 0 else 0

            # Determine if this day has "flat" pricing (same price all day)
            is_flat_pricing = variance_pct <= 8.0 or price_range <= 1.50
            is_discounted = below_avg_pct >= 8.0

            analysis = DayPriceAnalysis(
                day_of_week=day,
                day_name=DAY_NAMES[day],
                sample_count=len(prices),
                avg_price=round(avg, 2),
                min_price=round(min(prices), 2),
                max_price=round(max(prices), 2),
                price_range=round(price_range, 2),
                std_dev=round(std, 2),
                variance_pct=round(variance_pct, 1),
                below_avg_pct=round(below_avg_pct, 1),
                is_flat_pricing=is_flat_pricing,
                is_discounted=is_discounted,
                ticket_types_seen=list(day_ticket_types.get(day, []))
            )
            day_analysis.append(analysis)

            # Check if qualifies as discount day using improved criteria:
            # 1. Flat pricing (low variance OR small price range) - same price all day
            # 2. Price is notably lower than weekday average
            is_flat_pricing = variance_pct <= 8.0 or price_range <= 1.50
            is_discounted = below_avg_pct >= 8.0
            is_weekday = day < 5  # Only detect weekday discounts

            if is_flat_pricing and is_discounted and is_weekday and len(prices) >= 10:
                detected_discount_days.append({
                    'day_of_week': day,
                    'day': DAY_NAMES[day],
                    'price': round(min(prices), 2),  # Use min price as the discount price
                    'method': 'adult_flat_pricing',
                    'variance_pct': round(variance_pct, 1),
                    'below_avg_pct': round(below_avg_pct, 1),
                    'price_range': round(price_range, 2),
                    'is_flat': is_flat_pricing,
                    'is_discounted': is_discounted
                })

        # Also check for discount ticket type detection
        for ticket_type, day_data in discount_ticket_types.items():
            total = sum(day_data.values())
            if total >= 10:
                max_day = max(day_data.keys(), key=lambda d: day_data[d])
                if day_data[max_day] / total >= 0.7:
                    detected_discount_days.append({
                        'day': max_day,
                        'ticket_type': ticket_type,
                        'method': 'discount_ticket_type',
                        'sample_count': day_data[max_day]
                    })

        return DiscountDayDiagnostic(
            circuit_name=circuit_name,
            theater_count=len(theaters),
            total_samples=len(price_data),
            overall_avg_price=round(overall_avg, 2),
            day_analysis=sorted(day_analysis, key=lambda x: x.day_of_week),
            discount_ticket_types_found=dict(discount_ticket_types),
            detected_discount_days=detected_discount_days,
            detection_thresholds={
                'max_variance_pct': 8.0,  # Flat pricing threshold
                'max_price_range': 1.50,  # Alternative flat pricing threshold
                'min_below_avg_pct': 8.0,  # Must be 8% below weekday average
                'min_samples': 10,
                'discount_ticket_concentration': 0.7,
                'note': 'Compares adult ticket prices to Mon-Thu weekday average'
            }
        )


# ============================================================================
# DISCOUNT PROGRAMS ENDPOINTS
# ============================================================================

class DiscountProgramResponse(BaseModel):
    """Response model for a discount day program."""
    program_id: int
    circuit_name: str
    program_name: str
    day_of_week: int
    day_name: str
    discount_type: str
    discount_value: float
    applicable_ticket_types: Optional[List[str]] = None
    applicable_formats: Optional[List[str]] = None
    applicable_dayparts: Optional[List[str]] = None
    is_active: bool = True
    confidence_score: float = 0.0
    sample_count: int = 0
    source: str = "auto_discovery"
    discovered_at: datetime
    last_verified_at: Optional[datetime] = None


class CreateDiscountProgramRequest(BaseModel):
    """Request model for creating a discount program."""
    program_name: str = Field(..., description="Program name (e.g., '$5 Tuesdays')")
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    discount_type: str = Field(..., description="'flat_price', 'percentage_off', or 'amount_off'")
    discount_value: float = Field(..., description="Discount value (5.00 for $5, 20 for 20%)")
    applicable_ticket_types: Optional[List[str]] = Field(None, description="NULL = all ticket types")
    applicable_formats: Optional[List[str]] = Field(None, description="NULL = all formats")
    applicable_dayparts: Optional[List[str]] = Field(None, description="NULL = all dayparts")


class ProfileGapResponse(BaseModel):
    """Response model for a profile gap."""
    gap_id: int
    gap_type: str
    expected_value: str
    reason: Optional[str] = None
    first_detected_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    is_resolved: bool = False


class ResolveGapRequest(BaseModel):
    """Request model for resolving a gap."""
    resolution_notes: Optional[str] = None


def _program_to_response(program: DiscountDayProgram) -> DiscountProgramResponse:
    """Convert a DiscountDayProgram ORM object to response model."""
    return DiscountProgramResponse(
        program_id=program.program_id,
        circuit_name=program.circuit_name,
        program_name=program.program_name,
        day_of_week=program.day_of_week,
        day_name=program.day_name,
        discount_type=program.discount_type,
        discount_value=float(program.discount_value),
        applicable_ticket_types=program.applicable_ticket_types_list,
        applicable_formats=program.applicable_formats_list,
        applicable_dayparts=program.applicable_dayparts_list,
        is_active=program.is_active or False,
        confidence_score=float(program.confidence_score or 0),
        sample_count=program.sample_count or 0,
        source=program.source or "auto_discovery",
        discovered_at=program.discovered_at,
        last_verified_at=program.last_verified_at,
    )


def _gap_to_response(gap: CompanyProfileGap) -> ProfileGapResponse:
    """Convert a CompanyProfileGap ORM object to response model."""
    return ProfileGapResponse(
        gap_id=gap.gap_id,
        gap_type=gap.gap_type,
        expected_value=gap.expected_value,
        reason=gap.reason,
        first_detected_at=gap.first_detected_at,
        resolved_at=gap.resolved_at,
        resolution_notes=gap.resolution_notes,
        is_resolved=gap.is_resolved,
    )


@router.get("/{circuit_name}/discount-programs", response_model=List[DiscountProgramResponse])
async def list_discount_programs(
    circuit_name: str,
    active_only: bool = Query(True, description="Only return active programs"),
    current_user: dict = Depends(get_current_user)
):
    """
    List all discount day programs for a circuit.

    Discount programs define recurring discounts like "$5 Tuesdays" or "Senior Wednesdays".
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        query = session.query(DiscountDayProgram).filter(
            DiscountDayProgram.company_id == company_id,
            DiscountDayProgram.circuit_name == circuit_name
        )

        if active_only:
            query = query.filter(DiscountDayProgram.is_active == True)

        programs = query.order_by(DiscountDayProgram.day_of_week).all()
        return [_program_to_response(p) for p in programs]


@router.post("/{circuit_name}/discount-programs", response_model=DiscountProgramResponse)
async def create_discount_program(
    circuit_name: str,
    request: CreateDiscountProgramRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Create or update a discount day program for a circuit.

    If a program already exists for the same circuit, day, and program name,
    it will be updated instead of creating a duplicate.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        # Check if program already exists
        existing = session.query(DiscountDayProgram).filter(
            DiscountDayProgram.company_id == company_id,
            DiscountDayProgram.circuit_name == circuit_name,
            DiscountDayProgram.day_of_week == request.day_of_week,
            DiscountDayProgram.program_name == request.program_name
        ).first()

        if existing:
            # Update existing
            existing.discount_type = request.discount_type
            existing.discount_value = Decimal(str(request.discount_value))
            existing.applicable_ticket_types_list = request.applicable_ticket_types
            existing.applicable_formats_list = request.applicable_formats
            existing.applicable_dayparts_list = request.applicable_dayparts
            existing.is_active = True
            existing.source = "manual"
            existing.last_verified_at = datetime.now(UTC)
            session.commit()
            return _program_to_response(existing)

        # Create new
        program = DiscountDayProgram(
            company_id=company_id,
            circuit_name=circuit_name,
            program_name=request.program_name,
            day_of_week=request.day_of_week,
            discount_type=request.discount_type,
            discount_value=Decimal(str(request.discount_value)),
            is_active=True,
            source="manual",
            confidence_score=Decimal("1.0"),  # Manual entries have high confidence
            discovered_at=datetime.now(UTC),
            last_verified_at=datetime.now(UTC)
        )

        if request.applicable_ticket_types:
            program.applicable_ticket_types_list = request.applicable_ticket_types
        if request.applicable_formats:
            program.applicable_formats_list = request.applicable_formats
        if request.applicable_dayparts:
            program.applicable_dayparts_list = request.applicable_dayparts

        session.add(program)
        session.commit()
        session.refresh(program)

        return _program_to_response(program)


@router.delete("/{circuit_name}/discount-programs/{program_id}")
async def delete_discount_program(
    circuit_name: str,
    program_id: int,
    current_user: dict = Depends(require_operator)
):
    """
    Delete (deactivate) a discount day program.

    Programs are soft-deleted by setting is_active=False.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        program = session.query(DiscountDayProgram).filter(
            DiscountDayProgram.company_id == company_id,
            DiscountDayProgram.circuit_name == circuit_name,
            DiscountDayProgram.program_id == program_id
        ).first()

        if not program:
            raise HTTPException(status_code=404, detail="Discount program not found")

        program.is_active = False
        session.commit()

        return {"message": f"Discount program '{program.program_name}' deactivated"}


# ============================================================================
# PROFILE GAPS ENDPOINTS
# ============================================================================

@router.get("/{circuit_name}/gaps", response_model=List[ProfileGapResponse])
async def list_profile_gaps(
    circuit_name: str,
    include_resolved: bool = Query(False, description="Include resolved gaps"),
    current_user: dict = Depends(get_current_user)
):
    """
    List gaps/missing data in a company profile.

    Gaps are identified when expected data (formats, ticket types, etc.)
    is missing from the profile.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        # Find the profile
        profile = session.query(CompanyProfile).filter(
            CompanyProfile.company_id == company_id,
            CompanyProfile.circuit_name == circuit_name,
            CompanyProfile.is_current == True
        ).first()

        if not profile:
            raise HTTPException(status_code=404, detail=f"No profile found for circuit: {circuit_name}")

        query = session.query(CompanyProfileGap).filter(
            CompanyProfileGap.profile_id == profile.profile_id
        )

        if not include_resolved:
            query = query.filter(CompanyProfileGap.resolved_at.is_(None))

        gaps = query.order_by(CompanyProfileGap.gap_type, CompanyProfileGap.expected_value).all()
        return [_gap_to_response(g) for g in gaps]


@router.post("/{circuit_name}/gaps/{gap_id}/resolve", response_model=ProfileGapResponse)
async def resolve_profile_gap(
    circuit_name: str,
    gap_id: int,
    request: ResolveGapRequest = None,
    current_user: dict = Depends(require_operator)
):
    """
    Mark a profile gap as resolved.

    Use this when the missing data has been added or is no longer expected.
    """
    company_id = current_user.get("company_id", 1)
    user_id = current_user.get("user_id")

    with get_session() as session:
        gap = session.query(CompanyProfileGap).join(CompanyProfile).filter(
            CompanyProfileGap.gap_id == gap_id,
            CompanyProfile.company_id == company_id,
            CompanyProfile.circuit_name == circuit_name
        ).first()

        if not gap:
            raise HTTPException(status_code=404, detail="Gap not found")

        gap.resolved_at = datetime.now(UTC)
        gap.resolved_by = user_id
        if request and request.resolution_notes:
            gap.resolution_notes = request.resolution_notes

        session.commit()
        session.refresh(gap)

        return _gap_to_response(gap)


# ============================================================================
# PROFILE VERSIONS ENDPOINTS
# ============================================================================

@router.get("/{circuit_name}/versions", response_model=List[CompanyProfileResponse])
async def list_profile_versions(
    circuit_name: str,
    current_user: dict = Depends(get_current_user)
):
    """
    List all versions of a company profile.

    Returns profiles in version order (newest first).
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        profiles = session.query(CompanyProfile).filter(
            CompanyProfile.company_id == company_id,
            CompanyProfile.circuit_name == circuit_name
        ).order_by(CompanyProfile.version.desc()).all()

        if not profiles:
            raise HTTPException(status_code=404, detail=f"No profiles found for circuit: {circuit_name}")

        return [_profile_to_response(p) for p in profiles]


# ============================================================================
# DATA COVERAGE DIAGNOSTIC
# ============================================================================

class DayCoverage(BaseModel):
    """Coverage info for a single day."""
    day_of_week: int
    day_name: str
    sample_count: int
    theater_count: int
    date_range: Optional[str] = None
    has_sufficient_data: bool = False  # True if >= 10 samples


class DataCoverageResponse(BaseModel):
    """Response model for data coverage check."""
    circuit_name: str
    total_samples: int
    total_theaters: int
    day_coverage: List[DayCoverage]
    weekdays_with_data: int  # Count of Mon-Fri with sufficient data
    coverage_assessment: str  # "excellent", "good", "limited", "insufficient"
    can_detect_discount_days: bool
    recommendation: str


@router.get("/{circuit_name}/data-coverage", response_model=DataCoverageResponse)
async def get_data_coverage(
    circuit_name: str,
    lookback_days: int = Query(90, ge=7, le=365, description="Days of history"),
    current_user: dict = Depends(get_current_user)
):
    """
    Check data coverage for a circuit to assess if profile discovery will work well.

    Shows:
    - Which days of the week have data
    - Sample counts per day
    - Whether there's enough data for reliable discount day detection

    Use this to understand if you need to run more scrapes before discovering profiles.
    """
    from collections import defaultdict
    from datetime import timedelta

    company_id = current_user.get("company_id", 1)
    cutoff_date = datetime.now(UTC) - timedelta(days=lookback_days)

    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    with get_session() as session:
        from app.db_models import Showing, Price

        # Get all theaters for this circuit
        circuit_patterns = {
            'marcus': ['Marcus %', 'Movie Tavern %'],
            'amc': ['AMC %'],
            'regal': ['Regal %'],
            'cinemark': ['Cinemark %'],
            'b&b': ['B&B %'],
        }

        circuit_lower = circuit_name.lower()
        theaters = []

        for circuit_key, patterns in circuit_patterns.items():
            if circuit_key in circuit_lower:
                for pattern in patterns:
                    results = session.query(distinct(Showing.theater_name)).filter(
                        and_(
                            Showing.company_id == company_id,
                            Showing.theater_name.like(pattern)
                        )
                    ).all()
                    theaters.extend([r[0] for r in results])
                break

        if not theaters:
            # Generic pattern matching
            results = session.query(distinct(Showing.theater_name)).filter(
                and_(
                    Showing.company_id == company_id,
                    Showing.theater_name.like(f"%{circuit_name}%")
                )
            ).all()
            theaters = [r[0] for r in results]

        if not theaters:
            raise HTTPException(status_code=404, detail=f"No theaters found for circuit: {circuit_name}")

        # Get price data grouped by day
        query = session.query(
            Showing.theater_name,
            Showing.play_date,
            Price.price
        ).join(
            Showing, Price.showing_id == Showing.showing_id
        ).filter(
            and_(
                Price.company_id == company_id,
                Price.created_at >= cutoff_date,
                Price.price > 0,
                Showing.theater_name.in_(theaters)
            )
        )

        # Build day-by-day stats
        day_samples = defaultdict(list)
        day_theaters = defaultdict(set)
        day_dates = defaultdict(set)

        for theater_name, play_date, price in query.all():
            if play_date:
                dow = play_date.weekday()
                day_samples[dow].append(float(price))
                day_theaters[dow].add(theater_name)
                day_dates[dow].add(play_date)

        # Build coverage report
        day_coverage = []
        for dow in range(7):
            samples = day_samples.get(dow, [])
            theater_set = day_theaters.get(dow, set())
            date_set = day_dates.get(dow, set())

            date_range = None
            if date_set:
                min_date = min(date_set)
                max_date = max(date_set)
                if min_date != max_date:
                    date_range = f"{min_date.strftime('%m/%d')} - {max_date.strftime('%m/%d')}"
                else:
                    date_range = min_date.strftime('%m/%d')

            day_coverage.append(DayCoverage(
                day_of_week=dow,
                day_name=DAY_NAMES[dow],
                sample_count=len(samples),
                theater_count=len(theater_set),
                date_range=date_range,
                has_sufficient_data=len(samples) >= 10
            ))

        # Calculate assessment
        total_samples = sum(len(day_samples[d]) for d in range(7))
        all_theaters = set()
        for t_set in day_theaters.values():
            all_theaters.update(t_set)

        weekdays_with_data = sum(1 for d in range(5) if len(day_samples[d]) >= 10)

        # Determine coverage level
        if weekdays_with_data >= 4:
            assessment = "excellent"
            can_detect = True
            recommendation = "Data coverage is excellent. Profile discovery will be highly reliable."
        elif weekdays_with_data >= 3:
            assessment = "good"
            can_detect = True
            recommendation = "Data coverage is good. Profile discovery should work well."
        elif weekdays_with_data >= 2:
            assessment = "limited"
            can_detect = True
            recommendation = (
                "Data coverage is limited but sufficient for basic discount detection. "
                "Consider scraping more weekdays for higher confidence."
            )
        else:
            assessment = "insufficient"
            can_detect = False
            recommendation = (
                f"Only {weekdays_with_data} weekday(s) have sufficient data. "
                "Profile discovery needs at least 2 weekdays with data to detect discount patterns. "
                "Run scrapes for additional weekdays before discovering profiles."
            )

        return DataCoverageResponse(
            circuit_name=circuit_name,
            total_samples=total_samples,
            total_theaters=len(all_theaters),
            day_coverage=day_coverage,
            weekdays_with_data=weekdays_with_data,
            coverage_assessment=assessment,
            can_detect_discount_days=can_detect,
            recommendation=recommendation
        )
