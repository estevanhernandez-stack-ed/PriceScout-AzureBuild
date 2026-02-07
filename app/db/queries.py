"""
Data queries: theater/market lookups, historical data, analysis mode, utility queries.
"""

import pandas as pd
from datetime import datetime
from typing import Optional
from contextlib import contextmanager
from sqlalchemy import text, and_, func
from app.db_session import get_session, get_engine, legacy_db_connection
from app.db_models import (
    Company, Showing, Price, Film, ScrapeRun,
    OperatingHours, TheaterOperatingHours
)
from app.simplified_baseline_service import normalize_daypart
from app import config


@contextmanager
def _get_db_connection():
    """Legacy compatibility: context manager for database connections."""
    with legacy_db_connection() as conn:
        yield conn


# ============================================================================
# THEATER / MARKET QUERIES
# ============================================================================

def get_dates_for_theaters(theater_list):
    """Gets the unique dates that the selected theaters have records for."""
    if not theater_list:
        return []

    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(Showing.play_date).distinct()

        if company_id:
            query = query.filter(Showing.company_id == company_id)

        query = query.filter(Showing.theater_name.in_(theater_list))
        query = query.order_by(Showing.play_date.desc())

        results = query.all()
        return [row[0] for row in results]


def get_common_films_for_theaters_dates(theater_list, date_list):
    """Gets films available for ALL selected theaters on AT LEAST ONE of the selected dates."""
    if not theater_list or not date_list:
        return []

    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

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

        sub = subquery.subquery()
        query = session.query(sub.c.film_title).group_by(sub.c.film_title).having(
            func.count(func.distinct(sub.c.theater_name)) == len(theater_list)
        ).order_by(sub.c.film_title)

        results = query.all()
        return [row[0] for row in results]


def get_theater_comparison_summary(theater_list, start_date, end_date):
    """Generates a summary DataFrame for comparing multiple theaters side-by-side."""
    if not theater_list:
        return pd.DataFrame()

    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

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


def get_market_at_a_glance_data(theater_list: list[str], start_date: datetime.date, end_date: datetime.date, films: Optional[list[str]] = None) -> tuple[pd.DataFrame, Optional[datetime.date]]:
    """Fetches data for the 'Market At a Glance' report."""
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

        if films:
            film_placeholders = ",".join(["?"] * len(films))
            query += f" AND s.film_title IN ({film_placeholders})"
            params.extend(films)

        df = pd.read_sql_query(query, conn, params=params)

    latest_scrape_date = None
    if not df.empty and 'run_timestamp' in df.columns:
        latest_scrape_date = pd.to_datetime(df['run_timestamp']).max().date()

    if not df.empty:
        import json
        import os
        try:
            ticket_types_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ticket_types.json')
            with open(ticket_types_path, 'r') as f:
                ticket_types_data = json.load(f)
            base_type_map = ticket_types_data.get('base_type_map', {})

            reverse_map = {}
            for canonical, variations in base_type_map.items():
                reverse_map[canonical.lower()] = canonical
                for variation in variations:
                    reverse_map[variation.lower()] = canonical

            df['ticket_type'] = df['ticket_type'].str.lower().map(reverse_map).fillna(df['ticket_type'])

        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"  [DB-WARN] Could not consolidate ticket types for glance report. Error: {e}")

    return df, latest_scrape_date


def calculate_operating_hours_from_showings(theater_list: list[str], start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    """[FALLBACK] Calculates operating hours from min/max showtimes."""
    from app.utils import normalize_time_string
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

    df['time_obj'] = df['showtime'].apply(lambda x: datetime.strptime(normalize_time_string(x), "%I:%M%p").time())

    agg_df = df.groupby(['theater_name', 'scrape_date']).agg(
        open_time=('time_obj', 'min'),
        close_time=('time_obj', 'max')
    ).reset_index()

    agg_df['open_time'] = agg_df['open_time'].apply(lambda x: x.strftime('%I:%M %p').lstrip('0'))
    agg_df['close_time'] = agg_df['close_time'].apply(lambda x: x.strftime('%I:%M %p').lstrip('0'))

    return agg_df[['scrape_date', 'theater_name', 'open_time', 'close_time']]


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
# COMPANY CONTEXT (kept here for backward compat, canonical in core.py)
# ============================================================================

def set_current_company(company_name):
    """Set the current company context for all database operations."""
    with get_session() as session:
        company = session.query(Company).filter(Company.company_name == company_name).first()

        if company:
            config.CURRENT_COMPANY_ID = company.company_id
            print(f"[DB] Set current company: {company_name} (ID: {company.company_id})")
        else:
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
# ANALYSIS MODE QUERIES
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
            filters.append(Showing.daypart == (normalize_daypart(daypart) or daypart))

        query = query.filter(and_(*filters))

        df = pd.read_sql(query.statement, session.bind)
        return df


# ============================================================================
# UTILITY QUERIES
# ============================================================================

def get_available_films(theaters):
    """Get films available at theaters"""
    return get_common_films_for_theaters_dates(theaters, get_dates_for_theaters(theaters))


def get_available_dates(theaters, films):
    """Get dates with data for theaters and films"""
    return get_dates_for_theaters(theaters)


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


# ============================================================================
# LEGACY / NO-OP STUBS
# ============================================================================

def backfill_play_dates():
    """Legacy migration function - no-op in PostgreSQL"""
    pass


def consolidate_ticket_types() -> int:
    """Consolidate ticket type variations"""
    return 0
