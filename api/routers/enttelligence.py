"""
EntTelligence API Router
Endpoints for managing EntTelligence data sync and cache.
"""

from fastapi import APIRouter, HTTPException, Security, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta, UTC

from api.routers.auth import get_current_user, require_operator
from api.services.enttelligence_cache_service import get_cache_service, EntTelligenceCacheService
from app.audit_service import audit_service
from app import config


router = APIRouter(prefix="/enttelligence", tags=["EntTelligence"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SyncRequest(BaseModel):
    """Request to sync EntTelligence data"""
    start_date: str  # YYYY-MM-DD
    end_date: Optional[str] = None  # YYYY-MM-DD, defaults to start_date
    circuits: Optional[List[str]] = None  # Filter to specific circuits


class SyncResponse(BaseModel):
    """Response from sync operation"""
    status: str
    records_fetched: int
    records_cached: int
    circuits: List[str]
    errors: int
    message: str


class CacheStatsResponse(BaseModel):
    """Cache statistics response"""
    total_entries: int
    fresh_entries: int
    stale_entries: int
    by_circuit: dict
    last_fetch: Optional[str]
    cache_max_age_hours: int


class CacheLookupRequest(BaseModel):
    """Request to lookup cached prices"""
    showtime_keys: List[str]  # List of "date|theater|film|time" keys
    max_age_hours: Optional[int] = None


class CachedPriceResponse(BaseModel):
    """Single cached price entry"""
    theater_name: str
    film_title: str
    play_date: str
    showtime: str
    format: Optional[str]
    ticket_type: str
    price: float
    source: str
    fetched_at: str
    circuit_name: Optional[str]


class CacheLookupResponse(BaseModel):
    """Response from cache lookup"""
    results: dict  # showtime_key -> CachedPriceResponse or null
    cache_hits: int
    cache_misses: int


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/sync", response_model=SyncResponse)
async def sync_enttelligence_data(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_operator)
):
    """
    Sync pricing data from EntTelligence API.

    Requires admin role. Fetches showtime and pricing data for the specified
    date range and caches it locally for hybrid scrape optimization.

    This runs synchronously for now. For large date ranges, consider
    running as a background task.
    """
    try:
        cache_service = get_cache_service()

        # Get company_id from user (default to 1 if not set)
        company_id = 1  # Default company ID

        if config.USE_CELERY:
            from app.tasks.sync import sync_enttelligence_task
            task = sync_enttelligence_task.delay(
                company_id=company_id,
                start_date=request.start_date,
                end_date=request.end_date,
                circuits=request.circuits
            )
            return SyncResponse(
                status="pending",
                records_fetched=0,
                records_cached=0,
                circuits=request.circuits or [],
                errors=0,
                message=f"Sync task started successfully (Task ID: {task.id})"
            )

        result = cache_service.sync_prices_for_dates(
            company_id=company_id,
            start_date=request.start_date,
            end_date=request.end_date,
            circuits=request.circuits
        )

        # Audit sync completion
        audit_service.data_event(
            event_type="enttelligence_sync",
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            company_id=company_id,
            details={
                "start_date": request.start_date,
                "end_date": request.end_date,
                "records_fetched": result["records_fetched"],
                "records_cached": result["records_cached"],
                "errors": result["errors"]
            }
        )

        return SyncResponse(
            status=result["status"],
            records_fetched=result["records_fetched"],
            records_cached=result["records_cached"],
            circuits=result["circuits"],
            errors=result["errors"],
            message=f"Successfully cached {result['records_cached']} prices from EntTelligence"
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats(
    current_user: dict = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Get EntTelligence cache statistics.

    Returns information about cached entries, freshness, and circuit breakdown.
    """
    try:
        cache_service = get_cache_service()
        company_id = 1  # Default company ID (User model doesn't have company_id)

        stats = cache_service.get_cache_stats(company_id)

        return CacheStatsResponse(
            total_entries=stats["total_entries"],
            fresh_entries=stats["fresh_entries"],
            stale_entries=stats["stale_entries"],
            by_circuit=stats["by_circuit"],
            last_fetch=stats["last_fetch"],
            cache_max_age_hours=stats["cache_max_age_hours"]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/cache/lookup", response_model=CacheLookupResponse)
async def lookup_cached_prices(
    request: CacheLookupRequest,
    current_user: dict = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Look up cached prices for showtime keys.

    Used internally by the scrape trigger to check for cached EntTelligence
    prices before scraping Fandango.
    """
    try:
        cache_service = get_cache_service()
        company_id = 1  # Default company ID (User model doesn't have company_id)

        results = cache_service.lookup_cached_prices(
            showtime_keys=request.showtime_keys,
            company_id=company_id,
            max_age_hours=request.max_age_hours
        )

        # Convert to response format
        response_results = {}
        hits = 0
        misses = 0

        for key, cached in results.items():
            if cached:
                hits += 1
                response_results[key] = {
                    "theater_name": cached.theater_name,
                    "film_title": cached.film_title,
                    "play_date": cached.play_date,
                    "showtime": cached.showtime,
                    "format": cached.format,
                    "ticket_type": cached.ticket_type,
                    "price": cached.price,
                    "source": cached.source,
                    "fetched_at": cached.fetched_at.isoformat(),
                    "circuit_name": cached.circuit_name
                }
            else:
                misses += 1
                response_results[key] = None

        return CacheLookupResponse(
            results=response_results,
            cache_hits=hits,
            cache_misses=misses
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lookup failed: {str(e)}")


@router.post("/cache/cleanup")
async def cleanup_expired_cache(
    current_user: dict = Security(get_current_user, scopes=["admin"])
):
    """
    Remove expired entries from the cache.

    Requires admin role. Cleans up entries that have passed their expiration time.
    """
    try:
        cache_service = get_cache_service()
        company_id = 1  # Default company ID (User model doesn't have company_id)

        deleted = cache_service.cleanup_expired(company_id)

        # Audit cleanup
        audit_service.system_event(
            event_type="enttelligence_cache_cleanup",
            user_id=current_user.get("user_id"),
            username=current_user.get("username"),
            company_id=company_id,
            details={"entries_removed": deleted}
        )

        return {
            "status": "completed",
            "entries_removed": deleted
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@router.get("/status")
async def get_sync_status(
    current_user: dict = Security(get_current_user, scopes=["read:scrapes"])
):
    """
    Get current sync status and cache freshness.

    Returns whether cache is fresh enough for quick scrape mode.
    """
    try:
        cache_service = get_cache_service()
        company_id = 1  # Default company ID (User model doesn't have company_id)

        stats = cache_service.get_cache_stats(company_id)

        # Determine if cache is fresh enough
        is_fresh = stats["fresh_entries"] > 0

        # Calculate when data will expire
        if stats["last_fetch"]:
            lf_str = stats["last_fetch"]
            last_fetch = datetime.fromisoformat(lf_str.replace('Z', '+00:00'))
            if last_fetch.tzinfo is None: last_fetch = last_fetch.replace(tzinfo=UTC)
            expires_at = last_fetch + timedelta(hours=stats["cache_max_age_hours"])
            time_remaining = expires_at - datetime.now(UTC)
            hours_remaining = max(0, time_remaining.total_seconds() / 3600)
        else:
            hours_remaining = 0

        return {
            "is_fresh": is_fresh,
            "fresh_entries": stats["fresh_entries"],
            "total_entries": stats["total_entries"],
            "last_sync": stats["last_fetch"],
            "hours_until_stale": round(hours_remaining, 1),
            "quick_scrape_available": is_fresh
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")
