"""
Theater Amenities API Router

Endpoints for managing competitor theater amenities and features.

Endpoints:
    GET    /api/v1/theater-amenities             - List theater amenities
    GET    /api/v1/theater-amenities/{id}        - Get specific theater
    POST   /api/v1/theater-amenities             - Create amenity record
    PUT    /api/v1/theater-amenities/{id}        - Update amenity record
    DELETE /api/v1/theater-amenities/{id}        - Delete amenity record
    GET    /api/v1/theater-amenities/summary     - Get amenity summary by circuit
"""

from datetime import datetime, UTC
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from api.routers.auth import require_read_admin, require_operator
from app.db_session import get_session
from app.audit_service import audit_service
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class TheaterAmenitiesRequest(BaseModel):
    """Request for creating/updating theater amenities."""
    theater_name: str
    circuit_name: Optional[str] = None

    # Seating
    has_recliners: Optional[bool] = None
    has_reserved_seating: Optional[bool] = None
    has_heated_seats: Optional[bool] = None

    # Premium formats
    has_imax: Optional[bool] = None
    has_dolby_cinema: Optional[bool] = None
    has_dolby_atmos: Optional[bool] = None
    has_rpx: Optional[bool] = None
    has_4dx: Optional[bool] = None
    has_screenx: Optional[bool] = None
    has_dbox: Optional[bool] = None

    # Food & beverage
    has_dine_in: Optional[bool] = None
    has_full_bar: Optional[bool] = None
    has_premium_concessions: Optional[bool] = None
    has_reserved_food_delivery: Optional[bool] = None

    # Theater info
    screen_count: Optional[int] = Field(None, ge=1)
    premium_screen_count: Optional[int] = Field(None, ge=0)
    year_built: Optional[int] = Field(None, ge=1900, le=2100)
    year_renovated: Optional[int] = Field(None, ge=1900, le=2100)

    # Metadata
    notes: Optional[str] = None
    source: Optional[str] = "manual"


class TheaterAmenitiesResponse(BaseModel):
    """Response for theater amenities."""
    id: int
    theater_name: str
    circuit_name: Optional[str] = None

    # Seating
    has_recliners: Optional[bool] = None
    has_reserved_seating: Optional[bool] = None
    has_heated_seats: Optional[bool] = None

    # Premium formats
    has_imax: Optional[bool] = None
    has_dolby_cinema: Optional[bool] = None
    has_dolby_atmos: Optional[bool] = None
    has_rpx: Optional[bool] = None
    has_4dx: Optional[bool] = None
    has_screenx: Optional[bool] = None
    has_dbox: Optional[bool] = None

    # Food & beverage
    has_dine_in: Optional[bool] = None
    has_full_bar: Optional[bool] = None
    has_premium_concessions: Optional[bool] = None
    has_reserved_food_delivery: Optional[bool] = None

    # Theater info
    screen_count: Optional[int] = None
    premium_screen_count: Optional[int] = None
    year_built: Optional[int] = None
    year_renovated: Optional[int] = None

    # Computed properties
    premium_formats: List[str] = []
    amenity_score: int = 0

    # Metadata
    notes: Optional[str] = None
    source: Optional[str] = None
    last_verified: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class AmenitySummary(BaseModel):
    """Summary of amenities by circuit."""
    circuit_name: str
    theater_count: int
    with_recliners: int
    with_reserved_seating: int
    with_imax: int
    with_dolby: int
    with_dine_in: int
    with_bar: int
    avg_amenity_score: float


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/theater-amenities", response_model=List[TheaterAmenitiesResponse], tags=["Theater Amenities"])
async def list_theater_amenities(
    theater_name: Optional[str] = Query(None, description="Filter by theater (partial match)"),
    circuit_name: Optional[str] = Query(None, description="Filter by circuit"),
    has_recliners: Optional[bool] = Query(None, description="Filter by recliners"),
    has_imax: Optional[bool] = Query(None, description="Filter by IMAX"),
    has_dolby: Optional[bool] = Query(None, description="Filter by Dolby Cinema/Atmos"),
    has_dine_in: Optional[bool] = Query(None, description="Filter by dine-in"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(require_read_admin)
):
    """
    List theater amenities with optional filtering.
    """
    try:
        from app.db_models import TheaterAmenities

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            query = session.query(TheaterAmenities).filter(
                TheaterAmenities.company_id == company_id
            )

            if theater_name:
                query = query.filter(TheaterAmenities.theater_name.ilike(f"%{theater_name}%"))
            if circuit_name:
                query = query.filter(TheaterAmenities.circuit_name == circuit_name)
            if has_recliners is not None:
                query = query.filter(TheaterAmenities.has_recliners == has_recliners)
            if has_imax is not None:
                query = query.filter(TheaterAmenities.has_imax == has_imax)
            if has_dolby is not None:
                query = query.filter(
                    (TheaterAmenities.has_dolby_cinema == has_dolby) |
                    (TheaterAmenities.has_dolby_atmos == has_dolby)
                )
            if has_dine_in is not None:
                query = query.filter(TheaterAmenities.has_dine_in == has_dine_in)

            total = query.count()
            amenities = query.order_by(TheaterAmenities.theater_name).offset(offset).limit(limit).all()

            return [_to_response(a) for a in amenities]

    except Exception as e:
        logger.exception(f"Error listing theater amenities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/theater-amenities/summary", response_model=List[AmenitySummary], tags=["Theater Amenities"])
async def get_amenities_summary(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get amenity summary statistics by circuit.
    """
    try:
        from app.db_models import TheaterAmenities
        from sqlalchemy import func

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            # Get all amenities for this company
            amenities = session.query(TheaterAmenities).filter(
                TheaterAmenities.company_id == company_id
            ).all()

            # Group by circuit
            circuits: Dict[str, List] = {}
            for a in amenities:
                circuit = a.circuit_name or "Unknown"
                if circuit not in circuits:
                    circuits[circuit] = []
                circuits[circuit].append(a)

            summaries = []
            for circuit, theaters in circuits.items():
                count = len(theaters)
                summaries.append(AmenitySummary(
                    circuit_name=circuit,
                    theater_count=count,
                    with_recliners=sum(1 for t in theaters if t.has_recliners),
                    with_reserved_seating=sum(1 for t in theaters if t.has_reserved_seating),
                    with_imax=sum(1 for t in theaters if t.has_imax),
                    with_dolby=sum(1 for t in theaters if t.has_dolby_cinema or t.has_dolby_atmos),
                    with_dine_in=sum(1 for t in theaters if t.has_dine_in),
                    with_bar=sum(1 for t in theaters if t.has_full_bar),
                    avg_amenity_score=round(sum(t.amenity_score for t in theaters) / count, 1) if count else 0
                ))

            return sorted(summaries, key=lambda x: x.theater_count, reverse=True)

    except Exception as e:
        logger.exception(f"Error getting amenities summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/theater-amenities/{amenity_id}", response_model=TheaterAmenitiesResponse, tags=["Theater Amenities"])
async def get_theater_amenities(
    amenity_id: int,
    current_user: dict = Depends(require_read_admin)
):
    """
    Get a specific theater's amenities by ID.
    """
    try:
        from app.db_models import TheaterAmenities

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            amenities = session.query(TheaterAmenities).filter(
                TheaterAmenities.id == amenity_id,
                TheaterAmenities.company_id == company_id
            ).first()

            if not amenities:
                raise HTTPException(status_code=404, detail=f"Theater amenities {amenity_id} not found")

            return _to_response(amenities)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting theater amenities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/theater-amenities", response_model=TheaterAmenitiesResponse, status_code=201, tags=["Theater Amenities"])
async def create_theater_amenities(
    request: TheaterAmenitiesRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Create a new theater amenities record.
    """
    try:
        from app.db_models import TheaterAmenities

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            # Check for existing record
            existing = session.query(TheaterAmenities).filter(
                TheaterAmenities.company_id == company_id,
                TheaterAmenities.theater_name == request.theater_name
            ).first()

            if existing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Amenities already exist for theater '{request.theater_name}'. Use PUT to update."
                )

            amenities = TheaterAmenities(
                company_id=company_id,
                theater_name=request.theater_name,
                circuit_name=request.circuit_name,
                has_recliners=request.has_recliners,
                has_reserved_seating=request.has_reserved_seating,
                has_heated_seats=request.has_heated_seats,
                has_imax=request.has_imax,
                has_dolby_cinema=request.has_dolby_cinema,
                has_dolby_atmos=request.has_dolby_atmos,
                has_rpx=request.has_rpx,
                has_4dx=request.has_4dx,
                has_screenx=request.has_screenx,
                has_dbox=request.has_dbox,
                has_dine_in=request.has_dine_in,
                has_full_bar=request.has_full_bar,
                has_premium_concessions=request.has_premium_concessions,
                has_reserved_food_delivery=request.has_reserved_food_delivery,
                screen_count=request.screen_count,
                premium_screen_count=request.premium_screen_count,
                year_built=request.year_built,
                year_renovated=request.year_renovated,
                notes=request.notes,
                source=request.source or "manual"
            )
            session.add(amenities)
            session.flush()

            audit_service.data_event(
                event_type="create_theater_amenities",
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                company_id=company_id,
                details={
                    "theater": request.theater_name,
                    "circuit": request.circuit_name
                }
            )

            logger.info(f"Theater amenities created: {amenities.theater_name}")

            return _to_response(amenities)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating theater amenities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/theater-amenities/{amenity_id}", response_model=TheaterAmenitiesResponse, tags=["Theater Amenities"])
async def update_theater_amenities(
    amenity_id: int,
    request: TheaterAmenitiesRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Update a theater amenities record.
    """
    try:
        from app.db_models import TheaterAmenities

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            amenities = session.query(TheaterAmenities).filter(
                TheaterAmenities.id == amenity_id,
                TheaterAmenities.company_id == company_id
            ).first()

            if not amenities:
                raise HTTPException(status_code=404, detail=f"Theater amenities {amenity_id} not found")

            # Update fields
            amenities.theater_name = request.theater_name
            amenities.circuit_name = request.circuit_name
            amenities.has_recliners = request.has_recliners
            amenities.has_reserved_seating = request.has_reserved_seating
            amenities.has_heated_seats = request.has_heated_seats
            amenities.has_imax = request.has_imax
            amenities.has_dolby_cinema = request.has_dolby_cinema
            amenities.has_dolby_atmos = request.has_dolby_atmos
            amenities.has_rpx = request.has_rpx
            amenities.has_4dx = request.has_4dx
            amenities.has_screenx = request.has_screenx
            amenities.has_dbox = request.has_dbox
            amenities.has_dine_in = request.has_dine_in
            amenities.has_full_bar = request.has_full_bar
            amenities.has_premium_concessions = request.has_premium_concessions
            amenities.has_reserved_food_delivery = request.has_reserved_food_delivery
            amenities.screen_count = request.screen_count
            amenities.premium_screen_count = request.premium_screen_count
            amenities.year_built = request.year_built
            amenities.year_renovated = request.year_renovated
            amenities.notes = request.notes
            amenities.source = request.source or amenities.source
            amenities.last_verified = datetime.now(UTC)

            session.flush()

            logger.info(f"Theater amenities updated: {amenities.id}")

            return _to_response(amenities)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating theater amenities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/theater-amenities/{amenity_id}", status_code=204, tags=["Theater Amenities"])
async def delete_theater_amenities(
    amenity_id: int,
    current_user: dict = Depends(require_operator)
):
    """
    Delete a theater amenities record.
    """
    try:
        from app.db_models import TheaterAmenities

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            amenities = session.query(TheaterAmenities).filter(
                TheaterAmenities.id == amenity_id,
                TheaterAmenities.company_id == company_id
            ).first()

            if not amenities:
                raise HTTPException(status_code=404, detail=f"Theater amenities {amenity_id} not found")

            theater_name = amenities.theater_name
            session.delete(amenities)
            session.flush()

            audit_service.data_event(
                event_type="delete_theater_amenities",
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                company_id=company_id,
                details={"amenity_id": amenity_id, "theater": theater_name}
            )

            logger.info(f"Theater amenities deleted: {amenity_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting theater amenities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DISCOVERY ENDPOINTS
# ============================================================================

class DiscoveryRequest(BaseModel):
    """Request for discovering theater amenities from showings data."""
    theater_name: Optional[str] = None
    circuit_name: Optional[str] = None
    lookback_days: int = Field(30, ge=7, le=180, description="Days of data to analyze")


class ScreenCountEstimate(BaseModel):
    """Screen count estimate for a format category."""
    category: str
    estimated_screens: int
    showtimes_analyzed: int


class DiscoveryResult(BaseModel):
    """Result of amenity discovery."""
    theater_name: str
    formats_discovered: Dict[str, List[str]]
    screen_counts: Dict[str, int]
    amenities_updated: bool


class FormatSummary(BaseModel):
    """Summary of formats across all theaters."""
    by_format: Dict[str, int]
    by_category: Dict[str, int]
    total_theaters_with_plf: int


@router.post("/theater-amenities/discover", response_model=DiscoveryResult, tags=["Theater Amenities"])
async def discover_theater_amenities_endpoint(
    request: DiscoveryRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Discover and update theater amenities from showings data.

    Analyzes recent showings to:
    - Identify which premium formats the theater offers (IMAX, Dolby, etc.)
    - Estimate screen counts from overlapping showtimes
    - Update the theater_amenities record
    """
    try:
        from app.theater_amenity_discovery import TheaterAmenityDiscoveryService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        if not request.theater_name:
            raise HTTPException(status_code=400, detail="theater_name is required")

        service = TheaterAmenityDiscoveryService(company_id)

        # Discover formats
        formats = service.discover_theater_formats(request.theater_name, request.lookback_days)

        # Estimate screen counts
        screen_counts = service.estimate_screen_counts(
            request.theater_name,
            lookback_days=request.lookback_days
        )

        # Update amenities record
        amenities = service.update_theater_amenities(
            request.theater_name,
            circuit_name=request.circuit_name,
            lookback_days=request.lookback_days
        )

        logger.info(f"Discovered amenities for {request.theater_name}: formats={formats}, screens={screen_counts}")

        return DiscoveryResult(
            theater_name=request.theater_name,
            formats_discovered=formats,
            screen_counts=screen_counts,
            amenities_updated=amenities is not None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error discovering theater amenities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/theater-amenities/discover-all", tags=["Theater Amenities"])
async def discover_all_theater_amenities(
    request: DiscoveryRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Discover amenities for all theaters (optionally filtered by circuit).

    This can take a while for many theaters. Returns count of updated records.
    """
    try:
        from app.theater_amenity_discovery import TheaterAmenityDiscoveryService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        service = TheaterAmenityDiscoveryService(company_id)
        results = service.discover_all_theaters(
            circuit_name=request.circuit_name,
            lookback_days=request.lookback_days
        )

        logger.info(f"Discovered amenities for {len(results)} theaters")

        return {
            "theaters_updated": len(results),
            "circuit_filter": request.circuit_name,
            "lookback_days": request.lookback_days
        }

    except Exception as e:
        logger.exception(f"Error discovering all theater amenities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/theater-amenities/format-summary", response_model=FormatSummary, tags=["Theater Amenities"])
async def get_format_summary(
    lookback_days: int = Query(30, ge=7, le=180, description="Days of data to analyze"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Get a summary of premium formats across all theaters.

    Shows which formats are available and how many theaters have each.
    """
    try:
        from app.theater_amenity_discovery import TheaterAmenityDiscoveryService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        service = TheaterAmenityDiscoveryService(company_id)
        summary = service.get_format_summary(lookback_days)

        return FormatSummary(
            by_format=summary['by_format'],
            by_category=summary['by_category'],
            total_theaters_with_plf=summary['total_theaters_with_plf']
        )

    except Exception as e:
        logger.exception(f"Error getting format summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/theater-amenities/screen-counts/{theater_name}", tags=["Theater Amenities"])
async def get_screen_count_estimate(
    theater_name: str,
    lookback_days: int = Query(14, ge=7, le=90, description="Days of data to analyze"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Get estimated screen counts for a specific theater.

    Analyzes overlapping showtimes to determine how many screens of each
    format type the theater likely has.
    """
    try:
        from app.theater_amenity_discovery import TheaterAmenityDiscoveryService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        service = TheaterAmenityDiscoveryService(company_id)

        # Get format summary for this theater
        formats = service.discover_theater_formats(theater_name, lookback_days)

        # Get screen counts
        screen_counts = service.estimate_screen_counts(theater_name, lookback_days=lookback_days)

        # Get total screens estimate
        total = service._estimate_total_screens(theater_name, lookback_days)

        return {
            "theater_name": theater_name,
            "formats_available": formats,
            "screen_counts_by_category": screen_counts,
            "estimated_total_screens": total,
            "lookback_days": lookback_days
        }

    except Exception as e:
        logger.exception(f"Error estimating screen counts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _to_response(amenities) -> TheaterAmenitiesResponse:
    """Convert TheaterAmenities model to response."""
    return TheaterAmenitiesResponse(
        id=amenities.id,
        theater_name=amenities.theater_name,
        circuit_name=amenities.circuit_name,
        has_recliners=amenities.has_recliners,
        has_reserved_seating=amenities.has_reserved_seating,
        has_heated_seats=amenities.has_heated_seats,
        has_imax=amenities.has_imax,
        has_dolby_cinema=amenities.has_dolby_cinema,
        has_dolby_atmos=amenities.has_dolby_atmos,
        has_rpx=amenities.has_rpx,
        has_4dx=amenities.has_4dx,
        has_screenx=amenities.has_screenx,
        has_dbox=amenities.has_dbox,
        has_dine_in=amenities.has_dine_in,
        has_full_bar=amenities.has_full_bar,
        has_premium_concessions=amenities.has_premium_concessions,
        has_reserved_food_delivery=amenities.has_reserved_food_delivery,
        screen_count=amenities.screen_count,
        premium_screen_count=amenities.premium_screen_count,
        year_built=amenities.year_built,
        year_renovated=amenities.year_renovated,
        premium_formats=amenities.premium_formats,
        amenity_score=amenities.amenity_score,
        notes=amenities.notes,
        source=amenities.source,
        last_verified=amenities.last_verified,
        created_at=amenities.created_at,
        updated_at=amenities.updated_at
    )
