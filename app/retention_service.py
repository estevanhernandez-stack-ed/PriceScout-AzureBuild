"""
Retention Service
Handles automatic cleanup of historical data to manage database size and performance.
"""

import logging
from datetime import datetime, timedelta, UTC
from typing import Dict, Any

from app.db_session import get_session
from app.db_models import (
    Showing, Price, ScrapeRun, AuditLog, 
    PriceAlert, ScheduleAlert, EntTelligencePriceCache,
    OperatingHours, EntTelligenceSyncRun
)

logger = logging.getLogger(__name__)

# Default retention periods (in days)
DEFAULT_RETENTION = {
    'showings': 90,           # Scraped price data
    'scrape_runs': 90,        # Meta-data about scrapes
    'audit_log': 180,         # Security and change logs
    'price_alerts': 60,       # Individual price alerts
    'schedule_alerts': 60,    # Individual schedule alerts
    'cache': 7,               # EntTelligence hybrid cache (usually expires in 24h anyway)
    'operating_hours': 90,    # Historical operating hours
}

class RetentionService:
    """
    Service for cleaning up old historical data.
    """

    def __init__(self):
        pass

    def cleanup_old_data(self, retention_days: Dict[str, int] = None) -> Dict[str, int]:
        """
        Deletes historical data records older than specified retention periods.
        
        Returns:
           Dict with counts of deleted records per category
        """
        days = DEFAULT_RETENTION.copy()
        if retention_days:
            days.update(retention_days)

        results = {}
        
        with get_session() as session:
            # 1. Price Data (Showing -> Price cascade delete handled by DB/ORM)
            cutoff_showings = datetime.now(UTC) - timedelta(days=days['showings'])
            deleted_showings = session.query(Showing).filter(Showing.play_date < cutoff_showings.date()).delete(synchronize_session=False)
            results['showings'] = deleted_showings
            
            # Orphaned prices (manual cleanup if cascade isn't perfect or needed)
            deleted_prices = session.query(Price).filter(Price.play_date < cutoff_showings.date()).delete(synchronize_session=False)
            results['prices'] = deleted_prices

            # 2. Scrape Runs
            cutoff_scrapes = datetime.now(UTC) - timedelta(days=days['scrape_runs'])
            deleted_scrapes = session.query(ScrapeRun).filter(ScrapeRun.run_timestamp < cutoff_scrapes).delete(synchronize_session=False)
            results['scrape_runs'] = deleted_scrapes

            # 3. Audit Logs
            cutoff_audit = datetime.now(UTC) - timedelta(days=days['audit_log'])
            deleted_audit = session.query(AuditLog).filter(AuditLog.timestamp < cutoff_audit).delete(synchronize_session=False)
            results['audit_log'] = deleted_audit

            # 4. Alerts
            cutoff_price_alerts = datetime.now(UTC) - timedelta(days=days['price_alerts'])
            deleted_price_alerts = session.query(PriceAlert).filter(PriceAlert.triggered_at < cutoff_price_alerts).delete(synchronize_session=False)
            results['price_alerts'] = deleted_price_alerts

            cutoff_schedule_alerts = datetime.now(UTC) - timedelta(days=days['schedule_alerts'])
            deleted_schedule_alerts = session.query(ScheduleAlert).filter(ScheduleAlert.triggered_at < cutoff_schedule_alerts).delete(synchronize_session=False)
            results['schedule_alerts'] = deleted_schedule_alerts

            # 5. Hybrid Cache
            cutoff_cache = datetime.now(UTC) - timedelta(days=days['cache'])
            deleted_cache = session.query(EntTelligencePriceCache).filter(EntTelligencePriceCache.expires_at < cutoff_cache).delete(synchronize_session=False)
            results['cache'] = deleted_cache

            # 6. Operating Hours
            cutoff_op_hours = datetime.now(UTC) - timedelta(days=days['operating_hours'])
            deleted_op_hours = session.query(OperatingHours).filter(OperatingHours.scrape_date < cutoff_op_hours.date()).delete(synchronize_session=False)
            results['operating_hours'] = deleted_op_hours

            # 7. Sync Runs
            deleted_sync_runs = session.query(EntTelligenceSyncRun).filter(EntTelligenceSyncRun.started_at < cutoff_scrapes).delete(synchronize_session=False)
            results['sync_runs'] = deleted_sync_runs

            session.commit()
            
        logger.info(f"Retention Cleanup Completed: {results}")
        return results

def get_retention_service():
    return RetentionService()
