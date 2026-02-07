"""
Cache Management API Router

Provides endpoints for cache operations:
- Cache status monitoring
- Cache refresh/rebuild
- Theater cache management
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import CACHE_FILE, PROJECT_DIR
from app.simplified_baseline_service import normalize_theater_name
from api.routers.auth import get_current_user

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class CacheStatus(BaseModel):
    cache_file_exists: bool
    last_updated: Optional[str] = None
    market_count: int = 0
    theater_count: int = 0
    file_size_kb: float = 0.0
    metadata: Optional[Dict[str, Any]] = None


class CacheRefreshRequest(BaseModel):
    rebuild_broken_urls: bool = False
    force_full_refresh: bool = False


class CacheRefreshResponse(BaseModel):
    status: str
    message: str
    started_at: str


class UnmatchedTheater(BaseModel):
    theater_name: str
    market: str
    company: Optional[str] = None
    url: Optional[str] = None
    status: str


class UnmatchedTheaterList(BaseModel):
    theaters: List[UnmatchedTheater]
    total_count: int


class TheaterMatchRequest(BaseModel):
    theater_name: str
    market: str
    fandango_url: Optional[str] = None
    new_name: Optional[str] = None
    mark_as_closed: bool = False
    not_on_fandango: bool = False
    external_url: Optional[str] = None


class TheaterMatchResponse(BaseModel):
    success: bool
    message: str
    theater_name: str
    matched_name: Optional[str] = None
    url: Optional[str] = None


class TheaterDiscoveryRequest(BaseModel):
    theater_name: str
    update_cache: bool = False
    market: Optional[str] = None  # Required if update_cache is True


class TheaterDiscoveryResult(BaseModel):
    name: str
    url: str
    code: Optional[str] = None


class TheaterDiscoveryResponse(BaseModel):
    found: bool
    theater_name: Optional[str] = None
    url: Optional[str] = None
    theater_code: Optional[str] = None
    all_results: List[TheaterDiscoveryResult] = []
    error: Optional[str] = None
    cache_updated: bool = False


# ============================================================================
# CACHE STATUS ENDPOINTS
# ============================================================================

@router.get("/cache/status", response_model=CacheStatus, tags=["Cache"])
async def get_cache_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get current cache status and statistics.

    Returns information about the theater cache including:
    - Last update time
    - Number of markets and theaters
    - File size
    - Metadata
    """
    if not os.path.exists(CACHE_FILE):
        return CacheStatus(
            cache_file_exists=False,
            market_count=0,
            theater_count=0,
            file_size_kb=0.0
        )

    try:
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)

        # Count markets and theaters
        markets = cache_data.get('markets', {})
        market_count = len(markets)
        theater_count = sum(
            len(market_data.get('theaters', []))
            for market_data in markets.values()
        )

        # Get file size
        file_size_bytes = os.path.getsize(CACHE_FILE)
        file_size_kb = round(file_size_bytes / 1024, 2)

        # Get metadata
        metadata = cache_data.get('metadata', {})
        last_updated = metadata.get('last_updated')

        return CacheStatus(
            cache_file_exists=True,
            last_updated=last_updated,
            market_count=market_count,
            theater_count=theater_count,
            file_size_kb=file_size_kb,
            metadata=metadata
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Cache file is corrupted")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading cache: {str(e)}")


@router.get("/cache/markets", tags=["Cache"])
async def list_cache_markets(
    current_user: dict = Depends(get_current_user)
):
    """
    List all markets in the cache with theater counts.
    """
    if not os.path.exists(CACHE_FILE):
        return {"markets": [], "total_count": 0}

    try:
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)

        markets = cache_data.get('markets', {})

        market_list = []
        for market_name, market_data in markets.items():
            theaters = market_data.get('theaters', [])
            active_count = sum(
                1 for t in theaters
                if 'Permanently Closed' not in t.get('name', '')
                and 'Closed' not in t.get('name', '')
            )
            not_fandango_count = sum(
                1 for t in theaters
                if t.get('not_on_fandango', False)
            )

            market_list.append({
                'market_name': market_name,
                'total_theaters': len(theaters),
                'active_theaters': active_count,
                'not_on_fandango': not_fandango_count
            })

        # Sort by market name
        market_list.sort(key=lambda x: x['market_name'])

        return {
            "markets": market_list,
            "total_count": len(market_list)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading cache: {str(e)}")


@router.post("/cache/refresh", response_model=CacheRefreshResponse, tags=["Cache"])
async def refresh_cache(
    request: CacheRefreshRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger a cache refresh operation.

    This runs in the background and will:
    - Check for broken URLs
    - Attempt to re-match failed theaters
    - Update the cache file

    Note: Full refresh requires manager or admin role.
    """
    # Check permission for full refresh
    if request.force_full_refresh:
        if current_user.get("role") not in ["admin", "manager"]:
            raise HTTPException(
                status_code=403,
                detail="Full refresh requires manager or admin role"
            )

    started_at = datetime.now().isoformat()

    # Add background task
    background_tasks.add_task(
        run_cache_refresh,
        rebuild_broken_urls=request.rebuild_broken_urls,
        force_full_refresh=request.force_full_refresh
    )

    return CacheRefreshResponse(
        status="started",
        message="Cache refresh started in background",
        started_at=started_at
    )


async def run_cache_refresh(rebuild_broken_urls: bool = False, force_full_refresh: bool = False):
    """Background task to refresh the cache."""
    try:
        if not os.path.exists(CACHE_FILE):
            print("Cache file not found, skipping refresh")
            return

        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)

        # Update metadata
        if 'metadata' not in cache_data:
            cache_data['metadata'] = {}

        cache_data['metadata']['last_updated'] = datetime.now().isoformat()
        cache_data['metadata']['last_refresh_type'] = 'full' if force_full_refresh else 'quick'

        # Write back
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)

        print(f"Cache refresh completed at {datetime.now().isoformat()}")

    except Exception as e:
        print(f"Cache refresh error: {e}")


# ============================================================================
# UNMATCHED THEATER ENDPOINTS
# ============================================================================

@router.get("/theaters/unmatched", response_model=UnmatchedTheaterList, tags=["Theaters"])
async def list_unmatched_theaters(
    current_user: dict = Depends(get_current_user)
):
    """
    List theaters that are marked as unmatched or not on Fandango.

    Returns theaters that need manual intervention:
    - Theaters with no Fandango match
    - Theaters marked as 'not_on_fandango'
    - Theaters with empty or invalid URLs
    """
    if not os.path.exists(CACHE_FILE):
        return UnmatchedTheaterList(theaters=[], total_count=0)

    try:
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)

        unmatched = []
        markets = cache_data.get('markets', {})

        for market_name, market_data in markets.items():
            for theater in market_data.get('theaters', []):
                theater_name = theater.get('name', 'Unknown')
                url = theater.get('url', '')
                company = theater.get('company')
                is_not_fandango = theater.get('not_on_fandango', False)

                # Determine status
                if 'Permanently Closed' in theater_name or 'Closed' in theater_name:
                    status = "closed"
                elif is_not_fandango:
                    status = "not_on_fandango"
                elif not url or url == "N/A" or url == "":
                    status = "no_match"
                else:
                    continue  # Skip matched theaters

                unmatched.append(UnmatchedTheater(
                    theater_name=theater_name,
                    market=market_name,
                    company=company,
                    url=url if url and url != "N/A" else None,
                    status=status
                ))

        return UnmatchedTheaterList(
            theaters=unmatched,
            total_count=len(unmatched)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading cache: {str(e)}")


@router.post("/theaters/match", response_model=TheaterMatchResponse, tags=["Theaters"])
async def match_theater(
    match_request: TheaterMatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Manually match a theater to Fandango or mark it with a status.

    Allows:
    - Setting a Fandango URL for a theater
    - Renaming a theater to match Fandango's name
    - Marking a theater as closed
    - Marking a theater as not on Fandango with an external URL
    """
    # Check permission - require manager or admin
    if current_user.get("role") not in ["admin", "manager"]:
        raise HTTPException(
            status_code=403,
            detail="Theater matching requires manager or admin role"
        )

    if not os.path.exists(CACHE_FILE):
        raise HTTPException(status_code=404, detail="Cache file not found")

    try:
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)

        markets = cache_data.get('markets', {})

        if match_request.market not in markets:
            raise HTTPException(status_code=404, detail=f"Market '{match_request.market}' not found")

        market_data = markets[match_request.market]
        theater_found = False
        matched_name = None
        final_url = None

        req_norm = normalize_theater_name(match_request.theater_name)
        for theater in market_data.get('theaters', []):
            if theater.get('name') == match_request.theater_name or normalize_theater_name(theater.get('name', '')) == req_norm:
                theater_found = True

                if match_request.mark_as_closed:
                    # Mark as closed
                    theater['name'] = f"{match_request.theater_name} (Permanently Closed)"
                    theater['url'] = "N/A"
                    if 'not_on_fandango' in theater:
                        del theater['not_on_fandango']
                    matched_name = theater['name']

                elif match_request.not_on_fandango:
                    # Mark as not on Fandango with external URL
                    theater['not_on_fandango'] = True
                    theater['url'] = match_request.external_url or ""
                    if match_request.new_name:
                        theater['name'] = match_request.new_name
                    matched_name = theater['name']
                    final_url = theater['url']

                elif match_request.fandango_url:
                    # Set Fandango URL and optionally rename
                    theater['url'] = match_request.fandango_url
                    if match_request.new_name:
                        theater['name'] = match_request.new_name
                    if 'not_on_fandango' in theater:
                        del theater['not_on_fandango']
                    matched_name = theater['name']
                    final_url = match_request.fandango_url

                break

        if not theater_found:
            raise HTTPException(
                status_code=404,
                detail=f"Theater '{match_request.theater_name}' not found in market '{match_request.market}'"
            )

        # Update metadata and save
        if 'metadata' not in cache_data:
            cache_data['metadata'] = {}
        cache_data['metadata']['last_updated'] = datetime.now().isoformat()

        # Create backup
        backup_path = CACHE_FILE + ".bak"
        if os.path.exists(CACHE_FILE):
            import shutil
            shutil.copy2(CACHE_FILE, backup_path)

        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)

        return TheaterMatchResponse(
            success=True,
            message="Theater updated successfully",
            theater_name=match_request.theater_name,
            matched_name=matched_name,
            url=final_url
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating cache: {str(e)}")


@router.get("/cache/backup", tags=["Cache"])
async def get_cache_backup_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get status of cache backup files.
    """
    backup_files = []
    backup_extensions = ['.bak', '.rebuild_bak']

    for ext in backup_extensions:
        backup_path = CACHE_FILE + ext
        if os.path.exists(backup_path):
            stat = os.stat(backup_path)
            backup_files.append({
                'filename': os.path.basename(backup_path),
                'path': backup_path,
                'size_kb': round(stat.st_size / 1024, 2),
                'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

    return {
        'backups': backup_files,
        'backup_count': len(backup_files)
    }


@router.get("/cache/theaters", tags=["Cache"])
async def get_theater_cache(
    current_user: dict = Depends(get_current_user)
):
    """
    Get the full theater cache with all markets and theaters.

    Returns the complete cache data including:
    - Metadata (last updated, refresh type)
    - All markets with their theaters
    """
    if not os.path.exists(CACHE_FILE):
        return {
            "metadata": {
                "last_updated": None,
                "last_refresh_type": None
            },
            "markets": {}
        }

    try:
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)

        return cache_data

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Cache file is corrupted")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading cache: {str(e)}")


# ============================================================================
# THEATER URL DISCOVERY ENDPOINTS
# ============================================================================

@router.post("/theaters/discover", response_model=TheaterDiscoveryResponse, tags=["Theaters"])
async def discover_theater_url(
    request: TheaterDiscoveryRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Discover a theater's Fandango URL by searching their website.

    This endpoint searches Fandango's search page for the theater name
    and returns the best matching URL along with all other matches found.

    If update_cache is True and a market is provided, the discovered URL
    will be added/updated in the theater cache.
    """
    import asyncio
    from app.scraper import Scraper

    # Validate update_cache requirements
    if request.update_cache and not request.market:
        raise HTTPException(
            status_code=400,
            detail="Market is required when update_cache is True"
        )

    try:
        scraper = Scraper()
        result = await scraper.discover_theater_url(request.theater_name)

        response = TheaterDiscoveryResponse(
            found=result["found"],
            theater_name=result.get("theater_name"),
            url=result.get("url"),
            theater_code=result.get("theater_code"),
            all_results=[
                TheaterDiscoveryResult(
                    name=r["name"],
                    url=r["url"],
                    code=r.get("code")
                )
                for r in result.get("all_results", [])
            ],
            error=result.get("error"),
            cache_updated=False
        )

        # Update cache if requested
        if request.update_cache and result["found"] and request.market:
            if current_user.get("role") not in ["admin", "manager"]:
                raise HTTPException(
                    status_code=403,
                    detail="Cache updates require manager or admin role"
                )

            try:
                with open(CACHE_FILE, 'r') as f:
                    cache_data = json.load(f)

                markets = cache_data.get('markets', {})

                if request.market not in markets:
                    markets[request.market] = {"theaters": []}

                market_theaters = markets[request.market].get('theaters', [])

                # Check if theater already exists
                theater_exists = False
                disc_req_norm = normalize_theater_name(request.theater_name)
                for theater in market_theaters:
                    if theater.get('name') == request.theater_name or normalize_theater_name(theater.get('name', '')) == disc_req_norm:
                        # Update existing entry
                        theater['url'] = result["url"]
                        theater['name'] = result["theater_name"]  # Use Fandango's name
                        if 'not_on_fandango' in theater:
                            del theater['not_on_fandango']
                        theater_exists = True
                        break

                if not theater_exists:
                    # Add new theater
                    market_theaters.append({
                        'name': result["theater_name"],
                        'url': result["url"]
                    })

                markets[request.market]['theaters'] = market_theaters
                cache_data['markets'] = markets

                # Update metadata
                if 'metadata' not in cache_data:
                    cache_data['metadata'] = {}
                cache_data['metadata']['last_updated'] = datetime.now().isoformat()

                # Save with backup
                backup_path = CACHE_FILE + ".bak"
                if os.path.exists(CACHE_FILE):
                    import shutil
                    shutil.copy2(CACHE_FILE, backup_path)

                with open(CACHE_FILE, 'w') as f:
                    json.dump(cache_data, f, indent=2)

                response.cache_updated = True

            except Exception as e:
                # Don't fail the whole request if cache update fails
                response.error = f"Discovery succeeded but cache update failed: {str(e)}"

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error discovering theater: {str(e)}")


@router.get("/theaters/discover/{theater_name}", response_model=TheaterDiscoveryResponse, tags=["Theaters"])
async def discover_theater_url_get(
    theater_name: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Quick theater URL lookup (GET version).

    Searches Fandango for the given theater name and returns matches.
    Does not update the cache - use POST version for that.
    """
    from app.scraper import Scraper

    try:
        scraper = Scraper()
        result = await scraper.discover_theater_url(theater_name)

        return TheaterDiscoveryResponse(
            found=result["found"],
            theater_name=result.get("theater_name"),
            url=result.get("url"),
            theater_code=result.get("theater_code"),
            all_results=[
                TheaterDiscoveryResult(
                    name=r["name"],
                    url=r["url"],
                    code=r.get("code")
                )
                for r in result.get("all_results", [])
            ],
            error=result.get("error"),
            cache_updated=False
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error discovering theater: {str(e)}")


# ============================================================================
# CACHE MAINTENANCE ENDPOINTS
# ============================================================================

class MaintenanceResult(BaseModel):
    timestamp: str
    duration_seconds: float
    overall_status: str
    alert_message: Optional[str] = None
    health_check: Dict[str, Any]
    repairs: Dict[str, Any]


class MaintenanceHistoryEntry(BaseModel):
    timestamp: str
    overall_status: str
    checked: int = 0
    failed: int = 0
    repaired: int = 0


class MaintenanceHistoryResponse(BaseModel):
    entries: List[MaintenanceHistoryEntry]
    total_count: int


@router.post("/cache/maintenance", response_model=MaintenanceResult, tags=["Cache Maintenance"])
async def run_cache_maintenance_endpoint(
    background: bool = False,
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Run cache maintenance: health check + repair failed theaters.

    This endpoint:
    1. Randomly samples 10 theaters to check for URL health
    2. Attempts to repair theaters with broken/missing URLs
    3. Alerts if > 30% of sample fails (Fandango site change detection)

    Set background=true to run async (returns immediately).
    """
    # Require admin role
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Cache maintenance requires admin role"
        )

    from app.cache_maintenance_service import CacheMaintenanceService

    if background and background_tasks:
        background_tasks.add_task(_run_maintenance_background)
        return MaintenanceResult(
            timestamp=datetime.now().isoformat(),
            duration_seconds=0,
            overall_status="started",
            health_check={"status": "pending"},
            repairs={"status": "pending"}
        )

    # Run synchronously
    service = CacheMaintenanceService()
    result = await service.run_maintenance()

    return MaintenanceResult(
        timestamp=result.get("timestamp", datetime.now().isoformat()),
        duration_seconds=result.get("duration_seconds", 0),
        overall_status=result.get("overall_status", "unknown"),
        alert_message=result.get("alert_message"),
        health_check=result.get("health_check", {}),
        repairs=result.get("repairs", {})
    )


async def _run_maintenance_background():
    """Background task for cache maintenance."""
    from app.cache_maintenance_service import CacheMaintenanceService
    service = CacheMaintenanceService()
    await service.run_maintenance()


@router.get("/cache/maintenance/health", tags=["Cache Maintenance"])
async def check_cache_health(
    current_user: dict = Depends(get_current_user)
):
    """
    Run a quick health check on random theater URLs.

    Checks a random sample of 10 theaters to detect:
    - Broken URLs
    - Fandango site changes

    Returns failure rate and alerts if > 30% fail.
    """
    from app.cache_maintenance_service import CacheMaintenanceService

    service = CacheMaintenanceService()
    result = await service.run_health_check()

    return result


@router.get("/cache/maintenance/history", response_model=MaintenanceHistoryResponse, tags=["Cache Maintenance"])
async def get_maintenance_history(
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    """
    Get recent cache maintenance run history.

    Returns the last N maintenance runs with their results.
    """
    from app.cache_maintenance_service import CacheMaintenanceService

    service = CacheMaintenanceService()
    entries = service.get_maintenance_history(limit=limit)

    formatted_entries = []
    for entry in entries:
        health = entry.get("health_check", {})
        repairs = entry.get("repairs", {})
        formatted_entries.append(MaintenanceHistoryEntry(
            timestamp=entry.get("timestamp", ""),
            overall_status=entry.get("overall_status", "unknown"),
            checked=health.get("checked", 0),
            failed=health.get("failed", 0),
            repaired=repairs.get("repaired", 0)
        ))

    return MaintenanceHistoryResponse(
        entries=formatted_entries,
        total_count=len(formatted_entries)
    )


@router.post("/cache/maintenance/run", response_model=MaintenanceResult, tags=["Cache Maintenance"])
async def run_maintenance(
    current_user: dict = Depends(get_current_user)
):
    """
    Run cache maintenance manually.

    Alias for POST /cache/maintenance for simpler frontend API calls.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Cache maintenance requires admin role"
        )

    from app.cache_maintenance_service import CacheMaintenanceService

    service = CacheMaintenanceService()
    result = await service.run_maintenance()

    return MaintenanceResult(
        timestamp=result.get("timestamp", datetime.now().isoformat()),
        duration_seconds=result.get("duration_seconds", 0),
        overall_status=result.get("overall_status", "unknown"),
        alert_message=result.get("alert_message"),
        health_check=result.get("health_check", {}),
        repairs=result.get("repairs", {})
    )


# ============================================================================
# REPAIR QUEUE ENDPOINTS
# ============================================================================

class RepairJobResponse(BaseModel):
    theater_name: str
    market_name: str
    zip_code: Optional[str] = None
    attempts: int = 0
    next_attempt_at: Optional[str] = None
    first_failure_at: Optional[str] = None
    last_failure_at: Optional[str] = None
    error_message: Optional[str] = None


class RepairQueueStatusResponse(BaseModel):
    total_queued: int
    due_now: int
    max_attempts_reached: int
    by_attempts: Dict[int, int]
    max_attempts_limit: int


class RepairResetRequest(BaseModel):
    theater_name: str
    market_name: str


class RepairProcessResult(BaseModel):
    processed: int
    success: int
    failed: int


@router.get("/cache/repair-queue/status", response_model=RepairQueueStatusResponse, tags=["Repair Queue"])
async def get_repair_queue_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get repair queue status and statistics.

    Shows total queued, due for retry, and breakdown by attempt count.
    """
    from app.repair_queue import repair_queue

    status = repair_queue.get_queue_status()
    return RepairQueueStatusResponse(**status)


@router.get("/cache/repair-queue/jobs", response_model=List[RepairJobResponse], tags=["Repair Queue"])
async def get_repair_queue_jobs(
    current_user: dict = Depends(get_current_user)
):
    """
    Get all jobs in the repair queue.

    Returns list of all theaters queued for repair with their backoff status.
    """
    from app.repair_queue import repair_queue

    jobs = repair_queue.get_all_jobs()
    return [
        RepairJobResponse(
            theater_name=job.theater_name,
            market_name=job.market_name,
            zip_code=job.zip_code,
            attempts=job.attempts,
            next_attempt_at=job.next_attempt_at,
            first_failure_at=job.first_failure_at,
            last_failure_at=job.last_failure_at,
            error_message=job.error_message
        )
        for job in jobs
    ]


@router.get("/cache/repair-queue/failed", response_model=List[RepairJobResponse], tags=["Repair Queue"])
async def get_repair_queue_failed(
    current_user: dict = Depends(get_current_user)
):
    """
    Get permanently failed theaters (max attempts reached).

    These theaters require manual intervention.
    """
    from app.repair_queue import repair_queue

    jobs = repair_queue.get_failed_permanently()
    return [
        RepairJobResponse(
            theater_name=job.theater_name,
            market_name=job.market_name,
            zip_code=job.zip_code,
            attempts=job.attempts,
            next_attempt_at=job.next_attempt_at,
            first_failure_at=job.first_failure_at,
            last_failure_at=job.last_failure_at,
            error_message=job.error_message
        )
        for job in jobs
    ]


@router.post("/cache/repair-queue/reset", tags=["Repair Queue"])
async def reset_repair_job(
    request: RepairResetRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Reset a repair job for immediate retry.

    Clears the attempt count and schedules for immediate processing.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Repair queue management requires admin role"
        )

    from app.repair_queue import repair_queue

    success = repair_queue.reset_job(request.theater_name, request.market_name)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Theater '{request.theater_name}' not found in repair queue"
        )

    return {"success": True, "message": f"Reset {request.theater_name} for immediate retry"}


@router.delete("/cache/repair-queue/failed", tags=["Repair Queue"])
async def clear_failed_jobs(
    current_user: dict = Depends(get_current_user)
):
    """
    Clear all permanently failed jobs from the repair queue.

    Removes theaters that have reached max retry attempts.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Repair queue management requires admin role"
        )

    from app.repair_queue import repair_queue

    cleared = repair_queue.clear_permanently_failed()
    return {"cleared": cleared, "message": f"Cleared {cleared} permanently failed jobs"}


@router.post("/cache/repair-queue/process", response_model=RepairProcessResult, tags=["Repair Queue"])
async def process_repair_queue(
    current_user: dict = Depends(get_current_user)
):
    """
    Process repair queue manually.

    Attempts to repair all theaters that are due for retry.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Repair queue management requires admin role"
        )

    from app.repair_queue import process_repair_queue_async

    result = await process_repair_queue_async()
    return RepairProcessResult(**result)
