"""
Job management endpoints: trigger, status, cancel, list, collision check.

Endpoints:
    GET    /scrapes/active-theaters          - List theaters currently being scraped
    POST   /scrapes/check-collision          - Check if scrape would conflict
    GET    /scrapes/jobs                     - List recent scrape jobs
    POST   /scrapes/jobs/{job_id}/cancel     - Cancel a running scrape job
    POST   /scrapes/trigger                  - Trigger a full scrape job
    GET    /scrapes/{job_id}/status          - Get scrape job status
    POST   /scrapes/{job_id}/cancel          - Cancel a scrape by job ID
"""

from fastapi import APIRouter, Security, HTTPException, Depends
from api.routers.auth import get_current_user, User, require_operator
from api.telemetry import track_event
from app.audit_service import audit_service
from app import config
import logging
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

from ._shared import (
    _scrape_jobs, _job_counter,
    _check_theater_collision, _get_active_theater_urls,
    _launch_in_thread,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Pydantic models
# ============================================================================

class TheaterRequest(BaseModel):
    name: str
    url: str


class TriggerScrapeRequest(BaseModel):
    mode: str  # 'market', 'compsnipe', or 'lineup'
    market: Optional[str] = None
    theaters: List[TheaterRequest]
    dates: List[str]  # YYYY-MM-DD format
    selected_showtimes: Optional[List[str]] = None  # List of "date|theater|film|time" keys
    # Cache options for hybrid scrape
    use_cache: bool = False  # Use EntTelligence cache when fresh
    cache_max_age_hours: int = 24  # Staleness threshold for cached data


class TriggerScrapeResponse(BaseModel):
    job_id: int
    status: str
    message: str


class ScrapeStatusResponse(BaseModel):
    job_id: int
    status: str  # 'pending', 'running', 'completed', 'failed', 'cancelled'
    progress: int
    theaters_completed: int
    theaters_total: int
    showings_completed: Optional[int] = 0
    showings_total: Optional[int] = 0
    current_theater: Optional[str] = None
    current_showing: Optional[str] = None
    duration_seconds: Optional[float] = None
    results: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    # Cache statistics
    use_cache: Optional[bool] = False
    cache_hits: Optional[int] = 0
    cache_misses: Optional[int] = 0


class ActiveTheaterItem(BaseModel):
    """A theater currently being scraped."""
    url: str
    job_id: int


class ActiveTheatersResponse(BaseModel):
    """Response for active theaters query."""
    active_theater_count: int
    theaters: List[ActiveTheaterItem]


class CollisionCheckResponse(BaseModel):
    """Response for collision check - fields are optional when no collision."""
    has_collision: bool
    conflicting_theaters: Optional[List[str]] = None
    conflicting_job_ids: Optional[List[int]] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/scrapes/active-theaters", tags=["Scrapes"], response_model=ActiveTheatersResponse)
async def get_active_theaters(current_user: User = Security(get_current_user, scopes=["read:scrapes"])):
    """
    Get list of theaters currently being scraped.

    Use this endpoint to check if specific theaters are already being scraped
    before starting a new scrape job. Returns theater URLs mapped to their job IDs.
    """
    active = _get_active_theater_urls()
    return {
        "active_theater_count": len(active),
        "theaters": [
            {"url": url, "job_id": job_id}
            for url, job_id in active.items()
        ]
    }


@router.post("/scrapes/check-collision", tags=["Scrapes"], response_model=CollisionCheckResponse)
async def check_theater_collision(
    theaters: List[TheaterRequest],
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Check if any theaters would conflict with active scrape jobs.

    Use this before triggering a scrape to warn users about potential conflicts.
    """
    theater_dicts = [{"name": t.name, "url": t.url} for t in theaters]
    collision = _check_theater_collision(theater_dicts)

    if collision:
        return {
            "has_collision": True,
            "conflicting_theaters": [t["name"] for t in collision["conflicting_theaters"]],
            "conflicting_job_ids": collision["job_ids"]
        }

    return {"has_collision": False}


@router.get("/scrapes/jobs", tags=["Scrapes"])
async def list_scrape_jobs(
    all_users: bool = False,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """List scrape jobs. By default only shows current user's jobs.

    Args:
        all_users: If True and user is admin, show all users' jobs
    """
    current_username = current_user.get("username")
    is_admin = current_user.get("role") == "admin"

    jobs = []
    for job_id, job_info in _scrape_jobs.items():
        # Filter by user unless admin requesting all
        job_username = job_info.get("username")
        if not (all_users and is_admin):
            if job_username and job_username != current_username:
                continue  # Skip jobs from other users

        job_summary = job_info.copy()
        job_summary['job_id'] = job_id  # Include job_id in response
        # Always strip results — they may contain datetime.date objects
        # that can't be JSON-serialized in raw dict responses.
        # Use the /scrapes/{job_id}/status endpoint for full results.
        if 'results' in job_summary:
            if job_summary['results']:
                job_summary['result_count'] = len(job_summary['results'])
            del job_summary['results']
        jobs.append(job_summary)

    # Sort by job_id descending
    jobs.sort(key=lambda x: x.get('job_id', 0), reverse=True)
    return jobs


@router.post("/scrapes/jobs/{job_id}/cancel", tags=["Scrapes"])
async def cancel_scrape_job(job_id: int, current_user: User = Security(get_current_user, scopes=["write:scrapes"])):
    """Cancel a running scrape job."""
    if job_id not in _scrape_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _scrape_jobs[job_id]
    if job.get('status') in ['running', 'pending']:
        job['status'] = 'cancelled'
        job['message'] = "Job cancelled by user"
        return {"message": "Job cancelled"}

    return {"message": f"Job already in state: {job.get('status')}"}


@router.post("/scrapes/trigger", response_model=TriggerScrapeResponse, tags=["Scrapes"])
async def trigger_scrape(
    request: TriggerScrapeRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Trigger a new scrape job for specified theaters and dates.

    The scrape runs in the background and can be monitored via the status endpoint.

    **Theater Collision Prevention**: If any requested theaters are already being
    scraped by another job, this endpoint returns a 409 Conflict error with details
    about the conflicting theaters and job IDs.
    """
    from . import _shared as shared

    # Check for theater collisions with active jobs
    theater_dicts = [{"name": t.name, "url": t.url} for t in request.theaters]
    collision = _check_theater_collision(theater_dicts)

    if collision:
        conflicting_names = [t["name"] for t in collision["conflicting_theaters"]]
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Cannot start scrape: {len(conflicting_names)} theater(s) are already being scraped",
                "conflicting_theaters": conflicting_names,
                "conflicting_job_ids": collision["job_ids"],
                "suggestion": "Wait for the existing scrape to complete, or cancel it first"
            }
        )

    shared._job_counter += 1
    job_id = shared._job_counter

    # Initialize job state (including theaters for collision detection)
    _scrape_jobs[job_id] = {
        "status": "pending",
        "progress": 0,
        "theaters_completed": 0,
        "theaters_total": len(request.theaters),
        "theaters": theater_dicts,  # Store for collision detection
        "showings_completed": 0,
        "showings_total": len(request.selected_showtimes) if request.selected_showtimes else 0,
        "current_theater": None,
        "current_showing": None,
        "started_at": datetime.now().isoformat(),
        "results": [],
        "error": None,
        "username": current_user.get("username"),  # Track who started this job
    }

    # If Celery is enabled, use it for distributed processing
    if config.USE_CELERY:
        from app.tasks.scrapes import run_scrape_task
        task = run_scrape_task.delay(
            mode=request.mode,
            market=request.market,
            theaters=[t.model_dump() for t in request.theaters],
            dates=request.dates,
            company_id=current_user.get("company_id") or 1,
            use_cache=request.use_cache
        )
        # Store Celery task ID in our job tracker
        _scrape_jobs[job_id]["celery_task_id"] = task.id
        _scrape_jobs[job_id]["status"] = "distributed"
    else:
        from .execution import run_scrape_job
        # Launch scrape in a separate thread so the API stays responsive
        _launch_in_thread(
            run_scrape_job,
            job_id,
            request.mode,
            request.market,
            [t.model_dump() for t in request.theaters],
            request.dates,
            request.selected_showtimes,
            request.use_cache,
            request.cache_max_age_hours
        )

    track_event("PriceScout.ScrapeJob.Started", {
        "JobId": str(job_id),
        "Mode": request.mode,
        "TheaterCount": len(request.theaters),
        "DateCount": len(request.dates),
        "UseCache": request.use_cache
    })

    # Audit scrape trigger
    audit_service.data_event(
        event_type="trigger_scrape",
        user_id=current_user.get("user_id"),
        username=current_user.get("username"),
        company_id=current_user.get("company_id") or 1,
        details={
            "job_id": job_id,
            "mode": request.mode,
            "theater_count": len(request.theaters),
            "date_count": len(request.dates),
            "use_cache": request.use_cache
        }
    )

    return TriggerScrapeResponse(
        job_id=job_id,
        status="pending",
        message=f"Scrape job started for {len(request.theaters)} theaters"
    )


@router.get("/scrapes/{job_id}/status", response_model=ScrapeStatusResponse, tags=["Scrapes"])
async def get_scrape_status(
    job_id: int,
    current_user: User = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Get the status of a scrape job.

    Poll this endpoint to track progress of a running scrape.
    """
    if job_id not in _scrape_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = _scrape_jobs[job_id].copy()

    # If it's a Celery task, check the async result
    if "celery_task_id" in job and config.USE_CELERY:
        try:
            from celery.result import AsyncResult
            from app.celery_app import app as celery_app

            res = AsyncResult(job["celery_task_id"], app=celery_app)

            if res.state == 'SUCCESS':
                result = res.result
                job["status"] = "completed"
                job["progress"] = 100
                job["records_found"] = result.get('records', 0)
                job["completed_at"] = datetime.now().isoformat()
                job["duration_seconds"] = result.get('duration_seconds')
            elif res.state == 'FAILURE':
                job["status"] = "failed"
                job["error"] = str(res.result)
            elif res.state == 'PROGRESS':
                job["status"] = "running"
                info = res.info or {}
                job["progress"] = info.get('progress', 0)
                job["current_theater"] = info.get('current_theater')
        except Exception as e:
            logger.error(f"Error checking Celery task status: {e}")

    return ScrapeStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        theaters_completed=job.get("theaters_completed", 0),
        theaters_total=job.get("theaters_total", 0),
        showings_completed=job.get("showings_completed", 0),
        showings_total=job.get("showings_total", 0),
        current_theater=job.get("current_theater"),
        current_showing=job.get("current_showing"),
        duration_seconds=job.get("duration_seconds"),
        results=job.get("results") if job["status"] == "completed" else None,
        error=job.get("error"),
        use_cache=job.get("use_cache", False),
        cache_hits=job.get("cache_hits", 0),
        cache_misses=job.get("cache_misses", 0)
    )


@router.post("/scrapes/{job_id}/cancel", tags=["Scrapes"])
async def cancel_scrape(
    job_id: int,
    current_user: User = Security(get_current_user, scopes=["write:scrapes"])
):
    """
    Cancel a running scrape job.
    """
    if job_id not in _scrape_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = _scrape_jobs[job_id]

    if job["status"] not in ["pending", "running"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job['status']}'"
        )

    job["status"] = "cancelled"

    # Audit scrape cancellation
    audit_service.data_event(
        event_type="cancel_scrape",
        user_id=current_user.get("user_id"),
        username=current_user.get("username"),
        company_id=current_user.get("company_id") or 1,
        details={"job_id": job_id}
    )

    return {"message": f"Job {job_id} cancelled"}
