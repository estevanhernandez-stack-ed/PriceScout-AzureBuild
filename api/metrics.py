"""
Prometheus Metrics for PriceScout

Provides infrastructure-level metrics for monitoring dashboards (e.g., Grafana).
Exports metrics in Prometheus text format at /metrics endpoint.

Metrics Exported:
- pricescout_scrapes_total: Counter of scrape operations by mode and status
- pricescout_alerts_total: Counter of alerts triggered by type
- pricescout_repairs_total: Counter of theater repairs by status
- pricescout_scrape_duration_seconds: Histogram of scrape durations
- pricescout_api_request_duration_seconds: Histogram of API request durations
- pricescout_pending_alerts: Gauge of pending alerts by type
- pricescout_circuit_state: Gauge of circuit breaker states

Usage:
    Include the metrics router in your FastAPI app:

    from api.metrics import router as metrics_router
    app.include_router(metrics_router)

    Then access metrics at: GET /metrics
"""

import os
import sqlite3
import logging
from typing import Optional

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

from app import config

logger = logging.getLogger(__name__)

# Try to import prometheus_client
try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        Info,
        generate_latest,
        CONTENT_TYPE_LATEST,
        REGISTRY,
        CollectorRegistry
    )
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    logger.warning("prometheus_client not installed - metrics endpoint will return placeholder")


router = APIRouter(tags=["Metrics"])


if HAS_PROMETHEUS:
    # =========================================================================
    # Counters - Track cumulative totals
    # =========================================================================

    # Scrape operations counter
    scrape_total = Counter(
        'pricescout_scrapes_total',
        'Total number of scrape operations',
        ['mode', 'status']  # mode: market, compsnipe; status: success, failure
    )

    # Alerts counter
    alerts_total = Counter(
        'pricescout_alerts_total',
        'Total alerts triggered',
        ['type']  # type: price_increase, price_decrease, surge_detected, new_film, etc.
    )

    # Repairs counter
    repairs_total = Counter(
        'pricescout_repairs_total',
        'Total theater URL repair attempts',
        ['status']  # status: success, failure
    )

    # Notifications counter
    notifications_total = Counter(
        'pricescout_notifications_total',
        'Total notifications dispatched',
        ['type', 'channel']  # type: price, schedule; channel: webhook, email
    )

    # =========================================================================
    # Histograms - Track distributions
    # =========================================================================

    # Scrape duration histogram
    scrape_duration = Histogram(
        'pricescout_scrape_duration_seconds',
        'Duration of scrape operations',
        ['mode'],
        buckets=[5, 10, 30, 60, 120, 300, 600]  # 5s to 10min
    )

    # API request duration histogram
    api_request_duration = Histogram(
        'pricescout_api_request_duration_seconds',
        'Duration of API requests',
        ['endpoint', 'method'],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
    )

    # =========================================================================
    # Gauges - Track current values
    # =========================================================================

    # Pending alerts gauge
    pending_alerts = Gauge(
        'pricescout_pending_alerts',
        'Number of pending (unacknowledged) alerts',
        ['type']  # type: price, schedule
    )

    # Circuit breaker state gauge (1 = closed/healthy, 0 = open/unhealthy)
    circuit_state = Gauge(
        'pricescout_circuit_state',
        'Circuit breaker state (1=closed, 0=open)',
        ['name']  # name: fandango, enttelligence
    )

    # Repair queue size gauge
    repair_queue_size = Gauge(
        'pricescout_repair_queue_size',
        'Number of theaters in repair queue',
        ['status']  # status: pending, max_attempts
    )

    # Active theaters gauge
    active_theaters = Gauge(
        'pricescout_active_theaters',
        'Number of active theaters in cache',
        ['status']  # status: healthy, failed
    )

    # =========================================================================
    # Info - Static labels
    # =========================================================================

    app_info = Info(
        'pricescout',
        'PriceScout application information'
    )
    app_info.info({
        'version': '2.0.0',
        'environment': 'production' if config.is_production() else 'development'
    })


def _update_gauge_metrics():
    """Update gauge metrics with current values from database/services."""
    if not HAS_PROMETHEUS:
        return

    db_path = getattr(config, 'DB_FILE', None) or os.path.join(config.PROJECT_DIR, 'pricescout.db')

    # Update pending alerts
    try:
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Price alerts
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='price_alerts'
            """)
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM price_alerts WHERE is_acknowledged = 0")
                pending_alerts.labels(type='price').set(cursor.fetchone()[0] or 0)

            # Schedule alerts
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='schedule_alerts'
            """)
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM schedule_alerts WHERE is_acknowledged = 0")
                pending_alerts.labels(type='schedule').set(cursor.fetchone()[0] or 0)

            conn.close()
    except Exception as e:
        logger.debug(f"Error updating alert metrics: {e}")

    # Update circuit breaker states
    try:
        from app.circuit_breaker import fandango_breaker, enttelligence_breaker, CircuitState
        circuit_state.labels(name='fandango').set(
            1 if fandango_breaker.state == CircuitState.CLOSED else 0
        )
        circuit_state.labels(name='enttelligence').set(
            1 if enttelligence_breaker.state == CircuitState.CLOSED else 0
        )
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Error updating circuit breaker metrics: {e}")

    # Update repair queue metrics
    try:
        from app.repair_queue import repair_queue
        status = repair_queue.get_queue_status()
        repair_queue_size.labels(status='pending').set(
            status['total_queued'] - status['max_attempts_reached']
        )
        repair_queue_size.labels(status='max_attempts').set(
            status['max_attempts_reached']
        )
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Error updating repair queue metrics: {e}")


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus text exposition format.
    Scraped by Prometheus server for monitoring dashboards.

    Example metrics:
    ```
    # HELP pricescout_pending_alerts Number of pending (unacknowledged) alerts
    # TYPE pricescout_pending_alerts gauge
    pricescout_pending_alerts{type="price"} 5
    pricescout_pending_alerts{type="schedule"} 2
    ```
    """
    if not HAS_PROMETHEUS:
        return PlainTextResponse(
            "# prometheus_client not installed\n"
            "# Install with: pip install prometheus-client\n",
            media_type="text/plain"
        )

    # Update gauge metrics with current values
    _update_gauge_metrics()

    # Generate and return metrics
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST
    )


# =========================================================================
# Helper functions for recording metrics from other parts of the app
# =========================================================================

def record_scrape(mode: str, status: str, duration_seconds: Optional[float] = None):
    """
    Record a scrape operation metric.

    Args:
        mode: Scrape mode (market, compsnipe, etc.)
        status: Result status (success, failure)
        duration_seconds: Optional duration in seconds
    """
    if not HAS_PROMETHEUS:
        return

    scrape_total.labels(mode=mode, status=status).inc()
    if duration_seconds is not None:
        scrape_duration.labels(mode=mode).observe(duration_seconds)


def record_alert(alert_type: str):
    """
    Record an alert being triggered.

    Args:
        alert_type: Type of alert (price_increase, price_decrease, surge_detected, etc.)
    """
    if not HAS_PROMETHEUS:
        return

    alerts_total.labels(type=alert_type).inc()


def record_repair(status: str):
    """
    Record a theater repair attempt.

    Args:
        status: Result status (success, failure)
    """
    if not HAS_PROMETHEUS:
        return

    repairs_total.labels(status=status).inc()


def record_notification(notification_type: str, channel: str):
    """
    Record a notification being sent.

    Args:
        notification_type: Type of notification (price, schedule)
        channel: Delivery channel (webhook, email)
    """
    if not HAS_PROMETHEUS:
        return

    notifications_total.labels(type=notification_type, channel=channel).inc()


def record_api_request(endpoint: str, method: str, duration_seconds: float):
    """
    Record an API request metric.

    Args:
        endpoint: API endpoint path
        method: HTTP method
        duration_seconds: Request duration in seconds
    """
    if not HAS_PROMETHEUS:
        return

    api_request_duration.labels(endpoint=endpoint, method=method).observe(duration_seconds)
