"""
Database Core Module - Initialization and Company Context
PriceScout Database Adapter Layer

Provides:
- Database initialization
- Company context management (multi-tenant support)
"""

from contextlib import contextmanager
from app.db_session import get_session, legacy_db_connection
from app.db_models import Company
from app import config


def init_database():
    """Initialize database schema (SQLAlchemy version)"""
    from app.db_session import init_database as sa_init_database
    sa_init_database()


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


@contextmanager
def get_db_connection():
    """
    Legacy compatibility: context manager for database connections.
    Now uses SQLAlchemy underneath.
    """
    with legacy_db_connection() as conn:
        yield conn
