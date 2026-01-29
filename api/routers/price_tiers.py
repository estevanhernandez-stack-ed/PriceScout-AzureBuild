"""
Price Tier Discovery Router

API endpoints for discovering theater-specific pricing tiers from historical Fandango data.
Automatically detects discount days (e.g., "$5 Tuesdays") and separates them from regular pricing.

Endpoints:
- GET /price-tiers/discover/{theater_name} - Discover tiers for a specific theater
- GET /price-tiers/discover-all - Discover tiers for all theaters with sufficient data
- GET /price-tiers/discount-days/{theater_name} - Detect discount days for a theater
- GET /price-tiers/recommendations - Get scrape recommendations for better tier discovery
- GET /price-tiers/analyze/{theater_name} - Get detailed pricing analysis for a theater
- POST /price-tiers/save-baselines - Save discovered tiers as price baselines
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from decimal import Decimal

from api.routers.auth import get_current_user, User
from app.price_tier_discovery import (
    PriceTierDiscoveryService,
    discover_price_tiers,
    discover_all_tiers,
    detect_discount_days,
    get_scrape_recommendations,
    analyze_theater,
)

router = APIRouter(prefix="/price-tiers", tags=["Price Tiers"])


# ============================================================================
# SCHEMAS
# ============================================================================

class DiscountDaySchema(BaseModel):
    """Schema for a detected discount day."""
    day_of_week: int = Field(..., description="Day of week (0=Monday, 6=Sunday)")
    day_name: str = Field(..., description="Day name (e.g., 'Tuesday')")
    price: float = Field(..., description="Discount price")
    sample_count: int = Field(..., description="Number of samples used for detection")
    price_variance: float = Field(..., description="Price variance percentage")
    program_name: str = Field(..., description="Program name (e.g., '$8 Tuesdays')")


class PriceTierSchema(BaseModel):
    """Schema for a discovered price tier."""
    tier_name: str = Field(..., description="Tier name (e.g., 'Matinee', 'Evening')")
    price: float = Field(..., description="Average price for this tier")
    start_time: Optional[str] = Field(None, description="Start time (HH:MM)")
    end_time: Optional[str] = Field(None, description="End time (HH:MM)")
    sample_count: int = Field(..., description="Number of samples")
    price_variance: float = Field(..., description="Price variance within tier")


class TheaterPricingProfileSchema(BaseModel):
    """Schema for a complete theater pricing profile."""
    theater_name: str
    ticket_type: str
    format: str
    tiers: List[PriceTierSchema]
    tier_count: int
    discount_days: List[DiscountDaySchema]
    has_discount_days: bool
    regular_day_count: int
    total_samples: int


class ScrapeRecommendationSchema(BaseModel):
    """Schema for a scrape recommendation."""
    theater_name: str
    current_prices: int
    current_days: int
    needed_prices: int
    needed_days: int
    missing_days_of_week: List[str]
    date_range: str
    priority: str
    recommendation: str


class ScrapeRecommendationsResponse(BaseModel):
    """Response schema for scrape recommendations."""
    theaters_needing_data: List[ScrapeRecommendationSchema]
    theaters_ready: List[dict]
    summary: dict


class SaveBaselinesRequest(BaseModel):
    """Request schema for saving baselines."""
    profiles: List[dict] = Field(..., description="List of profiles to save")
    overwrite: bool = Field(False, description="Overwrite existing baselines")


class SaveBaselinesResponse(BaseModel):
    """Response schema for save baselines."""
    tiers_saved: int
    discount_days_saved: int


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get(
    "/discover/{theater_name}",
    response_model=TheaterPricingProfileSchema,
    summary="Discover price tiers for a theater",
    description="""
    Analyze historical price data to discover pricing tiers for a specific theater.

    Automatically detects and separates discount days (e.g., "$5 Tuesdays") from
    regular pricing tiers based on flat pricing patterns.

    A discount day is detected when:
    - All prices for that day of week are the same (within 3% variance)
    - The price is lower than the average of other days
    """
)
async def discover_theater_tiers(
    theater_name: str,
    ticket_type: str = Query("Adult", description="Ticket type to analyze"),
    format_type: str = Query("Standard", description="Format to analyze"),
    min_samples: int = Query(5, description="Minimum samples required"),
    current_user=Depends(get_current_user)
):
    """Discover price tiers for a specific theater."""
    company_id = current_user.get("company_id", 1)

    service = PriceTierDiscoveryService(company_id)
    profile = service.discover_tiers_for_theater(
        theater_name=theater_name,
        ticket_type=ticket_type,
        format_type=format_type,
        min_samples=min_samples
    )

    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Insufficient data to discover tiers for {theater_name}. "
                   f"Need at least {min_samples} prices for {ticket_type}/{format_type}."
        )

    return profile.to_dict()


@router.get(
    "/discover-all",
    response_model=List[TheaterPricingProfileSchema],
    summary="Discover price tiers for all theaters",
    description="""
    Discover pricing tiers for all theaters in your company that have sufficient data.

    Each profile includes:
    - Regular pricing tiers with time ranges
    - Detected discount days (separated from regular pricing)
    - Sample counts for confidence assessment
    """
)
async def discover_all_theater_tiers(
    min_prices: int = Query(20, description="Minimum prices per theater"),
    ticket_types: Optional[str] = Query(
        None,
        description="Comma-separated ticket types (default: Adult only)"
    ),
    current_user=Depends(get_current_user)
):
    """Discover price tiers for all theaters with sufficient data."""
    company_id = current_user.get("company_id", 1)

    service = PriceTierDiscoveryService(company_id)

    types_list = None
    if ticket_types:
        types_list = [t.strip() for t in ticket_types.split(",")]

    profiles = service.discover_all_theater_tiers(
        min_prices=min_prices,
        ticket_types=types_list
    )

    return [p.to_dict() for p in profiles]


@router.get(
    "/discount-days/{theater_name}",
    response_model=List[DiscountDaySchema],
    summary="Detect discount days for a theater",
    description="""
    Detect discount days (e.g., "$5 Tuesdays") for a specific theater.

    A discount day is detected when:
    - All prices for that day of week are nearly identical (within 3% variance)
    - The price is significantly lower than other days (at least 15% below average)

    This is useful for:
    - Identifying competitor discount programs
    - Setting separate baselines for discount vs regular pricing
    - Comparing discount offerings across theaters
    """
)
async def detect_theater_discount_days(
    theater_name: str,
    ticket_type: str = Query("Adult", description="Ticket type to analyze"),
    format_type: str = Query("Standard", description="Format to analyze"),
    current_user=Depends(get_current_user)
):
    """Detect discount days for a specific theater."""
    company_id = current_user.get("company_id", 1)

    service = PriceTierDiscoveryService(company_id)
    discount_days, _ = service.detect_discount_days(
        theater_name=theater_name,
        ticket_type=ticket_type,
        format_type=format_type
    )

    return [dd.to_dict() for dd in discount_days]


@router.get(
    "/recommendations",
    response_model=ScrapeRecommendationsResponse,
    summary="Get scrape recommendations",
    description="""
    Get recommendations for which theaters need more scrape data for accurate tier discovery.

    Returns:
    - Theaters ready for tier discovery (sufficient data)
    - Theaters needing more data with specific recommendations
    - Missing days of week that should be scraped
    """
)
async def get_tier_recommendations(
    target_samples: int = Query(50, description="Target prices per theater"),
    target_days: int = Query(5, description="Target unique days per theater"),
    current_user=Depends(get_current_user)
):
    """Get scrape recommendations for better tier discovery."""
    company_id = current_user.get("company_id", 1)

    service = PriceTierDiscoveryService(company_id)
    recommendations = service.get_scrape_recommendations(
        target_samples_per_theater=target_samples,
        target_days_per_theater=target_days
    )

    return recommendations


@router.get(
    "/analyze/{theater_name}",
    summary="Get pricing analysis for a theater",
    description="""
    Get detailed pricing breakdown for a theater including:
    - Price ranges by ticket type (Adult, Senior, Child, etc.)
    - Price ranges by format (Standard, IMAX, Dolby, etc.)
    - Price by showtime
    - Summary statistics
    """
)
async def analyze_theater_pricing(
    theater_name: str,
    current_user=Depends(get_current_user)
):
    """Get detailed pricing analysis for a theater."""
    company_id = current_user.get("company_id", 1)

    service = PriceTierDiscoveryService(company_id)
    analysis = service.analyze_theater_pricing(theater_name)

    if not analysis.get("summary", {}).get("total_prices"):
        raise HTTPException(
            status_code=404,
            detail=f"No price data found for {theater_name}"
        )

    return analysis


@router.post(
    "/save-baselines",
    response_model=SaveBaselinesResponse,
    summary="Save discovered tiers as baselines",
    description="""
    Save discovered pricing tiers and discount days as PriceBaseline records.

    Regular tiers are saved with:
    - daypart = tier name (e.g., "Matinee", "Evening")
    - day_of_week = NULL (applies to all regular days)

    Discount days are saved with:
    - daypart = program name (e.g., "$8 Tuesdays")
    - day_type = "discount"
    - day_of_week = specific day (e.g., 1 for Tuesday)

    This allows the alert system to compare:
    - Regular day prices against regular baselines
    - Discount day prices against discount baselines
    """
)
async def save_tiers_as_baselines(
    request: SaveBaselinesRequest,
    current_user=Depends(get_current_user)
):
    """Save discovered tiers as price baselines."""
    from app.price_tier_discovery import TheaterPricingProfile, PriceTier, DiscountDay
    from datetime import time
    from decimal import Decimal

    company_id = current_user.get("company_id", 1)
    service = PriceTierDiscoveryService(company_id)

    # Reconstruct profile objects from request
    profiles = []
    for profile_data in request.profiles:
        # Reconstruct tiers
        tiers = []
        for tier_data in profile_data.get("tiers", []):
            start_time = None
            if tier_data.get("start_time"):
                parts = tier_data["start_time"].split(":")
                start_time = time(int(parts[0]), int(parts[1]))

            end_time = None
            if tier_data.get("end_time"):
                parts = tier_data["end_time"].split(":")
                end_time = time(int(parts[0]), int(parts[1]))

            tiers.append(PriceTier(
                tier_name=tier_data["tier_name"],
                price=Decimal(str(tier_data["price"])),
                start_time=start_time,
                end_time=end_time,
                sample_count=tier_data.get("sample_count", 0),
                price_variance=tier_data.get("price_variance", 0)
            ))

        # Reconstruct discount days
        discount_days = []
        for dd_data in profile_data.get("discount_days", []):
            discount_days.append(DiscountDay(
                day_of_week=dd_data["day_of_week"],
                price=Decimal(str(dd_data["price"])),
                sample_count=dd_data.get("sample_count", 0),
                price_variance=dd_data.get("price_variance", 0),
                program_name=dd_data.get("program_name")
            ))

        profiles.append(TheaterPricingProfile(
            theater_name=profile_data["theater_name"],
            ticket_type=profile_data["ticket_type"],
            format_type=profile_data.get("format", "Standard"),
            tiers=tiers,
            discount_days=discount_days,
            regular_day_count=profile_data.get("regular_day_count", 0),
            total_samples=profile_data.get("total_samples", 0)
        ))

    result = service.save_tiers_as_baselines(profiles, overwrite=request.overwrite)
    return result


@router.get(
    "/compare-discount-programs",
    summary="Compare discount programs across theaters",
    description="""
    Compare discount day offerings across all theaters in a market.

    Useful for understanding:
    - Which competitors have discount days
    - What day(s) they run discounts
    - What prices they offer
    - How your circuit compares
    """
)
async def compare_discount_programs(
    market_name: Optional[str] = Query(None, description="Filter by market"),
    current_user=Depends(get_current_user)
):
    """Compare discount programs across theaters."""
    from app.db_session import get_session
    from app.db_models import Price, Showing
    from sqlalchemy import and_, func
    from collections import defaultdict

    company_id = current_user.get("company_id", 1)
    service = PriceTierDiscoveryService(company_id)

    with get_session() as session:
        # Get all theaters (optionally filtered by market)
        query = session.query(
            Showing.theater_name
        ).join(
            Price, Price.showing_id == Showing.showing_id
        ).filter(
            Price.company_id == company_id
        )

        if market_name:
            # Note: This assumes theater_name contains market info or we have market mapping
            # For now, we'll filter based on any market info available
            pass

        theaters = [t[0] for t in query.distinct().all()]

    comparison = {
        "theaters_with_discounts": [],
        "theaters_without_discounts": [],
        "discount_day_summary": defaultdict(list),  # day -> list of theaters
        "price_comparison": {}
    }

    for theater_name in theaters:
        discount_days, _ = service.detect_discount_days(theater_name)

        if discount_days:
            theater_info = {
                "theater_name": theater_name,
                "discount_days": [dd.to_dict() for dd in discount_days]
            }
            comparison["theaters_with_discounts"].append(theater_info)

            for dd in discount_days:
                comparison["discount_day_summary"][dd.day_name].append({
                    "theater": theater_name,
                    "price": float(dd.price),
                    "program": dd.program_name
                })
        else:
            comparison["theaters_without_discounts"].append(theater_name)

    # Calculate price statistics by day
    for day, theaters in comparison["discount_day_summary"].items():
        prices = [t["price"] for t in theaters]
        if prices:
            comparison["price_comparison"][day] = {
                "min_price": min(prices),
                "max_price": max(prices),
                "avg_price": round(sum(prices) / len(prices), 2),
                "theater_count": len(prices)
            }

    comparison["discount_day_summary"] = dict(comparison["discount_day_summary"])

    return comparison
