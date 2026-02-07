"""
Presales API Router

Provides endpoints for presale tracking and velocity analysis
sourced from EntTelligence (batch updates @ 2 AM CT).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import Optional, List
from datetime import date, datetime, timedelta
from pydantic import BaseModel
import sqlite3
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from app import config
from app.simplified_baseline_service import normalize_theater_name
from api.routers.auth import require_read_admin, require_operator
from api.services import get_sqlite_connection

router = APIRouter(prefix="/api/v1", tags=["Presales"])


# Pydantic models
class PresaleSnapshot(BaseModel):
    id: int
    circuit_name: str
    film_title: str
    release_date: str
    snapshot_date: str
    days_before_release: int
    total_tickets_sold: int = 0
    total_revenue: float = 0
    total_showtimes: int = 0
    total_theaters: int = 0
    avg_tickets_per_show: float = 0.0
    avg_tickets_per_theater: float = 0.0
    avg_ticket_price: float = 0.0
    tickets_imax: int = 0
    tickets_dolby: int = 0
    tickets_3d: int = 0
    tickets_premium: int = 0
    tickets_standard: int = 0
    data_source: str = "enttelligence"


class PresaleTrajectory(BaseModel):
    film_title: str
    release_date: str
    circuit_name: str
    snapshots: List[PresaleSnapshot]
    current_tickets: int
    current_revenue: float
    velocity_trend: str  # "accelerating", "steady", "decelerating"
    days_until_release: int


class FilmPresaleSummary(BaseModel):
    film_title: str
    release_date: str
    total_circuits: int
    total_tickets: int
    total_revenue: float
    top_circuit: str
    velocity: str


class VelocityMetrics(BaseModel):
    film_title: str
    circuit_name: str
    snapshot_date: str
    daily_tickets: int
    daily_revenue: float
    velocity_change: float  # Percentage change from previous day
    trend: str


class DemandMetric(BaseModel):
    """Per-showtime demand data from EntTelligence capacity fields."""
    theater_name: str
    film_title: str
    play_date: str
    showtime: str
    format: Optional[str] = None
    circuit_name: Optional[str] = None
    ticket_type: str = "Adult"
    price: float = 0
    capacity: int = 0
    available: int = 0
    tickets_sold: int = 0
    fill_rate_pct: float = 0.0


# Response models for Swagger documentation
class CircuitPresaleStats(BaseModel):
    """Aggregate presale statistics for a circuit."""
    circuit_name: str
    total_films: int
    total_tickets: int
    total_revenue: float
    snapshot_count: int


class FilmPresaleItem(BaseModel):
    """Presale data for a single film."""
    film_title: str
    release_date: str
    total_circuits: int
    circuit_name: Optional[str] = None
    current_tickets: int
    current_revenue: float
    days_until_release: int
    latest_snapshot: Optional[str] = None


class CircuitCompareItem(BaseModel):
    """Comparison data for a single circuit."""
    circuit_name: str
    total_tickets: int
    total_revenue: float
    theaters: int
    avg_ticket_price: float
    days_until_release: int
    market_share_pct: float


class PresaleComparisonResponse(BaseModel):
    """Response for presale circuit comparison."""
    film_title: str
    total_circuits: int
    total_tickets: int
    circuits: List[CircuitCompareItem]


def get_db_connection():
    """Get database connection based on environment."""
    return get_sqlite_connection()


def _build_circuit_presales_filter(market_scope: str):
    """
    Build (sql_clause, params) for filtering circuit_presales by market scope.
    Returns circuits that have any theater in the curated markets.json list.
    """
    if market_scope != 'our_markets':
        return '1=1', []
    from api.services.market_scope_service import get_in_market_theater_names
    names = sorted(get_in_market_theater_names())
    if not names:
        return '1=0', []
    placeholders = ','.join('?' * len(names))
    return (
        f"circuit_name IN ("
        f"SELECT DISTINCT circuit_name FROM enttelligence_price_cache "
        f"WHERE company_id = ? AND theater_name IN ({placeholders})"
        f")",
        [config.DEFAULT_COMPANY_ID] + names
    )


def _build_cache_theater_filter(market_scope: str, alias: str = 'e'):
    """
    Build (sql_clause, params) for filtering enttelligence_price_cache
    to theaters in the curated markets.json list.
    """
    if market_scope != 'our_markets':
        return '1=1', []
    from api.services.market_scope_service import get_in_market_theater_names
    names = sorted(get_in_market_theater_names())
    if not names:
        return '1=0', []
    placeholders = ','.join('?' * len(names))
    return f"{alias}.theater_name IN ({placeholders})", names


@router.get("/presales", response_model=List[PresaleSnapshot])
async def list_presales(
    film_title: Optional[str] = Query(None, description="Filter by film title"),
    circuit_name: Optional[str] = Query(None, description="Filter by circuit"),
    snapshot_date: Optional[str] = Query(None, description="Filter by snapshot date"),
    days_before_release: Optional[int] = Query(None, description="Filter by days before release"),
    market_scope: str = Query("our_markets", description="'our_markets' for Marcus DMA-scoped, 'full' for national", regex="^(our_markets|full)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_read_admin),
):
    """
    List presale snapshot data with optional filtering.

    Data is sourced from EntTelligence and updated daily at 2 AM CT.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        market_clause, market_params = _build_circuit_presales_filter(market_scope)
        where_clauses = [market_clause]
        params = list(market_params)

        if film_title:
            where_clauses.append("film_title LIKE ?")
            params.append(f"%{film_title}%")

        if circuit_name:
            where_clauses.append("circuit_name LIKE ?")
            params.append(f"%{circuit_name}%")

        if snapshot_date:
            where_clauses.append("snapshot_date = ?")
            params.append(snapshot_date)

        if days_before_release is not None:
            where_clauses.append("days_before_release = ?")
            params.append(days_before_release)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        cursor.execute(f"""
            SELECT * FROM circuit_presales
            {where_sql}
            ORDER BY snapshot_date DESC, film_title, circuit_name
            LIMIT ? OFFSET ?
        """, params + [limit, offset])

        rows = cursor.fetchall()
        return [PresaleSnapshot(**dict(row)) for row in rows]

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return []
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/presales/circuits", response_model=List[CircuitPresaleStats])
async def list_presale_circuits(
    market_scope: str = Query("our_markets", description="'our_markets' or 'full'", regex="^(our_markets|full)$"),
    current_user: dict = Depends(require_read_admin),
):
    """
    Get list of all circuits with presale data and aggregate statistics.
    Useful for filtering/grouping the film list by circuit.

    When market_scope=our_markets, queries raw enttelligence_price_cache
    with DMA join for truly in-market data.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        if market_scope == 'our_markets':
            # Query raw cache filtered to markets.json theaters
            market_clause, market_params = _build_cache_theater_filter(market_scope)
            cursor.execute(f"""
                SELECT
                    e.circuit_name,
                    COUNT(DISTINCT e.film_title) as total_films,
                    SUM(CASE WHEN COALESCE(e.capacity, 0) > COALESCE(e.available, 0)
                             THEN COALESCE(e.capacity, 0) - COALESCE(e.available, 0)
                             ELSE 0 END) as total_tickets,
                    SUM(CASE WHEN COALESCE(e.capacity, 0) > COALESCE(e.available, 0)
                             THEN (COALESCE(e.capacity, 0) - COALESCE(e.available, 0)) * COALESCE(e.price, 0)
                             ELSE 0 END) as total_revenue,
                    COUNT(DISTINCT e.theater_name) as snapshot_count
                FROM enttelligence_price_cache e
                WHERE e.company_id = ?
                  AND e.ticket_type = 'Adult'
                  AND e.release_date IS NOT NULL AND e.release_date != ''
                  AND {market_clause}
                GROUP BY e.circuit_name
                ORDER BY total_tickets DESC
            """, [config.DEFAULT_COMPANY_ID] + market_params)
        else:
            cursor.execute("""
                SELECT
                    circuit_name,
                    COUNT(DISTINCT film_title) as total_films,
                    SUM(total_tickets_sold) as total_tickets,
                    SUM(total_revenue) as total_revenue,
                    COUNT(DISTINCT snapshot_date) as snapshot_count
                FROM circuit_presales
                GROUP BY circuit_name
                ORDER BY total_tickets DESC
            """)

        circuits = []
        for row in cursor.fetchall():
            circuits.append({
                "circuit_name": row['circuit_name'],
                "total_films": row['total_films'],
                "total_tickets": row['total_tickets'] or 0,
                "total_revenue": float(row['total_revenue'] or 0),
                "snapshot_count": row['snapshot_count'],
            })

        return circuits

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return []
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/presales/films", response_model=List[FilmPresaleItem])
async def list_presale_films(
    circuit_name: Optional[str] = None,
    market_scope: str = Query("our_markets", description="'our_markets' or 'full'", regex="^(our_markets|full)$"),
    current_user: dict = Depends(require_read_admin),
):
    """
    Get list of all films with presale data and summary statistics.
    Optionally filter by circuit_name to see what a specific circuit is doing.
    Returns circuit_name for single-circuit films.

    When market_scope=our_markets, queries raw enttelligence_price_cache
    with DMA join for truly in-market data.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        if market_scope == 'our_markets':
            # Query raw cache filtered to markets.json theaters
            market_clause, market_params = _build_cache_theater_filter(market_scope)
            params = [config.DEFAULT_COMPANY_ID] + list(market_params)
            circuit_filter = ""
            if circuit_name:
                circuit_filter = "AND e.circuit_name = ?"
                params.append(circuit_name)

            cursor.execute(f"""
                SELECT
                    e.film_title,
                    e.release_date,
                    COUNT(DISTINCT e.circuit_name) as total_circuits,
                    CASE WHEN COUNT(DISTINCT e.circuit_name) = 1
                         THEN MIN(e.circuit_name) ELSE NULL END as circuit_name,
                    SUM(CASE WHEN COALESCE(e.capacity, 0) > COALESCE(e.available, 0)
                             THEN COALESCE(e.capacity, 0) - COALESCE(e.available, 0)
                             ELSE 0 END) as max_tickets,
                    SUM(CASE WHEN COALESCE(e.capacity, 0) > COALESCE(e.available, 0)
                             THEN (COALESCE(e.capacity, 0) - COALESCE(e.available, 0)) * COALESCE(e.price, 0)
                             ELSE 0 END) as max_revenue,
                    CAST(julianday(e.release_date) - julianday('now') AS INTEGER) as min_days_out,
                    date('now') as latest_snapshot
                FROM enttelligence_price_cache e
                WHERE e.company_id = ?
                  AND e.ticket_type = 'Adult'
                  AND e.release_date IS NOT NULL AND e.release_date != ''
                  AND {market_clause}
                  {circuit_filter}
                GROUP BY e.film_title, e.release_date
                ORDER BY e.release_date ASC, e.film_title
            """, params)
        else:
            # Full national: use circuit_presales (pre-aggregated snapshots)
            if circuit_name:
                cursor.execute("""
                    SELECT
                        film_title,
                        release_date,
                        circuit_name,
                        1 as total_circuits,
                        MAX(total_tickets_sold) as max_tickets,
                        MAX(total_revenue) as max_revenue,
                        MIN(days_before_release) as min_days_out,
                        MAX(snapshot_date) as latest_snapshot
                    FROM circuit_presales
                    WHERE circuit_name = ?
                    GROUP BY film_title, release_date, circuit_name
                    ORDER BY release_date ASC, film_title
                """, [circuit_name])
            else:
                cursor.execute("""
                    SELECT
                        film_title,
                        release_date,
                        COUNT(DISTINCT circuit_name) as total_circuits,
                        CASE WHEN COUNT(DISTINCT circuit_name) = 1
                             THEN MIN(circuit_name) ELSE NULL END as circuit_name,
                        MAX(total_tickets_sold) as max_tickets,
                        MAX(total_revenue) as max_revenue,
                        MIN(days_before_release) as min_days_out,
                        MAX(snapshot_date) as latest_snapshot
                    FROM circuit_presales
                    GROUP BY film_title, release_date
                    ORDER BY release_date ASC, film_title
                """)

        films = []
        for row in cursor.fetchall():
            films.append({
                "film_title": row['film_title'],
                "release_date": row['release_date'],
                "total_circuits": row['total_circuits'],
                "circuit_name": row['circuit_name'],
                "current_tickets": row['max_tickets'] or 0,
                "current_revenue": float(row['max_revenue'] or 0),
                "days_until_release": row['min_days_out'] or 0,
                "latest_snapshot": row['latest_snapshot']
            })

        return films

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return []
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/presales/velocity/{film_title}", response_model=List[VelocityMetrics])
async def get_velocity_metrics(
    film_title: str,
    market_scope: str = Query("our_markets", description="'our_markets' or 'full'", regex="^(our_markets|full)$"),
    current_user: dict = Depends(require_read_admin),
):
    """
    Get daily velocity metrics for a film showing acceleration/deceleration.

    Velocity = tickets sold per day
    Velocity change = percentage change from previous day
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        market_clause, market_params = _build_circuit_presales_filter(market_scope)
        cursor.execute(f"""
            SELECT
                film_title,
                circuit_name,
                snapshot_date,
                total_tickets_sold,
                total_revenue,
                days_before_release
            FROM circuit_presales
            WHERE film_title = ? AND {market_clause}
            ORDER BY circuit_name, snapshot_date ASC
        """, [film_title] + market_params)

        rows = cursor.fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail=f"No presale data for film: {film_title}")

        # Calculate velocity for each day
        metrics = []
        prev_by_circuit = {}

        for row in rows:
            circuit = row['circuit_name']
            current_tickets = row['total_tickets_sold']
            current_revenue = row['total_revenue']

            if circuit in prev_by_circuit:
                prev = prev_by_circuit[circuit]
                daily_tickets = current_tickets - prev['tickets']
                daily_revenue = current_revenue - prev['revenue']

                if prev['daily_tickets'] > 0:
                    velocity_change = ((daily_tickets - prev['daily_tickets']) / prev['daily_tickets']) * 100
                else:
                    velocity_change = 0

                if velocity_change > 10:
                    trend = "accelerating"
                elif velocity_change < -10:
                    trend = "decelerating"
                else:
                    trend = "steady"

                metrics.append(VelocityMetrics(
                    film_title=film_title,
                    circuit_name=circuit,
                    snapshot_date=row['snapshot_date'],
                    daily_tickets=daily_tickets,
                    daily_revenue=daily_revenue,
                    velocity_change=round(velocity_change, 1),
                    trend=trend
                ))

                prev_by_circuit[circuit] = {
                    'tickets': current_tickets,
                    'revenue': current_revenue,
                    'daily_tickets': daily_tickets
                }
            else:
                prev_by_circuit[circuit] = {
                    'tickets': current_tickets,
                    'revenue': current_revenue,
                    'daily_tickets': current_tickets  # First day = all tickets
                }

        return metrics

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            raise HTTPException(status_code=404, detail="Presales table not initialized")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/presales/compare", response_model=PresaleComparisonResponse)
async def compare_circuits_presales(
    film_title: str = Query(..., description="Film to compare"),
    circuits: Optional[str] = Query(None, description="Comma-separated circuit names (defaults to all)"),
    market_scope: str = Query("our_markets", description="'our_markets' or 'full'", regex="^(our_markets|full)$"),
    current_user: dict = Depends(require_read_admin),
):
    """
    Compare presale performance across circuits for a specific film.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        market_clause, market_params = _build_circuit_presales_filter(market_scope)
        if circuits:
            circuit_list = [c.strip() for c in circuits.split(",")]
            placeholders = ",".join("?" * len(circuit_list))
            cursor.execute(f"""
                SELECT
                    circuit_name,
                    MAX(total_tickets_sold) as total_tickets,
                    MAX(total_revenue) as total_revenue,
                    MAX(total_theaters) as theaters,
                    MAX(avg_ticket_price) as avg_price,
                    MIN(days_before_release) as days_out
                FROM circuit_presales
                WHERE film_title = ? AND circuit_name IN ({placeholders}) AND {market_clause}
                GROUP BY circuit_name
                ORDER BY total_tickets DESC
            """, [film_title] + circuit_list + market_params)
        else:
            cursor.execute(f"""
                SELECT
                    circuit_name,
                    MAX(total_tickets_sold) as total_tickets,
                    MAX(total_revenue) as total_revenue,
                    MAX(total_theaters) as theaters,
                    MAX(avg_ticket_price) as avg_price,
                    MIN(days_before_release) as days_out
                FROM circuit_presales
                WHERE film_title = ? AND {market_clause}
                GROUP BY circuit_name
                ORDER BY total_tickets DESC
            """, [film_title] + market_params)

        rows = cursor.fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail=f"No presale data for film: {film_title}")

        circuits_data = []
        total_tickets = 0

        for row in rows:
            circuits_data.append({
                "circuit_name": row['circuit_name'],
                "total_tickets": row['total_tickets'] or 0,
                "total_revenue": row['total_revenue'] or 0,
                "theaters": row['theaters'] or 0,
                "avg_ticket_price": row['avg_price'] or 0,
                "days_until_release": row['days_out'] or 0
            })
            total_tickets += row['total_tickets'] or 0

        # Calculate market share
        for c in circuits_data:
            c['market_share_pct'] = round((c['total_tickets'] / total_tickets * 100), 1) if total_tickets > 0 else 0

        return {
            "film_title": film_title,
            "total_circuits": len(circuits_data),
            "total_tickets": total_tickets,
            "circuits": circuits_data
        }

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            raise HTTPException(status_code=404, detail="Presales table not initialized")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/presales/sync")
async def trigger_presale_sync(background_tasks: BackgroundTasks, current_user: dict = Depends(require_operator)):
    """
    Trigger an EntTelligence sync for presale data.

    This runs in the background. Note: EntTelligence data only updates at 2 AM CT.
    """
    if not config.ENTTELLIGENCE_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="EntTelligence integration is not enabled. Set ENTTELLIGENCE_ENABLED=true"
        )

    if config.USE_CELERY:
        from app.tasks.sync import sync_presales_task
        task = sync_presales_task.delay()
        return {
            "status": "triggered",
            "message": "Presale sync task initiated via Celery",
            "task_id": task.id
        }

    background_tasks.add_task(run_presale_sync)

    return {
        "status": "started",
        "message": "Presale sync started in background"
    }


async def run_presale_sync():
    """Background task to sync presale data from EntTelligence."""
    try:
        from app.presale_reconciliation import sync_presales
        result = sync_presales(company_id=config.DEFAULT_COMPANY_ID)
        print(f"[PresaleSync] Completed: {result}")
    except ImportError as e:
        print(f"Warning: presale_reconciliation not available: {e}")
    except Exception as e:
        print(f"Presale sync error: {e}")


@router.get("/presales/compliance")
async def get_compliance(
    market_scope: str = Query("our_markets", description="'our_markets' or 'full'", regex="^(our_markets|full)$"),
    current_user: dict = Depends(require_read_admin),
):
    """
    Presale posting compliance analysis.

    Compares how far in advance each circuit posts showtimes for upcoming films.
    Highlights Marcus vs. competitors (AMC, Regal, Cinemark, etc.).
    """
    try:
        from app.presale_reconciliation import get_presale_compliance
        from api.services.market_scope_service import get_in_market_theater_names
        theater_names = get_in_market_theater_names() if market_scope == 'our_markets' else None
        return get_presale_compliance(company_id=config.DEFAULT_COMPANY_ID, theater_names=theater_names)
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"presale_reconciliation not available: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PRESALE HEATMAP DATA
# ============================================================================

class PresaleHeatmapTheater(BaseModel):
    """Per-theater presale data with geographic coordinates."""
    theater_name: str
    circuit_name: Optional[str] = None
    market: Optional[str] = None
    latitude: float
    longitude: float
    total_showtimes: int = 0
    total_capacity: int = 0
    total_available: int = 0
    total_tickets_sold: int = 0
    fill_rate_pct: float = 0.0
    avg_price: Optional[float] = None
    films_count: int = 0
    is_marcus: bool = False


class PresaleHeatmapResponse(BaseModel):
    """Response containing theaters with presale heatmap data."""
    total_theaters: int
    theaters_with_data: int
    film_filter: Optional[str] = None
    theaters: List[PresaleHeatmapTheater]


@router.get("/presales/heatmap-data", response_model=PresaleHeatmapResponse)
async def get_presale_heatmap_data(
    film_title: Optional[str] = Query(None, description="Filter by specific film"),
    circuit: Optional[str] = Query(None, description="Filter by circuit name"),
    market_scope: str = Query("our_markets", description="'our_markets' for Marcus DMA-scoped, 'full' for national", regex="^(our_markets|full)$"),
    current_user: dict = Depends(require_read_admin),
):
    """
    Get per-theater presale data with geographic coordinates for heatmap visualization.

    Joins enttelligence_price_cache (capacity/available/blocked) with theater_metadata
    (latitude/longitude) to produce geographic presale metrics.

    - Without film_title: shows aggregate presale activity across all upcoming films
    - With film_title: shows presale data for a specific film
    """
    from app.db_models import EntTelligencePriceCache, TheaterMetadata
    from app.db_session import get_session
    from sqlalchemy import func, and_, case

    company_id = config.DEFAULT_COMPANY_ID

    with get_session() as session:
        # Base filter: Adult tickets with capacity data
        filters = [
            EntTelligencePriceCache.company_id == company_id,
            EntTelligencePriceCache.ticket_type == 'Adult',
            EntTelligencePriceCache.capacity.isnot(None),
            EntTelligencePriceCache.capacity > 0,
        ]

        if film_title:
            filters.append(EntTelligencePriceCache.film_title == film_title)
        if circuit:
            filters.append(EntTelligencePriceCache.circuit_name.ilike(f'%{circuit}%'))

        # Aggregate presale metrics per theater
        theater_stats = session.query(
            EntTelligencePriceCache.theater_name,
            EntTelligencePriceCache.circuit_name,
            func.count().label('total_showtimes'),
            func.sum(EntTelligencePriceCache.capacity).label('total_capacity'),
            func.sum(EntTelligencePriceCache.available).label('total_available'),
            # tickets_sold = capacity - available
            # (blocked = capacity - available always; blocked IS the sold/reserved count)
            func.sum(
                case(
                    (
                        EntTelligencePriceCache.capacity
                        - func.coalesce(EntTelligencePriceCache.available, 0) > 0,
                        EntTelligencePriceCache.capacity
                        - func.coalesce(EntTelligencePriceCache.available, 0),
                    ),
                    else_=0,
                )
            ).label('total_tickets_sold'),
            func.avg(EntTelligencePriceCache.price).label('avg_price'),
            func.count(func.distinct(EntTelligencePriceCache.film_title)).label('films_count'),
        ).filter(
            and_(*filters)
        ).group_by(
            EntTelligencePriceCache.theater_name,
            EntTelligencePriceCache.circuit_name,
        ).all()

        # Build a lookup by theater_name
        stats_by_theater = {}
        for row in theater_stats:
            stats_by_theater[row.theater_name] = row

        # Now get coordinates from theater_metadata
        coord_filters = [
            TheaterMetadata.company_id == company_id,
            TheaterMetadata.latitude.isnot(None),
            TheaterMetadata.longitude.isnot(None),
        ]

        # Market scope: restrict to curated markets.json theaters
        if market_scope == 'our_markets':
            from api.services.market_scope_service import get_in_market_theater_names
            in_market_names = get_in_market_theater_names()
            coord_filters.append(TheaterMetadata.theater_name.in_(in_market_names))

        coord_query = session.query(
            TheaterMetadata.theater_name,
            TheaterMetadata.market,
            TheaterMetadata.latitude,
            TheaterMetadata.longitude,
        ).filter(
            and_(*coord_filters)
        )

        coords_by_theater = {}
        coords_by_norm = {}  # normalized name fallback
        for row in coord_query.all():
            coords_by_theater[row.theater_name] = row
            coords_by_norm[normalize_theater_name(row.theater_name)] = row

        # Join the two datasets
        theaters = []
        marcus_labels = ['marcus', 'movie tavern', 'spotlight']

        for theater_name, stats in stats_by_theater.items():
            coord = coords_by_theater.get(theater_name)
            if not coord:
                coord = coords_by_norm.get(normalize_theater_name(theater_name))
            if not coord:
                continue  # Skip theaters without coordinates

            cap = int(stats.total_capacity or 0)
            avail = int(stats.total_available or 0)
            sold = int(stats.total_tickets_sold or 0)
            fill = (sold / cap * 100) if cap > 0 else 0.0
            circuit_name = stats.circuit_name or ''
            is_marcus = any(label in circuit_name.lower() for label in marcus_labels)

            theaters.append(PresaleHeatmapTheater(
                theater_name=theater_name,
                circuit_name=stats.circuit_name,
                market=coord.market,
                latitude=float(coord.latitude),
                longitude=float(coord.longitude),
                total_showtimes=int(stats.total_showtimes or 0),
                total_capacity=cap,
                total_available=avail,
                total_tickets_sold=sold,
                fill_rate_pct=round(fill, 1),
                avg_price=round(float(stats.avg_price), 2) if stats.avg_price else None,
                films_count=int(stats.films_count or 0),
                is_marcus=is_marcus,
            ))

        # Sort by total_showtimes descending
        theaters.sort(key=lambda t: -t.total_showtimes)

        return PresaleHeatmapResponse(
            total_theaters=len(stats_by_theater),
            theaters_with_data=len(theaters),
            film_filter=film_title,
            theaters=theaters,
        )


# ============================================================================
# PRESALE WATCHES (Alert Configurations)
# ============================================================================

class PresaleWatchCreate(BaseModel):
    film_title: str
    alert_type: str  # velocity_drop, milestone, daily_change, format_shift
    threshold: float


class PresaleWatchUpdate(BaseModel):
    enabled: Optional[bool] = None
    threshold: Optional[float] = None


class PresaleWatch(BaseModel):
    id: int
    film_title: str
    alert_type: str
    threshold: float
    enabled: bool = True
    created_at: str
    last_triggered: Optional[str] = None
    trigger_count: int = 0


class PresaleWatchNotification(BaseModel):
    id: int
    watch_id: int
    film_title: str
    message: str
    triggered_at: str
    is_read: bool = False
    severity: str = "info"


VALID_ALERT_TYPES = {"velocity_drop", "velocity_spike", "milestone", "days_out", "market_share"}


def _ensure_watch_tables(conn):
    """Create watch tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS presale_watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            film_title TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            threshold REAL NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            last_triggered TEXT,
            trigger_count INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS presale_watch_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_id INTEGER NOT NULL,
            film_title TEXT NOT NULL,
            message TEXT NOT NULL,
            triggered_at TEXT DEFAULT (datetime('now')),
            is_read INTEGER DEFAULT 0,
            severity TEXT DEFAULT 'info',
            FOREIGN KEY (watch_id) REFERENCES presale_watches(id) ON DELETE CASCADE
        )
    """)
    conn.commit()


@router.get("/presales/watches", response_model=List[PresaleWatch])
async def list_watches(current_user: dict = Depends(require_read_admin)):
    """List all presale watch configurations."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    _ensure_watch_tables(conn)
    try:
        rows = conn.execute(
            "SELECT * FROM presale_watches ORDER BY created_at DESC"
        ).fetchall()
        return [
            PresaleWatch(
                id=r["id"],
                film_title=r["film_title"],
                alert_type=r["alert_type"],
                threshold=r["threshold"],
                enabled=bool(r["enabled"]),
                created_at=r["created_at"],
                last_triggered=r["last_triggered"],
                trigger_count=r["trigger_count"],
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.post("/presales/watches", response_model=PresaleWatch, status_code=201)
async def create_watch(body: PresaleWatchCreate, current_user: dict = Depends(require_operator)):
    """Create a new presale watch."""
    if body.alert_type not in VALID_ALERT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid alert_type. Must be one of: {', '.join(sorted(VALID_ALERT_TYPES))}"
        )

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    _ensure_watch_tables(conn)
    try:
        cursor = conn.execute(
            """INSERT INTO presale_watches (film_title, alert_type, threshold)
               VALUES (?, ?, ?)""",
            (body.film_title, body.alert_type, body.threshold),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM presale_watches WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return PresaleWatch(
            id=row["id"],
            film_title=row["film_title"],
            alert_type=row["alert_type"],
            threshold=row["threshold"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            last_triggered=row["last_triggered"],
            trigger_count=row["trigger_count"],
        )
    finally:
        conn.close()


@router.put("/presales/watches/{watch_id}", response_model=PresaleWatch)
async def update_watch(watch_id: int, body: PresaleWatchUpdate, current_user: dict = Depends(require_operator)):
    """Update a presale watch (toggle enabled, change threshold)."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    _ensure_watch_tables(conn)
    try:
        existing = conn.execute(
            "SELECT * FROM presale_watches WHERE id = ?", (watch_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Watch not found")

        updates = []
        params = []
        if body.enabled is not None:
            updates.append("enabled = ?")
            params.append(int(body.enabled))
        if body.threshold is not None:
            updates.append("threshold = ?")
            params.append(body.threshold)

        if updates:
            params.append(watch_id)
            conn.execute(
                f"UPDATE presale_watches SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()

        row = conn.execute(
            "SELECT * FROM presale_watches WHERE id = ?", (watch_id,)
        ).fetchone()
        return PresaleWatch(
            id=row["id"],
            film_title=row["film_title"],
            alert_type=row["alert_type"],
            threshold=row["threshold"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            last_triggered=row["last_triggered"],
            trigger_count=row["trigger_count"],
        )
    finally:
        conn.close()


@router.delete("/presales/watches/{watch_id}", status_code=204)
async def delete_watch(watch_id: int, current_user: dict = Depends(require_operator)):
    """Delete a presale watch and its notifications."""
    conn = get_db_connection()
    _ensure_watch_tables(conn)
    try:
        existing = conn.execute(
            "SELECT id FROM presale_watches WHERE id = ?", (watch_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Watch not found")

        conn.execute("DELETE FROM presale_watch_notifications WHERE watch_id = ?", (watch_id,))
        conn.execute("DELETE FROM presale_watches WHERE id = ?", (watch_id,))
        conn.commit()
    finally:
        conn.close()


@router.get("/presales/watches/notifications", response_model=List[PresaleWatchNotification])
async def list_watch_notifications(
    unread_only: bool = Query(False, description="Only return unread notifications"),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_read_admin),
):
    """List presale watch notifications (triggered alerts)."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    _ensure_watch_tables(conn)
    try:
        where = "WHERE is_read = 0" if unread_only else ""
        rows = conn.execute(
            f"SELECT * FROM presale_watch_notifications {where} ORDER BY triggered_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            PresaleWatchNotification(
                id=r["id"],
                watch_id=r["watch_id"],
                film_title=r["film_title"],
                message=r["message"],
                triggered_at=r["triggered_at"],
                is_read=bool(r["is_read"]),
                severity=r["severity"],
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.put("/presales/watches/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: int, current_user: dict = Depends(require_operator)):
    """Mark a watch notification as read."""
    conn = get_db_connection()
    _ensure_watch_tables(conn)
    try:
        existing = conn.execute(
            "SELECT id FROM presale_watch_notifications WHERE id = ?", (notification_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Notification not found")

        conn.execute(
            "UPDATE presale_watch_notifications SET is_read = 1 WHERE id = ?",
            (notification_id,),
        )
        conn.commit()
        return {"id": notification_id, "is_read": True}
    finally:
        conn.close()


# ============================================================================
# CATCH-ALL: Film trajectory by title (must be LAST to avoid catching
# static routes like /compliance, /heatmap-data, /watches, /compare)
# ============================================================================

@router.get("/presales/{film_title}", response_model=PresaleTrajectory)
async def get_film_trajectory(
    film_title: str,
    circuit_name: Optional[str] = Query(None, description="Filter by specific circuit"),
    market_scope: str = Query("our_markets", description="'our_markets' for Marcus DMA-scoped, 'full' for national", regex="^(our_markets|full)$"),
    current_user: dict = Depends(require_read_admin),
):
    """
    Get presale trajectory for a specific film showing daily buildup.

    Returns time series of presale snapshots showing how ticket sales
    accumulated over time leading up to release.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Build query with market scope filter
        market_clause, market_params = _build_circuit_presales_filter(market_scope)
        if circuit_name:
            cursor.execute(f"""
                SELECT * FROM circuit_presales
                WHERE film_title = ? AND circuit_name = ? AND {market_clause}
                ORDER BY snapshot_date ASC
            """, [film_title, circuit_name] + market_params)
        else:
            # Get aggregated across all circuits
            cursor.execute(f"""
                SELECT * FROM circuit_presales
                WHERE film_title = ? AND {market_clause}
                ORDER BY snapshot_date ASC
            """, [film_title] + market_params)

        rows = cursor.fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail=f"No presale data for film: {film_title}")

        snapshots = [PresaleSnapshot(**dict(row)) for row in rows]

        # Calculate velocity trend
        if len(snapshots) >= 3:
            recent_velocity = snapshots[-1].total_tickets_sold - snapshots[-2].total_tickets_sold
            prev_velocity = snapshots[-2].total_tickets_sold - snapshots[-3].total_tickets_sold

            if recent_velocity > prev_velocity * 1.1:
                trend = "accelerating"
            elif recent_velocity < prev_velocity * 0.9:
                trend = "decelerating"
            else:
                trend = "steady"
        else:
            trend = "insufficient_data"

        # Get latest snapshot data
        latest = snapshots[-1]

        return PresaleTrajectory(
            film_title=film_title,
            release_date=latest.release_date,
            circuit_name=circuit_name or "All Circuits",
            snapshots=snapshots,
            current_tickets=latest.total_tickets_sold,
            current_revenue=latest.total_revenue,
            velocity_trend=trend,
            days_until_release=latest.days_before_release
        )

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            raise HTTPException(status_code=404, detail="Presales table not initialized")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================================
# Demand Lookup — per-showtime sales data for Market Mode & Daily Lineup
# ============================================================================

@router.get("/presales/demand-lookup", response_model=List[DemandMetric])
async def demand_lookup(
    theaters: str = Query(..., description="Comma-separated theater names"),
    date_from: str = Query(..., description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD), defaults to date_from"),
    films: Optional[str] = Query(None, description="Comma-separated film titles (optional)"),
    current_user: dict = Depends(require_read_admin),
):
    """
    Look up per-showtime demand data from EntTelligence cache.

    Returns capacity, available, tickets_sold, and fill_rate for each showtime
    at the requested theaters and dates. Used by Market Mode (competitor demand)
    and Daily Lineup (presale alerts).

    Data comes from enttelligence_price_cache which is synced daily at 2 AM CT.
    Only returns Adult ticket type rows to avoid double-counting showtimes.
    """
    theater_list = [t.strip() for t in theaters.split(',') if t.strip()]
    if not theater_list:
        raise HTTPException(status_code=400, detail="At least one theater name is required")

    end_date = date_to or date_from

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        placeholders = ','.join('?' * len(theater_list))
        params: list = [config.DEFAULT_COMPANY_ID] + list(theater_list) + [date_from, end_date]

        film_clause = ""
        if films:
            film_list = [f.strip() for f in films.split(',') if f.strip()]
            if film_list:
                film_placeholders = ','.join('?' * len(film_list))
                film_clause = f"AND e.film_title IN ({film_placeholders})"
                params.extend(film_list)

        cursor.execute(f"""
            SELECT
                e.theater_name,
                e.film_title,
                e.play_date,
                e.showtime,
                e.format,
                e.circuit_name,
                e.ticket_type,
                COALESCE(e.price, 0) as price,
                COALESCE(e.capacity, 0) as capacity,
                COALESCE(e.available, 0) as available
            FROM enttelligence_price_cache e
            WHERE e.company_id = ?
              AND e.ticket_type = 'Adult'
              AND e.theater_name IN ({placeholders})
              AND e.play_date BETWEEN ? AND ?
              AND e.capacity IS NOT NULL
              AND e.capacity > 0
              {film_clause}
            ORDER BY e.theater_name, e.film_title, e.play_date, e.showtime
        """, params)

        rows = cursor.fetchall()

        results = []
        for row in rows:
            cap = row['capacity']
            avail = row['available']
            sold = max(0, cap - avail)
            fill_rate = round((sold / cap) * 100, 1) if cap > 0 else 0.0

            results.append(DemandMetric(
                theater_name=row['theater_name'],
                film_title=row['film_title'],
                play_date=str(row['play_date']),
                showtime=row['showtime'],
                format=row['format'],
                circuit_name=row['circuit_name'],
                ticket_type=row['ticket_type'],
                price=float(row['price']),
                capacity=cap,
                available=avail,
                tickets_sold=sold,
                fill_rate_pct=fill_rate,
            ))

        return results

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            raise HTTPException(status_code=404, detail="EntTelligence cache not initialized")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
