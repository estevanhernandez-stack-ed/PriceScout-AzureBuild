"""
Market Context API Router
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from typing import List, Optional
from datetime import date
from pydantic import BaseModel

from api.routers.auth import require_read_admin, require_operator
from api.services.market_context_service import get_market_context_service

router = APIRouter(prefix="/market-context", tags=["Market Context"])

class SyncTheatersRequest(BaseModel):
    theater_names: Optional[List[str]] = None


class TheaterMetadataResponse(BaseModel):
    theater_name: str
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip_code: Optional[str]
    market: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    circuit_name: Optional[str]

    class Config:
        from_attributes = True

class MarketEventResponse(BaseModel):
    event_id: int
    event_name: str
    event_type: str
    start_date: date
    end_date: date
    scope: str
    scope_value: Optional[str]
    impact_score: int
    description: Optional[str]

    class Config:
        from_attributes = True

class TheaterOperatingHoursResponse(BaseModel):
    day_of_week: int
    open_time: Optional[str]
    close_time: Optional[str]
    first_showtime: Optional[str]
    last_showtime: Optional[str]

    class Config:
        from_attributes = True

class TheaterOperatingHoursUpdate(BaseModel):
    theater_name: str
    hours: List[TheaterOperatingHoursResponse]

@router.get("/theaters", response_model=List[TheaterMetadataResponse])
async def get_theaters(current_user: dict = Depends(require_read_admin)):
    """Get all theater metadata for the user's company"""
    company_id = 1 # Default for now
    service = get_market_context_service()
    return service.get_theaters_metadata(company_id)

@router.get("/events", response_model=List[MarketEventResponse])
async def get_events(
    start_date: date,
    end_date: date,
    market: Optional[str] = None,
    current_user: dict = Depends(require_read_admin)
):
    """Get market events for a date range and optional market filter"""
    company_id = 1
    service = get_market_context_service()
    return service.get_market_events(company_id, start_date, end_date, market)

@router.get("/operating-hours", response_model=List[TheaterOperatingHoursResponse])
async def get_theater_operating_hours(
    theater_name: str,
    current_user: dict = Depends(require_read_admin)
):
    """Get configured operating hours for a specific theater"""
    company_id = 1
    service = get_market_context_service()
    return service.get_theater_operating_hours(company_id, theater_name)

@router.post("/operating-hours")
async def update_theater_operating_hours(
    update: TheaterOperatingHoursUpdate,
    current_user: dict = Depends(require_operator)
):
    """Update configured operating hours for a theater"""
    company_id = 1
    service = get_market_context_service()
    success = service.update_theater_operating_hours(
        company_id, 
        update.theater_name, 
        [h.dict() for h in update.hours]
    )
    return {"status": "success"} if success else {"status": "error"}

@router.post("/sync/theaters")
async def sync_theaters(
    request: SyncTheatersRequest = Body(default=None),
    current_user: dict = Depends(require_operator)
):
    """Trigger a sync of theater metadata from EntTelligence"""
    company_id = 1
    service = get_market_context_service()

    theater_names = request.theater_names if request else None
    if not theater_names:
        # Default to theaters found in our showings or markets
        # For simplicity in this demo endpoint, if no names provided, we'll need a list.
        # Real implementation would pull from unique theater_name in Showing table.
        from app.db_adapter import get_session, Showing
        with get_session() as session:
            theater_names = [r[0] for r in session.query(Showing.theater_name).distinct().all()]
            print(f"[DEBUG] Found {len(theater_names)} unique theaters in Showings table")

    if not theater_names:
        return {"status": "skipped", "message": "No theater names found to sync"}

    # Also populate default events
    service.populate_default_events(company_id)

    # Use Celery for background processing
    from app.tasks.sync import sync_market_context_task
    task = sync_market_context_task.delay(company_id, theater_names)

    return {
        "status": "triggered",
        "message": f"Sync started for {len(theater_names)} theaters in the background",
        "task_id": task.id
    }


# ============================================================================
# HEATMAP DATA ENDPOINT
# ============================================================================

class HeatmapTheaterData(BaseModel):
    """Theater data for heatmap visualization."""
    theater_name: str
    circuit_name: Optional[str] = None
    market: Optional[str] = None
    latitude: float
    longitude: float
    avg_price: Optional[float] = None
    baseline_count: int = 0
    formats: List[str] = []


class HeatmapDataResponse(BaseModel):
    """Response containing all theaters with heatmap data."""
    total_theaters: int
    theaters_with_coords: int
    theaters: List[HeatmapTheaterData]


@router.get("/theaters/heatmap-data", response_model=HeatmapDataResponse, tags=["Heatmap"])
async def get_heatmap_data(
    market: Optional[str] = Query(None, description="Filter by market"),
    circuit: Optional[str] = Query(None, description="Filter by circuit"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Get theater data for heatmap visualization.

    Returns theaters with coordinates, average baseline prices, and metadata.
    Use filters to narrow down to specific markets or circuits.
    """
    from app.db_models import TheaterMetadata, PriceBaseline
    from app.db_session import get_session
    from sqlalchemy import func

    company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

    with get_session() as session:
        # Query theaters with their baseline info
        base_query = session.query(
            TheaterMetadata.theater_name,
            TheaterMetadata.circuit_name,
            TheaterMetadata.market,
            TheaterMetadata.latitude,
            TheaterMetadata.longitude,
            func.avg(PriceBaseline.baseline_price).label('avg_price'),
            func.count(PriceBaseline.baseline_id).label('baseline_count')
        ).outerjoin(
            PriceBaseline,
            (TheaterMetadata.theater_name == PriceBaseline.theater_name) &
            (TheaterMetadata.company_id == PriceBaseline.company_id) &
            (PriceBaseline.effective_to == None)
        ).filter(
            TheaterMetadata.company_id == company_id
        )

        # Apply filters
        if market:
            base_query = base_query.filter(TheaterMetadata.market == market)
        if circuit:
            base_query = base_query.filter(TheaterMetadata.circuit_name.ilike(f'%{circuit}%'))

        results = base_query.group_by(
            TheaterMetadata.theater_name,
            TheaterMetadata.circuit_name,
            TheaterMetadata.market,
            TheaterMetadata.latitude,
            TheaterMetadata.longitude
        ).all()

        # Also get formats for each theater
        format_query = session.query(
            PriceBaseline.theater_name,
            func.array_agg(func.distinct(PriceBaseline.format)).label('formats')
        ).filter(
            PriceBaseline.company_id == company_id,
            PriceBaseline.effective_to == None,
            PriceBaseline.format != None
        ).group_by(
            PriceBaseline.theater_name
        )

        # SQLite doesn't support array_agg, so handle this differently
        try:
            format_results = format_query.all()
            formats_by_theater = {r.theater_name: r.formats for r in format_results}
        except Exception:
            # Fallback for SQLite
            format_query = session.query(
                PriceBaseline.theater_name,
                PriceBaseline.format
            ).filter(
                PriceBaseline.company_id == company_id,
                PriceBaseline.effective_to == None,
                PriceBaseline.format != None
            ).distinct()

            formats_by_theater = {}
            for r in format_query.all():
                if r.theater_name not in formats_by_theater:
                    formats_by_theater[r.theater_name] = []
                if r.format and r.format not in formats_by_theater[r.theater_name]:
                    formats_by_theater[r.theater_name].append(r.format)

        # Build response
        theaters = []
        theaters_with_coords = 0

        for row in results:
            has_coords = row.latitude is not None and row.longitude is not None
            if has_coords:
                theaters_with_coords += 1
                theaters.append(HeatmapTheaterData(
                    theater_name=row.theater_name,
                    circuit_name=row.circuit_name,
                    market=row.market,
                    latitude=float(row.latitude),
                    longitude=float(row.longitude),
                    avg_price=float(row.avg_price) if row.avg_price else None,
                    baseline_count=row.baseline_count or 0,
                    formats=formats_by_theater.get(row.theater_name, [])
                ))

        # Sort by baseline count (theaters with more data first)
        theaters.sort(key=lambda x: -x.baseline_count)

        return HeatmapDataResponse(
            total_theaters=len(results),
            theaters_with_coords=theaters_with_coords,
            theaters=theaters
        )
