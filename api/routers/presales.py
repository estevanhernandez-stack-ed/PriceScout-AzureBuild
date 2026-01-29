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


def get_db_connection():
    """Get database connection based on environment."""
    # Use the main pricescout.db database
    db_path = config.DB_FILE or os.path.join(config.PROJECT_DIR, 'pricescout.db')
    return sqlite3.connect(db_path)


@router.get("/presales", response_model=List[PresaleSnapshot])
async def list_presales(
    film_title: Optional[str] = Query(None, description="Filter by film title"),
    circuit_name: Optional[str] = Query(None, description="Filter by circuit"),
    snapshot_date: Optional[str] = Query(None, description="Filter by snapshot date"),
    days_before_release: Optional[int] = Query(None, description="Filter by days before release"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    List presale snapshot data with optional filtering.

    Data is sourced from EntTelligence and updated daily at 2 AM CT.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        where_clauses = []
        params = []

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

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

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


@router.get("/presales/films")
async def list_presale_films():
    """
    Get list of all films with presale data and summary statistics.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                film_title,
                release_date,
                COUNT(DISTINCT circuit_name) as total_circuits,
                MAX(total_tickets_sold) as max_tickets,
                MAX(total_revenue) as max_revenue,
                MIN(days_before_release) as min_days_out,
                MAX(snapshot_date) as latest_snapshot
            FROM circuit_presales
            GROUP BY film_title, release_date
            ORDER BY release_date DESC, film_title
        """)

        films = []
        for row in cursor.fetchall():
            films.append({
                "film_title": row['film_title'],
                "release_date": row['release_date'],
                "total_circuits": row['total_circuits'],
                "current_tickets": row['max_tickets'] or 0,
                "current_revenue": row['max_revenue'] or 0,
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


@router.get("/presales/{film_title}", response_model=PresaleTrajectory)
async def get_film_trajectory(
    film_title: str,
    circuit_name: Optional[str] = Query(None, description="Filter by specific circuit")
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
        # Build query
        if circuit_name:
            cursor.execute("""
                SELECT * FROM circuit_presales
                WHERE film_title = ? AND circuit_name = ?
                ORDER BY snapshot_date ASC
            """, [film_title, circuit_name])
        else:
            # Get aggregated across all circuits
            cursor.execute("""
                SELECT * FROM circuit_presales
                WHERE film_title = ?
                ORDER BY snapshot_date ASC
            """, [film_title])

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


@router.get("/presales/velocity/{film_title}", response_model=List[VelocityMetrics])
async def get_velocity_metrics(film_title: str):
    """
    Get daily velocity metrics for a film showing acceleration/deceleration.

    Velocity = tickets sold per day
    Velocity change = percentage change from previous day
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                film_title,
                circuit_name,
                snapshot_date,
                total_tickets_sold,
                total_revenue,
                days_before_release
            FROM circuit_presales
            WHERE film_title = ?
            ORDER BY circuit_name, snapshot_date ASC
        """, [film_title])

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


@router.get("/presales/compare")
async def compare_circuits_presales(
    film_title: str = Query(..., description="Film to compare"),
    circuits: Optional[str] = Query(None, description="Comma-separated circuit names (defaults to all)")
):
    """
    Compare presale performance across circuits for a specific film.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
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
                WHERE film_title = ? AND circuit_name IN ({placeholders})
                GROUP BY circuit_name
                ORDER BY total_tickets DESC
            """, [film_title] + circuit_list)
        else:
            cursor.execute("""
                SELECT
                    circuit_name,
                    MAX(total_tickets_sold) as total_tickets,
                    MAX(total_revenue) as total_revenue,
                    MAX(total_theaters) as theaters,
                    MAX(avg_ticket_price) as avg_price,
                    MIN(days_before_release) as days_out
                FROM circuit_presales
                WHERE film_title = ?
                GROUP BY circuit_name
                ORDER BY total_tickets DESC
            """, [film_title])

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
async def trigger_presale_sync(background_tasks: BackgroundTasks):
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
        from presale_reconciliation import sync_presales
        sync_presales()
    except ImportError:
        print("Warning: presale_reconciliation not available")
    except Exception as e:
        print(f"Presale sync error: {e}")
