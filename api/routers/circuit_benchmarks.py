"""
Circuit Benchmarks API Router

Provides endpoints for nationwide circuit competitive intelligence data
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
from api.routers.auth import require_read_admin, require_operator
from api.services import get_sqlite_connection

router = APIRouter(prefix="/api/v1", tags=["Circuit Benchmarks"])


# Pydantic models
class CircuitBenchmark(BaseModel):
    benchmark_id: int
    circuit_name: str
    week_ending_date: str
    period_start_date: Optional[str] = None
    total_showtimes: int = 0
    total_capacity: int = 0
    total_theaters: int = 0
    total_films: int = 0
    avg_screens_per_film: float = 0.0
    avg_showtimes_per_theater: float = 0.0
    format_standard_pct: float = 0.0
    format_imax_pct: float = 0.0
    format_dolby_pct: float = 0.0
    format_3d_pct: float = 0.0
    format_other_premium_pct: float = 0.0
    plf_total_pct: float = 0.0
    daypart_matinee_pct: float = 0.0
    daypart_evening_pct: float = 0.0
    daypart_late_pct: float = 0.0
    avg_price_general: Optional[float] = None
    avg_price_child: Optional[float] = None
    avg_price_senior: Optional[float] = None
    data_source: str = "enttelligence"
    created_at: Optional[str] = None


class CircuitBenchmarkList(BaseModel):
    benchmarks: List[CircuitBenchmark]
    total_count: int
    available_weeks: List[str]


class WeekSummary(BaseModel):
    week_ending_date: str
    period_start_date: str
    circuit_count: int
    total_showtimes: int
    data_freshness: str


class SyncStatus(BaseModel):
    status: str
    message: str
    last_sync: Optional[str] = None
    records_synced: int = 0
    task_id: Optional[str] = None


def get_db_connection():
    """Get database connection with schema auto-migration."""
    conn = get_sqlite_connection()
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection):
    """Add missing columns to circuit_benchmarks if table exists (auto-migration)."""
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(circuit_benchmarks)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if existing_cols and 'period_start_date' not in existing_cols:
            cursor.execute("ALTER TABLE circuit_benchmarks ADD COLUMN period_start_date DATE")
            conn.commit()
    except sqlite3.OperationalError:
        pass  # Table doesn't exist yet — handled by endpoint-level error handling


@router.get("/circuit-benchmarks", response_model=CircuitBenchmarkList)
async def list_circuit_benchmarks(
    week_ending_date: Optional[str] = Query(None, description="Filter by week ending date (YYYY-MM-DD)"),
    circuit_name: Optional[str] = Query(None, description="Filter by circuit name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_read_admin),
):
    """
    List circuit benchmark data with optional filtering.

    Data is sourced from EntTelligence and updated daily at 2 AM CT.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Build query
        where_clauses = []
        params = []

        if week_ending_date:
            where_clauses.append("week_ending_date = ?")
            params.append(week_ending_date)

        if circuit_name:
            where_clauses.append("circuit_name LIKE ?")
            params.append(f"%{circuit_name}%")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Get total count
        cursor.execute(f"SELECT COUNT(*) FROM circuit_benchmarks {where_sql}", params)
        total_count = cursor.fetchone()[0]

        # Get benchmarks
        cursor.execute(f"""
            SELECT * FROM circuit_benchmarks
            {where_sql}
            ORDER BY week_ending_date DESC, circuit_name
            LIMIT ? OFFSET ?
        """, params + [limit, offset])

        rows = cursor.fetchall()
        benchmarks = [CircuitBenchmark(**dict(row)) for row in rows]

        # Get available weeks
        cursor.execute("""
            SELECT DISTINCT week_ending_date
            FROM circuit_benchmarks
            ORDER BY week_ending_date DESC
            LIMIT 52
        """)
        available_weeks = [row[0] for row in cursor.fetchall()]

        return CircuitBenchmarkList(
            benchmarks=benchmarks,
            total_count=total_count,
            available_weeks=available_weeks
        )

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return CircuitBenchmarkList(
                benchmarks=[],
                total_count=0,
                available_weeks=[]
            )
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/circuit-benchmarks/weeks", response_model=List[WeekSummary])
async def list_available_weeks(current_user: dict = Depends(require_read_admin)):
    """
    Get list of available weeks with summary statistics.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                week_ending_date,
                MIN(period_start_date) as period_start_date,
                COUNT(DISTINCT circuit_name) as circuit_count,
                SUM(total_showtimes) as total_showtimes,
                MAX(created_at) as last_updated
            FROM circuit_benchmarks
            GROUP BY week_ending_date
            ORDER BY week_ending_date DESC
            LIMIT 52
        """)

        weeks = []
        now = datetime.now()

        for row in cursor.fetchall():
            last_updated = datetime.fromisoformat(row['last_updated']) if row['last_updated'] else None

            if last_updated:
                hours_ago = (now - last_updated).total_seconds() / 3600
                if hours_ago < 24:
                    freshness = f"{int(hours_ago)} hours ago"
                else:
                    freshness = f"{int(hours_ago / 24)} days ago"
            else:
                freshness = "Unknown"

            weeks.append(WeekSummary(
                week_ending_date=row['week_ending_date'],
                period_start_date=row['period_start_date'] or "",
                circuit_count=row['circuit_count'],
                total_showtimes=row['total_showtimes'],
                data_freshness=freshness
            ))

        return weeks

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return []
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/circuit-benchmarks/{week_ending_date}")
async def get_week_benchmarks(week_ending_date: str, current_user: dict = Depends(require_read_admin)):
    """
    Get all circuit benchmarks for a specific week.

    Args:
        week_ending_date: The Thursday that ends the Friday-Thursday week (YYYY-MM-DD)
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT * FROM circuit_benchmarks
            WHERE week_ending_date = ?
            ORDER BY total_showtimes DESC
        """, [week_ending_date])

        rows = cursor.fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail=f"No data for week ending {week_ending_date}")

        benchmarks = [dict(row) for row in rows]

        # Calculate aggregates
        total_showtimes = sum(b['total_showtimes'] for b in benchmarks)
        total_theaters = sum(b['total_theaters'] for b in benchmarks)

        return {
            "week_ending_date": week_ending_date,
            "circuit_count": len(benchmarks),
            "total_showtimes": total_showtimes,
            "total_theaters": total_theaters,
            "benchmarks": benchmarks
        }

    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            raise HTTPException(status_code=404, detail="Circuit benchmarks table not initialized")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/circuit-benchmarks/sync", response_model=SyncStatus)
async def trigger_sync(background_tasks: BackgroundTasks, current_user: dict = Depends(require_operator)):
    """
    Trigger an EntTelligence sync for circuit benchmark data.

    This runs in the background and pulls the latest data from EntTelligence API.
    Note: EntTelligence data is only updated at 2 AM CT daily.
    """
    if not config.ENTTELLIGENCE_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="EntTelligence integration is not enabled. Set ENTTELLIGENCE_ENABLED=true"
        )

    if not config.ENTTELLIGENCE_TOKEN_NAME or not config.ENTTELLIGENCE_TOKEN_SECRET:
        raise HTTPException(
            status_code=400,
            detail="EntTelligence credentials not configured. Set ENTTELLIGENCE_TOKEN_NAME and ENTTELLIGENCE_TOKEN_SECRET"
        )

    if config.USE_CELERY:
        from app.tasks.sync import sync_circuit_benchmarks_task
        task = sync_circuit_benchmarks_task.delay()
        return SyncStatus(
            status="triggered",
            message="Circuit benchmark sync task initiated via Celery",
            task_id=task.id
        )

    # Add sync task to background
    background_tasks.add_task(run_circuit_sync)

    return SyncStatus(
        status="started",
        message="Circuit benchmark sync started in background",
        records_synced=0
    )


async def run_circuit_sync():
    """Background task to aggregate circuit benchmarks from enttelligence_price_cache.

    Scoped to theaters defined in markets.json (204 theaters across 57 Marcus markets).
    Uses market_scope_service to resolve market theater names against EntTelligence names.
    Groups data into Fri-Thu weeks and calculates per-circuit metrics.
    """
    from api.services.market_scope_service import get_in_market_enttelligence_names

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Step 1: Resolve market theater names to EntTelligence names
        in_market_ent_names = get_in_market_enttelligence_names(conn)
        if not in_market_ent_names:
            print("[CircuitSync] No market theaters matched in EntTelligence cache")
            return

        ent_names_list = sorted(in_market_ent_names)
        placeholders = ",".join("?" * len(ent_names_list))
        print(f"[CircuitSync] Resolved {len(ent_names_list)} market theaters in EntTelligence")

        # Step 2: Discover circuits from matched theater names only
        cursor.execute(f"""
            SELECT DISTINCT circuit_name
            FROM enttelligence_price_cache
            WHERE theater_name IN ({placeholders})
              AND circuit_name IS NOT NULL
        """, ent_names_list)
        our_circuits = [r[0] for r in cursor.fetchall()]

        if not our_circuits:
            print("[CircuitSync] No circuits found for matched market theaters")
            return

        print(f"[CircuitSync] Found {len(our_circuits)} circuits in our markets")

        # Step 3: Get date range from matched theaters only
        cursor.execute(f"""
            SELECT MIN(play_date), MAX(play_date)
            FROM enttelligence_price_cache
            WHERE theater_name IN ({placeholders})
        """, ent_names_list)
        date_range = cursor.fetchone()
        if not date_range or not date_range[0]:
            print("[CircuitSync] No data in enttelligence_price_cache for market theaters")
            return

        min_date = datetime.strptime(date_range[0], "%Y-%m-%d").date()
        max_date = datetime.strptime(date_range[1], "%Y-%m-%d").date()

        # Generate Fri-Thu week boundaries
        days_since_friday = (min_date.weekday() - 4) % 7
        week_start = min_date - timedelta(days=days_since_friday)

        records_synced = 0

        while week_start <= max_date:
            week_end = week_start + timedelta(days=6)  # Thursday
            period_start = week_start.isoformat()
            period_end = week_end.isoformat()

            for circuit in our_circuits:
                # Aggregate metrics for this circuit + week, limited to market theaters
                cursor.execute(f"""
                    SELECT
                        COUNT(DISTINCT theater_name || '|' || play_date || '|' || showtime || '|' || film_title) as total_showtimes,
                        COUNT(DISTINCT theater_name) as total_theaters,
                        COUNT(DISTINCT film_title) as total_films,
                        SUM(CASE WHEN capacity IS NOT NULL THEN capacity ELSE 0 END) as total_capacity,
                        -- Format percentages
                        ROUND(100.0 * SUM(CASE WHEN format = '2D' THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 1) as format_standard_pct,
                        ROUND(100.0 * SUM(CASE WHEN format LIKE '%IMAX%' THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 1) as format_imax_pct,
                        ROUND(100.0 * SUM(CASE WHEN format LIKE '%Dolby%' OR format LIKE '%ATMOS%' THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 1) as format_dolby_pct,
                        ROUND(100.0 * SUM(CASE WHEN format = '3D' THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 1) as format_3d_pct,
                        ROUND(100.0 * SUM(CASE WHEN format NOT IN ('2D', '3D') AND format NOT LIKE '%IMAX%' AND format NOT LIKE '%Dolby%' AND format NOT LIKE '%ATMOS%' THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 1) as format_other_premium_pct,
                        -- Daypart percentages (matinee < 17:00, evening 17:00-21:00, late >= 21:00)
                        ROUND(100.0 * SUM(CASE WHEN showtime < '17:00' THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 1) as daypart_matinee_pct,
                        ROUND(100.0 * SUM(CASE WHEN showtime >= '17:00' AND showtime < '21:00' THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 1) as daypart_evening_pct,
                        ROUND(100.0 * SUM(CASE WHEN showtime >= '21:00' THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 1) as daypart_late_pct,
                        -- Pricing (only Adult ticket type, exclude $0)
                        ROUND(AVG(CASE WHEN ticket_type = 'Adult' AND price > 0 THEN price END), 2) as avg_price_general,
                        ROUND(AVG(CASE WHEN ticket_type = 'Child' AND price > 0 THEN price END), 2) as avg_price_child,
                        ROUND(AVG(CASE WHEN ticket_type = 'Senior' AND price > 0 THEN price END), 2) as avg_price_senior
                    FROM enttelligence_price_cache
                    WHERE circuit_name = ?
                      AND play_date >= ? AND play_date <= ?
                      AND theater_name IN ({placeholders})
                """, [circuit, period_start, period_end] + ent_names_list)

                row = cursor.fetchone()
                if not row or row['total_showtimes'] == 0:
                    continue

                total_theaters = row['total_theaters'] or 0
                total_films = row['total_films'] or 0
                total_showtimes = row['total_showtimes'] or 0

                # PLF = IMAX + Dolby + 3D + other premium
                plf_pct = round(
                    (row['format_imax_pct'] or 0) +
                    (row['format_dolby_pct'] or 0) +
                    (row['format_3d_pct'] or 0) +
                    (row['format_other_premium_pct'] or 0), 1
                )

                cursor.execute("""
                    INSERT OR REPLACE INTO circuit_benchmarks (
                        circuit_name, week_ending_date, period_start_date,
                        total_showtimes, total_capacity, total_theaters, total_films,
                        avg_screens_per_film, avg_showtimes_per_theater,
                        format_standard_pct, format_imax_pct, format_dolby_pct,
                        format_3d_pct, format_other_premium_pct, plf_total_pct,
                        daypart_matinee_pct, daypart_evening_pct, daypart_late_pct,
                        avg_price_general, avg_price_child, avg_price_senior,
                        data_source, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'enttelligence', datetime('now'))
                """, [
                    circuit, period_end, period_start,
                    total_showtimes, row['total_capacity'] or 0, total_theaters, total_films,
                    round(total_showtimes / max(total_films, 1), 1),
                    round(total_showtimes / max(total_theaters, 1), 1),
                    row['format_standard_pct'] or 0, row['format_imax_pct'] or 0,
                    row['format_dolby_pct'] or 0, row['format_3d_pct'] or 0,
                    row['format_other_premium_pct'] or 0, plf_pct,
                    row['daypart_matinee_pct'] or 0, row['daypart_evening_pct'] or 0,
                    row['daypart_late_pct'] or 0,
                    row['avg_price_general'], row['avg_price_child'], row['avg_price_senior'],
                ])
                records_synced += 1

            week_start += timedelta(days=7)

        conn.commit()
        print(f"[CircuitSync] Done — {records_synced} benchmark records created")

    except Exception as e:
        print(f"[CircuitSync] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


@router.get("/circuit-benchmarks/compare")
async def compare_circuits(
    circuits: str = Query(..., description="Comma-separated circuit names"),
    week_ending_date: Optional[str] = Query(None, description="Week to compare (defaults to latest)")
):
    """
    Compare multiple circuits side-by-side for a given week.
    """
    circuit_list = [c.strip() for c in circuits.split(",")]

    if len(circuit_list) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 circuits to compare")

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Get latest week if not specified
        if not week_ending_date:
            cursor.execute("SELECT MAX(week_ending_date) FROM circuit_benchmarks")
            result = cursor.fetchone()
            if not result or not result[0]:
                raise HTTPException(status_code=404, detail="No benchmark data available")
            week_ending_date = result[0]

        # Get data for each circuit
        placeholders = ",".join("?" * len(circuit_list))
        cursor.execute(f"""
            SELECT * FROM circuit_benchmarks
            WHERE week_ending_date = ? AND circuit_name IN ({placeholders})
        """, [week_ending_date] + circuit_list)

        rows = cursor.fetchall()
        benchmarks = {row['circuit_name']: dict(row) for row in rows}

        # Build comparison
        comparison = {
            "week_ending_date": week_ending_date,
            "circuits": benchmarks,
            "metrics_comparison": {
                "total_showtimes": {name: data.get('total_showtimes', 0) for name, data in benchmarks.items()},
                "plf_total_pct": {name: data.get('plf_total_pct', 0) for name, data in benchmarks.items()},
                "avg_showtimes_per_theater": {name: data.get('avg_showtimes_per_theater', 0) for name, data in benchmarks.items()},
            }
        }

        return comparison

    finally:
        conn.close()
