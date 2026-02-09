"""
Price Alerts API Router

Endpoints for managing price alerts per claude.md TheatreOperations platform standards.

Endpoints:
    GET    /api/v1/price-alerts              - List price alerts
    GET    /api/v1/price-alerts/{id}         - Get specific alert
    PUT    /api/v1/price-alerts/{id}/acknowledge - Acknowledge an alert
    GET    /api/v1/price-alerts/summary      - Get alert summary statistics
    GET    /api/v1/baselines/coverage-gaps   - Get coverage gap analysis
    GET    /api/v1/baselines/coverage-gaps/{theater_name} - Get theater coverage details
"""

from datetime import datetime, date, timezone, UTC, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Security, Query, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from api.routers.auth import get_current_user, User, require_operator, require_read_admin
from app.db_session import get_session
from app.audit_service import audit_service
from app.simplified_baseline_service import normalize_daypart, normalize_ticket_type
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# CROSS-SOURCE EQUIVALENCE MAPPINGS (read-layer only — stored data is unchanged)
# These mappings let cross-source comparisons and surge scans match correctly
# when Fandango and EntTelligence use different names for the same thing.
# ============================================================================

# Ticket types: EntTelligence "Adult" == Fandango "General Admission"
TICKET_TYPE_EQUIVALENTS: dict[str, list[str]] = {
    "Adult": ["General Admission"],
    "General Admission": ["Adult"],
}

# Formats: EntTelligence "2D" == Fandango "Standard" (regular, non-PLF screenings)
# NOTE: "Premium Format" is NOT equivalent to "2D" — Fandango is the source of
# truth for PLF pricing since EntTelligence lumps PLF into "2D" without distinction.
FORMAT_EQUIVALENTS: dict[str, list[str]] = {
    "2D": ["Standard"],
    "Standard": ["2D"],
}


def get_equivalent_ticket_types(ticket_type: str) -> list[str]:
    """Return a list of equivalent ticket type names for cross-source matching.

    Always includes the original type first, then any known equivalents.
    E.g., 'Adult' -> ['Adult', 'General Admission']
    """
    equivalents = TICKET_TYPE_EQUIVALENTS.get(ticket_type, [])
    return [ticket_type] + equivalents


def get_equivalent_formats(fmt: str) -> list[str]:
    """Return a list of equivalent format names for cross-source matching.

    Always includes the original format first, then any known equivalents.
    E.g., '2D' -> ['2D', 'Standard']
    """
    equivalents = FORMAT_EQUIVALENTS.get(fmt, [])
    return [fmt] + equivalents


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class PriceAlert(BaseModel):
    """Model for a price alert."""
    alert_id: int
    theater_name: str
    film_title: Optional[str] = None
    ticket_type: Optional[str] = None
    format: Optional[str] = None
    daypart: Optional[str] = None  # matinee, evening, late_night - for understanding comparisons
    showtime: Optional[str] = None  # e.g., "7:30 PM" - actual performance time
    alert_type: str  # price_increase, price_decrease, new_offering, discontinued
    old_price: Optional[float] = None
    new_price: Optional[float] = None
    old_price_captured_at: Optional[datetime] = None  # When the old/baseline price was captured
    price_change_percent: Optional[float] = None
    triggered_at: datetime
    play_date: Optional[date] = None
    is_acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    acknowledgment_notes: Optional[str] = None


class AcknowledgeRequest(BaseModel):
    """Request model for acknowledging an alert."""
    notes: Optional[str] = Field(None, max_length=1000, description="Optional notes")


class AcknowledgeResponse(BaseModel):
    """Response model for acknowledgment."""
    alert_id: int
    acknowledged: bool = True
    acknowledged_at: datetime
    acknowledged_by: str


class AcknowledgeAllRequest(BaseModel):
    """Request model for acknowledging all pending alerts."""
    notes: Optional[str] = Field(None, max_length=1000, description="Optional notes for the bulk acknowledgment")


class AlertSummary(BaseModel):
    """Summary statistics for alerts."""
    total_pending: int
    total_acknowledged: int
    by_type: dict  # {alert_type: count}
    by_theater: dict  # {theater_name: count}
    oldest_pending: Optional[datetime] = None
    newest_pending: Optional[datetime] = None


class AlertListResponse(BaseModel):
    """Response model for alert list."""
    total: int
    pending: int
    alerts: List[PriceAlert]


# ============================================================================
# PRICE ALERTS ENDPOINTS
# ============================================================================

@router.get("/price-alerts", response_model=AlertListResponse, tags=["Price Alerts"])
async def list_price_alerts(
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledgment status"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    theater_name: Optional[str] = Query(None, description="Filter by theater (partial match)"),
    days: int = Query(30, ge=1, le=365, description="Days of history to include"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(require_read_admin)
):
    """
    List price alerts with optional filtering.

    Returns alerts ordered by triggered_at descending (most recent first).
    """
    try:
        from app.db_models import PriceAlert as PriceAlertModel
        from app.db_models import User as UserModel
        from sqlalchemy import and_, func
        from datetime import timedelta

        with get_session() as session:
            company_id = current_user.get("company_id") or 1
            cutoff_date = datetime.now(UTC) - timedelta(days=days)

            # Build query using ORM
            query = session.query(PriceAlertModel).filter(
                and_(
                    PriceAlertModel.company_id == company_id,
                    PriceAlertModel.triggered_at >= cutoff_date
                )
            )

            if acknowledged is not None:
                query = query.filter(PriceAlertModel.is_acknowledged == acknowledged)
            if alert_type:
                query = query.filter(PriceAlertModel.alert_type == alert_type)
            if theater_name:
                query = query.filter(PriceAlertModel.theater_name.ilike(f"%{theater_name}%"))

            # Get counts
            total = query.count()
            pending = query.filter(PriceAlertModel.is_acknowledged == False).count()

            # Get paginated results
            alerts_data = query.order_by(PriceAlertModel.triggered_at.desc()).offset(offset).limit(limit).all()

            # Batch-fetch acknowledger usernames (avoid N+1 query)
            user_ids = {r.acknowledged_by for r in alerts_data if r.acknowledged_by}
            users_map = {}
            if user_ids:
                users_map = {
                    u.user_id: u.username
                    for u in session.query(UserModel).filter(UserModel.user_id.in_(user_ids)).all()
                }

            alerts = []
            for row in alerts_data:
                acknowledged_by_name = users_map.get(row.acknowledged_by) if row.acknowledged_by else None

                # Get showtime from related Showing if available
                showtime = row.showing.showtime if row.showing else None

                alerts.append(PriceAlert(
                    alert_id=row.alert_id,
                    theater_name=row.theater_name,
                    film_title=row.film_title,
                    ticket_type=row.ticket_type,
                    format=row.format,
                    daypart=row.daypart,  # Include daypart for context
                    showtime=showtime,  # Actual performance time
                    alert_type=row.alert_type,
                    old_price=float(row.old_price) if row.old_price else None,
                    new_price=float(row.new_price) if row.new_price else None,
                    old_price_captured_at=row.old_price_captured_at,  # When the baseline was recorded
                    price_change_percent=float(row.price_change_percent) if row.price_change_percent else None,
                    triggered_at=row.triggered_at,
                    play_date=row.play_date,
                    is_acknowledged=bool(row.is_acknowledged),
                    acknowledged_by=acknowledged_by_name,
                    acknowledged_at=row.acknowledged_at,
                    acknowledgment_notes=row.acknowledgment_notes
                ))

            return AlertListResponse(
                total=total,
                pending=pending,
                alerts=alerts
            )
    except Exception as e:
        logger.exception(f"Error listing price alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-alerts/summary", response_model=AlertSummary, tags=["Price Alerts"])
async def get_alert_summary(
    days: int = Query(30, ge=1, le=365, description="Days to include"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Get summary statistics for price alerts.

    Returns counts by type, by theater, and date range info.
    """
    try:
        from app.db_models import PriceAlert as PriceAlertModel
        from sqlalchemy import and_, func
        from datetime import timedelta

        with get_session() as session:
            company_id = current_user.get("company_id") or 1
            cutoff_date = datetime.now(UTC) - timedelta(days=days)

            base_filter = and_(
                PriceAlertModel.company_id == company_id,
                PriceAlertModel.triggered_at >= cutoff_date
            )

            # Get totals
            pending = session.query(func.count(PriceAlertModel.alert_id)).filter(
                base_filter,
                PriceAlertModel.is_acknowledged == False
            ).scalar() or 0

            acknowledged = session.query(func.count(PriceAlertModel.alert_id)).filter(
                base_filter,
                PriceAlertModel.is_acknowledged == True
            ).scalar() or 0

            # Get oldest/newest pending
            oldest = session.query(func.min(PriceAlertModel.triggered_at)).filter(
                base_filter,
                PriceAlertModel.is_acknowledged == False
            ).scalar()

            newest = session.query(func.max(PriceAlertModel.triggered_at)).filter(
                base_filter,
                PriceAlertModel.is_acknowledged == False
            ).scalar()

            # Get by type
            type_counts = session.query(
                PriceAlertModel.alert_type,
                func.count(PriceAlertModel.alert_id)
            ).filter(
                base_filter,
                PriceAlertModel.is_acknowledged == False
            ).group_by(PriceAlertModel.alert_type).all()
            by_type = {t: c for t, c in type_counts}

            # Get by theater (top 10)
            theater_counts = session.query(
                PriceAlertModel.theater_name,
                func.count(PriceAlertModel.alert_id)
            ).filter(
                base_filter,
                PriceAlertModel.is_acknowledged == False
            ).group_by(PriceAlertModel.theater_name).order_by(
                func.count(PriceAlertModel.alert_id).desc()
            ).limit(10).all()
            by_theater = {t: c for t, c in theater_counts}

            return AlertSummary(
                total_pending=pending,
                total_acknowledged=acknowledged,
                by_type=by_type,
                by_theater=by_theater,
                oldest_pending=oldest,
                newest_pending=newest
            )
    except Exception as e:
        logger.exception(f"Error getting alert summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: Config endpoint must be defined BEFORE /{alert_id} to avoid route conflicts
@router.get("/price-alerts/config", tags=["Price Alerts"])
async def get_alert_configuration(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get alert configuration for current company.

    Returns default values if no configuration exists.
    """
    try:
        from app.db_models import AlertConfiguration

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
            config = session.query(AlertConfiguration).filter(
                AlertConfiguration.company_id == company_id
            ).first()

            if config:
                return {
                    "config_id": config.config_id,
                    "company_id": config.company_id,
                    "min_price_change_percent": float(config.min_price_change_percent or 5.0),
                    "min_price_change_amount": float(config.min_price_change_amount or 1.0),
                    "alert_on_increase": config.alert_on_increase,
                    "alert_on_decrease": config.alert_on_decrease,
                    "alert_on_new_offering": config.alert_on_new_offering,
                    "alert_on_discontinued": config.alert_on_discontinued,
                    "alert_on_surge": config.alert_on_surge,
                    "surge_threshold_percent": float(config.surge_threshold_percent or 20.0),
                    "notification_enabled": config.notification_enabled,
                    "webhook_url": config.webhook_url,
                    "notification_email": config.notification_email,
                    "email_frequency": config.email_frequency or 'immediate',
                    "theaters_filter": config.theaters_filter_list,
                    "ticket_types_filter": config.ticket_types_filter_list,
                    "formats_filter": config.formats_filter_list,
                    "updated_at": config.updated_at
                }
            else:
                # Return defaults
                return {
                    "config_id": None,
                    "company_id": company_id,
                    "min_price_change_percent": 5.0,
                    "min_price_change_amount": 1.0,
                    "alert_on_increase": True,
                    "alert_on_decrease": True,
                    "alert_on_new_offering": True,
                    "alert_on_discontinued": False,
                    "alert_on_surge": True,
                    "surge_threshold_percent": 20.0,
                    "notification_enabled": True,
                    "webhook_url": None,
                    "notification_email": None,
                    "email_frequency": 'immediate',
                    "theaters_filter": [],
                    "ticket_types_filter": [],
                    "formats_filter": [],
                    "updated_at": None
                }
    except Exception as e:
        logger.exception(f"Error getting alert configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: Bulk action endpoints must be defined BEFORE /{alert_id} to avoid route conflicts.
# FastAPI/Starlette matches paths in declaration order — {alert_id} would catch "acknowledge-bulk" etc.

@router.put("/price-alerts/acknowledge-bulk", tags=["Price Alerts"])
async def acknowledge_alerts_bulk(
    alert_ids: List[int],
    notes: Optional[str] = None,
    current_user: dict = Depends(require_operator)
):
    """
    Acknowledge multiple alerts at once.

    Returns count of alerts acknowledged.
    """
    try:
        if not alert_ids:
            raise HTTPException(status_code=400, detail="No alert IDs provided")

        with get_session() as session:
            now = datetime.now(timezone.utc)

            # Build IN clause (safe since alert_ids are integers)
            id_list = ",".join(str(int(id)) for id in alert_ids)

            result = session.execute(
                text(f"""
                    UPDATE price_alerts
                    SET is_acknowledged = 1,
                        acknowledged_by = :user_id,
                        acknowledged_at = :now,
                        acknowledgment_notes = :notes
                    WHERE alert_id IN ({id_list})
                      AND company_id = :company_id
                      AND is_acknowledged = 0
                """),
                {
                    "company_id": current_user.get("company_id") or 1,
                    "user_id": current_user.get("user_id"),
                    "now": now,
                    "notes": notes
                }
            )

            count = result.rowcount
            session.commit()

            # Audit bulk acknowledgment
            audit_service.data_event(
                event_type="acknowledge_price_alerts_bulk",
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                company_id=current_user.get("company_id") or 1,
                details={"alert_ids_count": len(alert_ids), "count_updated": count}
            )

            logger.info(f"{count} alerts acknowledged by user {current_user.get('username')}")

            return {
                "acknowledged_count": count,
                "requested_count": len(alert_ids),
                "acknowledged_at": now.isoformat(),
                "acknowledged_by": current_user.get("username")
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error bulk acknowledging alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/price-alerts/acknowledge-all", tags=["Price Alerts"])
async def acknowledge_all_alerts(
    request: Optional[AcknowledgeAllRequest] = None,
    current_user: dict = Depends(require_operator)
):
    """
    Acknowledge ALL pending alerts for the current company.

    Use this to clear stale alerts in bulk (e.g., after fixing detection logic).
    Returns count of alerts acknowledged.
    """
    try:
        with get_session() as session:
            now = datetime.now(timezone.utc)
            company_id = current_user.get("company_id") or 1
            notes = request.notes if request else "Bulk cleared all pending alerts"

            result = session.execute(
                text("""
                    UPDATE price_alerts
                    SET is_acknowledged = 1,
                        acknowledged_by = :user_id,
                        acknowledged_at = :now,
                        acknowledgment_notes = :notes
                    WHERE company_id = :company_id
                      AND is_acknowledged = 0
                """),
                {
                    "company_id": company_id,
                    "user_id": current_user.get("user_id"),
                    "now": now,
                    "notes": notes
                }
            )

            count = result.rowcount
            session.commit()

            audit_service.data_event(
                event_type="acknowledge_all_price_alerts",
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                company_id=company_id,
                details={"count_acknowledged": count}
            )

            logger.info(f"All {count} pending alerts acknowledged by user {current_user.get('username')}")

            return {
                "acknowledged_count": count,
                "acknowledged_at": now.isoformat(),
                "acknowledged_by": current_user.get("username")
            }
    except Exception as e:
        logger.exception(f"Error acknowledging all alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-alerts/{alert_id}", response_model=PriceAlert, tags=["Price Alerts"])
async def get_price_alert(
    alert_id: int,
    current_user: User = Security(get_current_user, scopes=["read:alerts"])
):
    """
    Get a specific price alert by ID.
    """
    try:
        with get_session() as session:
            result = session.execute(
                text("""
                    SELECT
                        pa.alert_id, pa.theater_name, pa.film_title, pa.ticket_type,
                        pa.format, pa.alert_type, pa.old_price, pa.new_price,
                        pa.price_change_percent, pa.triggered_at, pa.play_date,
                        pa.is_acknowledged, u.username as acknowledged_by,
                        pa.acknowledged_at, pa.acknowledgment_notes
                    FROM price_alerts pa
                    LEFT JOIN users u ON pa.acknowledged_by = u.user_id
                    WHERE pa.alert_id = :alert_id AND pa.company_id = :company_id
                """),
                {"alert_id": alert_id, "company_id": current_user.get("company_id") or 1}
            )
            row = result.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

            return PriceAlert(
                alert_id=row[0],
                theater_name=row[1],
                film_title=row[2],
                ticket_type=row[3],
                format=row[4],
                alert_type=row[5],
                old_price=float(row[6]) if row[6] else None,
                new_price=float(row[7]) if row[7] else None,
                price_change_percent=float(row[8]) if row[8] else None,
                triggered_at=row[9],
                play_date=row[10],
                is_acknowledged=bool(row[11]),
                acknowledged_by=row[12],
                acknowledged_at=row[13],
                acknowledgment_notes=row[14]
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting price alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/price-alerts/{alert_id}/acknowledge", response_model=AcknowledgeResponse, tags=["Price Alerts"])
async def acknowledge_alert(
    alert_id: int,
    request: AcknowledgeRequest = None,
    current_user: dict = Depends(require_operator)
):
    """
    Acknowledge a price alert.

    Marks the alert as acknowledged and records who acknowledged it.
    """
    try:
        with get_session() as session:
            # Check alert exists
            check = session.execute(
                text("""
                    SELECT is_acknowledged
                    FROM price_alerts
                    WHERE alert_id = :alert_id AND company_id = :company_id
                """),
                {"alert_id": alert_id, "company_id": current_user.get("company_id") or 1}
            ).fetchone()

            if not check:
                raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

            if check[0]:
                raise HTTPException(status_code=400, detail="Alert already acknowledged")

            # Update alert
            now = datetime.now(timezone.utc)
            session.execute(
                text("""
                    UPDATE price_alerts
                    SET is_acknowledged = 1,
                        acknowledged_by = :user_id,
                        acknowledged_at = :now,
                        acknowledgment_notes = :notes
                    WHERE alert_id = :alert_id AND company_id = :company_id
                """),
                {
                    "alert_id": alert_id,
                    "company_id": current_user.get("company_id") or 1,
                    "user_id": current_user.get("user_id"),
                    "now": now,
                    "notes": request.notes if request else None
                }
            )
            session.commit()

            # Audit acknowledgment
            audit_service.data_event(
                event_type="acknowledge_price_alert",
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                company_id=current_user.get("company_id") or 1,
                details={"alert_id": alert_id, "notes": request.notes if request else None}
            )

            logger.info(f"Alert {alert_id} acknowledged by user {current_user.get("username")}")

            return AcknowledgeResponse(
                alert_id=alert_id,
                acknowledged=True,
                acknowledged_at=now,
                acknowledged_by=current_user.get("username")
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ALERT CONFIGURATION ENDPOINTS
# ============================================================================

class AlertConfigurationRequest(BaseModel):
    """Request model for alert configuration."""
    min_price_change_percent: Optional[float] = Field(5.0, ge=0, le=100)
    min_price_change_amount: Optional[float] = Field(1.00, ge=0)
    alert_on_increase: bool = True
    alert_on_decrease: bool = True
    alert_on_new_offering: bool = True
    alert_on_discontinued: bool = False
    alert_on_surge: bool = True
    surge_threshold_percent: Optional[float] = Field(20.0, ge=0, le=500)
    notification_enabled: bool = True
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    notification_email: Optional[str] = None
    email_frequency: str = Field("immediate", pattern="^(immediate|hourly|daily)$")
    theaters_filter: List[str] = []
    ticket_types_filter: List[str] = []
    formats_filter: List[str] = []


class AlertConfigurationResponse(BaseModel):
    """Response model for alert configuration."""
    config_id: Optional[int] = None
    company_id: int
    min_price_change_percent: float
    min_price_change_amount: float
    alert_on_increase: bool
    alert_on_decrease: bool
    alert_on_new_offering: bool
    alert_on_discontinued: bool
    alert_on_surge: bool
    surge_threshold_percent: float
    notification_enabled: bool
    webhook_url: Optional[str] = None
    notification_email: Optional[str] = None
    email_frequency: str
    theaters_filter: List[str] = []
    ticket_types_filter: List[str] = []
    formats_filter: List[str] = []
    updated_at: Optional[datetime] = None


@router.put("/price-alerts/config", response_model=AlertConfigurationResponse, tags=["Price Alerts"])
async def update_alert_configuration(
    request: AlertConfigurationRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Update alert configuration for current company.

    Creates configuration if it doesn't exist.
    """
    try:
        from app.db_models import AlertConfiguration
        from decimal import Decimal
        import json

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
            config = session.query(AlertConfiguration).filter(
                AlertConfiguration.company_id == company_id
            ).first()

            if not config:
                config = AlertConfiguration(company_id=company_id)
                session.add(config)

            # Update fields
            config.min_price_change_percent = Decimal(str(request.min_price_change_percent))
            config.min_price_change_amount = Decimal(str(request.min_price_change_amount))
            config.alert_on_increase = request.alert_on_increase
            config.alert_on_decrease = request.alert_on_decrease
            config.alert_on_new_offering = request.alert_on_new_offering
            config.alert_on_discontinued = request.alert_on_discontinued
            config.alert_on_surge = request.alert_on_surge
            config.surge_threshold_percent = Decimal(str(request.surge_threshold_percent))
            config.notification_enabled = request.notification_enabled
            config.webhook_url = request.webhook_url
            config.webhook_secret = request.webhook_secret
            config.notification_email = request.notification_email
            config.email_frequency = request.email_frequency
            config.theaters_filter = json.dumps(request.theaters_filter)
            config.ticket_types_filter = json.dumps(request.ticket_types_filter)
            config.formats_filter = json.dumps(request.formats_filter)
            session.flush()

            # Audit configuration update
            audit_service.data_event(
                event_type="update_alert_config",
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                company_id=company_id,
                details={"updated_at": config.updated_at.isoformat()}
            )

            logger.info(f"Alert configuration updated for company {company_id}")

            return AlertConfigurationResponse(
                config_id=config.config_id,
                company_id=config.company_id,
                min_price_change_percent=float(config.min_price_change_percent),
                min_price_change_amount=float(config.min_price_change_amount),
                alert_on_increase=config.alert_on_increase,
                alert_on_decrease=config.alert_on_decrease,
                alert_on_new_offering=config.alert_on_new_offering,
                alert_on_discontinued=config.alert_on_discontinued,
                alert_on_surge=config.alert_on_surge,
                surge_threshold_percent=float(config.surge_threshold_percent),
                notification_enabled=config.notification_enabled,
                webhook_url=config.webhook_url,
                notification_email=config.notification_email,
                email_frequency=config.email_frequency,
                theaters_filter=request.theaters_filter,
                ticket_types_filter=request.ticket_types_filter,
                formats_filter=request.formats_filter,
                updated_at=config.updated_at
            )
    except Exception as e:
        logger.exception(f"Error updating alert configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PRICE BASELINE ENDPOINTS
# ============================================================================

class PriceBaselineRequest(BaseModel):
    """Request for creating/updating price baselines."""
    theater_name: str
    ticket_type: str
    format: Optional[str] = None
    daypart: Optional[str] = None
    day_type: Optional[str] = None  # 'weekday', 'weekend', or None (all days)
    baseline_price: float = Field(..., gt=0)
    effective_from: date
    effective_to: Optional[date] = None


class PriceBaselineResponse(BaseModel):
    """Response for price baseline."""
    baseline_id: int
    theater_name: str
    ticket_type: str
    format: Optional[str] = None
    daypart: Optional[str] = None
    day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday, or None (all days)
    day_type: Optional[str] = None  # 'weekday', 'weekend', or None (all days)
    baseline_price: float
    effective_from: date
    effective_to: Optional[date] = None
    source: Optional[str] = None
    sample_count: Optional[int] = None
    last_discovery_at: Optional[datetime] = None
    created_at: datetime


@router.get("/price-baselines", response_model=List[PriceBaselineResponse], tags=["Price Alerts"])
async def list_price_baselines(
    theater_name: Optional[str] = Query(None, description="Filter by theater (partial match)"),
    ticket_type: Optional[str] = Query(None, description="Filter by ticket type"),
    day_type: Optional[str] = Query(None, description="Filter by day type: 'weekday', 'weekend', or 'all'"),
    active_only: bool = Query(True, description="Only show active baselines"),
    current_user: User = Security(get_current_user, scopes=["read:alerts"])
):
    """
    List price baselines for surge detection.

    Day type filtering:
    - 'weekday': Only baselines for Monday-Thursday
    - 'weekend': Only baselines for Friday-Sunday
    - 'all' or omit: All baselines
    """
    try:
        from app.db_models import PriceBaseline
        from sqlalchemy import and_, or_

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            query = session.query(PriceBaseline).filter(
                PriceBaseline.company_id == company_id
            )

            if theater_name:
                query = query.filter(PriceBaseline.theater_name.ilike(f"%{theater_name}%"))
            if ticket_type:
                query = query.filter(PriceBaseline.ticket_type == (normalize_ticket_type(ticket_type) or ticket_type))
            if day_type and day_type != 'all':
                query = query.filter(PriceBaseline.day_type == day_type)
            if active_only:
                today = date.today()
                query = query.filter(
                    and_(
                        PriceBaseline.effective_from <= today,
                        or_(
                            PriceBaseline.effective_to.is_(None),
                            PriceBaseline.effective_to >= today
                        )
                    )
                )

            baselines = query.order_by(PriceBaseline.theater_name, PriceBaseline.ticket_type, PriceBaseline.day_type).all()

            return [
                PriceBaselineResponse(
                    baseline_id=b.baseline_id,
                    theater_name=b.theater_name,
                    ticket_type=b.ticket_type,
                    format=b.format,
                    daypart=b.daypart,
                    day_of_week=b.day_of_week,
                    day_type=b.day_type,
                    baseline_price=float(b.baseline_price),
                    effective_from=b.effective_from,
                    effective_to=b.effective_to,
                    source=b.source,
                    sample_count=b.sample_count,
                    last_discovery_at=b.last_discovery_at,
                    created_at=b.created_at
                )
                for b in baselines
            ]
    except Exception as e:
        logger.exception(f"Error listing price baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/price-baselines", response_model=PriceBaselineResponse, status_code=201, tags=["Price Alerts"])
async def create_price_baseline(
    request: PriceBaselineRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Create or update a price baseline for surge detection.

    If an active baseline already exists for the same (theater, ticket_type, format, daypart),
    it is updated in place instead of creating a duplicate.
    """
    try:
        from app.db_models import PriceBaseline
        from decimal import Decimal
        from sqlalchemy import and_

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            norm_ticket = normalize_ticket_type(request.ticket_type) or request.ticket_type
            norm_daypart = normalize_daypart(request.daypart)

            # Check for existing active baseline with same dimensions
            filters = [
                PriceBaseline.company_id == company_id,
                PriceBaseline.theater_name == request.theater_name,
                PriceBaseline.ticket_type == norm_ticket,
                PriceBaseline.effective_to.is_(None),
            ]
            if request.format:
                filters.append(PriceBaseline.format == request.format)
            else:
                filters.append(PriceBaseline.format.is_(None))
            if norm_daypart:
                filters.append(PriceBaseline.daypart == norm_daypart)
            else:
                filters.append(PriceBaseline.daypart.is_(None))

            existing = session.query(PriceBaseline).filter(and_(*filters)).first()

            if existing:
                # Update existing baseline in place
                existing.baseline_price = Decimal(str(request.baseline_price))
                existing.effective_from = request.effective_from
                existing.effective_to = request.effective_to
                existing.day_type = request.day_type
                baseline = existing
                event_type = "update_price_baseline"
            else:
                baseline = PriceBaseline(
                    company_id=company_id,
                    theater_name=request.theater_name,
                    ticket_type=norm_ticket,
                    format=request.format,
                    daypart=norm_daypart,
                    day_type=request.day_type,
                    baseline_price=Decimal(str(request.baseline_price)),
                    effective_from=request.effective_from,
                    effective_to=request.effective_to,
                    source='manual',
                    tax_status='inclusive',
                    created_by=current_user.get("user_id")
                )
                session.add(baseline)
                event_type = "create_price_baseline"

            session.flush()

            # Audit baseline creation/update
            audit_service.data_event(
                event_type=event_type,
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                company_id=company_id,
                details={
                    "theater": request.theater_name,
                    "ticket_type": request.ticket_type,
                    "price": float(request.baseline_price),
                    "day_type": request.day_type
                }
            )

            logger.info(f"Price baseline {event_type.split('_')[0]}d: {baseline.theater_name} {baseline.ticket_type} ({baseline.day_type or 'all'}) = ${baseline.baseline_price}")

            return PriceBaselineResponse(
                baseline_id=baseline.baseline_id,
                theater_name=baseline.theater_name,
                ticket_type=baseline.ticket_type,
                format=baseline.format,
                daypart=baseline.daypart,
                day_type=baseline.day_type,
                baseline_price=float(baseline.baseline_price),
                effective_from=baseline.effective_from,
                effective_to=baseline.effective_to,
                created_at=baseline.created_at
            )
    except Exception as e:
        logger.exception(f"Error creating price baseline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BASELINE COVERAGE ANALYSIS
# ============================================================================

class BaselineCoverageResponse(BaseModel):
    """Response model for baseline coverage analysis."""
    total_theaters: int
    theaters_with_baselines: int
    theaters_missing_baselines: int
    coverage_percent: float
    by_circuit: Dict[str, Dict[str, int]]
    missing_theaters: List[Dict[str, str]]


@router.get("/price-baselines/coverage", tags=["Price Baselines"])
async def get_baseline_coverage(
    current_user: dict = Depends(require_read_admin)
) -> BaselineCoverageResponse:
    """
    Analyze baseline coverage across all theaters.

    Shows which theaters have baselines and which are missing.
    Uses EntTelligence cache as the source of truth for theater list.
    """
    from app.db_models import PriceBaseline, EntTelligencePriceCache
    from sqlalchemy import func, distinct

    company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

    with get_session() as session:
        # Get unique theaters from EntTelligence cache (our source of theater truth)
        ent_theaters_query = session.query(
            EntTelligencePriceCache.theater_name,
            EntTelligencePriceCache.circuit_name
        ).filter(
            EntTelligencePriceCache.company_id == company_id
        ).distinct().all()

        # Build dict of theater -> circuit
        all_theaters = {}
        for theater_name, circuit_name in ent_theaters_query:
            if theater_name:
                all_theaters[theater_name] = circuit_name or "Unknown"

        # Get unique theaters that have baselines
        baseline_theaters_query = session.query(
            distinct(PriceBaseline.theater_name)
        ).filter(
            PriceBaseline.company_id == company_id,
            PriceBaseline.effective_to.is_(None)  # Only active baselines
        ).all()

        theaters_with_baselines = {row[0] for row in baseline_theaters_query if row[0]}

        # Calculate coverage
        total_theaters = len(all_theaters)
        covered_count = len(theaters_with_baselines & set(all_theaters.keys()))
        missing_count = total_theaters - covered_count
        coverage_percent = (covered_count / total_theaters * 100) if total_theaters > 0 else 0

        # Group by circuit
        by_circuit = {}
        missing_theaters = []

        for theater_name, circuit in all_theaters.items():
            if circuit not in by_circuit:
                by_circuit[circuit] = {"total": 0, "covered": 0, "missing": 0}
            by_circuit[circuit]["total"] += 1

            if theater_name in theaters_with_baselines:
                by_circuit[circuit]["covered"] += 1
            else:
                by_circuit[circuit]["missing"] += 1
                missing_theaters.append({
                    "theater_name": theater_name,
                    "circuit": circuit
                })

        # Sort missing theaters by circuit
        missing_theaters.sort(key=lambda x: (x["circuit"], x["theater_name"]))

        return BaselineCoverageResponse(
            total_theaters=total_theaters,
            theaters_with_baselines=covered_count,
            theaters_missing_baselines=missing_count,
            coverage_percent=round(coverage_percent, 1),
            by_circuit=by_circuit,
            missing_theaters=missing_theaters[:100]  # Limit to first 100
        )


@router.put("/price-baselines/{baseline_id}", response_model=PriceBaselineResponse, tags=["Price Alerts"])
async def update_price_baseline(
    baseline_id: int,
    request: PriceBaselineRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Update a price baseline.
    """
    try:
        from app.db_models import PriceBaseline
        from decimal import Decimal

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            baseline = session.query(PriceBaseline).filter(
                PriceBaseline.baseline_id == baseline_id,
                PriceBaseline.company_id == company_id
            ).first()

            if not baseline:
                raise HTTPException(status_code=404, detail=f"Baseline {baseline_id} not found")

            baseline.theater_name = request.theater_name
            baseline.ticket_type = normalize_ticket_type(request.ticket_type) or request.ticket_type
            baseline.format = request.format
            baseline.daypart = normalize_daypart(request.daypart)
            baseline.day_type = request.day_type
            baseline.baseline_price = Decimal(str(request.baseline_price))
            baseline.effective_from = request.effective_from
            baseline.effective_to = request.effective_to

            session.flush()

            logger.info(f"Price baseline updated: {baseline.baseline_id}")

            return PriceBaselineResponse(
                baseline_id=baseline.baseline_id,
                theater_name=baseline.theater_name,
                ticket_type=baseline.ticket_type,
                format=baseline.format,
                daypart=baseline.daypart,
                day_type=baseline.day_type,
                baseline_price=float(baseline.baseline_price),
                effective_from=baseline.effective_from,
                effective_to=baseline.effective_to,
                created_at=baseline.created_at
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating price baseline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/price-baselines/{baseline_id}", status_code=204, tags=["Price Alerts"])
async def delete_price_baseline(
    baseline_id: int,
    current_user: dict = Depends(require_operator)
):
    """
    Delete a price baseline.
    """
    try:
        from app.db_models import PriceBaseline

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            baseline = session.query(PriceBaseline).filter(
                PriceBaseline.baseline_id == baseline_id,
                PriceBaseline.company_id == company_id
            ).first()

            if not baseline:
                raise HTTPException(status_code=404, detail=f"Baseline {baseline_id} not found")

            session.delete(baseline)
            logger.info(f"Price baseline deleted: {baseline_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting price baseline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/price-alerts/test-webhook", tags=["Price Alerts"])
async def test_webhook(
    current_user: User = Security(get_current_user, scopes=["write:alerts"])
):
    """
    Send a test webhook notification.

    Uses the configured webhook URL to send a test payload.
    """
    try:
        from app.db_models import AlertConfiguration
        import httpx
        import json

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
            config = session.query(AlertConfiguration).filter(
                AlertConfiguration.company_id == company_id
            ).first()

            if not config or not config.webhook_url:
                raise HTTPException(status_code=400, detail="No webhook URL configured")

            # Build test payload
            payload = {
                "event": "price_alerts_test",
                "timestamp": datetime.now(UTC).isoformat(),
                "company_id": company_id,
                "message": "This is a test notification from PriceScout",
                "alert_count": 0,
                "alerts": []
            }

            headers = {"Content-Type": "application/json"}

            # Add HMAC signature if secret configured
            if config.webhook_secret:
                import hmac
                import hashlib
                payload_json = json.dumps(payload, sort_keys=True, default=str)
                signature = hmac.new(
                    config.webhook_secret.encode(),
                    payload_json.encode(),
                    hashlib.sha256
                ).hexdigest()
                headers["X-PriceScout-Signature"] = f"sha256={signature}"
            else:
                payload_json = json.dumps(payload, default=str)

            # Send test request
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    config.webhook_url,
                    content=payload_json,
                    headers=headers
                )

            return {
                "success": response.status_code < 400,
                "status_code": response.status_code,
                "webhook_url": config.webhook_url,
                "message": "Test webhook sent successfully" if response.status_code < 400 else f"Webhook returned {response.status_code}"
            }

    except httpx.RequestError as e:
        return {
            "success": False,
            "error": f"Failed to connect to webhook: {str(e)}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error testing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BASELINE DISCOVERY ENDPOINTS
# ============================================================================

class DiscoveredBaseline(BaseModel):
    """Model for a discovered baseline."""
    theater_name: str
    ticket_type: str
    format: Optional[str] = None
    baseline_price: float
    sample_count: int
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    avg_price: Optional[float] = None
    volatility_percent: float
    is_premium: bool


class BaselineDiscoveryResponse(BaseModel):
    """Response for baseline discovery."""
    discovered_count: int
    saved_count: Optional[int] = None
    baselines: List[DiscoveredBaseline]


class PriceAnalysisResponse(BaseModel):
    """Response for price pattern analysis."""
    high_volatility_combinations: List[dict]
    format_price_comparison: dict


@router.get("/price-baselines/discover", tags=["Price Alerts"])
async def discover_baselines(
    min_samples: int = Query(5, ge=1, description="Minimum price samples required"),
    lookback_days: int = Query(90, ge=7, le=365, description="Days of history to analyze"),
    exclude_premium: bool = Query(False, description="Exclude premium formats (IMAX, Dolby, PLF). Default FALSE = include PLF baselines."),
    save: bool = Query(False, description="Save discovered baselines to database"),
    current_user: dict = Depends(require_operator)
):
    """
    Discover price baselines from historical scrape data.

    Analyzes historical prices to find the typical "normal" price for each
    theater/ticket_type/format combination. Uses the 25th percentile to
    establish a conservative baseline that ignores surge pricing spikes.

    Premium formats (IMAX, Dolby, 3D, etc.) are included by default so that
    PLF prices can be compared against PLF-specific baselines for accurate
    surge detection.
    """
    try:
        from app.baseline_discovery import BaselineDiscoveryService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        service = BaselineDiscoveryService(company_id)

        baselines = service.discover_baselines(
            min_samples=min_samples,
            lookback_days=lookback_days,
            exclude_premium=exclude_premium
        )

        saved_count = None
        if save and baselines:
            saved_count = service.save_discovered_baselines(baselines)

        return {
            "discovered_count": len(baselines),
            "saved_count": saved_count,
            "baselines": baselines
        }

    except Exception as e:
        logger.exception(f"Error discovering baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/price-baselines/refresh", tags=["Price Alerts"])
async def refresh_baselines(
    current_user: dict = Depends(require_operator)
):
    """
    Refresh all baselines with latest price data.

    Re-analyzes historical prices and updates existing baselines.
    New baselines are created for newly discovered combinations.
    """
    try:
        from app.baseline_discovery import refresh_baselines as do_refresh

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        count = do_refresh(company_id)

        return {
            "success": True,
            "baselines_updated": count,
            "message": f"Refreshed {count} baselines"
        }

    except Exception as e:
        logger.exception(f"Error refreshing baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/price-baselines/guarded-refresh", tags=["Price Alerts"])
async def guarded_refresh_baselines(
    source: str = Query("fandango", description="Data source: fandango or enttelligence"),
    max_drift_percent: float = Query(15.0, ge=1, le=50, description="Max allowed drift % before flagging"),
    min_samples: int = Query(8, ge=3, description="Minimum samples for auto-refresh"),
    lookback_days: int = Query(60, ge=7, le=365, description="Days of history to analyze"),
    dry_run: bool = Query(False, description="Preview changes without applying"),
    current_user: dict = Depends(require_operator)
):
    """
    Guarded baseline refresh with drift protection.

    Discovers new baselines from fresh data and compares each against
    the existing stored baseline. Only applies changes within the drift
    tolerance. Large changes are flagged for manual review instead of
    being applied, protecting against bad scrape data corrupting baselines.

    Use dry_run=true to preview what would change without writing anything.
    """
    try:
        from app.baseline_guard import guarded_refresh

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        result = guarded_refresh(
            company_id=company_id,
            source=source,
            max_drift_percent=max_drift_percent,
            min_samples=min_samples,
            lookback_days=lookback_days,
            dry_run=dry_run,
        )

        return result

    except Exception as e:
        logger.exception(f"Error in guarded baseline refresh: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-baselines/health", tags=["Price Alerts"])
async def get_baselines_health(
    current_user: dict = Security(get_current_user, scopes=["read:price_alerts"])
):
    """
    Data health dashboard for baselines and normalization.

    Returns freshness, staleness, source breakdown, normalization coverage,
    and theater metadata completeness — everything needed to assess whether
    the pricing data is current and well-formed.
    """
    company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

    try:
        with get_session() as session:
            # ── Baseline counts by source ──
            source_counts = session.execute(text("""
                SELECT source, COUNT(*) as cnt,
                       MIN(effective_from) as oldest,
                       MAX(effective_from) as newest,
                       MAX(last_discovery_at) as last_refresh
                FROM price_baselines
                WHERE effective_to IS NULL
                GROUP BY source
            """)).fetchall()

            sources = {}
            total_active = 0
            for r in source_counts:
                sources[r[0]] = {
                    "count": r[1],
                    "oldest_effective_from": str(r[2]) if r[2] else None,
                    "newest_effective_from": str(r[3]) if r[3] else None,
                    "last_refresh": str(r[4]) if r[4] else None,
                }
                total_active += r[1]

            # ── Staleness: baselines older than 30 days ──
            stale_30d = session.execute(text("""
                SELECT COUNT(*) FROM price_baselines
                WHERE effective_to IS NULL
                  AND effective_from < date('now', '-30 days')
            """)).scalar() or 0

            stale_90d = session.execute(text("""
                SELECT COUNT(*) FROM price_baselines
                WHERE effective_to IS NULL
                  AND effective_from < date('now', '-90 days')
            """)).scalar() or 0

            # ── Theater coverage ──
            theaters_with_baselines = session.execute(text("""
                SELECT COUNT(DISTINCT theater_name) FROM price_baselines
                WHERE effective_to IS NULL
            """)).scalar() or 0

            total_theaters = session.execute(text("""
                SELECT COUNT(*) FROM theater_metadata
                WHERE company_id = :cid
            """), {"cid": company_id}).scalar() or 0

            # ── Ticket type distribution ──
            ticket_types = session.execute(text("""
                SELECT ticket_type, COUNT(*) as cnt
                FROM price_baselines
                WHERE effective_to IS NULL
                GROUP BY ticket_type
                ORDER BY cnt DESC
            """)).fetchall()

            # ── Format distribution ──
            formats = session.execute(text("""
                SELECT COALESCE(format, 'NULL') as fmt, COUNT(*) as cnt
                FROM price_baselines
                WHERE effective_to IS NULL
                GROUP BY format
                ORDER BY cnt DESC
            """)).fetchall()

            # ── Daypart distribution ──
            dayparts = session.execute(text("""
                SELECT COALESCE(daypart, 'NULL') as dp, COUNT(*) as cnt
                FROM price_baselines
                WHERE effective_to IS NULL
                GROUP BY daypart
                ORDER BY cnt DESC
            """)).fetchall()

            # ── Theater metadata completeness ──
            meta_stats = session.execute(text("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN state IS NOT NULL AND state != '' THEN 1 ELSE 0 END) as with_state,
                    SUM(CASE WHEN dma IS NOT NULL AND dma != '' THEN 1 ELSE 0 END) as with_dma,
                    SUM(CASE WHEN circuit_name IS NOT NULL AND circuit_name != '' THEN 1 ELSE 0 END) as with_circuit,
                    SUM(CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END) as with_coords,
                    SUM(CASE WHEN market IS NOT NULL AND market != '' THEN 1 ELSE 0 END) as with_market
                FROM theater_metadata
                WHERE company_id = :cid
            """), {"cid": company_id}).fetchone()

            # ── EntTelligence cache freshness ──
            ent_cache = session.execute(text("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN play_date >= date('now') THEN 1 ELSE 0 END) as future,
                    MAX(fetched_at) as last_fetch,
                    COUNT(DISTINCT theater_name) as theaters,
                    COUNT(DISTINCT play_date) as dates
                FROM enttelligence_price_cache
                WHERE company_id = :cid
            """), {"cid": company_id}).fetchone()

            # ── Tax config coverage ──
            from api.services.tax_estimation import get_tax_config
            tax_config = get_tax_config(company_id)
            per_theater_count = len(tax_config.get("per_theater", {}))
            per_state_count = len(tax_config.get("per_state", {}))

            meta_total = meta_stats[0] if meta_stats else 0

            return {
                "baselines": {
                    "total_active": total_active,
                    "by_source": sources,
                    "stale_30d": stale_30d,
                    "stale_90d": stale_90d,
                    "stale_30d_pct": round(stale_30d / total_active * 100, 1) if total_active else 0,
                    "theaters_with_baselines": theaters_with_baselines,
                },
                "normalization": {
                    "ticket_types": {r[0]: r[1] for r in ticket_types},
                    "formats": {r[0]: r[1] for r in formats},
                    "dayparts": {r[0]: r[1] for r in dayparts},
                },
                "theater_metadata": {
                    "total": meta_total,
                    "with_state": meta_stats[1] if meta_stats else 0,
                    "with_state_pct": round((meta_stats[1] or 0) / meta_total * 100, 1) if meta_total else 0,
                    "with_dma": meta_stats[2] if meta_stats else 0,
                    "with_circuit": meta_stats[3] if meta_stats else 0,
                    "with_coords": meta_stats[4] if meta_stats else 0,
                    "with_market": meta_stats[5] if meta_stats else 0,
                },
                "enttelligence_cache": {
                    "total_entries": ent_cache[0] if ent_cache else 0,
                    "future_entries": ent_cache[1] if ent_cache else 0,
                    "last_fetch": str(ent_cache[2]) if ent_cache and ent_cache[2] else None,
                    "theaters": ent_cache[3] if ent_cache else 0,
                    "dates_covered": ent_cache[4] if ent_cache else 0,
                },
                "tax_estimation": {
                    "enabled": tax_config.get("enabled", False),
                    "default_rate": tax_config.get("default_rate", 0.075),
                    "per_theater_rates": per_theater_count,
                    "per_state_rates": per_state_count,
                    "total_theaters": meta_total,
                    "coverage_pct": round((per_theater_count + per_state_count) / max(meta_total, 1) * 100, 1),
                },
            }

    except Exception as e:
        logger.exception(f"Error getting baselines health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/price-baselines/plf-calibration", tags=["Price Alerts"])
async def refresh_plf_calibration(
    current_user: dict = Depends(require_operator)
):
    """
    Refresh PLF (Premium Large Format) calibration data.

    Uses Fandango's Premium Format baselines as the source of truth to build
    price thresholds for each theater. EntTelligence lumps PLF into "2D" without
    distinction, so these thresholds are used to separate likely PLF prices from
    standard 2D prices during baseline discovery.

    **How it works:**
    1. Loads Fandango `Standard` and `Premium Format` baselines for each theater
    2. Computes a price threshold (midpoint between Standard ceiling and PF floor)
    3. Cross-references with theater amenity data (PLF screen counts)
    4. Reports coverage gaps (theaters with PLF screens but no Fandango PF baselines)

    **Run this after:**
    - Fandango baseline discovery for theaters with PLF screens
    - Changes to theater amenity data
    - Periodically (weekly recommended) to keep PLF thresholds current

    Returns calibration stats, thresholds per theater, and gap analysis.
    """
    try:
        from app.plf_calibration_service import refresh_plf_calibration as _refresh

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        result = _refresh(company_id)

        # Summarize (don't return full thresholds dict in top-level response)
        summary = {
            "theaters_calibrated": result["theaters_calibrated"],
            "theaters_with_plf_screens": result["theaters_with_plf_screens"],
            "coverage_gaps": result["coverage_gaps"],
            "gap_details": result["gap_details"],
            "avg_plf_threshold_pretax": result["avg_plf_threshold_pretax"],
            "sample_thresholds": {
                k: v for k, v in list(result["thresholds"].items())[:5]
            },
        }
        return summary

    except Exception as e:
        logger.exception(f"Error in PLF calibration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-baselines/analyze", tags=["Price Alerts"])
async def analyze_price_patterns(
    lookback_days: int = Query(30, ge=7, le=365, description="Days to analyze"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Analyze price patterns to identify surge pricing candidates.

    Returns:
    - high_volatility_combinations: Theater/ticket/format combos with large price swings
    - format_price_comparison: Average prices by format (shows premium vs standard)

    Use this to understand pricing patterns before setting up surge detection.
    """
    try:
        from app.baseline_discovery import BaselineDiscoveryService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        service = BaselineDiscoveryService(company_id)

        analysis = service.analyze_price_patterns(lookback_days=lookback_days)

        return analysis

    except Exception as e:
        logger.exception(f"Error analyzing price patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-baselines/premium-formats", tags=["Price Alerts"])
async def list_premium_formats(
    current_user: dict = Depends(require_read_admin)
):
    """
    List known premium formats that have inherently higher prices.

    These formats are excluded from surge pricing detection since their
    higher prices are expected, not surge.
    """
    from app.baseline_discovery import PREMIUM_FORMATS, EVENT_CINEMA_KEYWORDS

    return {
        "premium_formats": sorted(list(PREMIUM_FORMATS)),
        "event_cinema_keywords": EVENT_CINEMA_KEYWORDS,
        "description": "These formats/events have expected higher prices and are excluded from surge detection"
    }


# ============================================================================
# ENTTELLIGENCE BASELINE DISCOVERY ENDPOINTS
# ============================================================================

class EntTelligenceDiscoveredBaseline(BaseModel):
    """Model for a baseline discovered from EntTelligence data."""
    theater_name: str
    ticket_type: str
    format: Optional[str] = None
    circuit_name: Optional[str] = None
    baseline_price: float
    sample_count: int
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    avg_price: Optional[float] = None
    volatility_percent: float
    is_premium: bool
    source: str = "enttelligence"


class EntTelligenceDiscoveryResponse(BaseModel):
    """Response for EntTelligence baseline discovery."""
    discovered_count: int
    saved_count: Optional[int] = None
    baselines: List[EntTelligenceDiscoveredBaseline]


class CircuitAnalysis(BaseModel):
    """Analysis for a single circuit."""
    record_count: int
    theater_count: int
    avg_price: Optional[float] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    price_range: Optional[float] = None


class EntTelligenceAnalysisResponse(BaseModel):
    """Response for EntTelligence price analysis."""
    circuits: Dict[str, CircuitAnalysis]
    format_breakdown: Dict[str, dict]
    overall_stats: dict
    data_coverage: Dict[str, int]


@router.get("/enttelligence-baselines/discover", tags=["EntTelligence Baselines"])
async def discover_enttelligence_baselines(
    min_samples: int = Query(5, ge=1, description="Minimum price samples required"),
    lookback_days: int = Query(30, ge=1, le=365, description="Days of history to analyze"),
    circuits: Optional[str] = Query(None, description="Comma-separated list of circuits to include"),
    split_by_day_type: bool = Query(False, description="Split baselines by weekday/weekend"),
    split_by_daypart: bool = Query(False, description="Split baselines by matinee/evening/late (legacy time-based)"),
    split_by_day_of_week: bool = Query(False, description="Split baselines by each day (Mon-Sun). If enabled, day_type is ignored."),
    price_based_dayparts: bool = Query(False, description="RECOMMENDED: Use price-based daypart detection. Only creates separate dayparts if prices actually differ across time periods."),
    exclude_premium: bool = Query(False, description="Exclude premium formats (IMAX, Dolby, PLF, etc.) from discovery. Default FALSE = include PLF baselines for accurate surge detection."),
    save: bool = Query(False, description="Save discovered baselines to database"),
    current_user: dict = Depends(require_operator)
):
    """
    Discover price baselines from EntTelligence cached data.

    Analyzes historical prices from the EntTelligence cache to find the typical
    "normal" price for each theater/ticket_type/format combination. Uses the 25th
    percentile to establish a conservative baseline.

    This is separate from Fandango-based baseline discovery to allow comparison
    between data sources.

    **Note:** EntTelligence data typically only has 'Adult' ticket type pricing.

    **Premium Formats:** By default, premium formats (IMAX, Dolby, PLF, etc.) are
    INCLUDED in discovery. PLF baselines are essential for accurate surge detection —
    PLF prices must be compared against PLF-specific baselines, not 2D baselines.

    **RECOMMENDED - Price-Based Dayparts:** When enabled, intelligently detects dayparts
    based on actual price differences, not arbitrary time cutoffs. If prices don't
    differ between matinee and evening, creates a single "Standard" baseline.
    This produces cleaner, more accurate baselines.

    **Day Type Splitting:** When enabled, calculates separate baselines for:
    - weekday: Monday through Thursday
    - weekend: Friday through Sunday

    **Day of Week Splitting:** When enabled, calculates separate baselines for each day:
    - 0: Monday, 1: Tuesday, ..., 6: Sunday
    - Note: This is more granular than day_type splitting and ignores day_type if both are enabled
    - Useful for theaters with specific discount days (e.g., "$5 Tuesdays")

    **Daypart Splitting (legacy):** When enabled, calculates separate baselines for:
    - Matinee: Before 4:00 PM
    - Twilight: 4:00 PM - 6:00 PM
    - Prime: 6:00 PM - 9:00 PM
    - Late Night: After 9:00 PM

    Splits can be combined for maximum granularity (e.g., Monday_matinee,
    Friday_evening, etc.). This is essential for accurate blockbuster pricing
    detection - comparing same day and daypart.
    """
    try:
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService
        from app.db_session import get_session
        from app.db_models import EntTelligencePriceCache
        from sqlalchemy import func
        from datetime import timedelta

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        logger.debug(f"Discovery: company_id={company_id}, user={current_user.get('username')}")

        # Debug: Check cache data availability
        with get_session() as debug_session:
            cutoff = datetime.now().date() - timedelta(days=lookback_days)
            cache_count = debug_session.query(func.count(EntTelligencePriceCache.cache_id)).filter(
                EntTelligencePriceCache.company_id == company_id,
                EntTelligencePriceCache.play_date >= cutoff,
                EntTelligencePriceCache.price > 0
            ).scalar()
            logger.debug(f"Cache records for company_id={company_id}, lookback={lookback_days}d: {cache_count}")

        # Parse circuit filter if provided
        circuit_filter = None
        if circuits:
            circuit_filter = [c.strip() for c in circuits.split(",") if c.strip()]

        service = EntTelligenceBaselineDiscoveryService(company_id)

        if price_based_dayparts:
            # Use smart price-based daypart detection (recommended)
            baselines = service.discover_baselines_price_based(
                min_samples=min_samples,
                lookback_days=lookback_days,
                exclude_premium=exclude_premium,
                circuit_filter=circuit_filter
            )
        else:
            # Use legacy time-based splitting
            baselines = service.discover_baselines(
                min_samples=min_samples,
                lookback_days=lookback_days,
                exclude_premium=exclude_premium,
                circuit_filter=circuit_filter,
                split_by_day_type=split_by_day_type,
                split_by_daypart=split_by_daypart,
                split_by_day_of_week=split_by_day_of_week
            )
        logger.debug(f"Found {len(baselines)} baselines")

        saved_count = None
        if save and baselines:
            saved_count = service.save_discovered_baselines(baselines)

        # Add summary stats for day type split
        day_type_summary = None
        if split_by_day_type and not split_by_day_of_week:
            weekday_count = len([b for b in baselines if b.get('day_type') == 'weekday'])
            weekend_count = len([b for b in baselines if b.get('day_type') == 'weekend'])
            day_type_summary = {
                "weekday_baselines": weekday_count,
                "weekend_baselines": weekend_count
            }

        # Add summary stats for day of week split
        day_of_week_summary = None
        if split_by_day_of_week:
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            day_of_week_summary = {}
            for i, day_name in enumerate(day_names):
                count = len([b for b in baselines if b.get('day_of_week') == i])
                day_of_week_summary[day_name] = count

        # Add summary stats for daypart split
        daypart_summary = None
        if split_by_daypart:
            matinee_count = len([b for b in baselines if b.get('daypart') == 'matinee'])
            evening_count = len([b for b in baselines if b.get('daypart') == 'evening'])
            late_count = len([b for b in baselines if b.get('daypart') == 'late'])
            daypart_summary = {
                "matinee_baselines": matinee_count,
                "evening_baselines": evening_count,
                "late_baselines": late_count
            }

        return {
            "discovered_count": len(baselines),
            "saved_count": saved_count,
            "split_by_day_type": split_by_day_type,
            "split_by_day_of_week": split_by_day_of_week,
            "split_by_daypart": split_by_daypart,
            "day_type_summary": day_type_summary,
            "day_of_week_summary": day_of_week_summary,
            "daypart_summary": daypart_summary,
            "baselines": baselines
        }

    except Exception as e:
        logger.exception(f"Error discovering EntTelligence baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enttelligence-baselines/refresh", tags=["EntTelligence Baselines"])
async def refresh_enttelligence_baselines(
    current_user: dict = Depends(require_operator)
):
    """
    Refresh all baselines with latest EntTelligence data.

    Re-analyzes EntTelligence cached prices and updates existing baselines.
    New baselines are created for newly discovered combinations.
    """
    try:
        from app.enttelligence_baseline_discovery import refresh_enttelligence_baselines as do_refresh

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        count = do_refresh(company_id)

        return {
            "success": True,
            "baselines_updated": count,
            "message": f"Refreshed {count} baselines from EntTelligence data",
            "source": "enttelligence"
        }

    except Exception as e:
        logger.exception(f"Error refreshing EntTelligence baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enttelligence-baselines/analyze", tags=["EntTelligence Baselines"])
async def analyze_enttelligence_prices(
    lookback_days: int = Query(30, ge=1, le=365, description="Days to analyze"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Analyze EntTelligence price patterns by circuit.

    Returns comprehensive analysis including:
    - Circuit-level pricing (avg, min, max, theater count)
    - Format breakdown with premium identification
    - Overall statistics
    - Data coverage by date

    Use this to understand pricing patterns before setting up baselines.
    """
    try:
        from app.enttelligence_baseline_discovery import analyze_enttelligence_prices

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        analysis = analyze_enttelligence_prices(company_id, lookback_days=lookback_days)

        return analysis

    except Exception as e:
        logger.exception(f"Error analyzing EntTelligence prices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enttelligence-baselines/circuits", tags=["EntTelligence Baselines"])
async def list_enttelligence_circuits(
    current_user: dict = Depends(require_read_admin)
):
    """
    List all circuits with data in the EntTelligence cache.

    Returns circuit names ordered by record count, useful for filtering
    baseline discovery to specific circuits.
    """
    try:
        from app.db_models import EntTelligencePriceCache
        from sqlalchemy import func

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        with get_session() as session:
            query = session.query(
                EntTelligencePriceCache.circuit_name,
                func.count(EntTelligencePriceCache.cache_id).label('record_count'),
                func.count(func.distinct(EntTelligencePriceCache.theater_name)).label('theater_count')
            ).filter(
                EntTelligencePriceCache.company_id == company_id
            ).group_by(
                EntTelligencePriceCache.circuit_name
            ).order_by(
                func.count(EntTelligencePriceCache.cache_id).desc()
            )

            circuits = [
                {
                    "circuit_name": row.circuit_name,
                    "record_count": row.record_count,
                    "theater_count": row.theater_count
                }
                for row in query.all()
                if row.circuit_name
            ]

            return {
                "total_circuits": len(circuits),
                "circuits": circuits
            }

    except Exception as e:
        logger.exception(f"Error listing EntTelligence circuits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enttelligence-baselines/circuit/{circuit_name}", tags=["EntTelligence Baselines"])
async def get_circuit_baselines(
    circuit_name: str,
    min_samples: int = Query(3, ge=1, description="Minimum price samples required"),
    lookback_days: int = Query(30, ge=1, le=365, description="Days of history to analyze"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Get discovered baselines for a specific circuit.

    Useful for analyzing pricing patterns of a specific theater chain
    (e.g., AMC, Regal, Cinemark) before setting baselines.
    """
    try:
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        service = EntTelligenceBaselineDiscoveryService(company_id)
        baselines = service.get_circuit_baselines(
            circuit_name=circuit_name,
            min_samples=min_samples,
            lookback_days=lookback_days
        )

        return {
            "circuit": circuit_name,
            "discovered_count": len(baselines),
            "baselines": baselines
        }

    except Exception as e:
        logger.exception(f"Error getting circuit baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enttelligence-baselines/event-cinema", tags=["EntTelligence Baselines"])
async def analyze_event_cinema(
    lookback_days: int = Query(30, ge=1, le=365, description="Days of history to analyze"),
    circuit: Optional[str] = Query(None, description="Filter to specific circuit"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Analyze event cinema pricing (Fathom Events, Met Opera, concerts, etc.).

    Event cinema has distributor-set pricing and is excluded from baseline calculations.
    This endpoint tracks event cinema separately to:

    - Document which event films are showing
    - Track price consistency across theaters (should be uniform if distributor-set)
    - Identify price variations that may indicate theater-level pricing
    - Compare event cinema prices to regular film averages

    Returns:
        - event_films: List of detected event cinema with pricing stats
        - summary: Overall stats comparing event vs regular pricing
        - price_variations: Films with $1+ price variation across theaters
    """
    try:
        from app.enttelligence_baseline_discovery import (
            EntTelligenceBaselineDiscoveryService,
            get_event_cinema_keywords
        )

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        service = EntTelligenceBaselineDiscoveryService(company_id)
        circuit_filter = [circuit] if circuit else None

        analysis = service.analyze_event_cinema(
            lookback_days=lookback_days,
            circuit_filter=circuit_filter
        )

        # Add keywords used for detection
        analysis['detection_keywords'] = get_event_cinema_keywords()

        return analysis

    except Exception as e:
        logger.exception(f"Error analyzing event cinema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enttelligence-baselines/event-cinema/keywords", tags=["EntTelligence Baselines"])
async def get_event_cinema_keywords_list(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get the list of keywords used to identify event cinema.

    These keywords are checked against film titles to classify them as
    event cinema (Fathom, opera broadcasts, concerts, etc.).

    Event cinema is excluded from baseline calculations because:
    - Prices are typically set by distributors, not theaters
    - Prices should be uniform across theaters in a region
    - Including them would inflate baseline prices
    """
    from app.enttelligence_baseline_discovery import get_event_cinema_keywords

    return {
        "keywords": get_event_cinema_keywords(),
        "description": "Film titles containing these keywords are classified as event cinema"
    }


# ============================================================================
# FANDANGO BASELINE DISCOVERY ENDPOINTS
# ============================================================================

@router.get("/fandango-baselines/discover", tags=["Fandango Baselines"])
async def discover_fandango_baselines(
    min_samples: int = Query(3, ge=1, description="Minimum price samples required"),
    lookback_days: int = Query(90, ge=1, le=365, description="Days of history to analyze"),
    theaters: Optional[str] = Query(None, description="Comma-separated list of theater names to include"),
    split_by_day_of_week: bool = Query(True, description="Split baselines by each day (Mon-Sun) for discount day detection"),
    exclude_premium: bool = Query(False, description="Exclude premium formats (IMAX, Dolby, etc.)"),
    save: bool = Query(False, description="Save discovered baselines to database"),
    current_user: dict = Depends(require_operator)
):
    """
    Discover price baselines from Fandango scraped data.

    Unlike EntTelligence discovery, this uses the **actual daypart values**
    from Fandango (Matinee, Prime, Twilight, Late Night) which reflect each
    theater's pricing structure - not derived from showtime.

    **Baseline Dimensions:**
    - theater_name: The specific theater
    - ticket_type: Adult, Child, Senior, etc.
    - format: 2D, IMAX, Dolby, etc.
    - daypart: Matinee, Prime, Twilight, Late Night (from Fandango's categories)
    - day_of_week: 0=Monday through 6=Sunday (for discount day detection)

    **Day of Week Splitting (Recommended):**
    When enabled (default), calculates separate baselines for each day.
    This is essential for:
    - Identifying discount days (e.g., "$5 Tuesdays")
    - Accurate surge detection (compare Friday to Friday, not Friday to Tuesday)

    **Usage:**
    1. Run discovery with default settings to see all baselines
    2. Review the discovered baselines
    3. Run with save=true to persist good baselines
    4. Use /fandango-baselines/discount-days to identify discount day patterns
    """
    try:
        from app.fandango_baseline_discovery import FandangoBaselineDiscoveryService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        # Parse theater filter if provided
        theater_filter = None
        if theaters:
            theater_filter = [t.strip() for t in theaters.split(",") if t.strip()]

        service = FandangoBaselineDiscoveryService(company_id)

        baselines = service.discover_baselines(
            min_samples=min_samples,
            lookback_days=lookback_days,
            theater_filter=theater_filter,
            split_by_day_of_week=split_by_day_of_week,
            exclude_premium=exclude_premium
        )

        saved_count = None
        if save and baselines:
            saved_count = service.save_baselines(baselines)

        # Summary stats
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_of_week_summary = {}
        if split_by_day_of_week:
            for i, day_name in enumerate(day_names):
                count = len([b for b in baselines if b.get('day_of_week') == i])
                day_of_week_summary[day_name] = count

        daypart_summary = {}
        dayparts = set(b.get('daypart') for b in baselines if b.get('daypart'))
        for daypart in dayparts:
            daypart_summary[daypart] = len([b for b in baselines if b.get('daypart') == daypart])

        theater_summary = {}
        theater_names = set(b.get('theater_name') for b in baselines)
        for theater in theater_names:
            theater_summary[theater] = len([b for b in baselines if b.get('theater_name') == theater])

        return {
            "discovered_count": len(baselines),
            "saved_count": saved_count,
            "split_by_day_of_week": split_by_day_of_week,
            "day_of_week_summary": day_of_week_summary if split_by_day_of_week else None,
            "daypart_summary": daypart_summary,
            "theater_count": len(theater_names),
            "theater_summary": theater_summary,
            "baselines": baselines
        }

    except Exception as e:
        logger.exception(f"Error discovering Fandango baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fandango-baselines/theater/{theater_name}", tags=["Fandango Baselines"])
async def analyze_theater_pricing(
    theater_name: str,
    lookback_days: int = Query(90, ge=1, le=365, description="Days of history to analyze"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Analyze a specific theater's pricing structure.

    Returns comprehensive analysis including:
    - Daypart pricing (Matinee, Prime, Twilight, Late Night)
    - Day of week pricing patterns
    - Potential discount days (days with significantly lower prices)
    - Ticket type breakdown
    - Format breakdown with premium identification

    Use this to understand a theater's pricing structure before setting baselines.
    """
    try:
        from app.fandango_baseline_discovery import FandangoBaselineDiscoveryService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        service = FandangoBaselineDiscoveryService(company_id)
        analysis = service.analyze_theater_pricing(theater_name, lookback_days)

        return analysis

    except Exception as e:
        logger.exception(f"Error analyzing theater pricing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fandango-baselines/discount-days", tags=["Fandango Baselines"])
async def detect_discount_days(
    theater: Optional[str] = Query(None, description="Specific theater to analyze (None = all)"),
    threshold_percent: float = Query(15.0, ge=5, le=50, description="Minimum discount percentage to flag"),
    min_samples: int = Query(5, ge=1, description="Minimum samples required"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Detect potential discount days across theaters.

    Analyzes pricing by day of week to identify days with significantly
    lower prices (e.g., "$5 Tuesdays", "Discount Wednesdays").

    **How it works:**
    1. Groups prices by theater, day of week, daypart, and ticket type
    2. Calculates average price for each combination
    3. Compares each day to the overall average for that combination
    4. Flags days that are {threshold_percent}% or more below average

    **Returns:**
    List of detected discount day patterns, sorted by discount percentage.
    Each entry includes:
    - theater_name
    - day_of_week and day_name
    - daypart and ticket_type
    - avg_price vs overall_avg
    - discount_percent

    Use this information to:
    - Configure DiscountProgram entries
    - Understand which theaters have discount days
    - Set separate baselines for discount days
    """
    try:
        from app.fandango_baseline_discovery import FandangoBaselineDiscoveryService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        service = FandangoBaselineDiscoveryService(company_id)
        discount_days = service.detect_discount_days(
            theater_name=theater,
            threshold_percent=threshold_percent,
            min_samples=min_samples
        )

        # Group by theater for summary
        by_theater = {}
        for d in discount_days:
            t_name = d['theater_name']
            if t_name not in by_theater:
                by_theater[t_name] = []
            by_theater[t_name].append(d)

        return {
            "detected_count": len(discount_days),
            "theaters_with_discounts": len(by_theater),
            "threshold_percent": threshold_percent,
            "by_theater": by_theater,
            "all_detected": discount_days
        }

    except Exception as e:
        logger.exception(f"Error detecting discount days: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fandango-baselines/theaters", tags=["Fandango Baselines"])
async def list_fandango_theaters(
    current_user: dict = Depends(require_read_admin)
):
    """
    List all theaters with Fandango scraped data.

    Returns theater names with their price record counts, useful for
    filtering baseline discovery to specific theaters.
    """
    try:
        from app.db_models import Showing, Price
        from sqlalchemy import func

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        with get_session() as session:
            query = session.query(
                Showing.theater_name,
                func.count(Price.price_id).label('price_count'),
                func.count(func.distinct(Showing.daypart)).label('daypart_count'),
                func.count(func.distinct(Price.ticket_type)).label('ticket_type_count')
            ).join(
                Price, Showing.showing_id == Price.showing_id
            ).filter(
                Price.company_id == company_id
            ).group_by(
                Showing.theater_name
            ).order_by(func.count(Price.price_id).desc())

            theaters = [
                {
                    "theater_name": row.theater_name,
                    "price_count": row.price_count,
                    "daypart_count": row.daypart_count,
                    "ticket_type_count": row.ticket_type_count
                }
                for row in query.all()
            ]

            return {
                "total_theaters": len(theaters),
                "theaters": theaters
            }

    except Exception as e:
        logger.exception(f"Error listing Fandango theaters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MARKET BASELINE SCRAPING ENDPOINTS
# ============================================================================

class MarketScrapeRequest(BaseModel):
    """Request to trigger market baseline scraping."""
    circuit: Optional[str] = Field(None, description="Filter to specific circuit (e.g., 'Marcus', 'AMC')")
    max_markets: Optional[int] = Field(None, ge=1, le=100, description="Maximum markets to scrape")
    days: int = Field(2, ge=1, le=7, description="Number of days to scrape")


class MarketScrapeStatus(BaseModel):
    """Status of a market scrape job."""
    job_id: str
    status: str
    total_markets: int
    completed_markets: int
    failed_markets: int
    current_market: Optional[str] = None
    error: Optional[str] = None


class MarketStats(BaseModel):
    """Statistics about available markets."""
    total_markets: int
    circuits: Dict[str, Dict[str, int]]


@router.get("/market-baselines/stats", tags=["Market Baselines"])
async def get_market_stats(
    current_user: dict = Depends(require_read_admin)
) -> MarketStats:
    """
    Get statistics about available markets for baseline scraping.

    Shows total markets and breakdown by circuit.
    """
    from app.market_baseline_service import get_market_scrape_stats

    stats = get_market_scrape_stats()
    return MarketStats(**stats)


@router.get("/market-baselines/plan", tags=["Market Baselines"])
async def get_market_scrape_plan(
    circuit: Optional[str] = Query(None, description="Filter to specific circuit"),
    max_markets: Optional[int] = Query(None, ge=1, le=100, description="Max markets to include"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Preview the market scrape plan without executing.

    Shows which theaters would be scraped for each market.
    """
    from app.market_baseline_service import build_market_scrape_plan

    plan = build_market_scrape_plan(circuit_filter=circuit, max_markets=max_markets)

    # Group by circuit for summary
    by_circuit = {}
    for item in plan:
        circuit_name = item["circuit"]
        if circuit_name not in by_circuit:
            by_circuit[circuit_name] = []
        by_circuit[circuit_name].append({
            "market": item["market"],
            "theater": item["theater_name"]
        })

    return {
        "total_markets": len(plan),
        "by_circuit": by_circuit,
        "plan": plan
    }


@router.post("/market-baselines/scrape", tags=["Market Baselines"])
async def trigger_market_baseline_scrape(
    request: MarketScrapeRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_read_admin)
):
    """
    Trigger market-by-market baseline scraping.

    This runs in the background and scrapes one theater per market
    to build comprehensive baseline data with multiple ticket types and formats.
    """
    from app.market_baseline_service import (
        build_market_scrape_plan,
        run_market_baseline_scrape
    )
    from datetime import date, timedelta
    import uuid

    company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

    # Build scrape plan
    plan = build_market_scrape_plan(
        circuit_filter=request.circuit,
        max_markets=request.max_markets
    )

    if not plan:
        raise HTTPException(status_code=400, detail="No markets found matching criteria")

    # Generate job ID
    job_id = str(uuid.uuid4())[:8]

    # Determine dates
    today = date.today()
    dates = [today + timedelta(days=i) for i in range(request.days)]

    # Start background task
    import asyncio

    async def run_scrape():
        await run_market_baseline_scrape(
            job_id=job_id,
            scrape_plan=plan,
            dates=dates,
            company_id=company_id
        )

    # Run in background
    asyncio.create_task(run_scrape())

    # Log audit
    audit_service.data_event(
        event_type="market_baseline_scrape_started",
        username=current_user.get("username", "unknown"),
        details={
            "job_id": job_id,
            "markets": len(plan),
            "circuit_filter": request.circuit,
            "days": request.days
        }
    )

    return {
        "job_id": job_id,
        "status": "started",
        "total_markets": len(plan),
        "dates": [d.isoformat() for d in dates],
        "message": f"Scraping {len(plan)} markets in background"
    }


@router.get("/market-baselines/scrape/{job_id}", tags=["Market Baselines"])
async def get_market_scrape_status(
    job_id: str,
    current_user: dict = Depends(require_read_admin)
) -> MarketScrapeStatus:
    """
    Get status of a market baseline scrape job.
    """
    from app.market_baseline_service import get_market_scrape_job

    job = get_market_scrape_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return MarketScrapeStatus(
        job_id=job.job_id,
        status=job.status,
        total_markets=job.total_markets,
        completed_markets=job.completed_markets,
        failed_markets=job.failed_markets,
        current_market=job.current_market,
        error=job.error
    )


@router.post("/market-baselines/scrape/{job_id}/cancel", tags=["Market Baselines"])
async def cancel_market_scrape(
    job_id: str,
    current_user: dict = Depends(require_read_admin)
):
    """
    Cancel a running market baseline scrape job.
    """
    from app.market_baseline_service import cancel_market_scrape_job

    success = cancel_market_scrape_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or not running")

    audit_service.data_event(
        event_type="market_baseline_scrape_cancelled",
        username=current_user.get("username", "unknown"),
        details={"job_id": job_id}
    )

    return {"status": "cancelled", "job_id": job_id}


# ============================================================================
# DISCOUNT PROGRAMS
# ============================================================================

class DiscountProgramRequest(BaseModel):
    """Request for creating/updating discount programs."""
    theater_name: str
    circuit_name: Optional[str] = None
    program_name: str
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    discount_type: str = Field(..., description="'flat_price', 'percentage', or 'amount_off'")
    discount_value: float = Field(..., gt=0)
    ticket_types: Optional[str] = None  # Comma-separated
    formats: Optional[str] = None  # Comma-separated
    dayparts: Optional[str] = None  # Comma-separated
    is_verified: bool = False
    notes: Optional[str] = None


class DiscountProgramResponse(BaseModel):
    """Response for discount program."""
    id: int
    theater_name: str
    circuit_name: Optional[str] = None
    program_name: str
    day_of_week: int
    day_name: str
    discount_type: str
    discount_value: float
    ticket_types: Optional[str] = None
    formats: Optional[str] = None
    dayparts: Optional[str] = None
    detected_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    confidence: float = 1.0
    is_verified: bool = False
    is_active: bool = True
    notes: Optional[str] = None


DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


@router.get("/discount-programs", tags=["Discount Programs"])
async def list_discount_programs(
    theater_name: Optional[str] = Query(None, description="Filter by theater (partial match)"),
    circuit_name: Optional[str] = Query(None, description="Filter by circuit"),
    day_of_week: Optional[int] = Query(None, ge=0, le=6, description="Filter by day (0=Monday)"),
    active_only: bool = Query(True, description="Only show active programs"),
    current_user: dict = Depends(require_read_admin)
) -> List[DiscountProgramResponse]:
    """
    List discount programs.

    Discount programs track recurring discount days like "$5 Tuesdays" or "Senior Wednesdays".
    """
    try:
        from app.db_models import DiscountProgram

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            query = session.query(DiscountProgram).filter(
                DiscountProgram.company_id == company_id
            )

            if theater_name:
                query = query.filter(DiscountProgram.theater_name.ilike(f"%{theater_name}%"))
            if circuit_name:
                query = query.filter(DiscountProgram.circuit_name == circuit_name)
            if day_of_week is not None:
                query = query.filter(DiscountProgram.day_of_week == day_of_week)
            if active_only:
                query = query.filter(DiscountProgram.is_active == True)

            programs = query.order_by(DiscountProgram.theater_name, DiscountProgram.day_of_week).all()

            return [
                DiscountProgramResponse(
                    id=p.id,
                    theater_name=p.theater_name,
                    circuit_name=p.circuit_name,
                    program_name=p.program_name,
                    day_of_week=p.day_of_week,
                    day_name=DAY_NAMES[p.day_of_week] if 0 <= p.day_of_week <= 6 else 'Unknown',
                    discount_type=p.discount_type,
                    discount_value=float(p.discount_value),
                    ticket_types=p.ticket_types,
                    formats=p.formats,
                    dayparts=p.dayparts,
                    detected_at=p.detected_at,
                    last_seen_at=p.last_seen_at,
                    confidence=float(p.confidence) if p.confidence else 1.0,
                    is_verified=p.is_verified,
                    is_active=p.is_active,
                    notes=p.notes
                )
                for p in programs
            ]
    except Exception as e:
        logger.exception(f"Error listing discount programs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discount-programs", response_model=DiscountProgramResponse, status_code=201, tags=["Discount Programs"])
async def create_discount_program(
    request: DiscountProgramRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Create a new discount program.
    """
    try:
        from app.db_models import DiscountProgram
        from decimal import Decimal

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            program = DiscountProgram(
                company_id=company_id,
                theater_name=request.theater_name,
                circuit_name=request.circuit_name,
                program_name=request.program_name,
                day_of_week=request.day_of_week,
                discount_type=request.discount_type,
                discount_value=Decimal(str(request.discount_value)),
                ticket_types=request.ticket_types,
                formats=request.formats,
                dayparts=request.dayparts,
                is_verified=request.is_verified,
                notes=request.notes,
                confidence=Decimal('1.0')
            )
            session.add(program)
            session.flush()

            audit_service.data_event(
                event_type="create_discount_program",
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                company_id=company_id,
                details={
                    "theater": request.theater_name,
                    "program_name": request.program_name,
                    "day_of_week": request.day_of_week
                }
            )

            logger.info(f"Discount program created: {program.theater_name} - {program.program_name}")

            return DiscountProgramResponse(
                id=program.id,
                theater_name=program.theater_name,
                circuit_name=program.circuit_name,
                program_name=program.program_name,
                day_of_week=program.day_of_week,
                day_name=DAY_NAMES[program.day_of_week],
                discount_type=program.discount_type,
                discount_value=float(program.discount_value),
                ticket_types=program.ticket_types,
                formats=program.formats,
                dayparts=program.dayparts,
                detected_at=program.detected_at,
                last_seen_at=program.last_seen_at,
                confidence=float(program.confidence) if program.confidence else 1.0,
                is_verified=program.is_verified,
                is_active=program.is_active,
                notes=program.notes
            )
    except Exception as e:
        logger.exception(f"Error creating discount program: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/discount-programs/{program_id}", response_model=DiscountProgramResponse, tags=["Discount Programs"])
async def update_discount_program(
    program_id: int,
    request: DiscountProgramRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Update a discount program.
    """
    try:
        from app.db_models import DiscountProgram
        from decimal import Decimal

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            program = session.query(DiscountProgram).filter(
                DiscountProgram.id == program_id,
                DiscountProgram.company_id == company_id
            ).first()

            if not program:
                raise HTTPException(status_code=404, detail=f"Discount program {program_id} not found")

            program.theater_name = request.theater_name
            program.circuit_name = request.circuit_name
            program.program_name = request.program_name
            program.day_of_week = request.day_of_week
            program.discount_type = request.discount_type
            program.discount_value = Decimal(str(request.discount_value))
            program.ticket_types = request.ticket_types
            program.formats = request.formats
            program.dayparts = request.dayparts
            program.is_verified = request.is_verified
            program.notes = request.notes

            session.flush()

            logger.info(f"Discount program updated: {program.id}")

            return DiscountProgramResponse(
                id=program.id,
                theater_name=program.theater_name,
                circuit_name=program.circuit_name,
                program_name=program.program_name,
                day_of_week=program.day_of_week,
                day_name=DAY_NAMES[program.day_of_week],
                discount_type=program.discount_type,
                discount_value=float(program.discount_value),
                ticket_types=program.ticket_types,
                formats=program.formats,
                dayparts=program.dayparts,
                detected_at=program.detected_at,
                last_seen_at=program.last_seen_at,
                confidence=float(program.confidence) if program.confidence else 1.0,
                is_verified=program.is_verified,
                is_active=program.is_active,
                notes=program.notes
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating discount program: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/discount-programs/{program_id}", status_code=204, tags=["Discount Programs"])
async def delete_discount_program(
    program_id: int,
    current_user: dict = Depends(require_operator)
):
    """
    Delete a discount program.
    """
    try:
        from app.db_models import DiscountProgram

        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

            program = session.query(DiscountProgram).filter(
                DiscountProgram.id == program_id,
                DiscountProgram.company_id == company_id
            ).first()

            if not program:
                raise HTTPException(status_code=404, detail=f"Discount program {program_id} not found")

            session.delete(program)
            session.flush()

            audit_service.data_event(
                event_type="delete_discount_program",
                user_id=current_user.get("user_id"),
                username=current_user.get("username"),
                company_id=company_id,
                details={"program_id": program_id}
            )

            logger.info(f"Discount program deleted: {program_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting discount program: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ADVANCE SURGE SCANNER
# ============================================================================

class SurgeDetection(BaseModel):
    """Model for a detected surge in advance pricing."""
    theater_name: str
    circuit_name: Optional[str] = None
    film_title: str
    play_date: date
    ticket_type: str
    format: Optional[str] = None
    current_price: float
    baseline_price: float
    surge_percent: float
    surge_multiplier: float
    day_type: Optional[str] = None  # weekday or weekend
    day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    daypart: Optional[str] = None   # matinee, evening, or late
    is_discount_day: bool = False   # True if this is a known discount day for the circuit
    discount_day_price: Optional[float] = None  # Expected discount price if is_discount_day


class DiscountDayComplianceItem(BaseModel):
    """Detail about a film/theater price on a discount day with compliance status."""
    theater_name: str
    circuit_name: Optional[str] = None
    film_title: str
    play_date: date
    ticket_type: str
    format: Optional[str] = None
    current_price: float
    expected_discount_price: float
    discount_program_name: Optional[str] = None
    is_compliant: bool  # True if price is at/below expected (within 5% tolerance)
    is_special_event: bool = False  # Excluded from compliance — distributor-set pricing
    is_loyalty_ac: bool = False  # Excluded from compliance — discounted from original price
    is_plf: bool = False  # Excluded from compliance — PLF screens priced differently even on discount days
    deviation_percent: Optional[float] = None  # How far above/below expected (positive = over)


class AdvanceSurgeScanResponse(BaseModel):
    """Response model for advance surge scan."""
    scan_date_from: date
    scan_date_to: date
    total_prices_scanned: int
    total_surges_found: int
    surge_threshold_percent: float
    min_surge_amount: Optional[float] = None  # Dollar amount threshold
    surges: List[SurgeDetection]
    circuits_scanned: List[str]
    films_with_surges: List[str]
    discount_day_prices_filtered: int = 0  # Count of prices skipped due to discount day matching
    discount_day_compliance: List[DiscountDayComplianceItem] = []  # Detailed compliance info per film
    discount_day_violations: int = 0  # Count of non-compliant (excluding special events/loyalty)
    circuits_with_profiles: List[str] = []  # Circuits that have discovered profiles


@router.get("/surge-scanner/advance", response_model=AdvanceSurgeScanResponse, tags=["Surge Scanner"])
async def scan_advance_dates_for_surges(
    date_from: date = Query(..., description="Start date to scan (YYYY-MM-DD)"),
    date_to: date = Query(..., description="End date to scan (YYYY-MM-DD)"),
    circuit: Optional[str] = Query(None, description="Filter by circuit name (partial match)"),
    theater: Optional[str] = Query(None, description="Filter by theater name (partial match)"),
    film: Optional[str] = Query(None, description="Filter by film title (partial match)"),
    surge_threshold: float = Query(20.0, ge=0.0, le=100.0, description="Minimum surge % to report (0 to disable)"),
    min_surge_amount: Optional[float] = Query(1.0, ge=0.0, le=50.0, description="Minimum surge $ amount to report (0 to disable)"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Scan EntTelligence cache data for surge pricing on advance dates.

    Compares cached prices against established baselines to detect surge pricing
    before it becomes current. Useful for identifying advance surges on special
    events, holidays, or anticipated high-demand films.

    **Detection Logic:** A surge is flagged if price exceeds baseline by:
    - >= surge_threshold percent (e.g., 20% above baseline), OR
    - >= min_surge_amount dollars (e.g., $1.00 above baseline)

    Set either threshold to 0 to disable that check. For example:
    - surge_threshold=0, min_surge_amount=1.0 → Only flag $1+ increases
    - surge_threshold=20, min_surge_amount=0 → Only flag 20%+ increases
    - surge_threshold=20, min_surge_amount=1.0 → Flag either (default)

    Examples:
    - Check Valentine's weekend: date_from=2025-02-14, date_to=2025-02-16
    - Check a specific circuit: circuit=Marcus
    - Check a specific film: film=Wuthering Heights
    """
    from app.db_models import EntTelligencePriceCache, PriceBaseline, CompanyProfile
    from sqlalchemy import func, or_
    from api.services.tax_estimation import (
        get_tax_config as _get_tax_config,
        get_tax_rate_for_theater,
        apply_estimated_tax,
        bulk_get_theater_states,
    )
    import json

    company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

    # Validate date range
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be before date_to")

    max_days = 30
    if (date_to - date_from).days > max_days:
        raise HTTPException(status_code=400, detail=f"Date range cannot exceed {max_days} days")

    # Load tax config for normalizing EntTelligence pre-tax prices to tax-inclusive
    # (baselines are stored tax-inclusive, EntTelligence cache is pre-tax)
    tax_config = _get_tax_config(company_id)

    # Load PLF thresholds for discount day compliance — PLF screens have separate
    # pricing even on discount days and should not be flagged as violations
    from app.plf_calibration_service import build_plf_thresholds
    try:
        plf_thresholds = build_plf_thresholds(company_id)
    except Exception:
        plf_thresholds = {}

    surges = []
    total_scanned = 0
    circuits_scanned = set()
    films_with_surges = set()
    discount_day_compliance_items = []
    discount_day_violations = 0

    # Use shared daypart classifier (canonical: Matinee/Twilight/Prime/Late Night)
    from app.simplified_baseline_service import (
        classify_daypart, normalize_daypart as _normalize_daypart,
        normalize_ticket_type as _normalize_ticket_type,
    )

    with get_session() as session:
        # Load active baselines into a lookup dict
        today = date.today()
        baselines_query = session.query(PriceBaseline).filter(
            PriceBaseline.company_id == company_id,
            PriceBaseline.effective_from <= today,
            or_(
                PriceBaseline.effective_to.is_(None),
                PriceBaseline.effective_to >= today
            )
        ).all()

        # Build flat baseline cache keyed by: "theater|ticket_type|format|daypart"
        # Matches AlertService._find_baseline() pattern. day_of_week is deprecated
        # (all baselines have day_of_week=NULL after dedup migration).
        baseline_cache: dict[str, PriceBaseline] = {}
        for bl in baselines_query:
            fmt = bl.format or '*'
            # Normalize format: "Standard" → "2D"
            if fmt.lower() == 'standard':
                fmt = '2D'
            dp = bl.daypart or '*'
            key = f"{bl.theater_name}|{bl.ticket_type}|{fmt}|{dp}"
            existing = baseline_cache.get(key)
            if not existing or (bl.sample_count or 0) > (existing.sample_count or 0):
                baseline_cache[key] = bl

        def find_baseline(theater: str, ticket_type: str, fmt: str, daypart: Optional[str]) -> Optional[PriceBaseline]:
            """Find best matching baseline with wildcard fallback."""
            fmt_norm = fmt or '*'
            if fmt_norm.lower() == 'standard':
                fmt_norm = '2D'
            dp = daypart or '*'
            # Try most specific → most general (same order as AlertService)
            for key in [
                f"{theater}|{ticket_type}|{fmt_norm}|{dp}",
                f"{theater}|{ticket_type}|{fmt_norm}|*",
                f"{theater}|{ticket_type}|*|{dp}",
                f"{theater}|{ticket_type}|*|*",
            ]:
                if key in baseline_cache:
                    return baseline_cache[key]
            return None

        # Load company profiles for discount day awareness
        # Build a lookup: {circuit_name: {day_of_week: discount_price}}
        profiles = session.query(CompanyProfile).filter(
            CompanyProfile.company_id == company_id
        ).all()

        discount_day_lookup: dict = {}  # {circuit_name: {day_of_week: (price, program_name)}}
        for profile in profiles:
            if profile.has_discount_days and profile.discount_days:
                try:
                    discount_days = json.loads(profile.discount_days) if isinstance(profile.discount_days, str) else profile.discount_days
                    if discount_days:
                        discount_day_lookup[profile.circuit_name] = {}
                        for dd in discount_days:
                            dow = dd.get('day_of_week')
                            price = dd.get('price')
                            name = dd.get('name') or dd.get('program_name') or f"Discount Day"
                            if dow is not None and price is not None:
                                discount_day_lookup[profile.circuit_name][dow] = (float(price), name)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Helper to check if a date/circuit is a discount day
        def get_discount_info(circuit_name: str, day_of_week: int) -> tuple:
            """Returns (is_discount_day, discount_price, program_name) for a circuit and day."""
            if circuit_name in discount_day_lookup:
                if day_of_week in discount_day_lookup[circuit_name]:
                    price, name = discount_day_lookup[circuit_name][day_of_week]
                    return True, price, name
            return False, None, None

        # Track circuits with profiles and discount day filtering
        circuits_with_profiles = list(discount_day_lookup.keys())
        discount_day_filtered_count = 0

        # Query EntTelligence cache for the date range (include showtime for daypart)
        query = session.query(
            EntTelligencePriceCache.theater_name,
            EntTelligencePriceCache.circuit_name,
            EntTelligencePriceCache.film_title,
            EntTelligencePriceCache.play_date,
            EntTelligencePriceCache.showtime,
            EntTelligencePriceCache.ticket_type,
            EntTelligencePriceCache.format,
            EntTelligencePriceCache.price
        ).filter(
            EntTelligencePriceCache.company_id == company_id,
            EntTelligencePriceCache.play_date >= date_from,
            EntTelligencePriceCache.play_date <= date_to,
            EntTelligencePriceCache.price > 0
        )

        # Apply optional filters
        if circuit:
            query = query.filter(EntTelligencePriceCache.circuit_name.ilike(f"%{circuit}%"))
        if theater:
            query = query.filter(EntTelligencePriceCache.theater_name.ilike(f"%{theater}%"))
        if film:
            query = query.filter(EntTelligencePriceCache.film_title.ilike(f"%{film}%"))

        # Get distinct price points (unique by theater/film/date/showtime/ticket_type/format)
        query = query.distinct(
            EntTelligencePriceCache.theater_name,
            EntTelligencePriceCache.film_title,
            EntTelligencePriceCache.play_date,
            EntTelligencePriceCache.showtime,
            EntTelligencePriceCache.ticket_type,
            EntTelligencePriceCache.format
        )

        results = query.all()
        total_scanned = len(results)

        # Batch-lookup theater states for per-theater tax rate resolution
        theater_names_in_results = list(set(row[0] for row in results))
        theater_states = bulk_get_theater_states(company_id, theater_names_in_results)

        # Helper to determine day type from date
        def get_day_type(d: date) -> str:
            return 'weekend' if d.weekday() >= 4 else 'weekday'

        # Check each price against baseline
        for row in results:
            theater_name, circuit_name, film_title, play_date_val, showtime, ticket_type, format_type, price = row

            circuits_scanned.add(circuit_name or "Unknown")

            # Determine day_of_week and daypart using canonical classifier
            day_of_week_val = play_date_val.weekday()
            day_type = get_day_type(play_date_val)
            daypart = classify_daypart(showtime)

            # Normalize ticket type before lookup (e.g., 'early bird' → 'Early Bird')
            norm_ticket = _normalize_ticket_type(ticket_type) or ticket_type

            # Find matching baseline using simplified flat cache with wildcard fallback.
            # Try normalized ticket type first, then equivalent types (Adult ↔ General Admission).
            baseline = find_baseline(theater_name, norm_ticket, format_type, daypart)
            if not baseline:
                for equiv_tt in get_equivalent_ticket_types(norm_ticket)[1:]:
                    baseline = find_baseline(theater_name, equiv_tt, format_type, daypart)
                    if baseline:
                        break

            if not baseline:
                continue  # No baseline to compare

            # Tax-aware price comparison:
            # - 'exclusive' baselines (Marcus/MT/Cinemark ENT) are pre-tax → compare directly
            # - 'inclusive' baselines (AMC/Regal/Fandango) are tax-inclusive → add tax to ENT price
            baseline_price = float(baseline.baseline_price)
            if hasattr(baseline, 'tax_status') and baseline.tax_status == 'exclusive':
                # Both baseline and ENT cache are pre-tax — compare directly
                current_price = float(price)
            else:
                # Baseline is tax-inclusive, ENT cache is pre-tax — add tax to ENT
                ent_tax_rate = get_tax_rate_for_theater(
                    tax_config, theater_states.get(theater_name), theater_name=theater_name
                )
                current_price = apply_estimated_tax(float(price), ent_tax_rate)

            if baseline_price <= 0:
                continue

            # Check if this is a known discount day for the circuit
            is_discount_day, discount_price, program_name = get_discount_info(circuit_name or "", day_of_week_val)

            # On discount days, build detailed compliance item and filter accordingly
            comparison_price = baseline_price
            if is_discount_day and discount_price is not None:
                from app.alternative_content_service import detect_content_type_from_title, detect_ac_from_ticket_type
                from app.plf_calibration_service import classify_price as classify_plf_price

                is_special = detect_content_type_from_title(film_title)[0] is not None
                is_ac = detect_ac_from_ticket_type(ticket_type)

                # Check if this price is from a PLF screen — PLF screens have separate
                # pricing even on discount days (e.g., UltraScreen on $5 Tuesday ≠ $5)
                is_plf = False
                if theater_name in plf_thresholds:
                    plf_class = classify_plf_price(float(price), theater_name, plf_thresholds)
                    is_plf = (plf_class == 'plf')

                price_compliant = current_price <= discount_price * 1.05  # 5% tolerance
                deviation = ((current_price - discount_price) / discount_price * 100) if discount_price > 0 else 0

                compliance_item = DiscountDayComplianceItem(
                    theater_name=theater_name,
                    circuit_name=circuit_name,
                    film_title=film_title,
                    play_date=play_date_val,
                    ticket_type=ticket_type,
                    format=format_type,
                    current_price=round(current_price, 2),
                    expected_discount_price=round(discount_price, 2),
                    discount_program_name=program_name,
                    is_compliant=price_compliant or is_special or is_ac or is_plf,
                    is_special_event=is_special,
                    is_loyalty_ac=is_ac,
                    is_plf=is_plf,
                    deviation_percent=round(deviation, 1),
                )
                discount_day_compliance_items.append(compliance_item)

                if not price_compliant and not is_special and not is_ac and not is_plf:
                    discount_day_violations += 1

                discount_day_filtered_count += 1
                continue  # Don't process discount day prices as surges

            surge_amount = current_price - comparison_price
            surge_percent = (surge_amount / comparison_price) * 100

            # Check if this qualifies as a surge (either threshold)
            is_surge = False
            if surge_threshold > 0 and surge_percent >= surge_threshold:
                is_surge = True
            if min_surge_amount and min_surge_amount > 0 and surge_amount >= min_surge_amount:
                is_surge = True

            if is_surge:
                surge_multiplier = current_price / comparison_price
                films_with_surges.add(film_title)

                surges.append(SurgeDetection(
                    theater_name=theater_name,
                    circuit_name=circuit_name,
                    film_title=film_title,
                    play_date=play_date_val,
                    ticket_type=ticket_type,
                    format=format_type,
                    current_price=round(current_price, 2),
                    baseline_price=round(baseline_price, 2),
                    surge_percent=round(surge_percent, 1),
                    surge_multiplier=round(surge_multiplier, 2),
                    day_type=day_type,
                    day_of_week=day_of_week_val,
                    daypart=daypart,
                    is_discount_day=is_discount_day,
                    discount_day_price=round(discount_price, 2) if discount_price else None
                ))

        # Sort surges by surge_percent descending
        surges.sort(key=lambda x: x.surge_percent, reverse=True)

        logger.info(f"Advance surge scan: {date_from} to {date_to}, "
                   f"scanned {total_scanned} prices, found {len(surges)} surges, "
                   f"filtered {discount_day_filtered_count} discount day prices, "
                   f"{discount_day_violations} discount day violations "
                   f"(thresholds: {surge_threshold}% or ${min_surge_amount})")

        return AdvanceSurgeScanResponse(
            scan_date_from=date_from,
            scan_date_to=date_to,
            total_prices_scanned=total_scanned,
            total_surges_found=len(surges),
            surge_threshold_percent=surge_threshold,
            min_surge_amount=min_surge_amount,
            surges=surges[:200],  # Limit to 200 results
            circuits_scanned=sorted(circuits_scanned),
            films_with_surges=sorted(films_with_surges),
            discount_day_prices_filtered=discount_day_filtered_count,
            discount_day_compliance=discount_day_compliance_items[:100],  # Limit to 100
            discount_day_violations=discount_day_violations,
            circuits_with_profiles=sorted(circuits_with_profiles)
        )


# ============================================================================
# NEW FILM MONITORING - Check recently posted films for surge pricing
# ============================================================================

class NewFilmSurge(BaseModel):
    """A surge detected on a recently posted film."""
    film_title: str
    theater_name: str
    circuit_name: Optional[str] = None
    play_date: date
    ticket_type: str
    format: Optional[str] = None
    current_price: float
    baseline_price: float
    surge_percent: float
    first_seen: Optional[datetime] = None
    is_presale: bool = False


class NewFilmSurgeResponse(BaseModel):
    """Response for new film monitoring."""
    check_time: datetime
    lookback_hours: int
    total_new_prices: int
    surges_found: int
    films_checked: List[str]
    surges: List[NewFilmSurge]


@router.get("/surge-scanner/new-films", response_model=NewFilmSurgeResponse, tags=["Surge Scanner"])
async def check_new_films_for_surges(
    lookback_hours: int = Query(24, ge=1, le=168, description="Hours to look back for new film postings (1-168)"),
    surge_threshold: float = Query(20.0, ge=0.0, le=100.0, description="Minimum surge % to report"),
    min_surge_amount: float = Query(1.0, ge=0.0, le=50.0, description="Minimum surge $ amount to report"),
    circuit: Optional[str] = Query(None, description="Filter by circuit name"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Monitor recently posted films for surge pricing.

    Checks EntTelligence cache for prices added in the last N hours and compares
    them against baselines. This helps detect surge pricing on new film announcements
    or presale openings before they become widespread.

    **Use Cases:**
    - Detect surge pricing when a new blockbuster opens presales
    - Monitor competitor pricing on newly posted films
    - Track premium format pricing on new releases

    Returns films with prices above baseline, sorted by surge percentage.
    """
    from app.db_models import EntTelligencePriceCache, PriceBaseline, CompanyProfile
    from sqlalchemy import func, or_
    from api.services.tax_estimation import (
        get_tax_config as _get_tax_config,
        get_tax_rate_for_theater,
        apply_estimated_tax,
        bulk_get_theater_states,
    )
    import json

    company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
    check_time = datetime.now(UTC)
    lookback_cutoff = check_time - timedelta(hours=lookback_hours)

    # Load tax config for normalizing EntTelligence pre-tax prices to tax-inclusive
    tax_config = _get_tax_config(company_id)

    surges = []
    films_checked = set()

    with get_session() as session:
        # Load active baselines into lookup
        today = date.today()
        baselines_query = session.query(PriceBaseline).filter(
            PriceBaseline.company_id == company_id,
            PriceBaseline.effective_from <= today,
            or_(
                PriceBaseline.effective_to.is_(None),
                PriceBaseline.effective_to >= today
            )
        ).all()

        # Build flat baseline cache (same pattern as advance scanner)
        from app.simplified_baseline_service import (
            classify_daypart as _classify_daypart_nf,
            normalize_ticket_type as _normalize_tt_nf,
        )
        baseline_cache_nf: dict[str, PriceBaseline] = {}
        for bl in baselines_query:
            fmt = bl.format or '*'
            if fmt.lower() == 'standard':
                fmt = '2D'
            dp = bl.daypart or '*'
            key = f"{bl.theater_name}|{bl.ticket_type}|{fmt}|{dp}"
            existing = baseline_cache_nf.get(key)
            if not existing or (bl.sample_count or 0) > (existing.sample_count or 0):
                baseline_cache_nf[key] = bl

        def find_baseline_nf(theater: str, ticket_type: str, fmt: str, daypart: Optional[str] = None) -> Optional[PriceBaseline]:
            """Find best matching baseline with wildcard fallback."""
            fmt_norm = fmt or '*'
            if fmt_norm.lower() == 'standard':
                fmt_norm = '2D'
            dp = daypart or '*'
            for key in [
                f"{theater}|{ticket_type}|{fmt_norm}|{dp}",
                f"{theater}|{ticket_type}|{fmt_norm}|*",
                f"{theater}|{ticket_type}|*|{dp}",
                f"{theater}|{ticket_type}|*|*",
            ]:
                if key in baseline_cache_nf:
                    return baseline_cache_nf[key]
            return None

        # Load company profiles for discount day awareness
        profiles = session.query(CompanyProfile).filter(
            CompanyProfile.company_id == company_id
        ).all()

        discount_day_lookup = {}
        for profile in profiles:
            if profile.has_discount_days and profile.discount_days:
                try:
                    discount_days = json.loads(profile.discount_days) if isinstance(profile.discount_days, str) else profile.discount_days
                    if discount_days:
                        discount_day_lookup[profile.circuit_name] = {}
                        for dd in discount_days:
                            dow = dd.get('day_of_week')
                            price = dd.get('price')
                            if dow is not None and price is not None:
                                discount_day_lookup[profile.circuit_name][dow] = float(price)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Query for recently added prices
        query = session.query(
            EntTelligencePriceCache.theater_name,
            EntTelligencePriceCache.circuit_name,
            EntTelligencePriceCache.film_title,
            EntTelligencePriceCache.play_date,
            EntTelligencePriceCache.ticket_type,
            EntTelligencePriceCache.format,
            EntTelligencePriceCache.price,
            EntTelligencePriceCache.created_at,
            EntTelligencePriceCache.is_presale
        ).filter(
            EntTelligencePriceCache.company_id == company_id,
            EntTelligencePriceCache.created_at >= lookback_cutoff,
            EntTelligencePriceCache.price > 0
        )

        if circuit:
            query = query.filter(EntTelligencePriceCache.circuit_name.ilike(f"%{circuit}%"))

        results = query.all()
        total_new_prices = len(results)

        # Batch-lookup theater states for per-theater tax rate resolution
        theater_names_in_results = list(set(row[0] for row in results))
        theater_states = bulk_get_theater_states(company_id, theater_names_in_results)

        for row in results:
            theater_name, circuit_name, film_title, play_date_val, ticket_type, format_type, price, created_at, is_presale = row
            films_checked.add(film_title)

            # Normalize ticket type and find matching baseline
            norm_ticket = _normalize_tt_nf(ticket_type) or ticket_type
            baseline = find_baseline_nf(theater_name, norm_ticket, format_type)
            if not baseline:
                for equiv_tt in get_equivalent_ticket_types(norm_ticket)[1:]:
                    baseline = find_baseline_nf(theater_name, equiv_tt, format_type)
                    if baseline:
                        break

            if not baseline:
                continue

            # Check discount day
            day_of_week = play_date_val.weekday()
            if circuit_name in discount_day_lookup:
                if day_of_week in discount_day_lookup[circuit_name]:
                    discount_price = discount_day_lookup[circuit_name][day_of_week]
                    if float(price) <= discount_price * 1.05:
                        continue  # Skip discount day pricing

            # Tax-aware price comparison (same logic as advance scanner)
            baseline_price = float(baseline.baseline_price)
            if hasattr(baseline, 'tax_status') and baseline.tax_status == 'exclusive':
                current_price = float(price)
            else:
                ent_tax_rate = get_tax_rate_for_theater(
                    tax_config, theater_states.get(theater_name), theater_name=theater_name
                )
                current_price = apply_estimated_tax(float(price), ent_tax_rate)

            if baseline_price <= 0:
                continue

            surge_amount = current_price - baseline_price
            surge_pct = (surge_amount / baseline_price) * 100

            # Check thresholds
            is_surge = False
            if surge_threshold > 0 and surge_pct >= surge_threshold:
                is_surge = True
            if min_surge_amount > 0 and surge_amount >= min_surge_amount:
                is_surge = True

            if is_surge:
                surges.append(NewFilmSurge(
                    film_title=film_title,
                    theater_name=theater_name,
                    circuit_name=circuit_name,
                    play_date=play_date_val,
                    ticket_type=ticket_type,
                    format=format_type,
                    current_price=round(current_price, 2),
                    baseline_price=round(baseline_price, 2),
                    surge_percent=round(surge_pct, 1),
                    first_seen=created_at,
                    is_presale=is_presale or False
                ))

        # Sort by surge percent descending
        surges.sort(key=lambda x: x.surge_percent, reverse=True)

        return NewFilmSurgeResponse(
            check_time=check_time,
            lookback_hours=lookback_hours,
            total_new_prices=total_new_prices,
            surges_found=len(surges),
            films_checked=sorted(films_checked),
            surges=surges[:100]  # Limit to 100 results
        )


# ============================================================================
# BASELINE BROWSER - Browse baselines by market and location
# ============================================================================

class MarketSummary(BaseModel):
    """Summary of a market with baseline counts."""
    market: str
    theater_count: int
    circuit_count: int
    baseline_count: int


class TheaterSummary(BaseModel):
    """Summary of a theater with baseline counts."""
    theater_name: str
    circuit_name: Optional[str] = None
    baseline_count: int
    formats: List[str] = []
    ticket_types: List[str] = []


class CircuitSummary(BaseModel):
    """Summary of a circuit within a market."""
    circuit_name: str
    theater_count: int
    baseline_count: int
    theaters: List[TheaterSummary] = []


class MarketDetail(BaseModel):
    """Detailed view of a market with circuits and theaters."""
    market: str
    total_theaters: int
    total_baselines: int
    circuits: List[CircuitSummary]


class TheaterBaseline(BaseModel):
    """A single baseline for a theater."""
    baseline_id: Optional[int] = None
    ticket_type: str
    format: Optional[str] = None
    baseline_price: float
    day_type: Optional[str] = None
    day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    daypart: Optional[str] = None
    sample_count: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    updated_at: Optional[datetime] = None


class TheaterBaselinesResponse(BaseModel):
    """All baselines for a specific theater."""
    theater_name: str
    circuit_name: Optional[str] = None
    market: Optional[str] = None
    total_baselines: int
    baselines: List[TheaterBaseline]


@router.get("/baselines/markets", response_model=List[MarketSummary], tags=["Baseline Browser"])
async def list_baseline_markets(
    current_user: dict = Depends(require_read_admin)
):
    """
    List all markets with baseline data.

    Returns a summary of each market including theater count, circuit count,
    and total baseline count. Markets are derived from TheaterMetadata (dma first,
    then market fallback) joined with PriceBaseline data.
    """
    try:
        from app.db_models import TheaterMetadata, PriceBaseline
        from sqlalchemy import func, distinct, case

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        with get_session() as session:
            # Get baselines joined with theater metadata for market and circuit info
            # Left join so we can include theaters without metadata (as "Unknown Market")
            # Priority: dma (EntTelligence) > market (Marcus) > 'Unknown Market'
            subquery = session.query(
                func.coalesce(TheaterMetadata.dma, TheaterMetadata.market, 'Unknown Market').label('market'),
                PriceBaseline.theater_name,
                func.coalesce(TheaterMetadata.circuit_name, 'Unknown').label('circuit_name'),
                func.count(PriceBaseline.baseline_id).label('baseline_count')
            ).outerjoin(
                TheaterMetadata,
                (PriceBaseline.theater_name == TheaterMetadata.theater_name) &
                (PriceBaseline.company_id == TheaterMetadata.company_id)
            ).filter(
                PriceBaseline.company_id == company_id,
                PriceBaseline.effective_to == None
            ).group_by(
                func.coalesce(TheaterMetadata.dma, TheaterMetadata.market, 'Unknown Market'),
                PriceBaseline.theater_name,
                func.coalesce(TheaterMetadata.circuit_name, 'Unknown')
            ).subquery()

            # Aggregate by market
            results = session.query(
                subquery.c.market,
                func.count(distinct(subquery.c.theater_name)).label('theater_count'),
                func.count(distinct(subquery.c.circuit_name)).label('circuit_count'),
                func.sum(subquery.c.baseline_count).label('baseline_count')
            ).group_by(
                subquery.c.market
            ).order_by(
                func.sum(subquery.c.baseline_count).desc()
            ).all()

            markets = [
                MarketSummary(
                    market=row.market or 'Unknown Market',
                    theater_count=row.theater_count,
                    circuit_count=row.circuit_count,
                    baseline_count=int(row.baseline_count or 0)
                )
                for row in results
            ]

            return markets

    except Exception as e:
        logger.exception(f"Error listing baseline markets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/baselines/market-detail", response_model=MarketDetail, tags=["Baseline Browser"])
async def get_market_baselines(
    market_name: str = Query(..., description="Market name to get details for (e.g. 'Dallas/Ft. Worth')"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Get detailed baseline information for a specific market.

    Returns all circuits and theaters in the market with their baseline counts.
    Use 'Unknown Market' to get theaters without market metadata.

    Note: Uses query parameter instead of path parameter to handle market names with slashes.
    Markets are matched against COALESCE(dma, market) to support both EntTelligence DMAs
    and Marcus-specific markets.
    """
    try:
        from app.db_models import TheaterMetadata, PriceBaseline
        from sqlalchemy import func, distinct, or_

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        with get_session() as session:
            # Query baselines with their formats and ticket types
            # Get circuit_name from TheaterMetadata since PriceBaseline doesn't have it
            if market_name == 'Unknown Market':
                # Theaters not in TheaterMetadata or with no dma/market
                base_query = session.query(
                    PriceBaseline.theater_name,
                    func.coalesce(TheaterMetadata.circuit_name, 'Unknown').label('circuit_name'),
                    PriceBaseline.format,
                    PriceBaseline.ticket_type,
                    func.count(PriceBaseline.baseline_id).label('baseline_count')
                ).outerjoin(
                    TheaterMetadata,
                    (PriceBaseline.theater_name == TheaterMetadata.theater_name) &
                    (PriceBaseline.company_id == TheaterMetadata.company_id)
                ).filter(
                    PriceBaseline.company_id == company_id,
                    PriceBaseline.effective_to == None,
                    or_(
                        TheaterMetadata.metadata_id == None,  # No metadata
                        (TheaterMetadata.dma == None) & (TheaterMetadata.market == None)  # Has metadata but no market/dma
                    )
                )
            else:
                # Match against dma first, then market
                # This handles both EntTelligence DMAs and Marcus markets
                base_query = session.query(
                    PriceBaseline.theater_name,
                    func.coalesce(TheaterMetadata.circuit_name, 'Unknown').label('circuit_name'),
                    PriceBaseline.format,
                    PriceBaseline.ticket_type,
                    func.count(PriceBaseline.baseline_id).label('baseline_count')
                ).join(
                    TheaterMetadata,
                    (PriceBaseline.theater_name == TheaterMetadata.theater_name) &
                    (PriceBaseline.company_id == TheaterMetadata.company_id)
                ).filter(
                    PriceBaseline.company_id == company_id,
                    PriceBaseline.effective_to == None,
                    func.coalesce(TheaterMetadata.dma, TheaterMetadata.market) == market_name
                )

            results = base_query.group_by(
                PriceBaseline.theater_name,
                func.coalesce(TheaterMetadata.circuit_name, 'Unknown'),
                PriceBaseline.format,
                PriceBaseline.ticket_type
            ).all()

            # Organize by circuit -> theater
            circuits_dict = {}
            for row in results:
                circuit = row.circuit_name or 'Independent'
                theater = row.theater_name

                if circuit not in circuits_dict:
                    circuits_dict[circuit] = {
                        'theaters': {},
                        'baseline_count': 0
                    }

                if theater not in circuits_dict[circuit]['theaters']:
                    circuits_dict[circuit]['theaters'][theater] = {
                        'baseline_count': 0,
                        'formats': set(),
                        'ticket_types': set()
                    }

                circuits_dict[circuit]['theaters'][theater]['baseline_count'] += row.baseline_count
                circuits_dict[circuit]['baseline_count'] += row.baseline_count
                if row.format:
                    circuits_dict[circuit]['theaters'][theater]['formats'].add(row.format)
                if row.ticket_type:
                    circuits_dict[circuit]['theaters'][theater]['ticket_types'].add(row.ticket_type)

            # Build response
            circuits = []
            total_theaters = 0
            total_baselines = 0

            for circuit_name, circuit_data in sorted(circuits_dict.items(), key=lambda x: -x[1]['baseline_count']):
                theaters = [
                    TheaterSummary(
                        theater_name=theater_name,
                        circuit_name=circuit_name if circuit_name != 'Independent' else None,
                        baseline_count=theater_data['baseline_count'],
                        formats=sorted(theater_data['formats']),
                        ticket_types=sorted(theater_data['ticket_types'])
                    )
                    for theater_name, theater_data in sorted(
                        circuit_data['theaters'].items(),
                        key=lambda x: -x[1]['baseline_count']
                    )
                ]

                circuits.append(CircuitSummary(
                    circuit_name=circuit_name,
                    theater_count=len(theaters),
                    baseline_count=circuit_data['baseline_count'],
                    theaters=theaters
                ))

                total_theaters += len(theaters)
                total_baselines += circuit_data['baseline_count']

            return MarketDetail(
                market=market_name,
                total_theaters=total_theaters,
                total_baselines=total_baselines,
                circuits=circuits
            )

    except Exception as e:
        logger.exception(f"Error getting market baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/baselines/theaters/{theater_name}", response_model=TheaterBaselinesResponse, tags=["Baseline Browser"])
async def get_theater_baselines(
    theater_name: str,
    current_user: dict = Depends(require_read_admin)
):
    """
    Get all baselines for a specific theater.

    Returns detailed baseline information including ticket types, formats,
    day types, dayparts, and pricing statistics.
    """
    try:
        from app.db_models import TheaterMetadata, PriceBaseline
        from urllib.parse import unquote

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        theater_name = unquote(theater_name)

        with get_session() as session:
            # Get baselines for this theater
            baselines_query = session.query(PriceBaseline).filter(
                PriceBaseline.company_id == company_id,
                PriceBaseline.theater_name == theater_name,
                PriceBaseline.effective_to == None
            ).order_by(
                PriceBaseline.ticket_type,
                PriceBaseline.format,
                PriceBaseline.day_of_week,
                PriceBaseline.daypart
            ).all()

            if not baselines_query:
                raise HTTPException(status_code=404, detail=f"No baselines found for theater: {theater_name}")

            # Get circuit and market info from TheaterMetadata
            # Priority: dma (EntTelligence) > market (Marcus)
            circuit_name = None
            market = None
            metadata = session.query(TheaterMetadata).filter(
                TheaterMetadata.company_id == company_id,
                TheaterMetadata.theater_name == theater_name
            ).first()
            if metadata:
                circuit_name = metadata.circuit_name
                market = metadata.dma or metadata.market

            baselines = [
                TheaterBaseline(
                    baseline_id=b.baseline_id,
                    ticket_type=b.ticket_type,
                    format=b.format,
                    baseline_price=float(b.baseline_price),
                    day_type=b.day_type,
                    day_of_week=b.day_of_week,
                    daypart=b.daypart,
                    sample_count=None,  # PriceBaseline doesn't have this field
                    min_price=None,  # PriceBaseline doesn't have this field
                    max_price=None,  # PriceBaseline doesn't have this field
                    updated_at=None  # PriceBaseline doesn't have this field
                )
                for b in baselines_query
            ]

            return TheaterBaselinesResponse(
                theater_name=theater_name,
                circuit_name=circuit_name,
                market=market,
                total_baselines=len(baselines),
                baselines=baselines
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting theater baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# COVERAGE GAPS ENDPOINTS
# ============================================================================

class GapInfoResponse(BaseModel):
    """Information about a specific coverage gap."""
    gap_type: str  # 'missing_day', 'missing_format', 'low_samples', 'no_data'
    severity: str  # 'warning', 'error'
    description: str
    details: Dict = {}


class BaselineInfoResponse(BaseModel):
    """Information about a healthy baseline."""
    format: str
    ticket_type: str
    day_of_week: int
    day_name: str
    sample_count: int
    avg_price: float
    variance_pct: float


class CoverageReportResponse(BaseModel):
    """Complete coverage report for a theater."""
    theater_name: str
    circuit_name: Optional[str] = None

    # Data summary
    total_samples: int
    unique_ticket_types: List[str]
    unique_formats: List[str]
    days_with_data: List[int]
    date_range_start: Optional[date] = None
    date_range_end: Optional[date] = None

    # Gaps found
    gaps: List[GapInfoResponse]
    gap_count: int

    # Coverage scores
    day_coverage_pct: float
    format_coverage_pct: float
    overall_coverage_score: float

    # Healthy baselines
    healthy_baselines: List[BaselineInfoResponse]
    healthy_count: int


class TheaterCoverageSummary(BaseModel):
    """Summary coverage info for a theater."""
    theater_name: str
    circuit_name: Optional[str] = None
    total_samples: int
    gap_count: int
    healthy_count: int
    coverage_score: float
    day_coverage_pct: float
    days_missing: List[str]
    formats: List[str]
    ticket_types: List[str]


class CoverageListResponse(BaseModel):
    """Response for list of theater coverage summaries."""
    total: int
    theaters: List[TheaterCoverageSummary]


@router.get("/baselines/coverage-gaps/{theater_name}", response_model=CoverageReportResponse, tags=["Coverage Gaps"])
async def get_theater_coverage_gaps(
    theater_name: str,
    lookback_days: int = Query(90, ge=7, le=365, description="Days of history to analyze"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Analyze coverage gaps for a specific theater.

    Returns detailed analysis of what price data is missing:
    - Missing days of the week (no data for Saturday, Sunday, etc.)
    - Low sample counts (less than 10 samples for a baseline)
    - Missing premium formats (expected based on circuit profile)

    Also shows healthy baselines that have sufficient data.
    """
    try:
        from app.coverage_gaps_service import CoverageGapsService
        from urllib.parse import unquote

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        theater_name = unquote(theater_name)

        service = CoverageGapsService(company_id)
        report = service.analyze_theater(theater_name, lookback_days)

        return CoverageReportResponse(
            theater_name=report.theater_name,
            circuit_name=report.circuit_name,
            total_samples=report.total_samples,
            unique_ticket_types=report.unique_ticket_types,
            unique_formats=report.unique_formats,
            days_with_data=report.days_with_data,
            date_range_start=report.date_range_start,
            date_range_end=report.date_range_end,
            gaps=[GapInfoResponse(
                gap_type=g.gap_type,
                severity=g.severity,
                description=g.description,
                details=g.details
            ) for g in report.gaps],
            gap_count=len(report.gaps),
            day_coverage_pct=report.day_coverage_pct,
            format_coverage_pct=report.format_coverage_pct,
            overall_coverage_score=report.overall_coverage_score,
            healthy_baselines=[BaselineInfoResponse(**b) for b in report.healthy_baselines],
            healthy_count=len(report.healthy_baselines)
        )

    except Exception as e:
        logger.exception(f"Error analyzing coverage gaps for {theater_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/baselines/coverage-gaps", response_model=CoverageListResponse, tags=["Coverage Gaps"])
async def list_theater_coverage(
    lookback_days: int = Query(90, ge=7, le=365, description="Days of history to analyze"),
    min_samples: int = Query(1, ge=1, description="Minimum samples to include theater"),
    circuit: Optional[str] = Query(None, description="Filter by circuit name prefix"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Get coverage summary for all theaters.

    Returns a list of theaters with their coverage scores and gap counts.
    Use this to identify which theaters need more data collection.
    """
    try:
        from app.coverage_gaps_service import CoverageGapsService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        service = CoverageGapsService(company_id)
        all_coverage = service.get_all_theater_coverage(lookback_days, min_samples)

        # Filter by circuit if specified
        if circuit:
            all_coverage = [t for t in all_coverage if t.get('circuit_name', '').startswith(circuit)]

        theaters = [
            TheaterCoverageSummary(
                theater_name=t['theater_name'],
                circuit_name=t['circuit_name'],
                total_samples=t['total_samples'],
                gap_count=t['gap_count'],
                healthy_count=t['healthy_count'],
                coverage_score=t['coverage_score'],
                day_coverage_pct=t['day_coverage_pct'],
                days_missing=t['days_missing'],
                formats=t['formats'],
                ticket_types=t['ticket_types']
            )
            for t in all_coverage
        ]

        return CoverageListResponse(
            total=len(theaters),
            theaters=theaters
        )

    except Exception as e:
        logger.exception(f"Error listing theater coverage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/baselines/coverage-hierarchy", tags=["Coverage Gaps"])
async def get_coverage_hierarchy(
    lookback_days: int = Query(90, ge=7, le=365, description="Days of history to analyze"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Get coverage organized by markets.json hierarchy.

    Returns a nested structure: company -> director -> market -> theaters
    with aggregated coverage scores at each level.
    """
    try:
        from app.coverage_gaps_service import CoverageGapsService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        service = CoverageGapsService(company_id)
        hierarchy = service.get_markets_hierarchy_coverage(lookback_days)

        return hierarchy

    except Exception as e:
        logger.exception(f"Error getting coverage hierarchy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/baselines/coverage-market/{director_name}/{market_name}", tags=["Coverage Gaps"])
async def get_market_coverage(
    director_name: str,
    market_name: str,
    lookback_days: int = Query(90, ge=7, le=365, description="Days of history to analyze"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Get detailed coverage for a specific market.

    Returns theater-level coverage details for all theaters in the market.
    """
    try:
        from app.coverage_gaps_service import CoverageGapsService
        from urllib.parse import unquote

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        director_name = unquote(director_name)
        market_name = unquote(market_name)

        service = CoverageGapsService(company_id)
        result = service.get_market_coverage(director_name, market_name, lookback_days)

        if 'error' in result:
            raise HTTPException(status_code=404, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting market coverage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BASELINE GAP FILLING
# ============================================================================

class ProposedGapFillResponse(BaseModel):
    """A proposed baseline to fill a coverage gap."""
    theater_name: str
    ticket_type: str
    format: str
    daypart: Optional[str] = None
    day_type: Optional[str] = None
    proposed_price: float
    source: str  # 'enttelligence' or 'circuit_average'
    sample_count: int
    confidence: float  # 0-1
    gap_type: str
    gap_description: str


class GapFillProposalsResponse(BaseModel):
    """Response for gap fill proposal analysis."""
    theater_name: str
    total_gaps: int
    proposals: List[ProposedGapFillResponse]
    fillable_count: int  # proposals with confidence >= threshold
    unfillable_gaps: int  # gaps with no data available


class GapFillApplyRequest(BaseModel):
    """Request to apply gap fill proposals."""
    min_confidence: float = Field(0.7, ge=0.0, le=1.0, description="Only apply proposals at or above this confidence")


class GapFillApplyResponse(BaseModel):
    """Response after applying gap fills."""
    baselines_created: int
    baselines_skipped: int
    theater_name: str


@router.get("/baselines/gap-fill/{theater_name}", response_model=GapFillProposalsResponse, tags=["Coverage Gaps"])
async def propose_gap_fills(
    theater_name: str,
    lookback_days: int = Query(90, ge=7, le=365, description="Days of history to analyze"),
    min_samples: int = Query(3, ge=1, le=50, description="Minimum samples required for proposal"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Analyze coverage gaps and propose baselines from available data.

    Returns proposals from two data sources:
    1. **EntTelligence cache** — prices from the EntTelligence API (higher confidence)
    2. **Circuit average** — averages from other theaters in the same circuit (lower confidence, capped at 0.5)

    Proposals include confidence scores (0-1) to help prioritize which fills to apply.
    Use the apply endpoint to save selected proposals as baselines.
    """
    try:
        from app.baseline_gap_filler import BaselineGapFillerService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        service = BaselineGapFillerService(company_id)
        proposals = service.analyze_and_propose(theater_name, lookback_days, min_samples)

        # Count gaps from coverage report
        report = service.coverage_service.analyze_theater(theater_name, lookback_days)
        total_gaps = len(report.gaps)
        fillable = sum(1 for p in proposals if p.confidence >= 0.7)
        unfillable = total_gaps - len(proposals)

        return GapFillProposalsResponse(
            theater_name=theater_name,
            total_gaps=total_gaps,
            proposals=[
                ProposedGapFillResponse(
                    theater_name=p.theater_name,
                    ticket_type=p.ticket_type,
                    format=p.format,
                    daypart=p.daypart,
                    day_type=p.day_type,
                    proposed_price=p.proposed_price,
                    source=p.source,
                    sample_count=p.sample_count,
                    confidence=p.confidence,
                    gap_type=p.gap_type,
                    gap_description=p.gap_description,
                )
                for p in proposals
            ],
            fillable_count=fillable,
            unfillable_gaps=max(0, unfillable),
        )

    except Exception as e:
        logger.exception(f"Error proposing gap fills for {theater_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/baselines/gap-fill/{theater_name}/apply", response_model=GapFillApplyResponse, tags=["Coverage Gaps"])
async def apply_gap_fills(
    theater_name: str,
    request: GapFillApplyRequest = None,
    lookback_days: int = Query(90, ge=7, le=365, description="Days of history to analyze"),
    min_samples: int = Query(3, ge=1, le=50, description="Minimum samples required"),
    current_user: dict = Depends(require_operator)
):
    """
    Apply gap fill proposals as new baselines for a theater.

    Re-analyzes gaps and applies proposals that meet the confidence threshold.
    Creates PriceBaseline records with source='gap_fill_enttelligence' or
    'gap_fill_circuit_average'.
    """
    try:
        from app.baseline_gap_filler import BaselineGapFillerService

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
        min_confidence = request.min_confidence if request else 0.7
        user_id = current_user.get("user_id")

        service = BaselineGapFillerService(company_id)
        proposals = service.analyze_and_propose(theater_name, lookback_days, min_samples)
        created, skipped = service.apply_fills(proposals, min_confidence, user_id)

        audit_service.data_event(
            event_type="apply_gap_fills",
            user_id=user_id,
            username=current_user.get("username"),
            company_id=company_id,
            details={
                "theater_name": theater_name,
                "baselines_created": created,
                "baselines_skipped": skipped,
                "min_confidence": min_confidence,
            }
        )

        return GapFillApplyResponse(
            baselines_created=created,
            baselines_skipped=skipped,
            theater_name=theater_name,
        )

    except Exception as e:
        logger.exception(f"Error applying gap fills for {theater_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BASELINE MAINTENANCE
# ============================================================================

@router.post("/baselines/deduplicate", tags=["Baseline Maintenance"])
async def deduplicate_baselines(
    dry_run: bool = Query(True, description="If true, only report duplicates without deleting"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Deduplicate price baselines by keeping only the most recent entry
    for each unique combination of (company_id, theater_name, ticket_type,
    format, day_of_week, daypart, day_type).

    **How it works:**
    - Groups baselines by all key fields (including nullable fields)
    - Keeps the baseline with the highest baseline_id (most recent)
    - Deletes older duplicates

    **Usage:**
    1. Run with dry_run=true (default) to see what would be deleted
    2. Review the results
    3. Run with dry_run=false to actually delete duplicates

    **Note:** Only affects active baselines (effective_to IS NULL)
    """
    try:
        from sqlalchemy import text
        from app.db_session import get_session

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        with get_session() as db:
            # First, count current baselines
            count_result = db.execute(text("""
                SELECT COUNT(*) as total FROM price_baselines
                WHERE company_id = :company_id AND effective_to IS NULL
            """), {"company_id": company_id})
            total_before = count_result.fetchone()[0]

            # Find duplicates - group by all key fields and find groups with more than one entry
            # Use COALESCE to handle NULL values in grouping
            duplicate_query = text("""
                SELECT
                    theater_name,
                    ticket_type,
                    COALESCE(format, '') as format_key,
                    COALESCE(day_of_week, -1) as dow_key,
                    COALESCE(daypart, '') as daypart_key,
                    COALESCE(day_type, '') as daytype_key,
                    COUNT(*) as count,
                    GROUP_CONCAT(baseline_id) as baseline_ids,
                    MAX(baseline_id) as keep_id
                FROM price_baselines
                WHERE company_id = :company_id AND effective_to IS NULL
                GROUP BY
                    theater_name,
                    ticket_type,
                    COALESCE(format, ''),
                    COALESCE(day_of_week, -1),
                    COALESCE(daypart, ''),
                    COALESCE(day_type, '')
                HAVING COUNT(*) > 1
                ORDER BY count DESC
            """)

            dup_result = db.execute(duplicate_query, {"company_id": company_id})
            duplicates = dup_result.fetchall()

            total_duplicate_groups = len(duplicates)
            total_to_delete = sum(row[6] - 1 for row in duplicates)  # count - 1 per group

            # Sample of what would be deleted
            sample_duplicates = []
            for row in duplicates[:10]:  # Show first 10 groups
                sample_duplicates.append({
                    "theater_name": row[0],
                    "ticket_type": row[1],
                    "format": row[2] if row[2] else None,
                    "day_of_week": row[3] if row[3] != -1 else None,
                    "daypart": row[4] if row[4] else None,
                    "day_type": row[5] if row[5] else None,
                    "duplicate_count": row[6],
                    "baseline_ids": row[7],
                    "keeping_id": row[8]
                })

            if dry_run:
                return {
                    "dry_run": True,
                    "total_baselines": total_before,
                    "duplicate_groups": total_duplicate_groups,
                    "to_delete": total_to_delete,
                    "would_remain": total_before - total_to_delete,
                    "sample_duplicates": sample_duplicates,
                    "message": f"Would delete {total_to_delete} duplicate baselines. Run with dry_run=false to execute."
                }

            # Actually delete duplicates - keep only the highest baseline_id per group
            delete_query = text("""
                DELETE FROM price_baselines
                WHERE company_id = :company_id
                AND effective_to IS NULL
                AND baseline_id NOT IN (
                    SELECT MAX(baseline_id)
                    FROM price_baselines
                    WHERE company_id = :company_id AND effective_to IS NULL
                    GROUP BY
                        theater_name,
                        ticket_type,
                        COALESCE(format, ''),
                        COALESCE(day_of_week, -1),
                        COALESCE(daypart, ''),
                        COALESCE(day_type, '')
                )
            """)

            db.execute(delete_query, {"company_id": company_id})
            db.commit()

            # Count after
            count_result = db.execute(text("""
                SELECT COUNT(*) as total FROM price_baselines
                WHERE company_id = :company_id AND effective_to IS NULL
            """), {"company_id": company_id})
            total_after = count_result.fetchone()[0]

            deleted_count = total_before - total_after

            # Audit log
            audit_service.data_event(
                event_type="baselines_deduplicated",
                username=current_user.get("username", "unknown"),
                details={
                    "before": total_before,
                    "after": total_after,
                    "deleted": deleted_count
                }
            )

            return {
                "dry_run": False,
                "success": True,
                "before": total_before,
                "after": total_after,
                "deleted": deleted_count,
                "message": f"Successfully deleted {deleted_count} duplicate baselines"
            }

    except Exception as e:
        logger.exception(f"Error deduplicating baselines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENTTELLIGENCE VS FANDANGO COMPARISON
# ============================================================================

class PriceComparisonItem(BaseModel):
    """Single price comparison between EntTelligence and Fandango baseline."""
    theater_name: str
    ticket_type: str
    format: Optional[str] = None
    daypart: Optional[str] = None
    day_of_week: Optional[int] = None
    enttelligence_price: float
    fandango_baseline: float
    difference: float
    difference_percent: float
    ent_sample_count: int
    fandango_sample_count: Optional[int] = None
    # Tax adjustment fields (populated when apply_tax=true)
    ent_price_tax_adjusted: Optional[float] = None
    tax_rate_applied: Optional[float] = None
    adjusted_difference: Optional[float] = None
    adjusted_difference_percent: Optional[float] = None


class PriceComparisonResponse(BaseModel):
    """Response for EntTelligence vs Fandango comparison."""
    total_comparisons: int
    avg_difference: float
    avg_difference_percent: float
    ent_higher_count: int
    fandango_higher_count: int
    exact_match_count: int
    likely_tax_exclusive_count: int  # EntTelligence prices ~8-10% lower
    comparisons: List[PriceComparisonItem]
    summary: Dict[str, Any]
    # Tax adjustment metadata
    tax_adjustment_applied: bool = False
    default_tax_rate: Optional[float] = None


@router.get("/baselines/compare-sources", response_model=PriceComparisonResponse, tags=["Baseline Analysis"])
async def compare_enttelligence_vs_fandango(
    theater_filter: Optional[str] = Query(None, description="Filter by theater name (partial match)"),
    min_samples: int = Query(3, ge=1, description="Minimum EntTelligence samples to include"),
    limit: int = Query(200, ge=1, le=1000, description="Max comparisons to return"),
    apply_tax: bool = Query(True, description="Apply estimated tax to EntTelligence prices (default: on for tax-inclusive display)"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Compare EntTelligence prices against Fandango baselines.

    This helps understand:
    - Are EntTelligence prices tax-inclusive or exclusive?
    - How accurate is EntTelligence pricing vs actual Fandango prices?
    - What's the typical difference between the two sources?

    **Tax Detection:**
    If EntTelligence prices are consistently 7-10% lower than Fandango,
    they're likely tax-exclusive. Fandango shows customer-facing (tax-inclusive) prices.

    **Tax Adjustment:**
    When `apply_tax=true`, estimated state/local tax is added to EntTelligence prices
    using the company's configured tax rates.

    **Returns:**
    - Per-theater/ticket/format comparisons
    - Overall statistics on price differences
    - Count of likely tax-exclusive entries
    """
    try:
        from sqlalchemy import text
        from app.db_session import get_session

        company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

        with get_session() as db:
            # Build query to compare EntTelligence aggregated prices vs Fandango baselines
            # EntTelligence: aggregate by theater, ticket_type, format
            # Fandango: use saved baselines

            theater_clause = ""
            params = {"company_id": company_id, "min_samples": min_samples, "limit": limit}
            if theater_filter:
                theater_clause = "AND e.theater_name LIKE :theater_filter"
                params["theater_filter"] = f"%{theater_filter}%"

            query = text(f"""
                WITH ent_prices AS (
                    SELECT
                        theater_name,
                        ticket_type,
                        COALESCE(format, '2D') as format,
                        AVG(price) as avg_price,
                        COUNT(*) as sample_count
                    FROM enttelligence_price_cache
                    WHERE company_id = :company_id
                        AND price IS NOT NULL
                        AND price > 0
                    GROUP BY theater_name, ticket_type, COALESCE(format, '2D')
                    HAVING COUNT(*) >= :min_samples
                )
                SELECT
                    e.theater_name,
                    e.ticket_type,
                    e.format,
                    b.daypart,
                    b.day_of_week,
                    e.avg_price as ent_price,
                    b.baseline_price as fandango_price,
                    e.sample_count as ent_samples,
                    b.sample_count as fandango_samples
                FROM ent_prices e
                INNER JOIN price_baselines b ON
                    e.theater_name = b.theater_name
                    AND (e.ticket_type = b.ticket_type
                         OR (e.ticket_type = 'Adult' AND b.ticket_type = 'General Admission')
                         OR (e.ticket_type = 'General Admission' AND b.ticket_type = 'Adult'))
                    AND (COALESCE(e.format, '2D') = COALESCE(b.format, '2D')
                         OR (COALESCE(e.format, '2D') = '2D' AND COALESCE(b.format, '2D') = 'Standard')
                         OR (COALESCE(e.format, '2D') = 'Standard' AND COALESCE(b.format, '2D') = '2D'))
                WHERE b.company_id = :company_id
                    AND b.effective_to IS NULL
                    {theater_clause}
                ORDER BY e.theater_name, e.ticket_type, e.format
                LIMIT :limit
            """)

            result = db.execute(query, params)
            rows = result.fetchall()

            # Load tax config if tax adjustment requested
            tax_config = None
            theater_states = {}
            if apply_tax:
                from api.services.tax_estimation import (
                    get_tax_config as _get_tax_config,
                    get_tax_rate_for_theater,
                    apply_estimated_tax,
                    bulk_get_theater_states,
                )
                tax_config = _get_tax_config(company_id)
                # Batch-lookup states for all theaters in results
                theater_names = list(set(row[0] for row in rows))
                theater_states = bulk_get_theater_states(company_id, theater_names)

            comparisons = []
            total_diff = 0
            total_diff_pct = 0
            ent_higher = 0
            fandango_higher = 0
            exact_match = 0
            likely_tax_exclusive = 0

            for row in rows:
                ent_price = float(row[5])
                fandango_price = float(row[6])
                diff = ent_price - fandango_price
                diff_pct = (diff / fandango_price * 100) if fandango_price > 0 else 0

                # Tax adjustment
                ent_adjusted = None
                tax_rate = None
                adj_diff = None
                adj_diff_pct = None
                if apply_tax and tax_config and tax_config.get("enabled"):
                    theater_state = theater_states.get(row[0])
                    tax_rate = get_tax_rate_for_theater(tax_config, theater_state, theater_name=row[0])
                    ent_adjusted = apply_estimated_tax(ent_price, tax_rate)
                    adj_diff = round(ent_adjusted - fandango_price, 2)
                    adj_diff_pct = round((adj_diff / fandango_price * 100) if fandango_price > 0 else 0, 1)

                comparisons.append(PriceComparisonItem(
                    theater_name=row[0],
                    ticket_type=row[1],
                    format=row[2],
                    daypart=row[3],
                    day_of_week=row[4],
                    enttelligence_price=round(ent_price, 2),
                    fandango_baseline=round(fandango_price, 2),
                    difference=round(diff, 2),
                    difference_percent=round(diff_pct, 1),
                    ent_sample_count=row[7],
                    fandango_sample_count=row[8],
                    ent_price_tax_adjusted=ent_adjusted,
                    tax_rate_applied=tax_rate,
                    adjusted_difference=adj_diff,
                    adjusted_difference_percent=adj_diff_pct,
                ))

                total_diff += diff
                total_diff_pct += diff_pct

                if abs(diff) < 0.05:
                    exact_match += 1
                elif diff > 0:
                    ent_higher += 1
                else:
                    fandango_higher += 1

                # Tax detection: if EntTelligence is 6-12% lower, likely tax-exclusive
                if -12 <= diff_pct <= -6:
                    likely_tax_exclusive += 1

            count = len(comparisons)
            avg_diff = total_diff / count if count > 0 else 0
            avg_diff_pct = total_diff_pct / count if count > 0 else 0

            # Summary statistics
            summary = {
                "interpretation": "",
                "tax_inclusive_likelihood": "unknown"
            }

            if count > 10:
                if avg_diff_pct < -6:
                    summary["interpretation"] = f"EntTelligence prices are on average {abs(avg_diff_pct):.1f}% LOWER than Fandango. This suggests EntTelligence may be showing TAX-EXCLUSIVE prices."
                    summary["tax_inclusive_likelihood"] = "likely_tax_exclusive"
                elif avg_diff_pct > 2:
                    summary["interpretation"] = f"EntTelligence prices are on average {avg_diff_pct:.1f}% HIGHER than Fandango. This is unusual - may indicate stale data or different pricing tiers."
                    summary["tax_inclusive_likelihood"] = "likely_tax_inclusive_but_different"
                else:
                    summary["interpretation"] = f"EntTelligence and Fandango prices are closely aligned (avg diff: {avg_diff_pct:.1f}%). EntTelligence appears to be TAX-INCLUSIVE."
                    summary["tax_inclusive_likelihood"] = "likely_tax_inclusive"

            return PriceComparisonResponse(
                total_comparisons=count,
                avg_difference=round(avg_diff, 2),
                avg_difference_percent=round(avg_diff_pct, 1),
                ent_higher_count=ent_higher,
                fandango_higher_count=fandango_higher,
                exact_match_count=exact_match,
                likely_tax_exclusive_count=likely_tax_exclusive,
                comparisons=comparisons,
                summary=summary,
                tax_adjustment_applied=apply_tax and bool(tax_config and tax_config.get("enabled")),
                default_tax_rate=tax_config.get("default_rate") if tax_config else None,
            )

    except Exception as e:
        logger.exception(f"Error comparing price sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))
