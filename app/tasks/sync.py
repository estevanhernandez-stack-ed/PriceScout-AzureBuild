"""
Celery tasks for Data Sync operations.
"""

from app.celery_app import app
from api.services.enttelligence_cache_service import get_cache_service
import logging

logger = logging.getLogger(__name__)

@app.task(name="app.tasks.sync.sync_enttelligence_task")
def sync_enttelligence_task(company_id, start_date, end_date=None, circuits=None):
    """
    Background task to sync data from EntTelligence.
    """
    try:
        cache_service = get_cache_service()
        result = cache_service.sync_prices_for_dates(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            circuits=circuits
        )
        
        return {
            'status': 'success',
            'records_fetched': result.get('records_fetched', 0),
            'records_cached': result.get('records_cached', 0),
            'errors': result.get('errors', 0)
        }
    except Exception as e:
        logger.exception(f"EntTelligence sync task failed: {e}")
        return {'status': 'failed', 'error': str(e)}

@app.task(name="app.tasks.sync.sync_market_context_task")
def sync_market_context_task(company_id, theater_names):
    """
    Background task to sync theater metadata and geocoding.
    """
    try:
        from api.services.market_context_service import get_market_context_service
        service = get_market_context_service()
        result = service.sync_theaters_from_enttelligence(
            company_id=company_id,
            theater_names=theater_names
        )
        return result
    except Exception as e:
        logger.exception(f"Market Context sync task failed: {e}")
        return {'status': 'failed', 'error': str(e)}
@app.task(name="app.tasks.sync.sync_presales_task")
def sync_presales_task():
    """
    Background task to sync presale data.
    """
    try:
        from presale_reconciliation import sync_presales
        sync_presales()
        return {'status': 'success', 'message': 'Presale data synced successfully'}
    except Exception as e:
        logger.exception(f"Presale sync task failed: {e}")
        return {'status': 'failed', 'error': str(e)}

@app.task(name="app.tasks.sync.sync_circuit_benchmarks_task")
def sync_circuit_benchmarks_task():
    """
    Background task to sync circuit benchmarks.
    """
    try:
        from sync_engine import run_nationwide_sync
        run_nationwide_sync()
        return {'status': 'success', 'message': 'Circuit benchmarks synced successfully'}
    except Exception as e:
        logger.exception(f"Circuit benchmark sync task failed: {e}")
        return {'status': 'failed', 'error': str(e)}
