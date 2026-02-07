"""
Operating hours management: save, merge (high water mark), query, and delete.
"""

import pandas as pd
from datetime import datetime
from sqlalchemy import and_
from app.db_session import get_session
from app.db_models import OperatingHours
from app.db.utils import _parse_time_to_minutes
from app import config


def save_operating_hours(run_id, operating_hours_data, conn=None):
    """Save operating hours data (compatibility wrapper)"""
    save_full_operating_hours_run(operating_hours_data, f"run_{run_id}")


def _merge_operating_hours_record(session, company_id, theater_name, market, scrape_date,
                                   new_open, new_close, new_first, new_last, new_count, new_duration):
    """
    Merge a single operating hours record using high water mark logic.

    Preserves the widest known operating window:
    - Keep earliest open time
    - Keep latest close time
    - Keep highest showtime count
    """
    existing = session.query(OperatingHours).filter(
        OperatingHours.company_id == company_id,
        OperatingHours.theater_name == theater_name,
        OperatingHours.scrape_date == scrape_date
    ).first()

    if not existing:
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

    new_open_mins = _parse_time_to_minutes(new_open)
    new_close_mins = _parse_time_to_minutes(new_close)
    existing_open_mins = _parse_time_to_minutes(existing.open_time)
    existing_close_mins = _parse_time_to_minutes(existing.close_time)

    final_open = existing.open_time
    final_close = existing.close_time
    final_first = existing.first_showtime
    final_last = existing.last_showtime
    final_count = existing.showtime_count or 0
    final_duration = existing.duration_hours or 0.0
    needs_update = False

    if new_open_mins is not None:
        if existing_open_mins is None or new_open_mins < existing_open_mins:
            final_open = new_open
            final_first = new_first
            needs_update = True

    if new_close_mins is not None:
        if existing_close_mins is None or new_close_mins > existing_close_mins:
            final_close = new_close
            final_last = new_last
            needs_update = True

    if new_count and new_count > final_count:
        final_count = new_count
        needs_update = True

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
    """
    if not operating_hours_data:
        return

    with get_session() as session:
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        if not company_id:
            company_id = 1

        stats = {'inserted': 0, 'updated': 0, 'kept': 0}

        if isinstance(operating_hours_data, list):
            for hours_record in operating_hours_data:
                showtime_range = hours_record.get('Showtime Range', '')
                if showtime_range and showtime_range != "No valid showtimes found":
                    if ' - ' in showtime_range:
                        open_time, close_time = showtime_range.split(' - ')
                    else:
                        open_time = close_time = None
                else:
                    open_time = close_time = None

                scrape_date = datetime.strptime(hours_record['Date'], '%Y-%m-%d').date()
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
