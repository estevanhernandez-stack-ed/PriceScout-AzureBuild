"""
Reports API Router

Endpoints for generating competitive intelligence reports (PDF, HTML, Excel).

Endpoints:
    POST   /api/v1/selection-analysis            - Generate selection analysis report
    POST   /api/v1/showtime-view/html            - Generate showtime view as HTML
    POST   /api/v1/showtime-view/pdf             - Generate showtime view as PDF
    GET    /api/v1/daily-lineup                   - Get daily lineup data
    GET    /api/v1/operating-hours                - Get operating hours comparison
    GET    /api/v1/plf-formats                    - Get PLF (premium large format) data
"""

from typing import Any, Dict, List, Optional
import logging
import io

logger = logging.getLogger(__name__)
import pandas as pd
from datetime import datetime
import time
from sqlalchemy import func
from fastapi import APIRouter, HTTPException, Query, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse, Response

from api.schemas import SelectionAnalysisRequest, ShowtimeViewRequest
from api.unified_auth import require_auth, AuthData

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
from app.db_session import get_session
from app.db_models import Showing, Film
from app import config

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
        from app.db.film_enrichment import backfill_film_details_from_fandango_single, enrich_new_films

        # Split into sync (immediate) and async (background) groups
        SYNC_LIMIT = 10
        films_for_sync = films_missing_runtime[:SYNC_LIMIT]
        films_for_background = films_missing_runtime[SYNC_LIMIT:]

        if films_for_sync:
            logger.info(f"[DailyLineup] Sync-enriching {len(films_for_sync)} films for immediate report...")
            for film_title in films_for_sync:
                try:
                    # Individual calls ensure one failure doesn't stop the whole report
                    backfill_film_details_from_fandango_single(film_title)
                except Exception as e:
                    logger.warning(f"[DailyLineup] Failed sync-enrich for '{film_title}': {e}")

        if films_for_background:
            logger.info(f"[DailyLineup] Queuing {len(films_for_background)} remaining films for background enrichment")
            # Run the batch enrichment in the background thread
            background_tasks.add_task(enrich_new_films, films_for_background, async_mode=False)
        
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
    auth: AuthData = Depends(require_auth)
):
    """
    Get premium large format (PLF) distribution across theaters.
    Shows which premium formats (IMAX, Dolby, ScreenX, etc.) are available.
    """
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


# ============================================================================
# Scrape Results PDF Export
# ============================================================================

from pydantic import BaseModel


class ScrapeResultsPdfRequest(BaseModel):
    results: List[Dict[str, Any]]
    market_name: Optional[str] = "Market Report"
    generated_at: Optional[str] = None


def _build_scrape_results_html(req: ScrapeResultsPdfRequest) -> bytes:
    """Build a styled HTML table from flat scrape results for PDF rendering."""
    import html as html_mod
    results = req.results
    market_name = html_mod.escape(req.market_name or "Market Report")
    generated_at = html_mod.escape(req.generated_at or datetime.now().strftime("%Y-%m-%d %H:%M"))

    # Group results by theater
    theaters: Dict[str, list] = {}
    for r in results:
        theater = r.get("theater_name") or r.get("Theater Name", "Unknown")
        theaters.setdefault(theater, []).append(r)

    # Count unique films
    all_films = set()
    for r in results:
        film = r.get("film_title") or r.get("Film Title", "")
        if film:
            all_films.add(film)

    esc = html_mod.escape

    html_parts = [f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>PriceScout — {market_name}</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', Arial, sans-serif; margin: 20px; color: #1a1a2e; font-size: 11px; }}
  h1 {{ font-size: 18px; margin-bottom: 4px; color: #0f3460; }}
  .meta {{ color: #666; font-size: 10px; margin-bottom: 16px; }}
  .summary {{ display: flex; gap: 24px; margin-bottom: 16px; }}
  .summary-item {{ text-align: center; }}
  .summary-value {{ font-size: 20px; font-weight: 700; color: #0f3460; }}
  .summary-label {{ font-size: 9px; text-transform: uppercase; color: #888; }}
  h2 {{ font-size: 13px; margin: 14px 0 6px; color: #16213e; border-bottom: 1px solid #ddd; padding-bottom: 3px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 12px; }}
  th {{ background: #0f3460; color: #fff; padding: 4px 8px; text-align: left; font-size: 10px; font-weight: 600; }}
  td {{ padding: 3px 8px; border-bottom: 1px solid #eee; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  .plf {{ color: #e94560; font-weight: 600; }}
  @media print {{ body {{ margin: 0; }} }}
</style></head><body>
<h1>PriceScout — {market_name}</h1>
<div class="meta">Generated {generated_at} &bull; {len(results)} price points &bull; {len(theaters)} theaters &bull; {len(all_films)} films</div>
<div class="summary">
  <div class="summary-item"><div class="summary-value">{len(theaters)}</div><div class="summary-label">Theaters</div></div>
  <div class="summary-item"><div class="summary-value">{len(all_films)}</div><div class="summary-label">Films</div></div>
  <div class="summary-item"><div class="summary-value">{len(results)}</div><div class="summary-label">Price Points</div></div>
</div>
"""]

    for theater_name_key, rows in sorted(theaters.items()):
        html_parts.append(f'<h2>{esc(theater_name_key)} ({len(rows)} prices)</h2>')
        html_parts.append('<table><tr><th>Film</th><th>Date</th><th>Showtime</th><th>Format</th><th>Ticket Type</th><th>Price</th></tr>')
        rows.sort(key=lambda r: (
            r.get("film_title") or r.get("Film Title", ""),
            r.get("showtime") or r.get("Showtime", ""),
            r.get("ticket_type") or r.get("Ticket Type", ""),
        ))
        for r in rows:
            film = r.get("film_title") or r.get("Film Title", "")
            play_date = r.get("play_date", "")
            if hasattr(play_date, 'strftime'):
                play_date = play_date.strftime('%Y-%m-%d')
            showtime = r.get("showtime") or r.get("Showtime", "")
            fmt = r.get("format") or r.get("Format", "Standard")
            ticket = r.get("ticket_type") or r.get("Ticket Type", "")
            price = r.get("price") or r.get("Price", "")
            fmt_class = ' class="plf"' if fmt.lower() not in ('standard', '2d', '') else ''
            html_parts.append(
                f'<tr><td>{esc(str(film))}</td><td>{esc(str(play_date))}</td><td>{esc(str(showtime))}</td>'
                f'<td{fmt_class}>{esc(str(fmt))}</td><td>{esc(str(ticket))}</td><td>{esc(str(price))}</td></tr>'
            )
        html_parts.append('</table>')

    html_parts.append('</body></html>')
    return ''.join(html_parts).encode('utf-8')


@router.post("/scrape-results/pdf", response_model=None)
async def scrape_results_pdf(
    req: ScrapeResultsPdfRequest,
    request: Request,
    auth: AuthData = Depends(require_auth),
):
    """Generate a PDF summary of scrape results."""
    if not req.results:
        return validation_error(
            detail="No results provided",
            errors={"results": ["At least one result row is required"]},
            instance=str(request.url.path),
        )

    start_time = time.time()
    html_bytes = _build_scrape_results_html(req)

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            try:
                await page.set_content(html_bytes.decode('utf-8'), wait_until="networkidle")
                pdf_bytes = await page.pdf(
                    format="Letter",
                    print_background=True,
                    margin={"top": "0.4in", "bottom": "0.4in", "left": "0.4in", "right": "0.4in"},
                )
            finally:
                await browser.close()

        generation_time = time.time() - start_time
        track_report_generated(
            report_type="scrape_results_pdf",
            theater_count=len(set(
                (r.get("theater_name") or r.get("Theater Name", "")) for r in req.results
            )),
            date_range=f"{len(req.results)} price points",
            generation_time_seconds=generation_time,
        )

        filename = f"PriceScout_{(req.market_name or 'report').replace(' ', '_')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        return pdf_generation_error(
            detail=f"PDF generation failed: {str(e)}",
            instance=str(request.url.path),
        )


# ============================================================================
# Box Office Board
# ============================================================================

# Premium format keywords (case-insensitive matching)
_PREMIUM_FORMATS = frozenset([
    'imax', 'dolby', 'dolby cinema', 'dolby atmos',
    'superscreen', 'ultrascreen', 'screenx', '4dx', 'rpx',
    'premium', 'plf', 'dbox', 'liemax', 'imax 3d',
])

# Patterns that indicate premium when found as substring
_PREMIUM_PATTERNS = ['imax', 'dolby', 'superscreen', 'ultrascreen', 'screenx', '4dx', 'rpx', 'dbox', 'plf', 'liemax', 'premium']


def _is_premium_format(fmt: str) -> bool:
    """Check if a format string indicates a premium large format."""
    if not fmt:
        return False
    lower = fmt.strip().lower()
    if lower in _PREMIUM_FORMATS:
        return True
    return any(p in lower for p in _PREMIUM_PATTERNS)


def _parse_showtime_minutes(t: str) -> int:
    """Parse a showtime string like '7:00 PM' to minutes since midnight."""
    import re
    match = re.match(r'(\d+):(\d+)\s*(AM|PM)?', t, re.IGNORECASE)
    if not match:
        return 0
    hours = int(match.group(1))
    mins = int(match.group(2))
    period = (match.group(3) or '').upper()
    if period == 'PM' and hours != 12:
        hours += 12
    if period == 'AM' and hours == 12:
        hours = 0
    return hours * 60 + mins


def _format_time_short(t: str) -> str:
    """Normalize a showtime to consistent display format like '7:00 PM'."""
    import re
    match = re.match(r'(\d+):(\d+)\s*(AM|PM)?', t, re.IGNORECASE)
    if not match:
        return t
    hours = int(match.group(1))
    mins = int(match.group(2))
    period = (match.group(3) or '').upper()
    if not period:
        period = 'AM' if hours < 12 else 'PM'
    return f"{hours}:{mins:02d} {period}"


# Resolution presets → (width_px, height_px)
_RESOLUTIONS = {
    '720p': (1280, 720),
    '1080p': (1920, 1080),
    '4k': (3840, 2160),
    'letter': (1056, 816),  # 11 x 8.5 inches at 96 DPI (landscape)
}


def _build_board_html(
    theater_name: str,
    circuit_name: Optional[str],
    date_str: str,
    premium_films: List[Dict],
    standard_films: List[Dict],
    resolution: str = '1080p',
) -> str:
    """Build self-contained HTML for the box office board.

    Args:
        theater_name: Full theater name
        circuit_name: Circuit/brand name (e.g. "Movie Tavern", "Marcus Theatres")
        date_str: Display date string (e.g. "Monday, February 02, 2026")
        premium_films: List of {title, format, showtimes: [str]}
        standard_films: List of {title, format, showtimes: [str]}
        resolution: One of '720p', '1080p', '4k', 'letter'
    """
    import html as html_mod
    esc = html_mod.escape

    w, h = _RESOLUTIONS.get(resolution, (1920, 1080))
    is_print = resolution == 'letter'

    # Scale factor relative to 1080p baseline
    scale = w / 1920

    # Font sizes (px) — scale with resolution
    title_size = round(28 * scale)
    brand_size = round(16 * scale)
    date_size = round(18 * scale)
    section_header_size = round(16 * scale)
    film_title_size = round(15 * scale)
    showtime_size = round(14 * scale)
    format_badge_size = round(11 * scale)

    # Padding
    pad = round(24 * scale)
    pad_sm = round(12 * scale)

    # Colors
    bg = '#ffffff' if is_print else '#1a1a2e'
    text_color = '#1a1a2e' if is_print else '#f0f0f0'
    brand_color = '#e63946'
    premium_bg = 'linear-gradient(135deg, #8b0000, #a00000)' if not is_print else '#8b0000'
    premium_text = '#fff'
    gold = '#ffd700'
    film_color = '#ffd700' if not is_print else '#1a1a2e'
    showtime_color = '#d0d0d0' if not is_print else '#333'
    border_color = '#333' if not is_print else '#ccc'

    # Derive brand and short theater name from the theater name itself.
    # e.g. "Movie Tavern Hulen" → brand="MOVIE TAVERN", theater="HULEN"
    #       "Marcus Addison Cinema" → brand="MARCUS", theater="ADDISON CINEMA"
    _BRAND_PREFIXES = [
        'movie tavern', 'marcus', 'amc', 'regal', 'cinemark',
        'alamo drafthouse', 'harkins', 'landmark', 'showcase',
        'bow tie', 'cinepolis', 'emagine',
    ]
    brand_display = ''
    theater_display = theater_name.upper()
    lower_theater = theater_name.lower()
    for prefix in sorted(_BRAND_PREFIXES, key=len, reverse=True):
        if lower_theater.startswith(prefix):
            brand_display = theater_name[:len(prefix)].upper()
            location_part = theater_name[len(prefix):].strip()
            if location_part:
                theater_display = location_part.upper()
            break

    # Build premium section
    premium_html = ''
    if premium_films:
        premium_items = []
        for film in premium_films:
            times = '&nbsp;&nbsp;&nbsp;'.join(esc(t) for t in film['showtimes'])
            fmt_badge = ''
            if film.get('format') and film['format'].lower() not in ('standard', '2d', ''):
                fmt_badge = f'<span style="background:{gold};color:#000;padding:2px {pad_sm//2}px;border-radius:3px;font-size:{format_badge_size}px;font-weight:700;margin-left:{pad_sm}px;">{esc(film["format"])}</span>'
            premium_items.append(
                f'<div style="display:flex;align-items:baseline;justify-content:space-between;padding:{pad_sm//2}px 0;">'
                f'<div style="font-size:{film_title_size}px;font-weight:600;color:{premium_text};">{esc(film["title"])}{fmt_badge}</div>'
                f'<div style="font-size:{showtime_size}px;color:#eee;white-space:nowrap;margin-left:{pad}px;">{times}</div>'
                f'</div>'
            )
        premium_html = f'''
        <div style="background:{premium_bg};padding:{pad}px;margin:{pad_sm}px {pad}px;border-radius:8px;">
            <div style="color:{gold};font-size:{section_header_size}px;font-weight:700;letter-spacing:2px;margin-bottom:{pad_sm}px;">
                SUPERSCREEN &amp; PREMIUM FORMATS
            </div>
            {''.join(premium_items)}
        </div>'''

    # Build standard section — two-column grid
    standard_html = ''
    if standard_films:
        std_items = []
        for film in standard_films:
            times = '&nbsp;&nbsp;&nbsp;'.join(esc(t) for t in film['showtimes'])
            fmt_badge = ''
            if film.get('format') and film['format'].lower() not in ('standard', '2d', ''):
                fmt_badge = f'<span style="background:rgba(255,255,255,0.15);color:#fff;padding:1px {pad_sm//3}px;border-radius:3px;font-size:{format_badge_size}px;margin-left:{pad_sm//2}px;">{esc(film["format"])}</span>'
            std_items.append(
                f'<div style="padding:{pad_sm//2}px 0;border-bottom:1px solid {border_color};">'
                f'<div style="font-size:{film_title_size}px;font-weight:600;color:{film_color};">{esc(film["title"])}{fmt_badge}</div>'
                f'<div style="font-size:{showtime_size}px;color:{showtime_color};margin-top:2px;">{times}</div>'
                f'</div>'
            )
        standard_html = f'''
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 {pad}px;padding:{pad_sm}px {pad}px {pad}px {pad}px;">
            {''.join(std_items)}
        </div>'''

    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Box Office Board — {esc(theater_name)}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  @media print {{
    body {{ margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
</style>
</head><body>
<div style="width:{w}px;height:{h}px;background:{bg};color:{text_color};font-family:Arial,Helvetica,sans-serif;overflow:hidden;position:relative;">
    <!-- Header -->
    <div style="display:flex;justify-content:space-between;align-items:center;padding:{pad}px {pad}px {pad_sm}px {pad}px;border-bottom:2px solid {brand_color};">
        <div>
            {f'<div style="color:{brand_color};font-size:{brand_size}px;font-weight:700;letter-spacing:3px;">{esc(brand_display)}</div>' if brand_display else ''}
            <div style="font-size:{title_size}px;font-weight:800;letter-spacing:1px;">{esc(theater_display)}</div>
        </div>
        <div style="font-size:{date_size}px;text-align:right;">{esc(date_str)}</div>
    </div>

    {premium_html}
    {standard_html}
</div>
</body></html>'''


@router.get("/box-office-board", response_model=None)
async def box_office_board(
    request: Request,
    theater: str = Query(..., description="Theater name (exact match)"),
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    resolution: str = Query("1080p", description="Resolution: 720p, 1080p, 4k, letter"),
    output_format: str = Query("html", description="Output: html or image"),
    auth: AuthData = Depends(require_auth),
):
    """
    Generate a box office board for digital signage or printing.

    Returns a self-contained HTML page (or PNG image) showing the day's schedule
    with premium formats highlighted in a separate section.
    """
    import re as re_mod
    from app.db_models import TheaterMetadata

    # Validate resolution
    if resolution not in _RESOLUTIONS:
        return validation_error(
            detail=f"Invalid resolution. Must be one of: {', '.join(_RESOLUTIONS.keys())}",
            errors={"resolution": [f"Got '{resolution}'"]},
            instance=str(request.url.path),
        )

    # Parse date
    try:
        play_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return validation_error(
            detail="Invalid date format",
            errors={"date": ["Must be in YYYY-MM-DD format"]},
            instance=str(request.url.path),
        )

    # Format the date for display
    date_display = play_date.strftime('%A, %B %d, %Y')

    # Query showings for this theater + date
    with get_session() as session:
        query = session.query(
            Showing.film_title,
            Showing.showtime,
            Showing.format,
        )
        if config.CURRENT_COMPANY_ID:
            query = query.filter(Showing.company_id == config.CURRENT_COMPANY_ID)

        query = query.filter(
            Showing.theater_name == theater,
            Showing.play_date == play_date,
        ).order_by(Showing.showtime, Showing.film_title)

        results = query.all()

        if not results:
            return not_found_error(
                detail=f"No showtimes found for {theater} on {date}",
                instance=str(request.url.path),
                resource_type="showtimes",
            )

        # Look up circuit name
        circuit_name = None
        meta = session.query(TheaterMetadata.circuit_name).filter(
            TheaterMetadata.theater_name == theater,
        ).first()
        if meta and meta.circuit_name:
            circuit_name = meta.circuit_name

    # Group showtimes by film+format, separating premium vs standard
    # Key: (film_title, format) → list of showtime strings
    film_groups: Dict[tuple, List[str]] = {}
    for row in results:
        key = (row.film_title, row.format or 'Standard')
        film_groups.setdefault(key, [])
        st = _format_time_short(row.showtime)
        if st not in film_groups[key]:
            film_groups[key].append(st)

    # Sort showtimes within each group
    for key in film_groups:
        film_groups[key].sort(key=_parse_showtime_minutes)

    # Separate into premium and standard
    premium_films = []
    standard_films = []
    for (title, fmt), showtimes in sorted(film_groups.items(), key=lambda x: x[0][0]):
        entry = {'title': title, 'format': fmt, 'showtimes': showtimes}
        if _is_premium_format(fmt):
            premium_films.append(entry)
        else:
            standard_films.append(entry)

    # Generate HTML
    html_content = _build_board_html(
        theater_name=theater,
        circuit_name=circuit_name,
        date_str=date_display,
        premium_films=premium_films,
        standard_films=standard_films,
        resolution=resolution,
    )

    if output_format == 'image':
        # Generate PNG screenshot using Playwright
        try:
            from playwright.async_api import async_playwright

            w, h = _RESOLUTIONS[resolution]
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page(viewport={'width': w, 'height': h})
                try:
                    await page.set_content(html_content, wait_until='networkidle')
                    png_bytes = await page.screenshot(
                        type='png',
                        clip={'x': 0, 'y': 0, 'width': w, 'height': h},
                    )
                finally:
                    await browser.close()

            filename = f"BoxOfficeBoard_{theater.replace(' ', '_')}_{date}_{resolution}.png"
            return Response(
                content=png_bytes,
                media_type='image/png',
                headers={'Content-Disposition': f'attachment; filename={filename}'},
            )
        except Exception as e:
            logger.error(f"Board image generation failed: {e}")
            return pdf_generation_error(
                detail=f"Image generation failed: {str(e)}",
                instance=str(request.url.path),
            )

    # Default: return HTML
    return Response(content=html_content.encode('utf-8'), media_type='text/html')
