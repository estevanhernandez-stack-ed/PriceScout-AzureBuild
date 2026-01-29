"""
Theater Onboarding API Router

Endpoints for managing the theater onboarding workflow:
- GET /theater-onboarding/status/{theater_name} - Get onboarding status
- GET /theater-onboarding/pending - List pending theaters
- POST /theater-onboarding/start - Start onboarding
- POST /theater-onboarding/{theater_name}/scrape - Record initial scrape
- POST /theater-onboarding/{theater_name}/discover - Discover baselines
- POST /theater-onboarding/{theater_name}/link - Link to profile
- POST /theater-onboarding/{theater_name}/confirm - Confirm baselines
- GET /theater-onboarding/{theater_name}/coverage - Get coverage indicators
"""

from fastapi import APIRouter, HTTPException, Security, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime

from api.routers.auth import get_current_user, User
from app.db_session import get_session
from app.theater_onboarding_service import TheaterOnboardingService


router = APIRouter(prefix="/theater-onboarding", tags=["Theater Onboarding"])


# Request/Response Models

class StartOnboardingRequest(BaseModel):
    theater_name: str = Field(..., description="Name of the theater to onboard")
    circuit_name: Optional[str] = Field(None, description="Circuit/chain name (auto-detected if not provided)")
    market: Optional[str] = Field(None, description="Market name")


class RecordScrapeRequest(BaseModel):
    source: str = Field(..., description="Data source: 'fandango' or 'enttelligence'")
    count: int = Field(..., description="Number of price records collected")


class DiscoverBaselinesRequest(BaseModel):
    lookback_days: int = Field(30, ge=7, le=365, description="Days to look back for price data")
    min_samples: int = Field(5, ge=3, le=100, description="Minimum samples per baseline")


class LinkProfileRequest(BaseModel):
    circuit_name: Optional[str] = Field(None, description="Circuit name (auto-detected if not provided)")


class ConfirmBaselinesRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Optional notes about the confirmation")


class BulkStartRequest(BaseModel):
    theaters: List[Dict[str, str]] = Field(..., description="List of theaters with 'name' and optional 'circuit'")
    market: str = Field(..., description="Market name for all theaters")


class OnboardingStepDetail(BaseModel):
    completed: bool
    timestamp: Optional[str]


class OnboardingStatusResponse(BaseModel):
    theater_name: str
    circuit_name: Optional[str]
    market: Optional[str]
    onboarding_status: str
    progress_percent: int
    completed_steps: int
    total_steps: int
    steps: Dict[str, Any]
    coverage: Dict[str, Any]
    notes: Optional[str]
    last_updated_at: Optional[str]


class PendingTheaterResponse(BaseModel):
    theater_name: str
    circuit_name: Optional[str]
    market: Optional[str]
    onboarding_status: str
    progress_percent: int
    next_step: str
    last_updated_at: Optional[str]


class CoverageResponse(BaseModel):
    theater_name: str
    baseline_count: int
    formats_discovered: List[str]
    formats_expected: List[str]
    format_coverage: float
    ticket_types_discovered: List[str]
    ticket_types_expected: List[str]
    ticket_type_coverage: float
    dayparts_discovered: List[str]
    dayparts_expected: List[str]
    daypart_coverage: float
    overall_score: float
    gaps: Dict[str, List[str]]


class DiscoveryResultResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    baselines_created: int = 0
    formats_discovered: List[str] = []
    ticket_types_discovered: List[str] = []
    dayparts_discovered: List[str] = []
    coverage_score: float = 0.0
    gaps: Dict[str, List[str]] = {}


# Endpoints

@router.get("/status/{theater_name}", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    theater_name: str,
    current_user: User = Security(get_current_user, scopes=["read:baselines"])
):
    """Get detailed onboarding status for a theater."""
    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        status = service.get_onboarding_status(theater_name)

        if not status:
            raise HTTPException(status_code=404, detail=f"No onboarding status found for theater: {theater_name}")

        return status


@router.get("/pending", response_model=List[PendingTheaterResponse])
async def list_pending_theaters(
    current_user: User = Security(get_current_user, scopes=["read:baselines"])
):
    """List all theaters with incomplete onboarding."""
    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        return service.list_pending_theaters()


@router.post("/start", response_model=OnboardingStatusResponse)
async def start_onboarding(
    request: StartOnboardingRequest,
    current_user: User = Security(get_current_user, scopes=["write:baselines"])
):
    """Start the onboarding process for a new theater."""
    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        status = service.start_onboarding(
            theater_name=request.theater_name,
            circuit_name=request.circuit_name,
            market=request.market
        )
        return service.get_onboarding_status(status.theater_name)


@router.post("/bulk-start", response_model=List[PendingTheaterResponse])
async def bulk_start_onboarding(
    request: BulkStartRequest,
    current_user: User = Security(get_current_user, scopes=["write:baselines"])
):
    """Start onboarding for multiple theaters at once."""
    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        service.bulk_start_onboarding(
            theaters=request.theaters,
            market=request.market
        )
        return service.list_theaters_by_market(request.market)


@router.post("/{theater_name}/scrape", response_model=OnboardingStatusResponse)
async def record_initial_scrape(
    theater_name: str,
    request: RecordScrapeRequest,
    current_user: User = Security(get_current_user, scopes=["write:baselines"])
):
    """Record that initial price collection has been completed."""
    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        service.record_initial_scrape(
            theater_name=theater_name,
            source=request.source,
            count=request.count
        )
        return service.get_onboarding_status(theater_name)


@router.post("/{theater_name}/discover", response_model=DiscoveryResultResponse)
async def discover_theater_baselines(
    theater_name: str,
    request: DiscoverBaselinesRequest = None,
    current_user: User = Security(get_current_user, scopes=["write:baselines"])
):
    """Discover baselines from collected price data."""
    if request is None:
        request = DiscoverBaselinesRequest()

    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        return service.discover_baselines(
            theater_name=theater_name,
            lookback_days=request.lookback_days,
            min_samples=request.min_samples
        )


@router.post("/{theater_name}/link", response_model=OnboardingStatusResponse)
async def link_to_profile(
    theater_name: str,
    request: LinkProfileRequest = None,
    current_user: User = Security(get_current_user, scopes=["write:baselines"])
):
    """Link theater to a company profile."""
    if request is None:
        request = LinkProfileRequest()

    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        try:
            service.link_to_profile(
                theater_name=theater_name,
                circuit_name=request.circuit_name
            )
            return service.get_onboarding_status(theater_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/{theater_name}/confirm", response_model=OnboardingStatusResponse)
async def confirm_baselines(
    theater_name: str,
    request: ConfirmBaselinesRequest = None,
    current_user: User = Security(get_current_user, scopes=["write:baselines"])
):
    """Confirm baselines after user review."""
    if request is None:
        request = ConfirmBaselinesRequest()

    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        service.confirm_baselines(
            theater_name=theater_name,
            user_id=current_user.user_id,
            notes=request.notes
        )
        return service.get_onboarding_status(theater_name)


@router.get("/{theater_name}/coverage", response_model=CoverageResponse)
async def get_coverage_indicators(
    theater_name: str,
    current_user: User = Security(get_current_user, scopes=["read:baselines"])
):
    """Get detailed coverage indicators showing what's discovered vs missing."""
    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        return service.get_coverage_indicators(theater_name)


@router.get("/market/{market}", response_model=List[Dict[str, Any]])
async def list_theaters_by_market(
    market: str,
    current_user: User = Security(get_current_user, scopes=["read:baselines"])
):
    """List all theaters in a market with their onboarding status."""
    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        return service.list_theaters_by_market(market)


# =============================================================================
# AMENITY DISCOVERY ENDPOINTS
# =============================================================================

class AmenityDiscoveryRequest(BaseModel):
    lookback_days: int = Field(30, ge=7, le=180, description="Days of showings data to analyze")


class BackfillAmenitiesRequest(BaseModel):
    circuit_name: Optional[str] = Field(None, description="Filter by circuit")
    market: Optional[str] = Field(None, description="Filter by market")
    lookback_days: int = Field(30, ge=7, le=180, description="Days of showings data to analyze")
    force_refresh: bool = Field(False, description="Refresh existing amenities records (not just missing ones)")


class TheaterMissingAmenities(BaseModel):
    theater_name: str
    circuit_name: Optional[str]
    market: Optional[str]
    showing_count: int
    format_count: int
    onboarding_status: str


class AmenityDiscoveryResult(BaseModel):
    theater_name: str
    formats_discovered: Dict[str, List[str]]
    screen_counts: Dict[str, int]
    amenities_updated: bool
    amenity_id: Optional[int]


class BackfillResult(BaseModel):
    theaters_checked: int
    theaters_needing_amenities: int
    theaters_updated: int
    theaters_failed: int
    details: List[Dict[str, Any]]


@router.get("/amenities/missing", response_model=List[TheaterMissingAmenities])
async def get_theaters_missing_amenities(
    circuit_name: Optional[str] = Query(None, description="Filter by circuit"),
    current_user: User = Security(get_current_user, scopes=["read:baselines"])
):
    """
    List theaters that have showings data but no amenities record.

    Use this to identify which theaters need amenity discovery.
    """
    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        return service.get_theaters_missing_amenities(circuit_name)


@router.post("/{theater_name}/amenities", response_model=AmenityDiscoveryResult)
async def discover_theater_amenities(
    theater_name: str,
    request: AmenityDiscoveryRequest = None,
    current_user: User = Security(get_current_user, scopes=["write:baselines"])
):
    """
    Discover amenities for a specific theater from showings data.

    Analyzes recent showings to determine:
    - Premium formats available (IMAX, Dolby, 4DX, etc.)
    - Estimated screen counts from overlapping showtimes
    """
    if request is None:
        request = AmenityDiscoveryRequest()

    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        return service.discover_theater_amenities(
            theater_name=theater_name,
            lookback_days=request.lookback_days
        )


@router.post("/amenities/backfill", response_model=BackfillResult)
async def backfill_amenities(
    request: BackfillAmenitiesRequest = None,
    current_user: User = Security(get_current_user, scopes=["write:baselines"])
):
    """
    Backfill amenities for all existing theaters with showings data.

    This populates amenities for theaters that were scraped before amenity
    discovery was integrated into onboarding. Use force_refresh=true to
    update existing records with new PLF screen counts.
    """
    if request is None:
        request = BackfillAmenitiesRequest()

    with get_session() as session:
        service = TheaterOnboardingService(session, current_user.company_id)
        return service.backfill_amenities_for_existing_theaters(
            circuit_name=request.circuit_name,
            market=request.market,
            lookback_days=request.lookback_days,
            force_refresh=request.force_refresh
        )
