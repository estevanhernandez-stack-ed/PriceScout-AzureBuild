"""
Analytics API Router

Specialized endpoints for advanced data analysis and visualization.
"""

import logging
from datetime import date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Security, Query, HTTPException
from pydantic import BaseModel
from api.routers.auth import get_current_user, User
from app.db_session import get_session
from sqlalchemy import text

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class DashboardStats(BaseModel):
    """Dashboard overview statistics"""
    total_price_checks: int
    price_checks_change_pct: float  # vs previous period
    active_alerts: int
    alerts_change: int  # vs previous period
    avg_price: float
    price_change_pct: float  # vs previous period
    total_theaters: int
    total_films: int


class ScrapeActivityEntry(BaseModel):
    """Scrape activity for a day of week"""
    day_name: str  # Mon, Tue, etc.
    day_index: int  # 0=Mon, 6=Sun
    scrape_count: int
    records_scraped: int


class PLFDistributionEntry(BaseModel):
    theater_name: str
    format_group: str  # "Standard", "PLF"
    specific_format: str # "Standard", "IMAX", "Dolby", "3D", etc.
    avg_price: float
    showing_count: int
    pct_of_total: float

class PriceTrendPoint(BaseModel):
    date: date
    standard_avg: Optional[float] = None
    plf_avg: Optional[float] = None
    imax_avg: Optional[float] = None
    dolby_avg: Optional[float] = None
    showing_count: int

# ============================================================================
# DASHBOARD ENDPOINTS
# ============================================================================

@router.get("/analytics/dashboard-stats", response_model=DashboardStats, tags=["Dashboard"])
async def get_dashboard_stats(
    days: int = Query(30, ge=1, le=365, description="Period in days for comparison"),
    current_user: User = Security(get_current_user, scopes=["read:prices"])
):
    """
    Get overview statistics for the intelligence dashboard.
    Compares current period against previous period of same length.
    """
    try:
        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
            today = date.today()
            current_start = today - timedelta(days=days)
            prev_start = current_start - timedelta(days=days)
            prev_end = current_start - timedelta(days=1)

            # Price checks count (current period)
            price_count_query = """
                SELECT COUNT(*) FROM prices
                WHERE company_id = :company_id AND created_at >= :start_date
            """
            current_prices = session.execute(
                text(price_count_query),
                {"company_id": company_id, "start_date": current_start}
            ).scalar() or 0

            # Price checks count (previous period)
            prev_prices = session.execute(
                text("""
                    SELECT COUNT(*) FROM prices
                    WHERE company_id = :company_id
                      AND created_at >= :start_date AND created_at <= :end_date
                """),
                {"company_id": company_id, "start_date": prev_start, "end_date": prev_end}
            ).scalar() or 0

            # Calculate price change percentage
            price_change_pct = 0.0
            if prev_prices > 0:
                price_change_pct = round(((current_prices - prev_prices) / prev_prices) * 100, 1)

            # Active alerts count
            alerts_query = """
                SELECT COUNT(*) FROM price_alerts
                WHERE company_id = :company_id AND is_acknowledged = 0
            """
            active_alerts = session.execute(
                text(alerts_query), {"company_id": company_id}
            ).scalar() or 0

            # Alerts from previous period (for comparison)
            prev_alerts = session.execute(
                text("""
                    SELECT COUNT(*) FROM price_alerts
                    WHERE company_id = :company_id
                      AND triggered_at >= :start_date AND triggered_at <= :end_date
                """),
                {"company_id": company_id, "start_date": prev_start, "end_date": prev_end}
            ).scalar() or 0

            # Average price (current period)
            avg_price_query = """
                SELECT AVG(price) FROM prices
                WHERE company_id = :company_id AND created_at >= :start_date
            """
            current_avg = session.execute(
                text(avg_price_query),
                {"company_id": company_id, "start_date": current_start}
            ).scalar()
            current_avg = float(current_avg) if current_avg else 0.0

            # Average price (previous period)
            prev_avg = session.execute(
                text("""
                    SELECT AVG(price) FROM prices
                    WHERE company_id = :company_id
                      AND created_at >= :start_date AND created_at <= :end_date
                """),
                {"company_id": company_id, "start_date": prev_start, "end_date": prev_end}
            ).scalar()
            prev_avg = float(prev_avg) if prev_avg else 0.0

            # Avg price change
            avg_price_change = 0.0
            if prev_avg > 0:
                avg_price_change = round(((current_avg - prev_avg) / prev_avg) * 100, 1)

            # Total unique theaters
            theaters_query = """
                SELECT COUNT(DISTINCT theater_name) FROM showings
                WHERE company_id = :company_id AND play_date >= :start_date
            """
            total_theaters = session.execute(
                text(theaters_query),
                {"company_id": company_id, "start_date": current_start}
            ).scalar() or 0

            # Total unique films
            films_query = """
                SELECT COUNT(DISTINCT film_title) FROM showings
                WHERE company_id = :company_id AND play_date >= :start_date
            """
            total_films = session.execute(
                text(films_query),
                {"company_id": company_id, "start_date": current_start}
            ).scalar() or 0

            return DashboardStats(
                total_price_checks=current_prices,
                price_checks_change_pct=price_change_pct,
                active_alerts=active_alerts,
                alerts_change=active_alerts - prev_alerts,
                avg_price=round(current_avg, 2),
                price_change_pct=avg_price_change,
                total_theaters=total_theaters,
                total_films=total_films
            )

    except Exception as e:
        logger.exception(f"Error getting dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/scrape-activity", response_model=List[ScrapeActivityEntry], tags=["Dashboard"])
async def get_scrape_activity(
    days: int = Query(30, ge=1, le=365, description="Days of history"),
    current_user: User = Security(get_current_user, scopes=["read:prices"])
):
    """
    Get scrape activity grouped by day of week.
    Returns counts for Mon-Sun based on historical data.
    """
    try:
        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
            start_date = date.today() - timedelta(days=days)

            # SQLite uses strftime, SQL Server uses DATEPART
            # Try SQLite first, fall back to generic
            try:
                # SQLite version
                query = """
                    SELECT
                        CAST(strftime('%w', run_timestamp) AS INTEGER) as day_num,
                        COUNT(*) as scrape_count,
                        COALESCE(SUM(records_scraped), 0) as records_scraped
                    FROM scrape_runs
                    WHERE company_id = :company_id
                      AND run_timestamp >= :start_date
                      AND status = 'completed'
                    GROUP BY day_num
                """
                result = session.execute(
                    text(query),
                    {"company_id": company_id, "start_date": start_date}
                )
                rows = result.fetchall()
            except Exception:
                # Fallback - just return empty/default data
                rows = []

            # Map day numbers to names (SQLite: 0=Sunday, 6=Saturday)
            # We want 0=Monday, 6=Sunday for display
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

            # Initialize all days with zeros
            activity = {i: {'count': 0, 'records': 0} for i in range(7)}

            for row in rows:
                # SQLite day: 0=Sunday, 1=Monday, ... 6=Saturday
                # Convert to: 0=Monday, 1=Tuesday, ... 6=Sunday
                sqlite_day = row[0]
                if sqlite_day == 0:  # Sunday
                    display_day = 6
                else:
                    display_day = sqlite_day - 1

                activity[display_day] = {
                    'count': row[1],
                    'records': row[2]
                }

            return [
                ScrapeActivityEntry(
                    day_name=day_names[i],
                    day_index=i,
                    scrape_count=activity[i]['count'],
                    records_scraped=activity[i]['records']
                )
                for i in range(7)
            ]

    except Exception as e:
        logger.exception(f"Error getting scrape activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/analytics/plf-distribution", response_model=List[PLFDistributionEntry], tags=["Analytics"])
async def get_plf_distribution(
    market: Optional[str] = Query(None, description="Filter by market"),
    days: int = Query(30, ge=1, le=365, description="Days of history to analyze"),
    current_user: User = Security(get_current_user, scopes=["read:prices"])
):
    """
    Analyze the distribution of PLF vs Standard showings and their relative pricing.
    """
    try:
        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
            start_date = date.today() - timedelta(days=days)
            
            # Subquery to classify formats
            classify_sql = """
                SELECT 
                    s.theater_name,
                    CASE 
                        WHEN s.format LIKE '%IMAX%' OR s.format LIKE '%Dolby%' OR s.format LIKE '%PLF%' 
                             OR s.format LIKE '%XD%' OR s.format LIKE '%RPX%' OR s.format LIKE '%Superscreen%'
                             OR s.is_plf = 1 THEN 'PLF'
                        ELSE 'Standard'
                    END as format_group,
                    CASE
                        WHEN s.format LIKE '%IMAX%' THEN 'IMAX'
                        WHEN s.format LIKE '%Dolby%' OR s.format LIKE '%Atmos%' THEN 'Dolby'
                        WHEN s.format LIKE '%3D%' THEN '3D'
                        WHEN s.format LIKE '%4DX%' THEN '4DX'
                        WHEN s.format LIKE '%ScreenX%' THEN 'ScreenX'
                        WHEN s.format IS NULL OR s.format = '' OR s.format = 'Standard' OR s.format = '2D' THEN 'Standard'
                        ELSE 'Other PLF'
                    END as specific_format,
                    p.price
                FROM prices p
                JOIN showings s ON p.showing_id = s.showing_id
                WHERE p.company_id = :company_id
                  AND s.play_date >= :start_date
            """
            
            # Aggregate by group and format
            query = f"""
                WITH ClassifiedPrices AS ({classify_sql})
                SELECT 
                    theater_name,
                    format_group,
                    specific_format,
                    AVG(price) as avg_price,
                    COUNT(*) as showing_count,
                    CAST(COUNT(*) AS FLOAT) / SUM(COUNT(*)) OVER (PARTITION BY theater_name) * 100 as pct_of_total
                FROM ClassifiedPrices
                GROUP BY theater_name, format_group, specific_format
                ORDER BY theater_name, format_group DESC, specific_format
            """
            
            params = {"company_id": company_id, "start_date": start_date}
            result = session.execute(text(query), params)
            
            distribution = []
            for row in result.fetchall():
                distribution.append(PLFDistributionEntry(
                    theater_name=row[0],
                    format_group=row[1],
                    specific_format=row[2],
                    avg_price=round(float(row[3]), 2),
                    showing_count=row[4],
                    pct_of_total=round(float(row[5]), 1)
                ))
                
            return distribution
    except Exception as e:
        logger.exception(f"Error calculating PLF distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/price-trends", response_model=List[PriceTrendPoint], tags=["Analytics"])
async def get_price_trends(
    theater_name: str,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Security(get_current_user, scopes=["read:prices"])
):
    """
    Returns time-series data for pricing trends, broken down by format categories.
    Ideal for multi-line charts.
    """
    try:
        with get_session() as session:
            company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
            start_date = date.today() - timedelta(days=days)
            
            query = """
                SELECT 
                    s.play_date,
                    AVG(CASE WHEN s.format IS NULL OR s.format IN ('', 'Standard', '2D') THEN p.price END) as standard_avg,
                    AVG(CASE WHEN s.is_plf = 1 OR s.format LIKE '%IMAX%' OR s.format LIKE '%Dolby%' OR s.format LIKE '%PLF%' THEN p.price END) as plf_avg,
                    AVG(CASE WHEN s.format LIKE '%IMAX%' THEN p.price END) as imax_avg,
                    AVG(CASE WHEN s.format LIKE '%Dolby%' THEN p.price END) as dolby_avg,
                    COUNT(*) as showing_count
                FROM prices p
                JOIN showings s ON p.showing_id = s.showing_id
                WHERE p.company_id = :company_id
                  AND s.theater_name = :theater_name
                  AND s.play_date >= :start_date
                GROUP BY s.play_date
                ORDER BY s.play_date
            """
            
            params = {
                "company_id": company_id, 
                "theater_name": theater_name,
                "start_date": start_date
            }
            result = session.execute(text(query), params)
            
            trends = []
            for row in result.fetchall():
                trends.append(PriceTrendPoint(
                    date=row[0],
                    standard_avg=round(float(row[1]), 2) if row[1] is not None else None,
                    plf_avg=round(float(row[2]), 2) if row[2] is not None else None,
                    imax_avg=round(float(row[3]), 2) if row[3] is not None else None,
                    dolby_avg=round(float(row[4]), 2) if row[4] is not None else None,
                    showing_count=row[5]
                ))
                
            return trends
    except Exception as e:
        logger.exception(f"Error calculating price trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))
