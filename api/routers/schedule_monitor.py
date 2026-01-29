"""
Schedule Monitor API Router

Endpoints for monitoring and detecting schedule changes at theaters.

Endpoints:
    GET    /api/v1/schedule-alerts              - List schedule alerts
    GET    /api/v1/schedule-alerts/summary      - Get alert summary statistics
    GET    /api/v1/schedule-alerts/{id}         - Get specific alert
    PUT    /api/v1/schedule-alerts/{id}/acknowledge - Acknowledge an alert
    POST   /api/v1/schedule-monitor/check       - Trigger manual schedule check
    GET    /api/v1/schedule-monitor/status      - Get monitoring status
    GET    /api/v1/schedule-monitor/config      - Get monitoring configuration
    PUT    /api/v1/schedule-monitor/config      - Update monitoring configuration
    POST   /api/v1/schedule-baselines/snapshot  - Create baseline snapshot
"""

from datetime import datetime, date, UTC
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Security, Query, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from api.routers.auth import get_current_user, User, require_operator, require_auditor, require_read_admin
from app.audit_service import audit_service
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ScheduleAlertResponse(BaseModel):
    """Model for a schedule alert."""
    alert_id: int
    theater_name: str
    film_title: Optional[str] = None
    play_date: Optional[str] = None
    alert_type: str  # new_film, new_showtime, removed_showtime, removed_film, format_added
    old_value: Optional[Dict] = None
    new_value: Optional[Dict] = None
    change_details: Optional[str] = None
    triggered_at: datetime
    is_acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    acknowledgment_notes: Optional[str] = None


class AlertListResponse(BaseModel):
    """Response model for alert list."""
    total: int
    pending: int
    alerts: List[ScheduleAlertResponse]


class AlertSummaryResponse(BaseModel):
    """Summary statistics for schedule alerts."""
    total_pending: int
    total_acknowledged: int
    by_type: Dict[str, int]
    by_theater: Dict[str, int]
    oldest_pending: Optional[str] = None
    newest_pending: Optional[str] = None


class AcknowledgeRequest(BaseModel):
    """Request model for acknowledging an alert."""
    notes: Optional[str] = Field(None, max_length=1000, description="Optional notes")


class AcknowledgeResponse(BaseModel):
    """Response model for acknowledgment."""
    alert_id: int
    acknowledged: bool = True
    acknowledged_at: datetime


class MonitorConfigResponse(BaseModel):
    """Schedule monitor configuration."""
    is_enabled: bool = True
    check_frequency_hours: Optional[int] = 6
    alert_on_new_film: bool = True
    alert_on_new_showtime: bool = True
    alert_on_removed_showtime: bool = True
    alert_on_removed_film: bool = True
    alert_on_format_added: bool = True
    alert_on_time_changed: bool = False
    alert_on_new_schedule: bool = True
    alert_on_event: bool = True
    alert_on_presale: bool = True
    theaters_filter: Optional[List[str]] = []
    films_filter: Optional[List[str]] = []
    circuits_filter: Optional[List[str]] = []
    days_ahead: Optional[int] = 14
    notification_enabled: bool = True
    webhook_url: Optional[str] = None
    notification_email: Optional[str] = None
    last_check_at: Optional[str] = None
    last_check_status: Optional[str] = None
    last_check_alerts_count: Optional[int] = 0


class MonitorConfigUpdate(BaseModel):
    """Request model for updating configuration."""
    is_enabled: Optional[bool] = None
    check_frequency_hours: Optional[int] = None
    alert_on_new_film: Optional[bool] = None
    alert_on_new_showtime: Optional[bool] = None
    alert_on_removed_showtime: Optional[bool] = None
    alert_on_removed_film: Optional[bool] = None
    alert_on_format_added: Optional[bool] = None
    alert_on_time_changed: Optional[bool] = None
    alert_on_new_schedule: Optional[bool] = None
    alert_on_event: Optional[bool] = None
    alert_on_presale: Optional[bool] = None
    theaters_filter: Optional[List[str]] = None
    films_filter: Optional[List[str]] = None
    circuits_filter: Optional[List[str]] = None
    days_ahead: Optional[int] = None
    notification_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    notification_email: Optional[str] = None


class CheckRequest(BaseModel):
    """Request to trigger a schedule check."""
    theaters: Optional[List[str]] = Field(None, description="Filter to specific theaters")
    dates: Optional[List[str]] = Field(None, description="Filter to specific dates (YYYY-MM-DD)")
    background: bool = Field(False, description="Whether to run in background")


class CheckResponse(BaseModel):
    """Response from schedule check."""
    status: str
    theaters_checked: int
    alerts_created: int
    changes: List[Dict] = []
    error: Optional[str] = None
    message: Optional[str] = None


class BaselineSnapshotRequest(BaseModel):
    """Request to create baseline snapshots."""
    theaters: Optional[List[str]] = Field(None, description="Filter to specific theaters")
    dates: Optional[List[str]] = Field(None, description="Filter to specific dates (YYYY-MM-DD)")


class BaselineSnapshotResponse(BaseModel):
    """Response from baseline snapshot creation."""
    baselines_created: int
    theaters_processed: int
    films_processed: int


class MonitorStatusResponse(BaseModel):
    """Current monitoring status."""
    is_enabled: bool
    last_check_at: Optional[str] = None
    last_check_status: Optional[str] = None
    last_check_alerts_count: Optional[int] = 0
    pending_alerts: int = 0
    next_check_in_hours: Optional[float] = None


# ============================================================================
# SCHEDULE ALERTS ENDPOINTS
# ============================================================================

@router.get("/schedule-alerts", response_model=AlertListResponse, tags=["Schedule Monitor"])
async def list_schedule_alerts(
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledgment status"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    theater_name: Optional[str] = Query(None, description="Filter by theater (partial match)"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(require_read_admin)
):
    """
    List schedule alerts with optional filtering.
    Returns alerts ordered by triggered_at descending (most recent first).
    """
    try:
        from app.schedule_monitor_service import get_schedule_monitor_service

        company_id = current_user.get("company_id") or 1
        service = get_schedule_monitor_service(company_id)

        alerts_data = service.get_alerts(
            is_acknowledged=acknowledged,
            alert_type=alert_type,
            theater_name=theater_name,
            limit=limit,
            offset=offset
        )

        alerts = []
        for row in alerts_data:
            alerts.append(ScheduleAlertResponse(
                alert_id=row['alert_id'],
                theater_name=row['theater_name'],
                film_title=row.get('film_title'),
                play_date=row.get('play_date'),
                alert_type=row['alert_type'],
                old_value=row.get('old_value'),
                new_value=row.get('new_value'),
                change_details=row.get('change_details'),
                triggered_at=datetime.fromisoformat(row['triggered_at']) if isinstance(row['triggered_at'], str) else row['triggered_at'],
                is_acknowledged=bool(row.get('is_acknowledged', False)),
                acknowledged_by=None,  # Could join with users table if needed
                acknowledged_at=datetime.fromisoformat(row['acknowledged_at']) if row.get('acknowledged_at') and isinstance(row['acknowledged_at'], str) else row.get('acknowledged_at'),
                acknowledgment_notes=row.get('acknowledgment_notes')
            ))

        # Get summary for totals
        summary = service.get_alert_summary()

        return AlertListResponse(
            total=summary['total_pending'] + summary['total_acknowledged'],
            pending=summary['total_pending'],
            alerts=alerts
        )

    except Exception as e:
        logger.exception(f"Error listing schedule alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule-alerts/summary", response_model=AlertSummaryResponse, tags=["Schedule Monitor"])
async def get_schedule_alert_summary(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get summary statistics for schedule alerts.
    Returns counts by type, by theater, and date range info.
    """
    try:
        from app.schedule_monitor_service import get_schedule_monitor_service

        company_id = current_user.get("company_id") or 1
        service = get_schedule_monitor_service(company_id)
        summary = service.get_alert_summary()

        return AlertSummaryResponse(
            total_pending=summary['total_pending'],
            total_acknowledged=summary['total_acknowledged'],
            by_type=summary['by_type'],
            by_theater=summary['by_theater'],
            oldest_pending=summary['oldest_pending'],
            newest_pending=summary['newest_pending']
        )

    except Exception as e:
        logger.exception(f"Error getting schedule alert summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/schedule-alerts/{alert_id}/acknowledge", response_model=AcknowledgeResponse, tags=["Schedule Monitor"])
async def acknowledge_schedule_alert(
    alert_id: int,
    request: AcknowledgeRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Acknowledge a schedule alert.
    """
    try:
        from app.schedule_monitor_service import get_schedule_monitor_service

        company_id = current_user.get("company_id") or 1
        user_id = current_user.get("user_id") or 1
        service = get_schedule_monitor_service(company_id)

        success = service.acknowledge_alert(
            alert_id=alert_id,
            user_id=user_id,
            notes=request.notes
        )

        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")

        return AcknowledgeResponse(
            alert_id=alert_id,
            acknowledged=True,
            acknowledged_at=datetime.now(UTC)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error acknowledging schedule alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SCHEDULE MONITOR ENDPOINTS
# ============================================================================

@router.post("/schedule-monitor/check", response_model=CheckResponse, tags=["Schedule Monitor"])
async def trigger_schedule_check(
    request: CheckRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Trigger a manual schedule check.
    Compares current EntTelligence cache data against stored baselines.
    Requires admin role.
    """
    try:
        from app.schedule_monitor_service import get_schedule_monitor_service

        company_id = current_user.get("company_id") or 1
        service = get_schedule_monitor_service(company_id)

        if request.background:
            from app.tasks.alerts import run_schedule_monitor_task
            task = run_schedule_monitor_task.delay(
                company_id=company_id,
                theater_names=request.theaters,
                play_dates=request.dates
            )
            return CheckResponse(
                status="queued",
                theaters_checked=0,
                alerts_created=0,
                changes=[],
                message=f"Schedule check task {task.id} queued in background"
            )

        result = service.run_check(
            theater_names=request.theaters,
            play_dates=request.dates
        )

        return CheckResponse(
            status=result['status'],
            theaters_checked=result.get('theaters_checked', 0),
            alerts_created=result.get('alerts_created', 0),
            changes=result.get('changes', []),
            error=result.get('error')
        )

    except Exception as e:
        logger.exception(f"Error running schedule check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule-monitor/status", response_model=MonitorStatusResponse, tags=["Schedule Monitor"])
async def get_monitor_status(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get current schedule monitoring status.
    """
    try:
        from app.schedule_monitor_service import get_schedule_monitor_service

        company_id = current_user.get("company_id") or 1
        service = get_schedule_monitor_service(company_id)

        config = service.get_or_create_config()
        summary = service.get_alert_summary()

        # Calculate next check time
        next_check_hours = None
        if config.get('last_check_at') and config.get('is_enabled'):
            lc_str = config['last_check_at']
            last_check = datetime.fromisoformat(lc_str.replace('Z', '+00:00'))
            if last_check.tzinfo is None: last_check = last_check.replace(tzinfo=UTC)
            next_check = last_check + timedelta(hours=config.get('check_frequency_hours', 6))
            remaining = next_check - datetime.now(UTC)
            next_check_hours = max(0, remaining.total_seconds() / 3600)

        return MonitorStatusResponse(
            is_enabled=bool(config.get('is_enabled', True)),
            last_check_at=config.get('last_check_at'),
            last_check_status=config.get('last_check_status'),
            last_check_alerts_count=config.get('last_check_alerts_count', 0),
            pending_alerts=summary['total_pending'],
            next_check_in_hours=round(next_check_hours, 1) if next_check_hours is not None else None
        )

    except Exception as e:
        logger.exception(f"Error getting monitor status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule-monitor/config", response_model=MonitorConfigResponse, tags=["Schedule Monitor"])
async def get_monitor_config(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get schedule monitoring configuration.
    Requires admin role.
    """
    try:
        from app.schedule_monitor_service import get_schedule_monitor_service
        import json

        company_id = current_user.get("company_id") or 1
        service = get_schedule_monitor_service(company_id)
        config = service.get_or_create_config()

        # Parse JSON filter fields
        theaters_filter = config.get('theaters_filter', '[]')
        if isinstance(theaters_filter, str):
            theaters_filter = json.loads(theaters_filter) if theaters_filter else []

        films_filter = config.get('films_filter', '[]')
        if isinstance(films_filter, str):
            films_filter = json.loads(films_filter) if films_filter else []

        circuits_filter = config.get('circuits_filter', '[]')
        if isinstance(circuits_filter, str):
            circuits_filter = json.loads(circuits_filter) if circuits_filter else []

        return MonitorConfigResponse(
            is_enabled=bool(config.get('is_enabled', True)),
            check_frequency_hours=config.get('check_frequency_hours', 6),
            alert_on_new_film=bool(config.get('alert_on_new_film', True)),
            alert_on_new_showtime=bool(config.get('alert_on_new_showtime', True)),
            alert_on_removed_showtime=bool(config.get('alert_on_removed_showtime', True)),
            alert_on_removed_film=bool(config.get('alert_on_removed_film', True)),
            alert_on_format_added=bool(config.get('alert_on_format_added', True)),
            alert_on_time_changed=bool(config.get('alert_on_time_changed', False)),
            alert_on_new_schedule=bool(config.get('alert_on_new_schedule', True)),
            alert_on_event=bool(config.get('alert_on_event', True)),
            alert_on_presale=bool(config.get('alert_on_presale', True)),
            theaters_filter=theaters_filter,
            films_filter=films_filter,
            circuits_filter=circuits_filter,
            days_ahead=config.get('days_ahead', 14),
            notification_enabled=bool(config.get('notification_enabled', True)),
            webhook_url=config.get('webhook_url'),
            notification_email=config.get('notification_email'),
            last_check_at=config.get('last_check_at'),
            last_check_status=config.get('last_check_status'),
            last_check_alerts_count=config.get('last_check_alerts_count', 0)
        )

    except Exception as e:
        logger.exception(f"Error getting monitor config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/schedule-monitor/config", response_model=MonitorConfigResponse, tags=["Schedule Monitor"])
async def update_monitor_config(
    request: MonitorConfigUpdate,
    current_user: dict = Depends(require_operator)
):
    """
    Update schedule monitoring configuration.
    Requires admin role.
    """
    try:
        from app.schedule_monitor_service import get_schedule_monitor_service

        company_id = current_user.get("company_id") or 1
        service = get_schedule_monitor_service(company_id)

        # Build updates dict from request
        updates = request.model_dump(exclude_none=True)
        service.update_config(updates)

        # Audit configuration change
        audit_service.data_event(
            event_type="update_monitor_config",
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            company_id=company_id,
            details={"updates": list(updates.keys())}
        )

        # Return updated config
        return await get_monitor_config(current_user)

    except Exception as e:
        logger.exception(f"Error updating monitor config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BASELINE ENDPOINTS
# ============================================================================

@router.post("/schedule-baselines/snapshot", response_model=BaselineSnapshotResponse, tags=["Schedule Monitor"])
async def create_baseline_snapshot(
    request: BaselineSnapshotRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Create baseline snapshots from current EntTelligence cache data.
    This establishes the initial baseline before monitoring.
    Requires admin role.
    """
    try:
        from app.schedule_monitor_service import get_schedule_monitor_service

        company_id = current_user.get("company_id") or 1
        user_id = current_user.get("user_id")
        service = get_schedule_monitor_service(company_id)

        result = service.create_baselines_from_cache(
            theater_names=request.theaters,
            play_dates=request.dates,
            user_id=user_id
        )

        # Audit snapshot creation
        audit_service.data_event(
            event_type="create_baseline_snapshots",
            user_id=user_id,
            username=current_user.get("username"),
            company_id=company_id,
            details={
                "theaters_count": len(request.theaters or []),
                "dates_count": len(request.dates or []),
                "theaters": request.theaters[:5] if request.theaters else []
            }
        )

        return BaselineSnapshotResponse(
            baselines_created=result['baselines_created'],
            theaters_processed=result['theaters_processed'],
            films_processed=result['films_processed']
        )

    except Exception as e:
        logger.exception(f"Error creating baseline snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Import timedelta for status calculation
from datetime import timedelta


# ============================================================================
# SCHEDULE POSTING CHECK ENDPOINTS (Fandango-based)
# ============================================================================

class PostingCheckRequest(BaseModel):
    """Request to trigger a schedule posting check (Fandango-based)."""
    theaters: Optional[List[Dict[str, str]]] = Field(None, description="List of {name, url} dicts")
    dates: Optional[List[str]] = Field(None, description="Dates to check (YYYY-MM-DD)")
    max_theaters: int = Field(20, ge=1, le=100, description="Max theaters to check per run")
    circuit_filter: Optional[List[str]] = Field(None, description="Filter to these circuits (e.g., ['Marcus', 'AMC'])")


class PostingCheckResponse(BaseModel):
    """Response from schedule posting check."""
    status: str
    theaters_checked: int
    dates_checked: int
    checks_performed: int
    new_postings: int
    alerts_created: int
    duration_seconds: Optional[float] = None
    postings: List[Dict] = []
    errors: List[str] = []
    message: Optional[str] = None


class PostingSummaryResponse(BaseModel):
    """Summary of schedule posting status."""
    total_checks: int
    posted_count: int
    theaters: int
    dates: int
    by_date: Dict[str, Dict[str, int]]
    recent_postings: List[Dict]


@router.post("/schedule-posting/check", response_model=PostingCheckResponse, tags=["Schedule Posting Monitor"])
async def trigger_posting_check(
    request: PostingCheckRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_operator)
):
    """
    Trigger a schedule posting check via Fandango.

    This is a LIGHTWEIGHT check that only detects IF schedules exist,
    not the full pricing details. Use this to catch same-day schedule
    postings before the EntTelligence 2 AM refresh.

    Intended for:
    - Major schedule posting days (Fridays for new releases)
    - Monitoring if competitors have posted before Marcus
    - Quick checks on specific upcoming dates
    """
    try:
        from app.schedule_posting_monitor import get_schedule_posting_monitor

        company_id = current_user.get("company_id") or 1
        monitor = get_schedule_posting_monitor(company_id)

        # Run the check
        result = monitor.run_check(
            theaters=request.theaters,
            play_dates=request.dates,
            max_theaters=request.max_theaters,
            circuit_filter=request.circuit_filter
        )

        # Audit the check
        audit_service.data_event(
            event_type="posting_check_triggered",
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            company_id=company_id,
            details={
                "theaters_checked": result.get("theaters_checked", 0),
                "new_postings": result.get("new_postings", 0)
            }
        )

        return PostingCheckResponse(
            status=result.get("status", "completed"),
            theaters_checked=result.get("theaters_checked", 0),
            dates_checked=result.get("dates_checked", 0),
            checks_performed=result.get("checks_performed", 0),
            new_postings=result.get("new_postings", 0),
            alerts_created=result.get("alerts_created", 0),
            duration_seconds=result.get("duration_seconds"),
            postings=result.get("postings", []),
            errors=result.get("errors", [])
        )

    except Exception as e:
        logger.exception(f"Error running posting check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule-posting/summary", response_model=PostingSummaryResponse, tags=["Schedule Posting Monitor"])
async def get_posting_summary(
    days_ahead: int = Query(14, ge=1, le=30, description="Days ahead to include"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Get summary of schedule posting status.

    Shows which theaters have posted schedules for upcoming dates,
    and recent new posting detections.
    """
    try:
        from app.schedule_posting_monitor import get_schedule_posting_monitor

        company_id = current_user.get("company_id") or 1
        monitor = get_schedule_posting_monitor(company_id)

        summary = monitor.get_posting_summary(days_ahead=days_ahead)

        return PostingSummaryResponse(
            total_checks=summary.get("total_checks", 0),
            posted_count=summary.get("posted_count", 0),
            theaters=summary.get("theaters", 0),
            dates=summary.get("dates", 0),
            by_date=summary.get("by_date", {}),
            recent_postings=summary.get("recent_postings", [])
        )

    except Exception as e:
        logger.exception(f"Error getting posting summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule-posting/pending-dates", tags=["Schedule Posting Monitor"])
async def get_pending_dates(
    days_ahead: int = Query(14, ge=1, le=30, description="Days ahead to check"),
    current_user: dict = Depends(require_read_admin)
):
    """
    Get dates that need schedule posting checks.

    Returns dates within the window that don't have known schedules yet.
    """
    try:
        from app.schedule_posting_monitor import get_schedule_posting_monitor

        company_id = current_user.get("company_id") or 1
        monitor = get_schedule_posting_monitor(company_id)

        pending = monitor.get_pending_dates(days_ahead=days_ahead)

        return {
            "pending_dates": pending,
            "count": len(pending)
        }

    except Exception as e:
        logger.exception(f"Error getting pending dates: {e}")
        raise HTTPException(status_code=500, detail=str(e))
