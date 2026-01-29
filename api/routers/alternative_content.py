"""
Alternative Content API Router

Endpoints for managing Alternative Content (special events) films
and circuit AC pricing strategies.
"""

from datetime import datetime, timezone
from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from api.routers.auth import get_current_user, require_operator
from app.db_session import get_session
from app.db_models import AlternativeContentFilm, CircuitACPricing
from app.alternative_content_service import (
    AlternativeContentService,
    detect_content_type_from_title,
    normalize_title,
    CONTENT_TYPE_PATTERNS,
)
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/alternative-content", tags=["Alternative Content"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ACFilmResponse(BaseModel):
    """Response model for an Alternative Content film."""
    id: int
    film_title: str
    normalized_title: str
    content_type: str
    content_source: Optional[str] = None
    detected_by: str
    detection_confidence: float
    detection_reason: Optional[str] = None
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int
    is_verified: bool
    is_active: bool


class ACFilmListResponse(BaseModel):
    """Response model for list of AC films."""
    total: int
    films: List[ACFilmResponse]
    content_types: List[str]  # Available content types for filtering


class UpdateACFilmRequest(BaseModel):
    """Request model for updating an AC film."""
    content_type: Optional[str] = None
    content_source: Optional[str] = None
    is_verified: Optional[bool] = None
    is_active: Optional[bool] = None


class CreateACFilmRequest(BaseModel):
    """Request model for manually creating an AC film."""
    film_title: str
    content_type: str
    content_source: Optional[str] = None


class DetectionResultResponse(BaseModel):
    """Response model for detection results."""
    title_detected: int
    ticket_type_detected: int
    total_unique: int
    new_saved: int
    message: str


class CircuitACPricingResponse(BaseModel):
    """Response model for circuit AC pricing strategy."""
    id: int
    circuit_name: str
    content_type: str
    standard_ticket_type: Optional[str] = None
    discount_ticket_type: Optional[str] = None
    typical_price_min: Optional[float] = None
    typical_price_max: Optional[float] = None
    discount_day_applies: bool
    discount_day_ticket_type: Optional[str] = None
    discount_day_price: Optional[float] = None
    notes: Optional[str] = None
    source: Optional[str] = None


class UpdateCircuitACPricingRequest(BaseModel):
    """Request model for updating circuit AC pricing."""
    standard_ticket_type: Optional[str] = None
    discount_ticket_type: Optional[str] = None
    typical_price_min: Optional[float] = None
    typical_price_max: Optional[float] = None
    discount_day_applies: Optional[bool] = None
    discount_day_ticket_type: Optional[str] = None
    discount_day_price: Optional[float] = None
    notes: Optional[str] = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _film_to_response(film: AlternativeContentFilm) -> ACFilmResponse:
    """Convert a database film to response model."""
    return ACFilmResponse(
        id=film.id,
        film_title=film.film_title,
        normalized_title=film.normalized_title or '',
        content_type=film.content_type,
        content_source=film.content_source,
        detected_by=film.detected_by,
        detection_confidence=float(film.detection_confidence) if film.detection_confidence else 0.0,
        detection_reason=film.detection_reason,
        first_seen_at=film.first_seen_at,
        last_seen_at=film.last_seen_at,
        occurrence_count=film.occurrence_count or 1,
        is_verified=film.is_verified or False,
        is_active=film.is_active if film.is_active is not None else True,
    )


def _pricing_to_response(pricing: CircuitACPricing) -> CircuitACPricingResponse:
    """Convert a database pricing to response model."""
    return CircuitACPricingResponse(
        id=pricing.id,
        circuit_name=pricing.circuit_name,
        content_type=pricing.content_type,
        standard_ticket_type=pricing.standard_ticket_type,
        discount_ticket_type=pricing.discount_ticket_type,
        typical_price_min=float(pricing.typical_price_min) if pricing.typical_price_min else None,
        typical_price_max=float(pricing.typical_price_max) if pricing.typical_price_max else None,
        discount_day_applies=pricing.discount_day_applies or False,
        discount_day_ticket_type=pricing.discount_day_ticket_type,
        discount_day_price=float(pricing.discount_day_price) if pricing.discount_day_price else None,
        notes=pricing.notes,
        source=pricing.source,
    )


# ============================================================================
# AC FILMS ENDPOINTS
# ============================================================================

@router.get("", response_model=ACFilmListResponse)
async def list_ac_films(
    content_type: Optional[str] = Query(None, description="Filter by content type"),
    is_verified: Optional[bool] = Query(None, description="Filter by verification status"),
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search in film title"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """
    List Alternative Content films with optional filters.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        query = session.query(AlternativeContentFilm).filter(
            AlternativeContentFilm.company_id == company_id
        )

        if content_type:
            query = query.filter(AlternativeContentFilm.content_type == content_type)
        if is_verified is not None:
            query = query.filter(AlternativeContentFilm.is_verified == is_verified)
        if is_active is not None:
            query = query.filter(AlternativeContentFilm.is_active == is_active)
        if search:
            query = query.filter(AlternativeContentFilm.film_title.ilike(f"%{search}%"))

        total = query.count()

        films = query.order_by(
            AlternativeContentFilm.last_seen_at.desc()
        ).offset(offset).limit(limit).all()

        # Get available content types
        content_types = list(CONTENT_TYPE_PATTERNS.keys()) + ['unknown']

        return ACFilmListResponse(
            total=total,
            films=[_film_to_response(f) for f in films],
            content_types=content_types
        )


@router.get("/{film_id}", response_model=ACFilmResponse)
async def get_ac_film(
    film_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific Alternative Content film."""
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        film = session.query(AlternativeContentFilm).filter(
            AlternativeContentFilm.company_id == company_id,
            AlternativeContentFilm.id == film_id
        ).first()

        if not film:
            raise HTTPException(status_code=404, detail="AC film not found")

        return _film_to_response(film)


@router.post("", response_model=ACFilmResponse)
async def create_ac_film(
    request: CreateACFilmRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Manually create an Alternative Content film entry.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        # Check if already exists
        normalized = normalize_title(request.film_title)
        existing = session.query(AlternativeContentFilm).filter(
            AlternativeContentFilm.company_id == company_id,
            AlternativeContentFilm.normalized_title == normalized
        ).first()

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Film already exists with id {existing.id}"
            )

        film = AlternativeContentFilm(
            company_id=company_id,
            film_title=request.film_title,
            normalized_title=normalized,
            content_type=request.content_type,
            content_source=request.content_source,
            detected_by='manual',
            detection_confidence=Decimal('1.0'),
            detection_reason='Manually added',
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            occurrence_count=1,
            is_verified=True,
        )

        session.add(film)
        session.commit()
        session.refresh(film)

        return _film_to_response(film)


@router.put("/{film_id}", response_model=ACFilmResponse)
async def update_ac_film(
    film_id: int,
    request: UpdateACFilmRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Update an Alternative Content film (e.g., change classification, verify).
    """
    company_id = current_user.get("company_id", 1)
    user_id = current_user.get("user_id")

    with get_session() as session:
        film = session.query(AlternativeContentFilm).filter(
            AlternativeContentFilm.company_id == company_id,
            AlternativeContentFilm.id == film_id
        ).first()

        if not film:
            raise HTTPException(status_code=404, detail="AC film not found")

        if request.content_type is not None:
            film.content_type = request.content_type
        if request.content_source is not None:
            film.content_source = request.content_source
        if request.is_verified is not None:
            film.is_verified = request.is_verified
            if request.is_verified:
                film.verified_by = user_id
                film.verified_at = datetime.now(timezone.utc)
        if request.is_active is not None:
            film.is_active = request.is_active

        session.commit()
        session.refresh(film)

        return _film_to_response(film)


@router.delete("/{film_id}")
async def delete_ac_film(
    film_id: int,
    current_user: dict = Depends(require_operator)
):
    """
    Delete (deactivate) an Alternative Content film.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        film = session.query(AlternativeContentFilm).filter(
            AlternativeContentFilm.company_id == company_id,
            AlternativeContentFilm.id == film_id
        ).first()

        if not film:
            raise HTTPException(status_code=404, detail="AC film not found")

        film.is_active = False
        session.commit()

        return {"message": "AC film deactivated", "film_id": film_id}


# ============================================================================
# DETECTION ENDPOINTS
# ============================================================================

@router.post("/detect", response_model=DetectionResultResponse)
async def run_detection(
    lookback_days: int = Query(90, ge=7, le=365, description="Days of history to scan"),
    current_user: dict = Depends(require_operator)
):
    """
    Run Alternative Content detection on recent showings.

    Scans film titles and ticket types to identify AC films.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        service = AlternativeContentService(session, company_id)
        results = service.run_full_detection(lookback_days)

        return DetectionResultResponse(
            **results,
            message=f"Detection complete. Found {results['total_unique']} AC films, saved {results['new_saved']} new."
        )


@router.get("/detect/preview")
async def preview_detection(
    lookback_days: int = Query(90, ge=7, le=365),
    current_user: dict = Depends(get_current_user)
):
    """
    Preview what would be detected without saving.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        service = AlternativeContentService(session, company_id)

        title_detected = service.detect_ac_films_from_showings(lookback_days)
        ticket_detected = service.detect_ac_from_ticket_types(lookback_days)

        return {
            "title_detected": title_detected,
            "ticket_type_detected": ticket_detected,
            "total_title": len(title_detected),
            "total_ticket_type": len(ticket_detected),
        }


@router.get("/check/{film_title}")
async def check_film(
    film_title: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Check if a specific film title would be classified as Alternative Content.
    """
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        service = AlternativeContentService(session, company_id)
        is_ac, content_type = service.is_alternative_content(film_title)

        # Also check title patterns
        pattern_type, confidence, reason = detect_content_type_from_title(film_title)

        return {
            "film_title": film_title,
            "normalized_title": normalize_title(film_title),
            "is_alternative_content": is_ac,
            "content_type": content_type,
            "pattern_detection": {
                "detected_type": pattern_type,
                "confidence": confidence,
                "reason": reason,
            } if pattern_type else None
        }


# ============================================================================
# CIRCUIT AC PRICING ENDPOINTS
# ============================================================================

@router.get("/circuit-pricing", response_model=List[CircuitACPricingResponse])
async def list_circuit_ac_pricing(
    current_user: dict = Depends(get_current_user)
):
    """List all circuit AC pricing strategies."""
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        strategies = session.query(CircuitACPricing).filter(
            CircuitACPricing.company_id == company_id
        ).order_by(CircuitACPricing.circuit_name).all()

        return [_pricing_to_response(s) for s in strategies]


@router.get("/circuit-pricing/{circuit_name}", response_model=CircuitACPricingResponse)
async def get_circuit_ac_pricing(
    circuit_name: str,
    current_user: dict = Depends(get_current_user)
):
    """Get AC pricing strategy for a specific circuit."""
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        strategy = session.query(CircuitACPricing).filter(
            CircuitACPricing.company_id == company_id,
            CircuitACPricing.circuit_name == circuit_name
        ).first()

        if not strategy:
            raise HTTPException(status_code=404, detail=f"No AC pricing strategy for {circuit_name}")

        return _pricing_to_response(strategy)


@router.put("/circuit-pricing/{circuit_name}", response_model=CircuitACPricingResponse)
async def update_circuit_ac_pricing(
    circuit_name: str,
    request: UpdateCircuitACPricingRequest,
    current_user: dict = Depends(require_operator)
):
    """Update AC pricing strategy for a circuit."""
    company_id = current_user.get("company_id", 1)

    with get_session() as session:
        strategy = session.query(CircuitACPricing).filter(
            CircuitACPricing.company_id == company_id,
            CircuitACPricing.circuit_name == circuit_name
        ).first()

        if not strategy:
            # Create new
            strategy = CircuitACPricing(
                company_id=company_id,
                circuit_name=circuit_name,
                content_type='all',
                source='manual',
            )
            session.add(strategy)

        if request.standard_ticket_type is not None:
            strategy.standard_ticket_type = request.standard_ticket_type
        if request.discount_ticket_type is not None:
            strategy.discount_ticket_type = request.discount_ticket_type
        if request.typical_price_min is not None:
            strategy.typical_price_min = Decimal(str(request.typical_price_min))
        if request.typical_price_max is not None:
            strategy.typical_price_max = Decimal(str(request.typical_price_max))
        if request.discount_day_applies is not None:
            strategy.discount_day_applies = request.discount_day_applies
        if request.discount_day_ticket_type is not None:
            strategy.discount_day_ticket_type = request.discount_day_ticket_type
        if request.discount_day_price is not None:
            strategy.discount_day_price = Decimal(str(request.discount_day_price))
        if request.notes is not None:
            strategy.notes = request.notes

        strategy.source = 'manual'
        session.commit()
        session.refresh(strategy)

        return _pricing_to_response(strategy)
