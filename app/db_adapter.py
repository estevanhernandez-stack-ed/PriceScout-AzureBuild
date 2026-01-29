"""
Database Adapter Layer for PriceScout
Version: 1.0.0
Date: November 13, 2025

This module provides a compatibility layer between legacy sqlite3 code and SQLAlchemy ORM.
It maintains the same function signatures as database.py while using SQLAlchemy underneath.

Usage:
    # Drop-in replacement for old database.py imports
    from app.db_adapter import get_dates_for_theaters, get_data_for_trend_report
    
    # Works exactly like before
    dates = get_dates_for_theaters(['Theater 1', 'Theater 2'])
"""

import pandas as pd
from datetime import datetime, UTC
from contextlib import contextmanager
from sqlalchemy import text, and_, or_, func
from app.db_session import get_session, get_engine, legacy_db_connection
from app.db_models import (
    Company, User, ScrapeRun, ScrapeCheckpoint, Showing, Price, Film,
    OperatingHours, UnmatchedFilm, IgnoredFilm, UnmatchedTicketType,
    TheaterMetadata, MarketEvent, TheaterOperatingHours
)
from app import config
import asyncio
from thefuzz import fuzz
import concurrent.futures
import re


def _parse_time_to_minutes(time_str):
    """
    Parse time string like '10:30 AM' or '10:30am' to minutes since midnight.
    Used for comparing operating hours in high water mark logic.
    """
    if not time_str or time_str in ('N/A', 'N\\A', None):
        return None
    match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?', str(time_str).strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    meridiem = match.group(3)
    if meridiem:
        meridiem = meridiem.upper()
        if meridiem == 'PM' and hour != 12:
            hour += 12
        elif meridiem == 'AM' and hour == 12:
            hour = 0
    return hour * 60 + minute


def run_async_safe(coro):
    """
    Safely runs an async coroutine from a synchronous context.
    Works inside FastAPI (which has a running loop) and outside (e.g., Streamlit).
    """
    try:
        # Check if we are in an event loop
        loop = asyncio.get_running_loop()
        # If we are, we must run it in a separate thread to avoid "RuntimeError: asyncio.run() cannot be called from a running event loop"
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    except (RuntimeError, ValueError):
        # No loop running, asyncio.run is safe
        return asyncio.run(coro)

def backfill_film_details_from_fandango_single(title: str) -> int:
    """
    Backfill film details for a single film title using OMDb with Fandango fallback.
    Returns 1 if updated, 0 otherwise.
    """
    company_id = getattr(config, 'CURRENT_COMPANY_ID', None) or 1  # Default to company 1
        
    result = _enrich_films_sync([title], company_id)
    return result.get('enriched', 0)


# ============================================================================
# COMPATIBILITY LAYER: Legacy function implementations using SQLAlchemy
# ============================================================================

@contextmanager
def _get_db_connection():
    """
    Legacy compatibility: context manager for database connections.
    Now uses SQLAlchemy underneath.
    """
    with legacy_db_connection() as conn:
        yield conn


def init_database():
    """Initialize database schema (SQLAlchemy version)"""
    from app.db_session import init_database as sa_init_database
    sa_init_database()


def get_dates_for_theaters(theater_list):
    """Gets the unique dates that the selected theaters have records for."""
    if not theater_list:
        return []
    
    with get_session() as session:
        # Get company_id from config (set by main app)
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Showing.play_date).distinct()
        
        if company_id:
            query = query.filter(Showing.company_id == company_id)
        
        query = query.filter(Showing.theater_name.in_(theater_list))
        query = query.order_by(Showing.play_date.desc())
        
        results = query.all()
        return [row[0] for row in results]


def get_common_films_for_theaters_dates(theater_list, date_list):
    """Gets films that are available for ALL selected theaters on AT LEAST ONE of the selected dates."""
    if not theater_list or not date_list:
        return []
    
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        # Subquery: distinct film_title, theater_name combinations
        subquery = session.query(
            Showing.film_title,
            Showing.theater_name
        ).distinct()
        
        if company_id:
            subquery = subquery.filter(Showing.company_id == company_id)
        
        subquery = subquery.filter(
            and_(
                Showing.theater_name.in_(theater_list),
                Showing.play_date.in_(date_list)
            )
        )
        
        # Group by film and count distinct theaters
        sub = subquery.subquery()
        query = session.query(sub.c.film_title).group_by(sub.c.film_title).having(
            func.count(func.distinct(sub.c.theater_name)) == len(theater_list)
        ).order_by(sub.c.film_title)
        
        results = query.all()
        return [row[0] for row in results]


def get_theater_comparison_summary(theater_list, start_date, end_date):
    """
    Generates a summary DataFrame for comparing multiple theaters side-by-side.
    """
    if not theater_list:
        return pd.DataFrame()

    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        # Query for main stats
        query = session.query(
            Showing.theater_name,
            func.count(func.distinct(Showing.showing_id)).label('Total Showings'),
            func.count(func.distinct(Showing.film_title)).label('Unique Films'),
            func.group_concat(func.distinct(Showing.format)).label('all_formats')
        ).outerjoin(
            Price, Showing.showing_id == Price.showing_id
        ).filter(
            Showing.theater_name.in_(theater_list),
            Showing.play_date.between(start_date, end_date)
        )

        if company_id:
            query = query.filter(Showing.company_id == company_id)

        df = pd.read_sql(query.group_by(Showing.theater_name).statement, session.bind)

        # Query for average price
        avg_price_query = session.query(
            Showing.theater_name,
            func.avg(Price.price).label('Overall Avg. Price')
        ).join(
            Price, Showing.showing_id == Price.showing_id
        ).filter(
            Showing.theater_name.in_(theater_list),
            Showing.play_date.between(start_date, end_date),
            Price.ticket_type.in_(['Adult', 'Senior', 'Child'])
        )

        if company_id:
            avg_price_query = avg_price_query.filter(Showing.company_id == company_id)

        avg_price_df = pd.read_sql(avg_price_query.group_by(Showing.theater_name).statement, session.bind)

        if not df.empty and not avg_price_df.empty:
            df = pd.merge(df, avg_price_df, on='theater_name', how='left')

    if not df.empty and 'all_formats' in df.columns:
        def process_formats(format_str):
            if not format_str:
                return 0, "N/A"
            
            all_formats = set(part.strip() for item in format_str.split(',') for part in item.split(','))
            premium_formats = {f for f in all_formats if f != '2D'}
            num_premium = len(premium_formats)
            display_str = ", ".join(sorted(list(premium_formats))) if premium_formats else "N/A"
            return num_premium, display_str

        processed_formats_df = df['all_formats'].apply(lambda x: pd.Series(process_formats(x), index=['# Premium Formats', 'Premium Formats']))
        df = pd.concat([df, processed_formats_df], axis=1).drop(columns=['all_formats'])
        df['PLF Count'] = df['# Premium Formats']

    return df

from typing import Optional

def get_market_at_a_glance_data(theater_list: list[str], start_date: datetime.date, end_date: datetime.date, films: Optional[list[str]] = None) -> tuple[pd.DataFrame, Optional[datetime.date]]:
    """
    Fetches data for the 'Market At a Glance' report.
    - Gets data from the specified date range.
    - Joins showings and prices to get all necessary details.
    - Returns the DataFrame and the most recent scrape date found.
    """
    if not theater_list:
        return pd.DataFrame(), None

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    with _get_db_connection() as conn:
        placeholders = ",".join(["?"] * len(theater_list))

        query = f"""
            SELECT
                s.theater_name,
                s.film_title,
                s.daypart,
                f.release_date,
                s.format,
                s.is_plf,
                p.ticket_type,
                p.price,
                r.run_timestamp
            FROM prices p
            JOIN showings s ON p.showing_id = s.showing_id
            LEFT JOIN films f ON s.film_title = f.film_title
            JOIN scrape_runs r ON p.run_id = r.run_id
            WHERE s.theater_name IN ({placeholders})
            AND s.play_date BETWEEN ? AND ?
        """
        params = theater_list + [start_date_str, end_date_str]

        # --- NEW: Add film filter if provided ---
        if films:
            film_placeholders = ",".join(["?"] * len(films))
            query += f" AND s.film_title IN ({film_placeholders})"
            params.extend(films)

        df = pd.read_sql_query(query, conn, params=params)

    latest_scrape_date = None
    if not df.empty and 'run_timestamp' in df.columns:
        latest_scrape_date = pd.to_datetime(df['run_timestamp']).max().date()

    # --- NEW: Consolidate ticket types in memory for accurate reporting ---
    if not df.empty:
        import json
        import os
        try:
            ticket_types_path = os.path.join(os.path.dirname(__file__), 'ticket_types.json')
            with open(ticket_types_path, 'r') as f:
                ticket_types_data = json.load(f)
            base_type_map = ticket_types_data.get('base_type_map', {})
            
            # Create a reverse map from variation to canonical name
            reverse_map = {}
            for canonical, variations in base_type_map.items():
                reverse_map[canonical.lower()] = canonical
                for variation in variations:
                    reverse_map[variation.lower()] = canonical

            # Apply the mapping. If a type isn't in the map, it keeps its original name.
            df['ticket_type'] = df['ticket_type'].str.lower().map(reverse_map).fillna(df['ticket_type'])

        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"  [DB-WARN] Could not consolidate ticket types for glance report. File missing or corrupt. Error: {e}")
            # Continue with unconsolidated data if the mapping file is missing

    return df, latest_scrape_date

def calculate_operating_hours_from_showings(theater_list: list[str], start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    """
    [FALLBACK] Calculates operating hours by finding the min/max showtimes
    from the 'showings' table. This is used when no data is in the 'operating_hours' table.
    """
    from app.utils import normalize_time_string # Local import to avoid circular dependency
    if not theater_list:
        return pd.DataFrame()

    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(
            Showing.theater_name,
            Showing.play_date.label('scrape_date'),
            Showing.showtime
        ).filter(
            Showing.theater_name.in_(theater_list),
            Showing.play_date.between(start_date, end_date)
        )
        
        if company_id:
            query = query.filter(Showing.company_id == company_id)

        df = pd.read_sql(query.statement, session.bind)

    if df.empty:
        return pd.DataFrame()

    # Convert showtime strings to datetime objects for correct min/max calculation
    df['time_obj'] = df['showtime'].apply(lambda x: datetime.strptime(normalize_time_string(x), "%I:%M%p").time())

    # Group by theater and date, then find the min and max times
    agg_df = df.groupby(['theater_name', 'scrape_date']).agg(
        open_time=('time_obj', 'min'),
        close_time=('time_obj', 'max')
    ).reset_index()

    # Format times back to strings for consistency with the primary operating_hours table
    agg_df['open_time'] = agg_df['open_time'].apply(lambda x: x.strftime('%I:%M %p').lstrip('0'))
    agg_df['close_time'] = agg_df['close_time'].apply(lambda x: x.strftime('%I:%M %p').lstrip('0'))

    # Ensure column names match the output of get_operating_hours_for_theaters_and_dates
    return agg_df[['scrape_date', 'theater_name', 'open_time', 'close_time']]
    
def update_database_schema():
    """
    Legacy compatibility: Schema updates now handled by SQLAlchemy migrations.
    This is a no-op for backward compatibility.
    """
    print("[DB] Schema updates handled by SQLAlchemy. Use migrations for changes.")


# ============================================================================
# FILM MANAGEMENT: OMDB integration
# ============================================================================

def get_all_film_titles():
    """Get all unique film titles from showings"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Showing.film_title).distinct()
        
        if company_id:
            query = query.filter(Showing.company_id == company_id)
        
        results = query.all()
        return [row[0] for row in results]


def get_film_metadata(film_title):
    """Get film metadata from films table"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Film).filter(Film.film_title == film_title)
        
        if company_id:
            query = query.filter(Film.company_id == company_id)
        
        film = query.first()
        
        if not film:
            return None
        
        # Convert to dict for backward compatibility
        return {
            'film_title': film.film_title,
            'imdb_id': film.imdb_id,
            'genre': film.genre,
            'mpaa_rating': film.mpaa_rating,
            'director': film.director,
            'actors': film.actors,
            'plot': film.plot,
            'poster_url': film.poster_url,
            'metascore': film.metascore,
            'imdb_rating': float(film.imdb_rating) if film.imdb_rating else None,
            'release_date': film.release_date,
            'domestic_gross': film.domestic_gross,
            'runtime': film.runtime,
            'opening_weekend_domestic': film.opening_weekend_domestic,
            'last_omdb_update': film.last_omdb_update
        }


def save_film_metadata(film_data, company_id: int = None):
    """Save or update film metadata"""
    with get_session() as session:
        # Use passed company_id or fall back to config
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        if not company_id:
            company_id = 1  # Default to company 1 for API calls
        
        # Check if film exists
        film = session.query(Film).filter(
            and_(
                Film.company_id == company_id,
                Film.film_title == film_data['film_title']
            )
        ).first()
        
        if film:
            # Update existing
            for key, value in film_data.items():
                if hasattr(film, key):
                    setattr(film, key, value)
            film.last_omdb_update = datetime.now(UTC)
        else:
            # Create new
            film = Film(
                company_id=company_id,
                last_omdb_update=datetime.now(UTC),
                **film_data
            )
            session.add(film)


def get_unmatched_films() -> pd.DataFrame:
    """Get list of films that couldn't be matched to OMDB.

    Returns:
        pd.DataFrame with columns: film_title, first_seen
    """
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(UnmatchedFilm)

        if company_id:
            query = query.filter(UnmatchedFilm.company_id == company_id)

        results = query.all()
        data = [{'film_title': row.film_title, 'first_seen': row.first_seen} for row in results]
        return pd.DataFrame(data)


def add_unmatched_film(film_title, company_id: int = None):
    """Add or update unmatched film"""
    with get_session() as session:
        # Use passed company_id or fall back to config
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        if not company_id:
            company_id = 1  # Default to company 1 for API calls
        
        # Check if exists
        film = session.query(UnmatchedFilm).filter(
            and_(
                UnmatchedFilm.company_id == company_id,
                UnmatchedFilm.film_title == film_title
            )
        ).first()
        
        if film:
            # Update occurrence
            film.last_seen = datetime.now(UTC)
            film.occurrence_count += 1
        else:
            # Create new
            film = UnmatchedFilm(
                company_id=company_id,
                film_title=film_title,
                first_seen=datetime.now(UTC),
                last_seen=datetime.now(UTC),
                occurrence_count=1
            )
            session.add(film)


def get_ignored_films():
    """Get list of films that are ignored"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(IgnoredFilm.film_title)
        
        if company_id:
            query = query.filter(IgnoredFilm.company_id == company_id)
        
        results = query.all()
        return [row[0] for row in results]


def add_ignored_film(film_title, reason=None, company_id: int = None):
    """Add film to ignored list"""
    with get_session() as session:
        # Use passed company_id or fall back to config
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        if not company_id:
            company_id = 1  # Default to company 1 for API calls
        
        # Check if exists
        existing = session.query(IgnoredFilm).filter(
            and_(
                IgnoredFilm.company_id == company_id,
                IgnoredFilm.film_title == film_title
            )
        ).first()
        
        if not existing:
            film = IgnoredFilm(
                company_id=company_id,
                film_title=film_title,
                reason=reason
            )
            session.add(film)


def remove_ignored_film(film_title):
    """Remove film from ignored list"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(IgnoredFilm).filter(
            IgnoredFilm.film_title == film_title
        )

        if company_id:
            query = query.filter(IgnoredFilm.company_id == company_id)

        film = query.first()
        if film:
            session.delete(film)


def enrich_new_films(film_titles: list, async_mode: bool = False) -> dict:
    """
    Automatically enrich films with OMDb/Fandango metadata.
    Proactively checks for films missing critical data like runtime.

    Args:
        film_titles: List of film titles to potentially enrich
        async_mode: If True, run enrichment in background (non-blocking)

    Returns:
        dict with counts: enriched, failed, skipped
    """
    if not film_titles:
        return {'enriched': 0, 'failed': 0, 'skipped': 0}

    company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
    if not company_id:
        print("  [ENRICH] No company ID set, skipping enrichment")
        return {'enriched': 0, 'failed': 0, 'skipped': len(film_titles)}

    # Deduplicate
    unique_titles = list(set(film_titles))

    with get_session() as session:
        # Find films that are ALREADY COMPLETE (have a runtime)
        complete = session.query(Film.film_title).filter(
            and_(
                Film.company_id == company_id,
                Film.film_title.in_(unique_titles),
                Film.runtime.isnot(None),
                Film.runtime != 'N/A'
            )
        ).all()
        complete_titles = {row[0] for row in complete}

        # Also check ignored films
        ignored = session.query(IgnoredFilm.film_title).filter(
            and_(
                IgnoredFilm.company_id == company_id,
                IgnoredFilm.film_title.in_(unique_titles)
            )
        ).all()
        ignored_titles = {row[0] for row in ignored}

    # Films that need enrichment (either missing entirely or missing runtime)
    titles_to_enrich = [t for t in unique_titles if t not in complete_titles and t not in ignored_titles]

    if not titles_to_enrich:
        return {'enriched': 0, 'failed': 0, 'skipped': len(unique_titles)}

    print(f"  [ENRICH] Found {len(titles_to_enrich)} films that need detail enrichment/updates")

    # Run enrichment
    if async_mode:
        import threading
        thread = threading.Thread(target=_enrich_films_sync, args=(titles_to_enrich, company_id))
        thread.start()
        return {'enriched': 0, 'failed': 0, 'skipped': len(complete_titles) + len(ignored_titles), 'pending': len(titles_to_enrich)}
    else:
        return _enrich_films_sync(titles_to_enrich, company_id)


def _enrich_films_sync(film_titles: list, company_id: int) -> dict:
    """Synchronously enrich films with OMDb data and Fandango fallback."""
    enriched = 0
    failed = 0

    try:
        from app.omdb_client import OMDbClient
        omdb = OMDbClient()
    except Exception as e:
        print(f"  [ENRICH] Could not initialize OMDB client: {e}")
        return {'enriched': 0, 'failed': len(film_titles), 'skipped': 0}

    from app.scraper import Scraper
    scraper = Scraper()

    for title in film_titles:
        film_data = None
        try:
            # Clean title for special cases
            from app.utils import clean_film_title
            cleaned_title = clean_film_title(title)

            # 1. Try OMDb first
            print(f"  [ENRICH] Trying OMDb for '{title}'...")
            film_data = omdb.get_film_details(cleaned_title)

            # 2. Check if OMDb result is sufficient (needs runtime)
            needs_fallback = not film_data or not film_data.get('runtime') or film_data.get('runtime') == 'N/A'
            
            if needs_fallback:
                print(f"  [ENRICH] OMDb results insufficient for '{title}'. Attempting Fandango fallback...")
                try:
                    search_results = run_async_safe(scraper.search_fandango_for_film_url(cleaned_title))
                    if search_results:
                        # Find best match
                        best_match = None
                        for res in search_results:
                            if fuzz.ratio(title.lower(), res['title'].lower()) > 85:
                                best_match = res
                                break
                        
                        if not best_match:
                            best_match = search_results[0]
                            
                        print(f"  [ENRICH] Scrapping Fandango details from: {best_match['url']}")
                        fandango_data = run_async_safe(scraper.get_film_details_from_fandango_url(best_match['url']))
                        
                        if fandango_data:
                            # Merge Fandango data into OMDb data (prioritize Fandango for missing pieces)
                            if not film_data:
                                film_data = fandango_data
                            else:
                                for key, value in fandango_data.items():
                                    if not film_data.get(key) or film_data[key] in [None, 'N/A']:
                                        film_data[key] = value
                except Exception as ex:
                    print(f"  [ENRICH] Fandango fallback failed for '{title}': {ex}")

            if film_data:
                # Use original title as the primary key
                film_data['film_title'] = title
                upsert_film_details(film_data, company_id=company_id)
                print(f"  [ENRICH] ✓ Successfully enriched: {title}")
                enriched += 1
            else:
                # Log as unmatched for manual review
                log_unmatched_film(title, company_id=company_id)
                print(f"  [ENRICH] ✗ Failed to find any data for: {title}")
                failed += 1

        except Exception as e:
            print(f"  [ENRICH] Unexpected error enriching '{title}': {e}")
            try:
                log_unmatched_film(title, company_id=company_id)
            except:
                pass
            failed += 1

    print(f"  [ENRICH] Batch Complete: {enriched} enriched, {failed} failed")
    return {'enriched': enriched, 'failed': failed, 'skipped': 0}


# ============================================================================
# SCRAPE RUN MANAGEMENT
# ============================================================================

def create_scrape_run(mode, context=None, company_id=None, user_id=None):
    """Create a new scrape run and return its ID"""
    with get_session() as session:
        # Use passed company_id or fall back to config
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        if not company_id:
            # Default to company 1 if not set (for API calls outside Streamlit)
            company_id = 1
        
        # Get current user ID from session state if not provided
        if user_id is None:
            try:
                import streamlit as st
                if hasattr(st, 'session_state') and 'user' in st.session_state:
                    user_dict = st.session_state.user
                    # Handle both dict formats: {'id': ...} or {'user_id': ...}
                    user_id = user_dict.get('user_id') or user_dict.get('id')
                    print(f"  [DB] Got user_id from session: {user_id}")
            except Exception as e:
                print(f"  [DB] Could not get user_id from session: {e}")
                user_id = None
        
        print(f"  [DB] Creating scrape run - mode: {mode}, user_id: {user_id}, context: {context}")
        
        run = ScrapeRun(
            company_id=company_id,
            run_timestamp=datetime.now(UTC),
            mode=mode,
            user_id=user_id,
            status='running'
        )
        session.add(run)
        session.flush()  # Get the ID before commit
        print(f"  [DB] Created scrape run with ID: {run.run_id}")
        return run.run_id


def update_scrape_run_status(run_id, status, records_scraped=0, error_message=None):
    """Update scrape run status"""
    with get_session() as session:
        run = session.query(ScrapeRun).filter(ScrapeRun.run_id == run_id).first()
        if run:
            run.status = status
            run.records_scraped = records_scraped
            run.error_message = error_message


# ============================================================================
# RAW SQL SUPPORT: For complex queries not yet migrated
# ============================================================================

def execute_raw_sql(query, params=None):
    """
    Execute raw SQL query and return DataFrame.
    Use this for complex queries during migration period.
    """
    with get_session() as session:
        if params:
            result = session.execute(text(query), params)
        else:
            result = session.execute(text(query))
        
        # Try to convert to DataFrame if possible
        try:
            return pd.DataFrame(result.fetchall(), columns=result.keys())
        except:
            return result


def execute_raw_sql_pandas(query, params=None):
    """
    Execute raw SQL and return pandas DataFrame.
    Maintains compatibility with pd.read_sql_query usage.
    """
    engine = get_engine()
    return pd.read_sql_query(text(query), engine, params=params)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_all_theaters():
    """Get list of all theater names"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Showing.theater_name).distinct()
        
        if company_id:
            query = query.filter(Showing.company_id == company_id)
        
        query = query.order_by(Showing.theater_name)
        
        results = query.all()
        return [row[0] for row in results]


def get_all_markets():
    """Get list of all market names"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(OperatingHours.market).distinct()
        
        if company_id:
            query = query.filter(OperatingHours.company_id == company_id)
        
        query = query.filter(OperatingHours.market.isnot(None))
        query = query.order_by(OperatingHours.market)
        
        results = query.all()
        return [row[0] for row in results]


def get_theaters_by_market(market):
    """Get theaters in a specific market"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(OperatingHours.theater_name).distinct()
        
        if company_id:
            query = query.filter(OperatingHours.company_id == company_id)
        
        query = query.filter(OperatingHours.market == market)
        query = query.order_by(OperatingHours.theater_name)
        
        results = query.all()
        return [row[0] for row in results]


def get_configured_operating_hours(theater_name):
    """Get the configured operating hours for a theater."""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(TheaterOperatingHours).filter(
            TheaterOperatingHours.theater_name == theater_name
        )
        
        if company_id:
            query = query.filter(TheaterOperatingHours.company_id == company_id)
            
        results = query.order_by(TheaterOperatingHours.day_of_week).all()
        
        return [
            {
                'day_of_week': r.day_of_week,
                'open_time': r.open_time,
                'close_time': r.close_time,
                'first_showtime': r.first_showtime,
                'last_showtime': r.last_showtime
            } for r in results
        ]


# ============================================================================
# MIGRATION HELPERS: Functions to ease transition
# ============================================================================

def set_current_company(company_name):
    """
    Set the current company context for all database operations.
    This should be called at app startup after user login.
    """
    with get_session() as session:
        company = session.query(Company).filter(Company.company_name == company_name).first()
        
        if company:
            config.CURRENT_COMPANY_ID = company.company_id
            print(f"[DB] Set current company: {company_name} (ID: {company.company_id})")
        else:
            # Create company if it doesn't exist
            company = Company(company_name=company_name, is_active=True)
            session.add(company)
            session.flush()
            config.CURRENT_COMPANY_ID = company.company_id
            print(f"[DB] Created company: {company_name} (ID: {company.company_id})")


def get_current_company():
    """Get the current company context"""
    company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
    if not company_id:
        return None
    
    with get_session() as session:
        company = session.query(Company).filter(Company.company_id == company_id).first()
        return company.company_name if company else None


# Expose legacy connection manager for backward compatibility
get_db_connection = _get_db_connection


# ============================================================================
# SCRAPING: Core functions for saving scraped data
# ============================================================================

def save_prices(run_id: int, df: pd.DataFrame, company_id: int = None, batch_size: int = 50):
    """Save scraped prices to database with batch commits for crash resilience.

    Args:
        run_id: The scrape run ID
        df: DataFrame with price data
        company_id: Company ID (defaults to config or 1)
        batch_size: Number of prices to commit at once (default 50)
    """
    import datetime as dt
    print(f"  [DB] save_prices called with {len(df)} rows, run_id={run_id}, batch_size={batch_size}")
    if 'play_date' not in df.columns or df['play_date'].isnull().all():
        print("  [DB] [ERROR] save_prices called with missing 'play_date'. Aborting.")
        return

    # Ensure play_date is a date object, not string (SQLite requires date objects)
    if df['play_date'].dtype == 'object':
        def to_date(val):
            if isinstance(val, str):
                return dt.datetime.strptime(val, "%Y-%m-%d").date()
            elif isinstance(val, dt.datetime):
                return val.date()
            return val
        df = df.copy()
        df['play_date'] = df['play_date'].apply(to_date)
        print(f"  [DB] Converted play_date strings to date objects")

    with get_session() as session:
        # Use passed company_id or fall back to config
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        if not company_id:
            company_id = 1  # Default to company 1 for API calls

        # Get showing IDs for all prices
        prices_saved = 0
        prices_in_batch = 0
        prices_skipped_no_showing = 0
        prices_skipped_duplicate = 0
        prices_skipped_error = 0
        batches_committed = 0

        for idx, row in df.iterrows():
            showing = session.query(Showing).filter(
                and_(
                    Showing.company_id == company_id,
                    Showing.play_date == row['play_date'],
                    Showing.theater_name == row['Theater Name'],
                    Showing.film_title == row['Film Title'],
                    Showing.showtime == row['Showtime'],
                    Showing.format == row['Format']
                )
            ).first()

            if showing:
                try:
                    price_value = float(str(row['Price']).replace('$', ''))
                    ticket_type = row['Ticket Type']

                    # Check for existing price (skip duplicates on re-run)
                    existing_price = session.query(Price).filter(
                        and_(
                            Price.showing_id == showing.showing_id,
                            Price.ticket_type == ticket_type
                        )
                    ).first()

                    if existing_price:
                        prices_skipped_duplicate += 1
                        continue  # Skip duplicate

                    price = Price(
                        company_id=company_id,
                        run_id=run_id,
                        showing_id=showing.showing_id,
                        ticket_type=ticket_type,
                        price=price_value,
                        capacity=row.get('Capacity'),
                        play_date=row['play_date']
                    )
                    session.add(price)
                    prices_saved += 1
                    prices_in_batch += 1

                    # Batch commit for crash resilience
                    if prices_in_batch >= batch_size:
                        session.commit()
                        batches_committed += 1
                        print(f"  [DB] Committed batch {batches_committed} ({prices_saved} prices so far)")
                        prices_in_batch = 0

                except (ValueError, KeyError) as e:
                    print(f"  [DB] [WARN] Skipping price: {e}")
                    prices_skipped_error += 1
            else:
                prices_skipped_no_showing += 1
                if prices_skipped_no_showing <= 3:  # Only log first 3 to avoid spam
                    print(f"  [DB] [WARN] No matching showing for: {row['Theater Name']} | {row['Film Title']} | {row['Showtime']} | {row['Format']} | {row['play_date']}")

        if prices_skipped_no_showing > 3:
            print(f"  [DB] [WARN] ... and {prices_skipped_no_showing - 3} more prices skipped (no matching showing)")

        # Final commit for any remaining prices in the batch
        if prices_in_batch > 0:
            session.commit()
            batches_committed += 1
            print(f"  [DB] Final batch {batches_committed} committed")

        print(f"  [DB] Saved {prices_saved} prices for run ID {run_id} in {batches_committed} batches. Skipped: {prices_skipped_no_showing} (no showing), {prices_skipped_duplicate} (duplicates), {prices_skipped_error} (errors)")


# ============================================================================
# CHECKPOINT TRACKING: For crash-resilient long-running scrapes
# ============================================================================

def create_checkpoint(job_id: str, run_id: int, theater_name: str, play_date, phase: str,
                     company_id: int = None, market: str = None) -> int:
    """Create or update a checkpoint for a theater scrape.

    Args:
        job_id: Unique identifier for this scrape job
        run_id: The scrape run ID
        theater_name: Name of the theater being scraped
        play_date: Date being scraped
        phase: 'showings' or 'prices'
        company_id: Company ID (defaults to config or 1)
        market: Optional market name

    Returns:
        checkpoint_id
    """
    import datetime as dt
    from app.db_models import ScrapeCheckpoint

    if isinstance(play_date, str):
        play_date = dt.datetime.strptime(play_date, '%Y-%m-%d').date()
    elif isinstance(play_date, dt.datetime):
        play_date = play_date.date()

    with get_session() as session:
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None) or 1

        # Check if checkpoint exists
        existing = session.query(ScrapeCheckpoint).filter(
            and_(
                ScrapeCheckpoint.job_id == job_id,
                ScrapeCheckpoint.theater_name == theater_name,
                ScrapeCheckpoint.play_date == play_date,
                ScrapeCheckpoint.phase == phase
            )
        ).first()

        if existing:
            existing.status = 'in_progress'
            existing.started_at = dt.datetime.now(dt.timezone.utc)
            existing.completed_at = None
            session.commit()
            return existing.checkpoint_id
        else:
            checkpoint = ScrapeCheckpoint(
                job_id=job_id,
                run_id=run_id,
                company_id=company_id,
                theater_name=theater_name,
                market=market,
                play_date=play_date,
                phase=phase,
                status='in_progress'
            )
            session.add(checkpoint)
            session.commit()
            return checkpoint.checkpoint_id


def complete_checkpoint(job_id: str, theater_name: str, play_date, phase: str,
                       showings_count: int = 0, prices_count: int = 0):
    """Mark a checkpoint as completed.

    Args:
        job_id: Unique identifier for this scrape job
        theater_name: Name of the theater
        play_date: Date being scraped
        phase: 'showings' or 'prices'
        showings_count: Number of showings scraped (for showings phase)
        prices_count: Number of prices scraped (for prices phase)
    """
    import datetime as dt
    from app.db_models import ScrapeCheckpoint

    if isinstance(play_date, str):
        play_date = dt.datetime.strptime(play_date, '%Y-%m-%d').date()
    elif isinstance(play_date, dt.datetime):
        play_date = play_date.date()

    with get_session() as session:
        checkpoint = session.query(ScrapeCheckpoint).filter(
            and_(
                ScrapeCheckpoint.job_id == job_id,
                ScrapeCheckpoint.theater_name == theater_name,
                ScrapeCheckpoint.play_date == play_date,
                ScrapeCheckpoint.phase == phase
            )
        ).first()

        if checkpoint:
            checkpoint.status = 'completed'
            checkpoint.completed_at = dt.datetime.now(dt.timezone.utc)
            checkpoint.showings_count = showings_count
            checkpoint.prices_count = prices_count
            session.commit()
            print(f"  [CHECKPOINT] Completed: {theater_name} ({phase}) - {showings_count} showings, {prices_count} prices")


def fail_checkpoint(job_id: str, theater_name: str, play_date, phase: str, error_message: str):
    """Mark a checkpoint as failed.

    Args:
        job_id: Unique identifier for this scrape job
        theater_name: Name of the theater
        play_date: Date being scraped
        phase: 'showings' or 'prices'
        error_message: Error that caused the failure
    """
    import datetime as dt
    from app.db_models import ScrapeCheckpoint

    if isinstance(play_date, str):
        play_date = dt.datetime.strptime(play_date, '%Y-%m-%d').date()
    elif isinstance(play_date, dt.datetime):
        play_date = play_date.date()

    with get_session() as session:
        checkpoint = session.query(ScrapeCheckpoint).filter(
            and_(
                ScrapeCheckpoint.job_id == job_id,
                ScrapeCheckpoint.theater_name == theater_name,
                ScrapeCheckpoint.play_date == play_date,
                ScrapeCheckpoint.phase == phase
            )
        ).first()

        if checkpoint:
            checkpoint.status = 'failed'
            checkpoint.completed_at = dt.datetime.now(dt.timezone.utc)
            checkpoint.error_message = error_message[:500] if error_message else None
            session.commit()
            print(f"  [CHECKPOINT] Failed: {theater_name} ({phase}) - {error_message[:100] if error_message else 'Unknown'}")


def get_completed_theaters(job_id: str, play_date, phase: str = 'prices') -> set:
    """Get set of theater names that have completed a given phase.

    Args:
        job_id: Unique identifier for this scrape job
        play_date: Date being scraped
        phase: 'showings' or 'prices'

    Returns:
        Set of theater names that are complete
    """
    import datetime as dt
    from app.db_models import ScrapeCheckpoint

    if isinstance(play_date, str):
        play_date = dt.datetime.strptime(play_date, '%Y-%m-%d').date()
    elif isinstance(play_date, dt.datetime):
        play_date = play_date.date()

    with get_session() as session:
        checkpoints = session.query(ScrapeCheckpoint.theater_name).filter(
            and_(
                ScrapeCheckpoint.job_id == job_id,
                ScrapeCheckpoint.play_date == play_date,
                ScrapeCheckpoint.phase == phase,
                ScrapeCheckpoint.status == 'completed'
            )
        ).all()

        return {cp.theater_name for cp in checkpoints}


def get_job_progress(job_id: str) -> dict:
    """Get progress summary for a scrape job.

    Args:
        job_id: Unique identifier for this scrape job

    Returns:
        Dict with progress info: total_theaters, completed, in_progress, failed, showings_total, prices_total
    """
    from app.db_models import ScrapeCheckpoint

    with get_session() as session:
        checkpoints = session.query(ScrapeCheckpoint).filter(
            ScrapeCheckpoint.job_id == job_id
        ).all()

        completed = sum(1 for cp in checkpoints if cp.status == 'completed')
        in_progress = sum(1 for cp in checkpoints if cp.status == 'in_progress')
        failed = sum(1 for cp in checkpoints if cp.status == 'failed')
        showings_total = sum(cp.showings_count or 0 for cp in checkpoints)
        prices_total = sum(cp.prices_count or 0 for cp in checkpoints)

        return {
            'job_id': job_id,
            'total_checkpoints': len(checkpoints),
            'completed': completed,
            'in_progress': in_progress,
            'failed': failed,
            'showings_total': showings_total,
            'prices_total': prices_total,
            'theaters': [
                {
                    'theater': cp.theater_name,
                    'market': cp.market,
                    'phase': cp.phase,
                    'status': cp.status,
                    'showings': cp.showings_count,
                    'prices': cp.prices_count
                }
                for cp in checkpoints
            ]
        }


def cleanup_old_checkpoints(days_old: int = 7):
    """Clean up checkpoints older than specified days.

    Args:
        days_old: Delete checkpoints older than this many days
    """
    import datetime as dt
    from app.db_models import ScrapeCheckpoint

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_old)

    with get_session() as session:
        deleted = session.query(ScrapeCheckpoint).filter(
            ScrapeCheckpoint.started_at < cutoff
        ).delete(synchronize_session=False)
        session.commit()
        if deleted > 0:
            print(f"  [CHECKPOINT] Cleaned up {deleted} old checkpoints")


# ============================================================================
# PROGRESS JOURNAL: File-based recovery for crashes (works even if DB is down)
# ============================================================================

import os
import json

PROGRESS_JOURNAL_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'progress_journals')


def _ensure_journal_dir():
    """Ensure the progress journal directory exists."""
    os.makedirs(PROGRESS_JOURNAL_DIR, exist_ok=True)


def get_journal_path(job_id: str) -> str:
    """Get the path to a progress journal file."""
    _ensure_journal_dir()
    return os.path.join(PROGRESS_JOURNAL_DIR, f"{job_id}.json")


def write_progress_journal(job_id: str, data: dict):
    """Write or update progress journal for a job.

    This is a file-based backup that survives database failures.
    The file is updated atomically to prevent corruption.

    Args:
        job_id: Unique identifier for this scrape job
        data: Dict with job progress data
    """
    import datetime as dt

    _ensure_journal_dir()
    journal_path = get_journal_path(job_id)
    temp_path = journal_path + '.tmp'

    # Add timestamp
    data['last_updated'] = dt.datetime.now(dt.timezone.utc).isoformat()

    try:
        # Write to temp file first (atomic write pattern)
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)

        # Atomically replace the old file
        if os.path.exists(journal_path):
            os.remove(journal_path)
        os.rename(temp_path, journal_path)

    except Exception as e:
        print(f"  [JOURNAL] Error writing progress journal: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


def read_progress_journal(job_id: str) -> dict:
    """Read a progress journal file.

    Args:
        job_id: Unique identifier for this scrape job

    Returns:
        Dict with job progress data, or empty dict if not found
    """
    journal_path = get_journal_path(job_id)

    if not os.path.exists(journal_path):
        return {}

    try:
        with open(journal_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  [JOURNAL] Error reading progress journal: {e}")
        return {}


def update_theater_progress(job_id: str, theater_name: str, phase: str, status: str,
                           showings: int = 0, prices: int = 0, error: str = None):
    """Update progress for a specific theater in the journal.

    Args:
        job_id: Unique identifier for this scrape job
        theater_name: Name of the theater
        phase: 'showings' or 'prices'
        status: 'started', 'completed', 'failed'
        showings: Number of showings (for showings phase)
        prices: Number of prices (for prices phase)
        error: Error message if failed
    """
    import datetime as dt

    journal = read_progress_journal(job_id)

    if 'theaters' not in journal:
        journal['theaters'] = {}

    if theater_name not in journal['theaters']:
        journal['theaters'][theater_name] = {
            'showings_status': 'pending',
            'prices_status': 'pending',
            'showings_count': 0,
            'prices_count': 0
        }

    theater_data = journal['theaters'][theater_name]
    theater_data[f'{phase}_status'] = status
    theater_data[f'{phase}_at'] = dt.datetime.now(dt.timezone.utc).isoformat()

    if phase == 'showings':
        theater_data['showings_count'] = showings
    elif phase == 'prices':
        theater_data['prices_count'] = prices

    if error:
        theater_data['error'] = error

    # Update summary counts
    theaters = journal['theaters']
    journal['summary'] = {
        'total_theaters': len(theaters),
        'showings_completed': sum(1 for t in theaters.values() if t.get('showings_status') == 'completed'),
        'prices_completed': sum(1 for t in theaters.values() if t.get('prices_status') == 'completed'),
        'failed': sum(1 for t in theaters.values() if t.get('showings_status') == 'failed' or t.get('prices_status') == 'failed'),
        'total_showings': sum(t.get('showings_count', 0) for t in theaters.values()),
        'total_prices': sum(t.get('prices_count', 0) for t in theaters.values())
    }

    write_progress_journal(job_id, journal)


def get_resumable_theaters(job_id: str, all_theaters: list, phase: str = 'prices') -> list:
    """Get list of theaters that need to be resumed (not completed).

    Args:
        job_id: Unique identifier for this scrape job
        all_theaters: Full list of theater names to scrape
        phase: 'showings' or 'prices'

    Returns:
        List of theater names that haven't completed the phase
    """
    journal = read_progress_journal(job_id)

    if not journal or 'theaters' not in journal:
        return all_theaters

    completed = set()
    for theater_name, data in journal['theaters'].items():
        if data.get(f'{phase}_status') == 'completed':
            completed.add(theater_name)

    remaining = [t for t in all_theaters if t not in completed]

    if len(remaining) < len(all_theaters):
        print(f"  [JOURNAL] Resuming: {len(all_theaters) - len(remaining)} theaters already completed, {len(remaining)} remaining")

    return remaining


def start_scrape_journal(job_id: str, theaters: list, play_date, market: str = None,
                        company_id: int = None, run_id: int = None):
    """Initialize a progress journal for a new scrape.

    Args:
        job_id: Unique identifier for this scrape job
        theaters: List of theater names to scrape
        play_date: Date being scraped
        market: Optional market name
        company_id: Company ID
        run_id: Scrape run ID
    """
    import datetime as dt

    journal = {
        'job_id': job_id,
        'run_id': run_id,
        'company_id': company_id,
        'market': market,
        'play_date': str(play_date),
        'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'theaters': {t: {'showings_status': 'pending', 'prices_status': 'pending'} for t in theaters},
        'summary': {
            'total_theaters': len(theaters),
            'showings_completed': 0,
            'prices_completed': 0,
            'failed': 0,
            'total_showings': 0,
            'total_prices': 0
        }
    }

    write_progress_journal(job_id, journal)
    print(f"  [JOURNAL] Started progress journal for job {job_id} with {len(theaters)} theaters")


def complete_scrape_journal(job_id: str, status: str = 'completed'):
    """Mark a scrape job as completed in the journal.

    Args:
        job_id: Unique identifier for this scrape job
        status: 'completed', 'failed', or 'cancelled'
    """
    import datetime as dt

    journal = read_progress_journal(job_id)
    if journal:
        journal['status'] = status
        journal['completed_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_progress_journal(job_id, journal)
        print(f"  [JOURNAL] Job {job_id} marked as {status}")


def list_incomplete_jobs() -> list:
    """List all jobs that haven't been marked as completed.

    Returns:
        List of job_id strings for incomplete jobs
    """
    _ensure_journal_dir()
    incomplete = []

    try:
        for filename in os.listdir(PROGRESS_JOURNAL_DIR):
            if filename.endswith('.json'):
                job_id = filename[:-5]
                journal = read_progress_journal(job_id)
                if journal and journal.get('status') not in ('completed', 'failed', 'cancelled'):
                    incomplete.append(job_id)
    except Exception as e:
        print(f"  [JOURNAL] Error listing incomplete jobs: {e}")

    return incomplete


def cleanup_old_journals(days_old: int = 7):
    """Clean up journal files older than specified days.

    Args:
        days_old: Delete journals older than this many days
    """
    import datetime as dt

    _ensure_journal_dir()
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_old)
    deleted = 0

    try:
        for filename in os.listdir(PROGRESS_JOURNAL_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(PROGRESS_JOURNAL_DIR, filename)
                mtime = dt.datetime.fromtimestamp(os.path.getmtime(filepath), tz=dt.timezone.utc)
                if mtime < cutoff:
                    os.remove(filepath)
                    deleted += 1
    except Exception as e:
        print(f"  [JOURNAL] Error cleaning up journals: {e}")

    if deleted > 0:
        print(f"  [JOURNAL] Cleaned up {deleted} old journal files")


def upsert_showings(all_showings, play_date, company_id: int = None, enrich_films: bool = True):
    """Insert or update showings in database.

    Args:
        all_showings: Dict of {theater_name: [showing_data, ...]}
        play_date: Date for the showings
        enrich_films: If True, automatically enrich new films with OMDB metadata
    """
    import datetime

    # Ensure play_date is a date object, not a string
    if isinstance(play_date, str):
        play_date = datetime.datetime.strptime(play_date, '%Y-%m-%d').date()
    elif isinstance(play_date, datetime.datetime):
        play_date = play_date.date()

    if not all_showings:
        print(f"  [DB] [WARN] No showings to upsert")
        return

    # Collect unique film titles for enrichment
    unique_film_titles = set()

    try:
        with get_session() as session:
            # Use passed company_id or fall back to config
            if company_id is None:
                company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
            if not company_id:
                company_id = 1  # Default to company 1 for API calls

            showing_count = 0
            for theater_name, showings in all_showings.items():
                print(f"  [DB] Processing {len(showings)} showings for {theater_name}")
                for showing_data in showings:
                    # Collect film titles for enrichment
                    if 'film_title' in showing_data:
                        unique_film_titles.add(showing_data['film_title'])
                    # Remove play_date from showing_data if present (we pass it separately)
                    showing_data.pop('play_date', None)

                    # Check if showing exists
                    existing = session.query(Showing).filter(
                        and_(
                            Showing.company_id == company_id,
                            Showing.play_date == play_date,
                            Showing.theater_name == theater_name,
                            Showing.film_title == showing_data['film_title'],
                            Showing.showtime == showing_data['showtime'],
                            Showing.format == showing_data['format']
                        )
                    ).first()

                    if not existing:
                        showing = Showing(
                            company_id=company_id,
                            play_date=play_date,
                            theater_name=theater_name,
                            film_title=showing_data['film_title'],
                            showtime=showing_data['showtime'],
                            format=showing_data['format'],
                            daypart=showing_data['daypart'],
                            is_plf=showing_data.get('is_plf', False),
                            ticket_url=showing_data.get('ticket_url')
                        )
                        session.add(showing)
                        showing_count += 1

            try:
                session.flush()
                print(f"  [DB] Upserted {showing_count} showings for {play_date.strftime('%Y-%m-%d')}.")
            except Exception as e:
                # Handle duplicate constraint errors gracefully
                print(f"  [DB] [WARN] Some showings may already exist: {e}")
                session.rollback()
                # Try inserting one at a time to skip duplicates
                for theater_name, showings in all_showings.items():
                    for showing_data in showings:
                        showing_data.pop('play_date', None)
                        try:
                            existing = session.query(Showing).filter(
                                and_(
                                    Showing.company_id == company_id,
                                    Showing.play_date == play_date,
                                    Showing.theater_name == theater_name,
                                    Showing.film_title == showing_data['film_title'],
                                    Showing.showtime == showing_data['showtime'],
                                    Showing.format == showing_data['format']
                                )
                            ).first()
                            if not existing:
                                showing = Showing(
                                    company_id=company_id,
                                    play_date=play_date,
                                    theater_name=theater_name,
                                    film_title=showing_data['film_title'],
                                    showtime=showing_data['showtime'],
                                    format=showing_data['format'],
                                    daypart=showing_data['daypart'],
                                    is_plf=showing_data.get('is_plf', False),
                                    ticket_url=showing_data.get('ticket_url')
                                )
                                session.add(showing)
                                session.commit()
                        except:
                            session.rollback()
                print(f"  [DB] Finished upserting showings for {play_date.strftime('%Y-%m-%d')} (some may have been skipped as duplicates).")

        # Auto-enrich new films with OMDB metadata
        if enrich_films and unique_film_titles:
            try:
                enrich_result = enrich_new_films(list(unique_film_titles), async_mode=True)
                if enrich_result.get('pending', 0) > 0:
                    print(f"  [DB] Queued {enrich_result['pending']} films for background enrichment")
            except Exception as enrich_err:
                print(f"  [DB] [WARN] Film enrichment failed (non-fatal): {enrich_err}")
                # Don't fail the upsert if enrichment fails

    except Exception as e:
        print(f"  [DB] [ERROR] Failed to upsert showings: {e}")
        import traceback
        traceback.print_exc()
        raise


# ============================================================================
# HISTORICAL DATA QUERIES
# ============================================================================

def get_scrape_runs():
    """Get all scrape runs"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(ScrapeRun).order_by(ScrapeRun.run_timestamp.desc())
        
        if company_id:
            query = query.filter(ScrapeRun.company_id == company_id)
        
        runs = query.all()
        return [{
            'run_id': r.run_id,
            'run_timestamp': r.run_timestamp,
            'mode': r.mode,
            'status': r.status,
            'records_scraped': r.records_scraped
        } for r in runs]


def get_prices_for_run(run_id):
    """Get all prices for a specific scrape run"""
    with get_session() as session:
        query = session.query(
            Price.price,
            Price.ticket_type,
            Showing.play_date,
            Showing.theater_name,
            Showing.film_title,
            Showing.showtime,
            Showing.format,
            Showing.daypart
        ).join(
            Showing, Price.showing_id == Showing.showing_id
        ).filter(Price.run_id == run_id)
        
        df = pd.read_sql(query.statement, session.bind)
        return df


def query_historical_data(start_date, end_date, theaters=None, films=None, genres=None, ratings=None):
    """Query historical price data with filters"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(
            Showing.play_date,
            Showing.theater_name,
            Showing.film_title,
            Showing.showtime,
            Showing.format,
            Showing.daypart,
            Price.ticket_type,
            Price.price,
            Film.genre,
            Film.mpaa_rating
        ).join(
            Price, Price.showing_id == Showing.showing_id
        ).outerjoin(
            Film, and_(
                Film.film_title == Showing.film_title,
                Film.company_id == Showing.company_id
            )
        )
        
        if company_id:
            query = query.filter(Showing.company_id == company_id)
        
        query = query.filter(
            and_(
                Showing.play_date >= start_date,
                Showing.play_date <= end_date
            )
        )
        
        if theaters:
            query = query.filter(Showing.theater_name.in_(theaters))
        
        if films:
            query = query.filter(Showing.film_title.in_(films))
        
        if genres:
            query = query.filter(Film.genre.in_(genres))
        
        if ratings:
            query = query.filter(Film.mpaa_rating.in_(ratings))
        
        df = pd.read_sql(query.statement, session.bind)
        return df


# ============================================================================
# UTILITY QUERIES
# ============================================================================

def get_unique_column_values(column_name):
    """Get unique values for a column"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        if column_name == 'theater_name':
            query = session.query(Showing.theater_name).distinct()
            if company_id:
                query = query.filter(Showing.company_id == company_id)
        elif column_name == 'film_title':
            query = session.query(Showing.film_title).distinct()
            if company_id:
                query = query.filter(Showing.company_id == company_id)
        else:
            return []
        
        results = query.all()
        return sorted([r[0] for r in results if r[0]])


def get_dates_for_theater(theater_name):
    """Get all dates with data for a theater"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Showing.play_date).distinct()
        
        if company_id:
            query = query.filter(Showing.company_id == company_id)
        
        query = query.filter(Showing.theater_name == theater_name)
        query = query.order_by(Showing.play_date.desc())
        
        results = query.all()
        return [r[0] for r in results]


def get_films_for_theater_date(theater_name, date):
    """Get all films for a theater on a specific date"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Showing.film_title).distinct()
        
        if company_id:
            query = query.filter(Showing.company_id == company_id)
        
        query = query.filter(
            and_(
                Showing.theater_name == theater_name,
                Showing.play_date == date
            )
        )
        query = query.order_by(Showing.film_title)
        
        results = query.all()
        return [r[0] for r in results]


def get_final_prices(theater_name, date, film_title, daypart="All"):
    """Get prices for a specific showing"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(
            Showing.showtime,
            Showing.format,
            Price.ticket_type,
            Price.price
        ).join(
            Price, Price.showing_id == Showing.showing_id
        )
        
        if company_id:
            query = query.filter(Showing.company_id == company_id)
        
        filters = [
            Showing.theater_name == theater_name,
            Showing.play_date == date,
            Showing.film_title == film_title
        ]
        
        if daypart != "All":
            filters.append(Showing.daypart == daypart)
        
        query = query.filter(and_(*filters))
        
        df = pd.read_sql(query.statement, session.bind)
        return df


# ============================================================================
# OPERATING HOURS MANAGEMENT
# ============================================================================

def save_operating_hours(run_id, operating_hours_data, conn=None):
    """Save operating hours data (compatibility wrapper)"""
    # conn parameter ignored in SQLAlchemy version
    save_full_operating_hours_run(operating_hours_data, f"run_{run_id}")


def _merge_operating_hours_record(session, company_id, theater_name, market, scrape_date,
                                   new_open, new_close, new_first, new_last, new_count, new_duration):
    """
    Merge a single operating hours record using high water mark logic.

    Preserves the widest known operating window:
    - Keep earliest open time (protects against late-day scrapes missing morning shows)
    - Keep latest close time (protects against early scrapes missing late shows)
    - Keep highest showtime count (protects against weather cancellations)

    Returns: 'inserted', 'updated', or 'kept'
    """
    # Check for existing record
    existing = session.query(OperatingHours).filter(
        OperatingHours.company_id == company_id,
        OperatingHours.theater_name == theater_name,
        OperatingHours.scrape_date == scrape_date
    ).first()

    if not existing:
        # No existing record - insert new
        op_hours = OperatingHours(
            company_id=company_id,
            theater_name=theater_name,
            market=market,
            scrape_date=scrape_date,
            open_time=new_open,
            close_time=new_close,
            first_showtime=new_first,
            last_showtime=new_last,
            showtime_count=new_count or 0,
            duration_hours=new_duration or 0.0
        )
        session.add(op_hours)
        return 'inserted'

    # Parse times for comparison
    new_open_mins = _parse_time_to_minutes(new_open)
    new_close_mins = _parse_time_to_minutes(new_close)
    existing_open_mins = _parse_time_to_minutes(existing.open_time)
    existing_close_mins = _parse_time_to_minutes(existing.close_time)

    # High water mark logic
    final_open = existing.open_time
    final_close = existing.close_time
    final_first = existing.first_showtime
    final_last = existing.last_showtime
    final_count = existing.showtime_count or 0
    final_duration = existing.duration_hours or 0.0
    needs_update = False

    # Keep earliest open time
    if new_open_mins is not None:
        if existing_open_mins is None or new_open_mins < existing_open_mins:
            final_open = new_open
            final_first = new_first
            needs_update = True

    # Keep latest close time
    if new_close_mins is not None:
        if existing_close_mins is None or new_close_mins > existing_close_mins:
            final_close = new_close
            final_last = new_last
            needs_update = True

    # Keep highest showtime count (weather cancellations shouldn't reduce count)
    if new_count and new_count > final_count:
        final_count = new_count
        needs_update = True

    # Keep longest duration
    if new_duration and new_duration > final_duration:
        final_duration = new_duration
        needs_update = True

    if needs_update:
        existing.open_time = final_open
        existing.close_time = final_close
        existing.first_showtime = final_first
        existing.last_showtime = final_last
        existing.showtime_count = final_count
        existing.duration_hours = final_duration
        return 'updated'

    return 'kept'


def save_full_operating_hours_run(operating_hours_data, context, company_id: int = None):
    """
    Save complete operating hours data using high water mark merge logic.

    This preserves the best data from previous scrapes:
    - Earliest open time is kept
    - Latest close time is kept
    - Highest showtime count is kept
    """
    if not operating_hours_data:
        return

    with get_session() as session:
        # Use passed company_id or fall back to config
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        if not company_id:
            company_id = 1  # Default to company 1 for API calls

        stats = {'inserted': 0, 'updated': 0, 'kept': 0}

        # Handle both list format (from utils.py) and dict format (legacy)
        if isinstance(operating_hours_data, list):
            # List format: [{"Date": "...", "Theater": "...", "Market": "...", "Showtime Range": "...", "Duration (hrs)": ...}]
            for hours_record in operating_hours_data:
                # Parse showtime range to get open_time and close_time
                showtime_range = hours_record.get('Showtime Range', '')
                if showtime_range and showtime_range != "No valid showtimes found":
                    # Format: "9:00am - 11:00pm" or similar
                    if ' - ' in showtime_range:
                        open_time, close_time = showtime_range.split(' - ')
                    else:
                        open_time = close_time = None
                else:
                    open_time = close_time = None

                # Parse date
                scrape_date = datetime.strptime(hours_record['Date'], '%Y-%m-%d').date()

                # Get values from record
                duration_hours = hours_record.get('Duration (hrs)', 0.0)
                showtime_count = hours_record.get('Showtime Count') or hours_record.get('Showtimes') or 0
                first_showtime = hours_record.get('First Showtime')
                last_showtime = hours_record.get('Last Showtime')

                result = _merge_operating_hours_record(
                    session=session,
                    company_id=company_id,
                    theater_name=hours_record['Theater'],
                    market=hours_record.get('Market'),
                    scrape_date=scrape_date,
                    new_open=open_time,
                    new_close=close_time,
                    new_first=first_showtime,
                    new_last=last_showtime,
                    new_count=showtime_count,
                    new_duration=duration_hours
                )
                stats[result] += 1
        else:
            # Dict format: {theater_name: [{...}, {...}]}
            for theater_name, hours_list in operating_hours_data.items():
                for hours in hours_list:
                    result = _merge_operating_hours_record(
                        session=session,
                        company_id=company_id,
                        theater_name=theater_name,
                        market=hours.get('market'),
                        scrape_date=hours['scrape_date'],
                        new_open=hours.get('opens_at') or hours.get('open_time'),
                        new_close=hours.get('closes_at') or hours.get('close_time'),
                        new_first=hours.get('first_showtime'),
                        new_last=hours.get('last_showtime'),
                        new_count=hours.get('showtime_count') or hours.get('count') or 0,
                        new_duration=hours.get('duration_hours')
                    )
                    stats[result] += 1

        session.flush()
        print(f"  [DB] Operating hours for {context}: {stats['inserted']} inserted, {stats['updated']} updated, {stats['kept']} kept")


def delete_operating_hours(theater_names, scrape_date, conn=None):
    """Delete operating hours for theaters on date"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(OperatingHours).filter(
            OperatingHours.scrape_date == scrape_date
        )
        
        if company_id:
            query = query.filter(OperatingHours.company_id == company_id)
        
        if theater_names:
            query = query.filter(OperatingHours.theater_name.in_(theater_names))
        
        count = query.delete()
        print(f"  [DB] Deleted {count} operating hours records")


def get_operating_hours_for_theaters_and_dates(theater_list, start_date, end_date):
    """Get operating hours for theaters in date range"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(OperatingHours)
        
        if company_id:
            query = query.filter(OperatingHours.company_id == company_id)
        
        query = query.filter(
            and_(
                OperatingHours.theater_name.in_(theater_list),
                OperatingHours.scrape_date >= start_date,
                OperatingHours.scrape_date <= end_date
            )
        )
        
        df = pd.read_sql(query.statement, session.bind)
        return df


def get_all_op_hours_dates(theater_list):
    """Get all dates with operating hours data"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(OperatingHours.scrape_date).distinct()
        
        if company_id:
            query = query.filter(OperatingHours.company_id == company_id)
        
        if theater_list:
            query = query.filter(OperatingHours.theater_name.in_(theater_list))
        
        query = query.order_by(OperatingHours.scrape_date.desc())
        
        results = query.all()
        return [r[0] for r in results]


# ============================================================================
# FILM METADATA ENRICHMENT
# ============================================================================

def upsert_film_details(film_data: dict, company_id: int = None):
    """Save or update film metadata"""
    with get_session() as session:
        cid = company_id or getattr(config, 'CURRENT_COMPANY_ID', None)
        if not cid:
            # Fallback to 1 if we really can't find it - better than crashing
            cid = 1
        
        film = session.query(Film).filter(
            and_(
                Film.company_id == cid,
                Film.film_title == film_data['film_title']
            )
        ).first()
        
        if film:
            # Update existing
            for key, value in film_data.items():
                if hasattr(film, key) and key != 'film_id':
                    setattr(film, key, value)
            film.last_omdb_update = datetime.now(UTC)
        else:
            # Create new - exclude film_id and last_omdb_update to avoid duplicates
            filtered_data = {k: v for k, v in film_data.items()
                           if k not in ('film_id', 'last_omdb_update', 'company_id')}
            film = Film(
                company_id=cid,
                last_omdb_update=datetime.now(UTC),
                **filtered_data
            )
            session.add(film)
        
        session.flush()


def check_film_exists(film_title: str) -> bool:
    """Check if film metadata exists"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Film).filter(Film.film_title == film_title)
        
        if company_id:
            query = query.filter(Film.company_id == company_id)
        
        return query.first() is not None


def get_film_details(film_title: str) -> dict | None:
    """Get film metadata"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Film).filter(Film.film_title == film_title)
        
        if company_id:
            query = query.filter(Film.company_id == company_id)
        
        film = query.first()
        
        if not film:
            return None
        
        return {
            'film_title': film.film_title,
            'imdb_id': film.imdb_id,
            'genre': film.genre,
            'mpaa_rating': film.mpaa_rating,
            'director': film.director,
            'actors': film.actors,
            'plot': film.plot,
            'poster_url': film.poster_url,
            'metascore': film.metascore,
            'imdb_rating': float(film.imdb_rating) if film.imdb_rating else None,
            'release_date': film.release_date,
            'domestic_gross': film.domestic_gross,
            'runtime': film.runtime,
            'opening_weekend_domestic': film.opening_weekend_domestic,
            'last_omdb_update': film.last_omdb_update
        }


def get_all_unique_genres() -> list[str]:
    """Get all unique genres"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Film.genre).distinct()
        
        if company_id:
            query = query.filter(Film.company_id == company_id)
        
        query = query.filter(Film.genre.isnot(None))
        
        results = query.all()
        return sorted([r[0] for r in results if r[0]])


def get_all_unique_ratings() -> list[str]:
    """Get all unique MPAA ratings"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Film.mpaa_rating).distinct()
        
        if company_id:
            query = query.filter(Film.company_id == company_id)
        
        query = query.filter(Film.mpaa_rating.isnot(None))
        
        results = query.all()
        return sorted([r[0] for r in results if r[0]])


def log_unmatched_film(film_title: str, company_id: int = None):
    """Log film that couldn't be matched"""
    with get_session() as session:
        cid = company_id or getattr(config, 'CURRENT_COMPANY_ID', None)
        if not cid:
            cid = 1
        
        film = session.query(UnmatchedFilm).filter(
            and_(
                UnmatchedFilm.company_id == cid,
                UnmatchedFilm.film_title == film_title
            )
        ).first()
        
        if film:
            film.last_seen = datetime.now(UTC)
            film.occurrence_count += 1
        else:
            film = UnmatchedFilm(
                company_id=cid,
                film_title=film_title,
                first_seen=datetime.now(UTC),
                last_seen=datetime.now(UTC),
                occurrence_count=1
            )
            session.add(film)
        
        session.flush()


def delete_unmatched_film(film_title: str):
    """Remove film from unmatched list"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(UnmatchedFilm).filter(
            UnmatchedFilm.film_title == film_title
        )
        
        if company_id:
            query = query.filter(UnmatchedFilm.company_id == company_id)
        
        film = query.first()
        if film:
            session.delete(film)
            session.flush()


# ============================================================================
# TICKET TYPE MANAGEMENT
# ============================================================================

def get_ticket_type_usage_counts() -> pd.DataFrame:
    """Get usage counts for each ticket type"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(
            Price.ticket_type,
            func.count(Price.price_id).label('count')
        ).group_by(Price.ticket_type)
        
        if company_id:
            query = query.filter(Price.company_id == company_id)
        
        query = query.order_by(func.count(Price.price_id).desc())
        
        df = pd.read_sql(query.statement, session.bind)
        return df


def log_unmatched_ticket_type(original_description: str, unmatched_part: str, showing_details: dict | None = None):
    """Log unmatched ticket type"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None) or 1
        
        ticket_type = UnmatchedTicketType(
            company_id=company_id,
            original_description=original_description,
            unmatched_part=unmatched_part,
            first_seen=datetime.now(UTC)
        )
        
        if showing_details:
            ticket_type.theater_name = showing_details.get('theater_name')
            ticket_type.film_title = showing_details.get('film_title')
            ticket_type.showtime = showing_details.get('showtime')
        
        session.add(ticket_type)
        session.flush()


def get_unmatched_ticket_types() -> pd.DataFrame:
    """Get all unmatched ticket types"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(UnmatchedTicketType)
        
        if company_id:
            query = query.filter(UnmatchedTicketType.company_id == company_id)
        
        df = pd.read_sql(query.statement, session.bind)
        return df


def delete_unmatched_ticket_type(unmatched_id: int):
    """Delete unmatched ticket type"""
    with get_session() as session:
        ticket_type = session.query(UnmatchedTicketType).filter(
            UnmatchedTicketType.unmatched_id == unmatched_id
        ).first()
        
        if ticket_type:
            session.delete(ticket_type)
            session.flush()


# ============================================================================
# ADDITIONAL UTILITY FUNCTIONS
# ============================================================================

def get_films_missing_release_date() -> list[str]:
    """Get films without release dates"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Film.film_title).filter(
            or_(Film.release_date.is_(None), Film.release_date == '')
        )
        
        if company_id:
            query = query.filter(Film.company_id == company_id)
        
        results = query.all()
        return [r[0] for r in results]


def get_films_missing_metadata() -> list[str]:
    """Get films without complete metadata"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        # Get films in showings that don't have metadata
        query = session.query(Showing.film_title).distinct().outerjoin(
            Film, and_(
                Film.film_title == Showing.film_title,
                Film.company_id == Showing.company_id
            )
        ).filter(Film.film_id.is_(None))
        
        if company_id:
            query = query.filter(Showing.company_id == company_id)
        
        results = query.all()
        return [r[0] for r in results]


def get_all_films_for_enrichment(as_df=False):
    """Get all films for metadata enrichment"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Film)
        
        if company_id:
            query = query.filter(Film.company_id == company_id)
        
        if as_df:
            return pd.read_sql(query.statement, session.bind)
        else:
            results = query.all()
            return [
                {
                    'film_title': r.film_title,
                    'imdb_id': r.imdb_id,
                    'genre': r.genre,
                    'mpaa_rating': r.mpaa_rating,
                    'director': r.director,
                    'actors': r.actors,
                    'plot': r.plot,
                    'poster_url': r.poster_url,
                    'metascore': r.metascore,
                    'imdb_rating': float(r.imdb_rating) if r.imdb_rating else None,
                    'release_date': r.release_date,
                    'domestic_gross': r.domestic_gross,
                    'runtime': r.runtime,
                    'opening_weekend_domestic': r.opening_weekend_domestic,
                    'last_omdb_update': r.last_omdb_update
                } for r in results
            ]


def get_ignored_film_titles() -> list[str]:
    """Alias for get_ignored_films for backward compatibility"""
    return get_ignored_films()


def get_first_play_date_for_all_films() -> dict[str, str]:
    """Get the first date each film was seen in a scrape"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(
            Showing.film_title,
            func.min(Showing.play_date)
        ).group_by(Showing.film_title)
        
        if company_id:
            query = query.filter(Showing.company_id == company_id)
            
        results = query.all()
        return {r[0]: str(r[1]) for r in results}


# Stub functions for complex queries - can be implemented as needed
def get_available_films(theaters):
    """Get films available at theaters"""
    return get_common_films_for_theaters_dates(theaters, get_dates_for_theaters(theaters))


def get_available_dates(theaters, films):
    """Get dates with data for theaters and films"""
    dates = get_dates_for_theaters(theaters)
    return dates


def get_available_dayparts(theaters, films, start_date, end_date):
    """Get available dayparts"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        
        query = session.query(Showing.daypart).distinct()
        
        if company_id:
            query = query.filter(Showing.company_id == company_id)
        
        query = query.filter(
            and_(
                Showing.theater_name.in_(theaters),
                Showing.film_title.in_(films),
                Showing.play_date >= start_date,
                Showing.play_date <= end_date
            )
        )
        
        results = query.all()
        return [r[0] for r in results if r[0]]


def get_theaters_with_data(data_type):
    """Get theaters with specific data type"""
    if data_type == 'operating_hours':
        with get_session() as session:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
            
            query = session.query(OperatingHours.theater_name).distinct()
            
            if company_id:
                query = query.filter(OperatingHours.company_id == company_id)
            
            results = query.all()
            return [r[0] for r in results]
    else:
        return get_all_theaters()


def get_common_dates_for_theaters(theaters, data_type):
    """Get dates common to all theaters"""
    return get_dates_for_theaters(theaters)


def backfill_play_dates():
    """Legacy migration function - no-op in PostgreSQL"""
    pass


def migrate_schema():
    """Legacy migration function - no-op in PostgreSQL"""
    return "Schema managed by SQLAlchemy migrations"


def consolidate_ticket_types() -> int:
    """Consolidate ticket type variations"""
    # TODO: Implement ticket type consolidation
    return 0


# ============================================================================
# BACKFILL FUNCTIONS
# ============================================================================

def backfill_film_details_from_fandango() -> int:
    """
    Backfill film details (runtime, MPAA rating, poster, etc.) from OMDB
    for films that exist in showings but don't have complete metadata.

    Returns:
        Number of films updated
    """
    from app.omdb_client import OMDbClient

    count = 0

    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        # If no company_id set (admin without company), get all companies with showings
        if not company_id:
            company_ids = session.query(Showing.company_id).distinct().all()
            company_ids = [c[0] for c in company_ids if c[0]]
        else:
            company_ids = [company_id]

        if not company_ids:
            return 0

        try:
            omdb = OMDbClient()
        except ValueError:
            # No OMDB API key configured
            return 0

        for cid in company_ids:
            # Temporarily set the company_id for upsert operations
            original_company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
            config.CURRENT_COMPANY_ID = cid

            try:
                # Get all distinct film titles from showings for this company
                showing_films = session.query(Showing.film_title).filter(
                    Showing.company_id == cid
                ).distinct().all()
                showing_titles = {r[0] for r in showing_films}

                # Get existing films that need updating (missing runtime or mpaa_rating)
                existing_films = session.query(Film.film_title).filter(
                    and_(
                        Film.company_id == cid,
                        or_(
                            Film.runtime.is_(None),
                            Film.runtime == '',
                            Film.runtime == 'N/A',
                            Film.mpaa_rating.is_(None),
                            Film.mpaa_rating == '',
                            Film.mpaa_rating == 'N/A'
                        )
                    )
                ).all()
                films_needing_update = {r[0] for r in existing_films}

                # Get titles that don't exist in films table
                all_film_titles = session.query(Film.film_title).filter(
                    Film.company_id == cid
                ).all()
                existing_titles = {r[0] for r in all_film_titles}
                missing_titles = showing_titles - existing_titles

                # Combine: titles not in films table + titles missing data
                titles_to_fetch = missing_titles | films_needing_update

                for title in titles_to_fetch:
                    try:
                        film_details = omdb.get_film_details(title)
                        if film_details and film_details.get('runtime'):
                            film_details['film_title'] = title  # Preserve original title
                            upsert_film_details(film_details)
                            count += 1
                        else:
                            # Log unmatched film for review
                            add_unmatched_film(title)
                    except Exception as e:
                        print(f"Error fetching details for '{title}': {e}")
                        add_unmatched_film(title)
                        continue
            finally:
                # Restore original company_id
                config.CURRENT_COMPANY_ID = original_company_id

    return count


def backfill_imdb_ids_from_fandango() -> int:
    """
    Backfill IMDB IDs for films that don't have them.

    Returns:
        Number of films updated
    """
    from app.omdb_client import OMDbClient

    count = 0

    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        # If no company_id set, get all companies with films
        if not company_id:
            company_ids = session.query(Film.company_id).distinct().all()
            company_ids = [c[0] for c in company_ids if c[0]]
        else:
            company_ids = [company_id]

        if not company_ids:
            return 0

        try:
            omdb = OMDbClient()
        except ValueError:
            return 0

        for cid in company_ids:
            original_company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
            config.CURRENT_COMPANY_ID = cid

            try:
                # Get films without IMDB IDs
                films_without_ids = session.query(Film.film_title).filter(
                    and_(
                        Film.company_id == cid,
                        or_(
                            Film.imdb_id.is_(None),
                            Film.imdb_id == '',
                            Film.imdb_id == 'N/A'
                        )
                    )
                ).all()

                for (title,) in films_without_ids:
                    try:
                        film_details = omdb.get_film_details(title)
                        if film_details and film_details.get('imdb_id'):
                            film_details['film_title'] = title
                            upsert_film_details(film_details)
                            count += 1
                    except Exception as e:
                        print(f"Error fetching IMDB ID for '{title}': {e}")
                        continue
            finally:
                config.CURRENT_COMPANY_ID = original_company_id

    return count


def backfill_showtimes_data_from_fandango() -> int:
    """
    Ensure all films in the showings table have corresponding entries
    in the films table (creates placeholder entries if needed).

    Returns:
        Number of films created
    """
    count = 0

    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        # If no company_id set, get all companies with showings
        if not company_id:
            company_ids = session.query(Showing.company_id).distinct().all()
            company_ids = [c[0] for c in company_ids if c[0]]
        else:
            company_ids = [company_id]

        if not company_ids:
            return 0

        for cid in company_ids:
            # Get all distinct film titles from showings
            showing_films = session.query(Showing.film_title).filter(
                Showing.company_id == cid
            ).distinct().all()
            showing_titles = {r[0] for r in showing_films}

            # Get all existing film titles
            existing_films = session.query(Film.film_title).filter(
                Film.company_id == cid
            ).all()
            existing_titles = {r[0] for r in existing_films}

            # Find missing titles
            missing_titles = showing_titles - existing_titles

            # Create placeholder entries for missing films
            for title in missing_titles:
                film = Film(
                    company_id=cid,
                    film_title=title
                )
                session.add(film)
                count += 1

        if count > 0:
            session.flush()

    return count
