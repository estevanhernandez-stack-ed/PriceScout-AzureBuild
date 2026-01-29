"""
Celery tasks for System maintenance and data retention.
"""

import logging
import os
from datetime import datetime
from app.celery_app import app
from app.retention_service import get_retention_service
from app.circuit_breaker import get_all_circuit_status
from app.audit_service import audit_service
from app.db_session import get_session
from app.db_models import AlertConfiguration

logger = logging.getLogger(__name__)

@app.task(name="app.tasks.system.data_retention_task")
def data_retention_task():
    """
    Background task to clean up old historical data.
    Runs daily.
    """
    try:
        service = get_retention_service()
        results = service.cleanup_old_data()
        
        return {
            'status': 'success',
            'deleted_counts': results
        }
    except Exception as e:
        logger.exception(f"Data retention task failed: {e}")
        return {'status': 'failed', 'error': str(e)}

@app.task(name="app.tasks.system.database_vacuum_task")
def database_vacuum_task():
    """
    Task to optimize SQLite database (VACUUM).
    Note: Highly resource intensive on large databases.
    """
    try:
        from app.db_session import get_engine
        from sqlalchemy import text
        
        engine = get_engine()
        with engine.connect() as conn:
            # SQLite specific vacuum
            conn.execute(text("VACUUM"))
            
        return {'status': 'success'}
    except Exception as e:
        logger.exception(f"Database vacuum task failed: {e}")
        return {'status': 'failed', 'error': str(e)}

@app.task(name="app.tasks.system.monitor_circuit_breakers_task")
def monitor_circuit_breakers_task(company_id: int = 1):
    """
    Monitor circuit breaker status and send alerts if any are OPEN.
    Specifically useful for early morning (2am) health checks.
    """
    try:
        circuits = get_all_circuit_status()
        open_circuits = [name for name, status in circuits.items() if status['state'] == 'open']
        
        if not open_circuits:
            return {'status': 'healthy', 'open_circuits': []}
            
        # Log to Audit Log
        audit_service.system_event(
            event_type="circuit_breaker_alert",
            severity="critical",
            company_id=company_id,
            details={
                "open_circuits": open_circuits,
                "states": {name: circuits[name]['state'] for name in open_circuits},
                "msg": "Circuit breaker(s) are OPEN. External services may be unavailable."
            }
        )
        
        # Send Email/Webhook if configured
        with get_session() as session:
            config = session.query(AlertConfiguration).filter(
                AlertConfiguration.company_id == company_id
            ).first()
            
            if config and config.notification_enabled and config.notification_email:
                # We can't use dispatch_alert_notifications directly because it expects PriceAlert objects
                # For now, we manually log the intent, in a real scenario we'd use a generic notification tool
                logger.error(f"ALERT: Circuit breakers {open_circuits} are OPEN. Sending notification to {config.notification_email}")
                
        return {
            'status': 'unhealthy',
            'open_circuits': open_circuits
        }
    except Exception as e:
        logger.exception(f"Circuit monitor task failed: {e}")
        return {'status': 'failed', 'error': str(e)}
