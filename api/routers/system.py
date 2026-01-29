"""
System API Router

Provides endpoints for system health, circuit breaker management, 
and background task status.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import os
import time
import sqlite3
from datetime import datetime, timezone

from api.routers.auth import require_admin, require_operator, require_read_admin
from app.audit_service import audit_service
from app.circuit_breaker import (
    fandango_breaker, 
    enttelligence_breaker, 
    get_all_circuit_status, 
    reset_all_circuits,
    CircuitState
)
from app import config
from app.retention_service import DEFAULT_RETENTION, get_retention_service
from app.tasks.system import data_retention_task

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class CircuitBreakerStatus(BaseModel):
    name: str
    state: str
    failures: int
    failure_threshold: int
    reset_timeout: int
    last_failure_time: Optional[float] = None
    last_state_change: float
    is_open: bool


class SystemHealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    timestamp: str
    circuits: Dict[str, CircuitBreakerStatus]
    features: Dict[str, bool]
    components: Dict[str, Any]


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/system/health", response_model=SystemHealthResponse, tags=["System"])
async def get_system_health(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get detailed system health and status.
    
    Requires admin/auditor access.
    """
    statuses = get_all_circuit_status()
    
    # Map raw statuses to Pydantic models
    circuits = {}
    for name, data in statuses.items():
        circuits[name] = CircuitBreakerStatus(
            name=name,
            state=data.get("state"),
            failures=data.get("failures"),
            failure_threshold=data.get("failure_threshold"),
            reset_timeout=data.get("reset_timeout"),
            last_failure_time=data.get("last_failure_time"),
            last_state_change=data.get("last_state_change"),
            is_open=data.get("state") == "open"
        )

    # -------------------------------------------------------------------------
    # COMPONENT HEALTH (Migrated from main.py)
    # -------------------------------------------------------------------------
    components = {}
    overall_status = "healthy"

    # 1. Database
    try:
        from app.db_session import get_session
        from sqlalchemy import text
        with get_session() as session:
            session.execute(text("SELECT 1"))
        components["database"] = {"status": "ok"}
    except Exception as e:
        components["database"] = {"status": "error", "message": str(e)}
        overall_status = "degraded"

    # 2. Fandango Scraper
    try:
        from app.cache_maintenance_service import CacheMaintenanceService
        service = CacheMaintenanceService()
        history = service.get_maintenance_history(limit=1)
        if history:
            last_run = history[0]
            val = last_run.get('health_check', {})
            fail_rate = val.get('failure_rate_percent', 0)
            c_status = "ok"
            if fail_rate >= 50: 
                c_status = "critical"
                overall_status = "unhealthy"
            elif fail_rate >= 20: 
                c_status = "degraded"
                overall_status = "degraded"
            components["fandango_scraper"] = {
                "status": c_status,
                "last_check": last_run.get('timestamp'),
                "failure_rate_percent": fail_rate,
                "theaters_checked": val.get('checked', 0),
                "theaters_failed": val.get('failed', 0)
            }
    except:
        components["fandango_scraper"] = {"status": "unknown"}

    # 3. EntTelligence Sync
    try:
        db_path = getattr(config, 'DB_FILE', None) or os.path.join(config.PROJECT_DIR, 'pricescout.db')
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT started_at, status, theaters_synced FROM enttelligence_sync_runs ORDER BY started_at DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    components["enttelligence"] = {
                        "status": "ok" if row[1] == 'success' else "degraded",
                        "last_sync": row[0],
                        "records_synced": row[2]
                    }
    except:
        components["enttelligence"] = {"status": "unknown"}

    if "enttelligence" not in components:
        components["enttelligence"] = {"status": "unknown"}

    if "fandango_scraper" not in components:
        components["fandango_scraper"] = {"status": "unknown"}
        
    if "scheduler" not in components:
        components["scheduler"] = {"status": "unknown"}

    # 4. Alerts
    try:
        db_path = getattr(config, 'DB_FILE', None) or os.path.join(config.PROJECT_DIR, 'pricescout.db')
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM price_alerts WHERE is_acknowledged = 0")
                p_pending = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM schedule_alerts WHERE is_acknowledged = 0")
                s_pending = cursor.fetchone()[0] or 0
                components["alerts"] = {
                    "status": "ok",
                    "price_pending": p_pending,
                    "schedule_pending": s_pending,
                    "total_pending": p_pending + s_pending
                }
    except:
        components["alerts"] = {"status": "unknown"}

    # 5. Scheduler
    try:
        log_path = os.path.join(config.PROJECT_DIR, 'scheduler.log')
        if os.path.exists(log_path):
            mtime = os.path.getmtime(log_path)
            age = (time.time() - mtime) / 60
            components["scheduler"] = {
                "status": "ok" if age < 10 else "degraded" if age < 60 else "stale",
                "age_minutes": round(age, 1)
            }
    except:
        components["scheduler"] = {"status": "unknown"}

    return SystemHealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version=config.APP_VERSION,
        environment=os.getenv("ENVIRONMENT", "development"),
        circuits=circuits,
        features={
            "celery": config.USE_CELERY,
            "redis": config.USE_REDIS_CACHE,
            "entra_id": config.ENTRA_ENABLED,
            "enttelligence": config.ENTTELLIGENCE_ENABLED
        },
        components=components
    )


@router.post("/system/circuits/reset", tags=["System"])
async def reset_circuit_breakers(
    current_user: dict = Depends(require_operator)
):
    """
    Force reset all circuit breakers to CLOSED state.
    
    Requires operator or higher access.
    """
    reset_all_circuits()
    
    audit_service.system_event(
        event_type="circuits_reset",
        severity="warning",
        user_id=current_user.get("user_id"),
        username=current_user.get("username"),
        details={"action": "manual_reset"}
    )
    
    return {"message": "All circuit breakers have been reset to CLOSED"}


@router.post("/system/circuits/{name}/reset", tags=["System"])
async def reset_specific_circuit(
    name: str,
    current_user: dict = Depends(require_operator)
):
    """
    Force reset a specific circuit breaker.
    
    Requires operator or higher access.
    """
    breaker = None
    if name == "fandango":
        breaker = fandango_breaker
    elif name == "enttelligence":
        breaker = enttelligence_breaker
    else:
        raise HTTPException(status_code=404, detail=f"Circuit breaker '{name}' not found")
        
    breaker.force_close()
    
    audit_service.system_event(
        event_type="circuit_reset",
        severity="warning",
        user_id=current_user.get("user_id"),
        username=current_user.get("username"),
        details={"circuit": name, "action": "manual_reset"}
    )
    
    return {"message": f"Circuit breaker '{name}' has been reset to CLOSED"}


@router.post("/system/circuits/{name}/open", tags=["System"])
async def force_open_circuit(
    name: str,
    current_user: dict = Depends(require_admin)
):
    """
    Force open a specific circuit breaker (Manual Trip).
    
    Requires admin access.
    """
    breaker = None
    if name == "fandango":
        breaker = fandango_breaker
    elif name == "enttelligence":
        breaker = enttelligence_breaker
    else:
        raise HTTPException(status_code=404, detail=f"Circuit breaker '{name}' not found")
        
    breaker.force_open()
    
    audit_service.system_event(
        event_type="circuit_trip_manual",
        severity="error",
        user_id=current_user.get("user_id"),
        username=current_user.get("username"),
        details={"circuit": name, "action": "manual_trip"}
    )
    
    return {"message": f"Circuit breaker '{name}' has been forced OPEN"}
@router.post("/system/maintenance/retention", tags=["System"])
async def run_data_retention(
    current_user: dict = Depends(require_admin)
):
    """
    Trigger immediate data retention cleanup.
    
    Requires admin access.
    """
    if config.USE_CELERY:
        task = data_retention_task.delay()
        return {"status": "triggered", "task_id": task.id}
    else:
        service = get_retention_service()
        results = service.cleanup_old_data()
        return {"status": "completed", "results": results}


@router.get("/system/maintenance/status", tags=["System"])
async def get_maintenance_status(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get information about data retention configuration and status.
    """
    return {
        "retention_policy": DEFAULT_RETENTION,
        "tasks": {
            "data_retention": {
                "schedule": "0 0 * * * (daily)",
                "description": "Purges historical data records based on retention policy."
            },
            "database_vacuum": {
                "schedule": "0 1 * * 0 (weekly)",
                "description": "Optimizes SQLite database file size."
            }
        }
    }


@router.get("/system/tasks/{task_id}", tags=["System"])
async def get_task_status(
    task_id: str,
    current_user: dict = Depends(require_read_admin)
):
    """
    Get the status of a Celery background task.
    """
    if not config.USE_CELERY:
        return {"status": "NOT_CONFIGURED", "message": "Celery is not enabled"}

    try:
        from celery.result import AsyncResult
        from app.celery_app import app as celery_app
        
        res = AsyncResult(task_id, app=celery_app)
        
        response = {
            "task_id": task_id,
            "status": res.status,
            "ready": res.ready(),
        }
        
        if res.ready():
            if res.successful():
                response["result"] = res.result
            else:
                response["error"] = str(res.result)
        elif res.status == 'PROGRESS':
            response["progress"] = res.info
            
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check task status: {str(e)}")
