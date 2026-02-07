"""
Ticket type management: usage tracking and unmatched type logging.
"""

import pandas as pd
from datetime import datetime, UTC
from sqlalchemy import func
from app.db_session import get_session
from app.db_models import Price, UnmatchedTicketType
from app import config


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
