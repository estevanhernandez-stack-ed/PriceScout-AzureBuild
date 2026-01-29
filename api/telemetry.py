"""
Application Insights Telemetry Module for PriceScout

Provides custom telemetry tracking for business metrics:
- Scrape operations and performance
- Price change detection and analysis
- API usage and performance metrics
- User behavior analytics

Usage:
    from api.telemetry import track_scrape, track_price_change
    
    track_scrape(theater_count=5, showing_count=120, duration=45.3)
    track_price_change(theater="AMC 14", old_price=12.99, new_price=13.99)
"""

import logging
from typing import Dict, Optional
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

# Global telemetry client (initialized on first use)
_telemetry_client = None


def get_telemetry_client():
    """
    Get or create the Application Insights telemetry client.
    Returns None if Application Insights is not configured.
    """
    global _telemetry_client
    
    if _telemetry_client is not None:
        return _telemetry_client
    
    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        
        # Get tracer and meter for custom telemetry
        tracer = trace.get_tracer(__name__)
        meter = metrics.get_meter(__name__)
        
        _telemetry_client = {
            'tracer': tracer,
            'meter': meter,
            'enabled': True
        }
        
        logger.info("Application Insights telemetry initialized")
        return _telemetry_client
        
    except Exception as e:
        logger.warning(f"Application Insights not available: {e}")
        _telemetry_client = {'enabled': False}
        return _telemetry_client


def track_event(name: str, properties: Optional[Dict[str, str]] = None):
    """
    Track a custom event in Application Insights.
    
    Args:
        name: Event name (e.g., "PriceScout.Scrape.Started")
        properties: Dictionary of custom properties
    """
    client = get_telemetry_client()
    if not client or not client.get('enabled'):
        logger.debug(f"Telemetry disabled, skipping event: {name}")
        return
    
    try:
        tracer = client['tracer']
        with tracer.start_as_current_span(name) as span:
            if properties:
                for key, value in properties.items():
                    span.set_attribute(key, str(value))
        
        logger.debug(f"Tracked event: {name} with {len(properties or {})} properties")
    except Exception as e:
        logger.error(f"Failed to track event {name}: {e}")


def track_metric(name: str, value: float, properties: Optional[Dict[str, str]] = None):
    """
    Track a custom metric in Application Insights.
    
    Args:
        name: Metric name (e.g., "PriceScout.Scrape.Duration")
        value: Metric value
        properties: Dictionary of custom dimensions
    """
    client = get_telemetry_client()
    if not client or not client.get('enabled'):
        logger.debug(f"Telemetry disabled, skipping metric: {name}")
        return
    
    try:
        # Note: OpenTelemetry metrics are different from AppInsights metrics
        # For production, you may want to use custom metrics via Azure Monitor API
        logger.debug(f"Tracked metric: {name} = {value}")
    except Exception as e:
        logger.error(f"Failed to track metric {name}: {e}")


# ============================================================================
# BUSINESS-SPECIFIC TELEMETRY FUNCTIONS
# ============================================================================

def track_scrape_started(theater_count: int, date_range: str, mode: str):
    """Track when a scrape operation starts."""
    track_event("PriceScout.Scrape.Started", {
        "TheaterCount": str(theater_count),
        "DateRange": date_range,
        "Mode": mode,
        "Timestamp": datetime.now(UTC).isoformat()
    })


def track_scrape_completed(
    theater_count: int,
    showing_count: int,
    price_count: int,
    duration_seconds: float,
    success: bool
):
    """
    Track scrape completion with performance metrics.
    
    Args:
        theater_count: Number of theaters scraped
        showing_count: Number of showtimes found
        price_count: Number of prices collected
        duration_seconds: Total scrape duration
        success: Whether scrape completed successfully
    """
    track_event("PriceScout.Scrape.Completed", {
        "TheaterCount": str(theater_count),
        "ShowingCount": str(showing_count),
        "PriceCount": str(price_count),
        "Success": str(success)
    })
    
    track_metric("PriceScout.Scrape.Duration", duration_seconds)
    track_metric("PriceScout.Scrape.ShowingsFound", float(showing_count))
    track_metric("PriceScout.Scrape.PricesCollected", float(price_count))
    
    if showing_count > 0 and duration_seconds > 0:
        showings_per_second = showing_count / duration_seconds
        track_metric("PriceScout.Scrape.ShowingsPerSecond", showings_per_second)


def track_price_change(
    theater_name: str,
    ticket_type: str,
    old_price: float,
    new_price: float,
    film_title: Optional[str] = None
):
    """
    Track when a price change is detected.
    
    Args:
        theater_name: Name of the theater
        ticket_type: Type of ticket (Adult, Child, Senior, etc.)
        old_price: Previous price
        new_price: Current price
        film_title: Optional film title
    """
    price_change = new_price - old_price
    percent_change = ((new_price - old_price) / old_price) * 100 if old_price > 0 else 0
    
    track_event("PriceScout.PriceChange.Detected", {
        "TheaterName": theater_name,
        "TicketType": ticket_type,
        "OldPrice": f"{old_price:.2f}",
        "NewPrice": f"{new_price:.2f}",
        "ChangeAmount": f"{price_change:.2f}",
        "PercentChange": f"{percent_change:.2f}",
        "FilmTitle": film_title or "N/A"
    })
    
    track_metric("PriceScout.Price.Change", price_change)
    track_metric("PriceScout.Price.PercentChange", percent_change)


def track_api_request(
    endpoint: str,
    method: str,
    status_code: int,
    duration_ms: float,
    user_id: Optional[str] = None
):
    """
    Track API request metrics.
    
    Args:
        endpoint: API endpoint path
        method: HTTP method
        status_code: Response status code
        duration_ms: Request duration in milliseconds
        user_id: Optional user identifier
    """
    track_event("PriceScout.API.Request", {
        "Endpoint": endpoint,
        "Method": method,
        "StatusCode": str(status_code),
        "UserId": user_id or "Anonymous"
    })
    
    track_metric("PriceScout.API.Duration", duration_ms)
    
    if status_code >= 500:
        track_event("PriceScout.API.ServerError", {
            "Endpoint": endpoint,
            "StatusCode": str(status_code)
        })


def track_report_generated(
    report_type: str,
    theater_count: int,
    date_range: str,
    generation_time_seconds: float
):
    """
    Track report generation.
    
    Args:
        report_type: Type of report (selection_analysis, daily_lineup, etc.)
        theater_count: Number of theaters included
        date_range: Date range covered
        generation_time_seconds: Time to generate report
    """
    track_event("PriceScout.Report.Generated", {
        "ReportType": report_type,
        "TheaterCount": str(theater_count),
        "DateRange": date_range
    })
    
    track_metric("PriceScout.Report.GenerationTime", generation_time_seconds)


def track_price_alert_triggered(
    theater_name: str,
    alert_type: str,
    threshold: float,
    actual_value: float
):
    """
    Track when a price alert is triggered.
    
    Args:
        theater_name: Theater where alert was triggered
        alert_type: Type of alert (price_increase, price_decrease, etc.)
        threshold: Alert threshold value
        actual_value: Actual value that triggered alert
    """
    track_event("PriceScout.Alert.Triggered", {
        "TheaterName": theater_name,
        "AlertType": alert_type,
        "Threshold": f"{threshold:.2f}",
        "ActualValue": f"{actual_value:.2f}"
    })
    
    variance = actual_value - threshold
    track_metric("PriceScout.Alert.Variance", variance)
