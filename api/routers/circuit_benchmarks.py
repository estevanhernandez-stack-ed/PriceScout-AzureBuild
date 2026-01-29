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
    """Get database connection based on environment."""
    # Use the main pricescout.db database
    db_path = config.DB_FILE or os.path.join(config.PROJECT_DIR, 'pricescout.db')
    return sqlite3.connect(db_path)


@router.get("/circuit-benchmarks", response_model=CircuitBenchmarkList)
async def list_circuit_benchmarks(
    week_ending_date: Optional[str] = Query(None, description="Filter by week ending date (YYYY-MM-DD)"),
    circuit_name: Optional[str] = Query(None, description="Filter by circuit name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
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
async def list_available_weeks():
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
async def get_week_benchmarks(week_ending_date: str):
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
async def trigger_sync(background_tasks: BackgroundTasks):
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
    """Background task to sync circuit benchmarks from EntTelligence."""
    try:
        from sync_engine import run_nationwide_sync
        run_nationwide_sync()
    except ImportError:
        print("Warning: sync_engine not available")
    except Exception as e:
        print(f"Sync error: {e}")


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
