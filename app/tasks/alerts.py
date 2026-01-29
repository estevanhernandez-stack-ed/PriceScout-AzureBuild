"""
Celery tasks for Monitoring and Alerts.
"""

from app.celery_app import app
from app.schedule_monitor_service import ScheduleMonitorService
from app.notification_service import dispatch_schedule_alert_notifications
import logging

logger = logging.getLogger(__name__)

@app.task(name="app.tasks.alerts.run_schedule_monitor_task")
def run_schedule_monitor_task(company_id, theater_names=None, play_dates=None):
    """
    Background task to run a schedule monitor check.
    """
    try:
        service = ScheduleMonitorService(company_id)
        
        # Run the check
        changes = service.run_check(
            theater_names=theater_names,
            play_dates=play_dates
        )
        
        if changes:
            # Convert ScheduleChange objects to dicts for notification
            alerts = [
                {
                    'theater_name': c.theater_name,
                    'film_title': c.film_title,
                    'play_date': c.play_date,
                    'alert_type': c.alert_type,
                    'change_details': c.change_details,
                    'old_value': c.old_value,
                    'new_value': c.new_value
                } for c in changes
            ]
            
            # Dispatch notifications
            # This is async, so we'll run it in the loop
            import asyncio
            import sys
            
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(dispatch_schedule_alert_notifications(company_id, alerts))
            finally:
                loop.close()
                
        return {
            'status': 'success',
            'changes_found': len(changes) if changes else 0
        }
    except Exception as e:
        logger.exception(f"Schedule monitor task failed: {e}")
        return {'status': 'failed', 'error': str(e)}
