"""
Scrape Run Management Module
PriceScout Database Adapter Layer

Provides scrape run tracking:
- create_scrape_run: Create a new scrape run
- update_scrape_run_status: Update run status
"""

from datetime import datetime, UTC
from app.db_session import get_session
from app.db_models import ScrapeRun
from app import config


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
