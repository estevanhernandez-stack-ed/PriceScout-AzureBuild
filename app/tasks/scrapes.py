"""
Celery tasks for Scrape operations.
"""

from app.celery_app import app
from app.scraper import Scraper
from app.alert_service import generate_alerts_for_scrape
from app.notification_service import dispatch_alerts_sync
from app import db_adapter as database
import pandas as pd
import asyncio
import sys
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def _run_async_in_thread(coro):
    """Utility to run async code in sync Celery task."""
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.task(bind=True, name="app.tasks.scrapes.run_scrape_task")
def run_scrape_task(self, mode, market, theaters, dates, company_id=1, use_cache=False, cache_max_age_hours=6):
    """
    Distributed task to run a scrape.
    """
    self.update_state(state='PROGRESS', meta={'progress': 0, 'status': 'Starting scraper...'})
    
    start_time = datetime.now()
    scout = Scraper(headless=True)
    all_results = []
    
    # Pre-calculate total theaters/dates for progress tracking
    total_steps = len(theaters) * len(dates)
    current_step = 0

    try:
        for i, theater in enumerate(theaters):
            for date_str in dates:
                current_step += 1
                progress = int((current_step / total_steps) * 100)
                self.update_state(state='PROGRESS', meta={
                    'progress': progress, 
                    'status': f'Scraping {theater["name"]} for {date_str}...',
                    'current_theater': theater["name"]
                })

                # Perform scrape
                showings_by_theater = _run_async_in_thread(
                    scout.get_all_showings_for_theaters([theater], date_str)
                )
                
                theater_results = showings_by_theater.get(theater["name"], [])
                all_results.extend(theater_results)

        if not all_results:
            return {'status': 'completed', 'records': 0, 'message': 'No showtimes found'}

        # Save to database
        df = pd.DataFrame(all_results)
        # We need a run_id
        run_id = database.create_scrape_run(mode, market or "Manual Distributed")
        database.save_prices(run_id, df)
        
        # Generate alerts
        alerts = generate_alerts_for_scrape(company_id, run_id, df)
        
        # Dispatch notifications if alerts found
        if alerts:
            dispatch_alerts_sync(company_id, alerts)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        return {
            'status': 'completed',
            'run_id': run_id,
            'records': len(all_results),
            'duration_seconds': duration,
            'alerts_generated': len(alerts)
        }

    except Exception as e:
        logger.exception(f"Scrape task failed: {e}")
        return {'status': 'failed', 'error': str(e)}
