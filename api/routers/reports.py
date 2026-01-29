from typing import Any, Dict
import logging
import io

logger = logging.getLogger(__name__)
import sys
import pandas as pd
from datetime import datetime
import time
from sqlalchemy import func
from fastapi import APIRouter, HTTPException, Query, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse, Response

# Ensure the app package is importable when running from repo root
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.schemas import SelectionAnalysisRequest, ShowtimeViewRequest
from api.unified_auth import require_auth, AuthData
from api.auth import verify_api_key, check_rate_limit
from api.telemetry import track_report_generated
from api.errors import (
    validation_error,
    not_found_error,
    pdf_generation_error
)

from app.utils import (
    generate_selection_analysis_report,
    to_csv,
    generate_showtime_html_report,
    generate_showtime_pdf_report,
)
from app.db_adapter import get_session, Showing, Film, config

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.post("/selection-analysis", response_model=None)
async def selection_analysis(
    req: SelectionAnalysisRequest,
    request: Request,
    format: str = Query("csv", regex="^(csv|json)$"),
    auth: AuthData = Depends(require_auth)
):
    start_time = time.time()
    df = generate_selection_analysis_report(req.selected_showtimes)
    
    # Track report generation
    generation_time = time.time() - start_time
    track_report_generated(
        report_type="selection_analysis",
        theater_count=len(req.selected_showtimes),
        date_range=f"{len(req.selected_showtimes)} showtimes",
        generation_time_seconds=generation_time
    )
    
    if format == "json":
        return JSONResponse(content={"rows": df.to_dict(orient="records") if not df.empty else []})
    # CSV default
    csv_bytes = to_csv(df)
    return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=Showtime_Selection_Analysis.csv"
    })


@router.post("/showtime-view/html", response_model=None)
async def showtime_view_html(
    req: ShowtimeViewRequest,
    request: Request,
    auth: AuthData = Depends(require_auth)
):
    start_time = time.time()
    html_bytes = generate_showtime_html_report(
        req.all_showings,
        req.selected_films,
        req.theaters,
        (req.date_start, req.date_end),
        cache_data={},
        context_title=req.context_title,
    )
    
    # Track report generation
    generation_time = time.time() - start_time
    track_report_generated(
        report_type="showtime_view_html",
        theater_count=len(req.theaters),
        date_range=f"{req.date_start} to {req.date_end}",
        generation_time_seconds=generation_time
    )
    
    return Response(content=html_bytes, media_type="text/html")


@router.post("/showtime-view/pdf", response_model=None)
async def showtime_view_pdf(
    req: ShowtimeViewRequest,
    request: Request,
    auth: AuthData = Depends(require_auth)
):
    start_time = time.time()
    try:
        pdf_bytes = await generate_showtime_pdf_report(
            req.all_showings,
            req.selected_films,
            req.theaters,
            (req.date_start, req.date_end),
            cache_data={},
            context_title=req.context_title,
        )
        
        # Track report generation
        generation_time = time.time() - start_time
        track_report_generated(
            report_type="showtime_view_pdf",
            theater_count=len(req.theaters),
            date_range=f"{req.date_start} to {req.date_end}",
            generation_time_seconds=generation_time
        )
        
        return Response(content=pdf_bytes, media_type="application/pdf", headers={
            "Content-Disposition": "attachment; filename=Showtime_View.pdf"
        })
    except Exception as e:
        return pdf_generation_error(
            detail=f"PDF generation failed: {str(e)}",
            instance=str(request.url.path)
        )


@router.get("/daily-lineup", response_model=None)
async def daily_lineup(
    request: Request,
    background_tasks: BackgroundTasks,
    theater: str = Query(..., description="Theater name (exact match)"),
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    format: str = Query("json", regex="^(json|csv)$", description="Response format"),
    auth: AuthData = Depends(require_auth)
):
    """
    Get daily lineup for a specific theater and date.
    Returns chronologically sorted showtimes with film titles and formats.
    """
    # Parse date
    try:
        play_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return validation_error(
            detail="Invalid date format",
            errors={"date": ["Must be in YYYY-MM-DD format"]},
            instance=str(request.url.path)
        )

    # Query showings
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(
            Showing.film_title,
            Showing.showtime,
            Showing.format,
            Showing.daypart,
            Showing.is_plf,
            Film.runtime
        ).outerjoin(
            Film,
            (Showing.film_title == Film.film_title) & (Showing.company_id == Film.company_id)
        )

        if config.CURRENT_COMPANY_ID:
            query = query.filter(Showing.company_id == config.CURRENT_COMPANY_ID)

        query = query.filter(
            Showing.theater_name == theater,
            Showing.play_date == play_date
        ).order_by(Showing.showtime, Showing.film_title)

        results = query.all()

        if not results:
            return not_found_error(
                detail=f"No showtimes found for {theater} on {date}",
                instance=str(request.url.path),
                resource_type="showtimes"
            )

        # Convert to DataFrame for consistent processing
        df = pd.DataFrame(
            results,
            columns=['film_title', 'showtime', 'format', 'daypart', 'is_plf', 'runtime']
        )

    # Auto-enrich films missing runtime data
    films_missing_runtime = df[df['runtime'].isna()]['film_title'].unique().tolist()
    if films_missing_runtime:
        from app import db_adapter as database
        
        # Split into sync (immediate) and async (background) groups
        SYNC_LIMIT = 10
        films_for_sync = films_missing_runtime[:SYNC_LIMIT]
        films_for_background = films_missing_runtime[SYNC_LIMIT:]
        
        if films_for_sync:
            logger.info(f"[DailyLineup] Sync-enriching {len(films_for_sync)} films for immediate report...")
            for film_title in films_for_sync:
                try:
                    # Individual calls ensure one failure doesn't stop the whole report
                    database.backfill_film_details_from_fandango_single(film_title)
                except Exception as e:
                    logger.warning(f"[DailyLineup] Failed sync-enrich for '{film_title}': {e}")
        
        if films_for_background:
            logger.info(f"[DailyLineup] Queuing {len(films_for_background)} remaining films for background enrichment")
            # Run the batch enrichment in the background thread
            background_tasks.add_task(database.enrich_new_films, films_for_background, async_mode=False)
        
        # Re-query only if we actually did some sync enrichment
        if films_for_sync:
            with get_session() as session:
                query = session.query(
                    Showing.film_title,
                    Showing.showtime,
                    Showing.format,
                    Showing.daypart,
                    Showing.is_plf,
                    Film.runtime
                ).outerjoin(
                    Film,
                    (Showing.film_title == Film.film_title) & (Showing.company_id == Film.company_id)
                )

                if config.CURRENT_COMPANY_ID:
                    query = query.filter(Showing.company_id == config.CURRENT_COMPANY_ID)

                query = query.filter(
                    Showing.theater_name == theater,
                    Showing.play_date == play_date
                ).order_by(Showing.showtime, Showing.film_title)

                results = query.all()
                df = pd.DataFrame(
                    results,
                    columns=['film_title', 'showtime', 'format', 'daypart', 'is_plf', 'runtime']
                )

    # Format response
    if format == "json":
        rows = df.to_dict(orient="records")
        return JSONResponse(content={
            "theater": theater,
            "date": date,
            "showtime_count": len(rows),
            "showtimes": rows
        })
    
    # CSV format
    csv_data = df.to_csv(index=False).encode('utf-8')
    filename = f"daily_lineup_{theater.replace(' ', '_')}_{date}.csv"
    return StreamingResponse(
        io.BytesIO(csv_data),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/operating-hours", response_model=None)
async def operating_hours(
    request: Request,
    theater: str = Query(None, description="Theater name filter (optional)"),
    date: str = Query(None, description="Date in YYYY-MM-DD format (optional)"),
    limit: int = Query(100, description="Maximum records to return (default 100)"),
    format: str = Query("json", regex="^(json|csv)$", description="Response format"),
    auth: AuthData = Depends(require_auth)
):
    """
    Get derived operating hours (first/last showtime) per theater per date.
    Based on actual showing data in the database.
    """
    from sqlalchemy import func
    
    from app.db_models import OperatingHours
    
    with get_session() as session:
        # Build query from OperatingHours model
        query = session.query(
            OperatingHours.theater_name,
            OperatingHours.scrape_date.label('play_date'),
            OperatingHours.open_time.label('opening_time'),
            OperatingHours.close_time.label('closing_time'),
            OperatingHours.first_showtime,
            OperatingHours.last_showtime,
            OperatingHours.showtime_count
        )
        
        if config.CURRENT_COMPANY_ID:
            query = query.filter(OperatingHours.company_id == config.CURRENT_COMPANY_ID)
        
        # Optional filters
        if theater:
            query = query.filter(OperatingHours.theater_name == theater)
        if date:
            try:
                date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                query = query.filter(OperatingHours.scrape_date == date_obj)
            except ValueError:
                return validation_error(
                    detail="Invalid date format",
                    errors={"date": ["Must be in YYYY-MM-DD format"]},
                    instance=str(request.url.path)
                )

        # Order
        query = query.order_by(OperatingHours.scrape_date.desc(), OperatingHours.theater_name)

        # Apply limit to avoid long queries
        query = query.limit(limit)

        results = query.all()

        if not results:
            return not_found_error(
                detail="No operating hours data found",
                instance=str(request.url.path),
                resource_type="operating_hours"
            )
        
        # Convert to simple dict list
        data = [{
            'theater_name': r.theater_name,
            'date': r.play_date.strftime('%Y-%m-%d'),
            'opening_time': r.opening_time,
            'closing_time': r.closing_time,
            'first_showtime': r.first_showtime,
            'last_showtime': r.last_showtime,
            'total_showtimes': r.showtime_count
        } for r in results]
        
        if format == "json":
            dates = [r['date'] for r in data]
            return {
                "record_count": len(data),
                "date_range": {
                    "earliest": min(dates) if dates else None,
                    "latest": max(dates) if dates else None
                },
                "operating_hours": data
            }
        
        # CSV format - simple string building
        csv_lines = ["theater_name,date,opening_time,closing_time,first_showtime,last_showtime"]
        for r in data:
            csv_lines.append(f"{r['theater_name']},{r['date']},{r['opening_time']},{r['closing_time']},{r['first_showtime']},{r['last_showtime']}")
        csv_content = "\n".join(csv_lines).encode('utf-8')
        
        filename = f"operating_hours_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        return StreamingResponse(
            io.BytesIO(csv_content),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


@router.get("/plf-formats", response_model=None)
async def plf_formats(
    request: Request,
    date: str = Query(None, description="Date filter in YYYY-MM-DD format (optional)"),
    limit: int = Query(100, description="Maximum records to return (default 100)"),
    format: str = Query("json", regex="^(json|csv)$", description="Response format"),
    api_key_data: dict = Depends(verify_api_key)
):
    """
    Get premium large format (PLF) distribution across theaters.
    Shows which premium formats (IMAX, Dolby, ScreenX, etc.) are available.
    """
    await check_rate_limit(api_key_data, request)
    with get_session() as session:
        # Query distinct formats per theater
        query = session.query(
            Showing.theater_name,
            Showing.format,
            func.count(Showing.showing_id).label('showtime_count')
        )
        
        # Apply company filter
        if config.CURRENT_COMPANY_ID:
            query = query.filter(Showing.company_id == config.CURRENT_COMPANY_ID)
        
        # Filter for premium formats only (not Standard/2D)
        plf_formats = ['IMAX', 'Dolby', 'ScreenX', 'UltraScreen', 'SuperScreen', 
                       'IMAX 3D', 'Dolby 3D', '3D', 'DBox', 'RPX']
        query = query.filter(Showing.format.in_(plf_formats))
        
        # Optional date filter
        if date:
            try:
                date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                query = query.filter(Showing.play_date == date_obj)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Group and order
        query = query.group_by(Showing.theater_name, Showing.format)
        query = query.order_by(Showing.theater_name, Showing.format)
        
        # Apply limit
        query = query.limit(limit)
        
        results = query.all()
        
        if not results:
            raise HTTPException(status_code=404, detail="No PLF format data found")
        
        # Convert to simple dict list (no pandas)
        data = [{
            'theater_name': r.theater_name,
            'format': r.format,
            'showtime_count': r.showtime_count
        } for r in results]
        
        if format == "json":
            # Group by theater manually
            theaters_plf = {}
            for item in data:
                theater = item['theater_name']
                if theater not in theaters_plf:
                    theaters_plf[theater] = []
                theaters_plf[theater].append({
                    'format': item['format'],
                    'showtime_count': item['showtime_count']
                })
            
            total_showtimes = sum(item['showtime_count'] for item in data)
            
            return {
                "theater_count": len(theaters_plf),
                "total_plf_showtimes": total_showtimes,
                "theaters": theaters_plf
            }
        
        # CSV format - simple string building
        csv_lines = ["theater_name,format,showtime_count"]
        for r in data:
            csv_lines.append(f"{r['theater_name']},{r['format']},{r['showtime_count']}")
        csv_content = "\n".join(csv_lines).encode('utf-8')
        
        date_suffix = f"_{date}" if date else ""
        filename = f"plf_formats{date_suffix}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        return StreamingResponse(
            io.BytesIO(csv_content),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
