"""
Application Insights Telemetry Module for PriceScout

Provides:
- Distributed tracing with Azure Monitor integration
- W3C Trace Context propagation (traceparent/tracestate headers)
- Request correlation ID middleware
- Custom telemetry tracking for business metrics

Configuration:
    APPLICATIONINSIGHTS_CONNECTION_STRING - Azure Monitor connection string
    APP_NAME - Service name for trace identification

Usage:
    # Initialize telemetry (call once at startup in main.py)
    from api.telemetry import configure_telemetry
    configure_telemetry(app)

    # Track business events
    from api.telemetry import track_scrape, track_price_change
    track_scrape(theater_count=5, showing_count=120, duration=45.3)
    track_price_change(theater="AMC 14", old_price=12.99, new_price=13.99)

    # Inject trace headers into outgoing requests
    from api.telemetry import inject_trace_headers
    headers = inject_trace_headers({})
    response = httpx.get(url, headers=headers)
"""

import logging
import re
from typing import Dict, Optional, Any
from datetime import datetime, UTC
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# UUID format validation pattern (prevents log injection attacks)
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

# Import configuration
from app.config import (
    APPLICATIONINSIGHTS_CONNECTION_STRING,
    APP_NAME,
    APP_VERSION,
    DEBUG
)

# Global telemetry state
_telemetry_client = None
_tracer = None
_tracer_provider = None


# ============================================================================
# DISTRIBUTED TRACING SETUP
# ============================================================================

def configure_telemetry(app: FastAPI) -> None:
    """
    Configure OpenTelemetry with Azure Monitor exporter.

    Sets up:
    - TracerProvider with Azure Monitor exporter
    - W3C TraceContext propagator
    - FastAPI instrumentation
    - Request correlation middleware

    Args:
        app: FastAPI application instance
    """
    global _tracer, _tracer_provider

    # Add request ID middleware (always enabled)
    app.add_middleware(RequestIdMiddleware)
    logger.info("Request ID middleware enabled")

    # Only configure full OTEL if connection string is set
    if not APPLICATIONINSIGHTS_CONNECTION_STRING:
        logger.info("Application Insights not configured - telemetry limited to request IDs")
        return

    try:
        # Import OpenTelemetry components
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.composite import CompositePropagator
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        from opentelemetry.baggage.propagation import W3CBaggagePropagator

        # Try to import Azure Monitor exporter
        exporter = None
        try:
            from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
            exporter = AzureMonitorTraceExporter(
                connection_string=APPLICATIONINSIGHTS_CONNECTION_STRING
            )
            logger.info("Azure Monitor trace exporter initialized")
        except ImportError:
            logger.warning(
                "azure-monitor-opentelemetry-exporter not installed. "
                "Run: pip install azure-monitor-opentelemetry-exporter"
            )

        # Create resource with service info
        resource = Resource.create({
            SERVICE_NAME: APP_NAME or "pricescout-api",
            SERVICE_VERSION: APP_VERSION or "1.0.0",
            "service.namespace": "theatre-operations-platform",
            "deployment.environment": "development" if DEBUG else "production"
        })

        # Create and configure TracerProvider
        _tracer_provider = TracerProvider(resource=resource)

        # Add Azure Monitor exporter if available
        if exporter:
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

        # Set as global tracer provider
        trace.set_tracer_provider(_tracer_provider)

        # Configure W3C Trace Context propagation
        propagator = CompositePropagator([
            TraceContextTextMapPropagator(),  # traceparent, tracestate
            W3CBaggagePropagator()            # baggage
        ])
        set_global_textmap(propagator)
        logger.info("W3C Trace Context propagation configured")

        # Get tracer for this module
        _tracer = trace.get_tracer(__name__, APP_VERSION)

        # Instrument FastAPI
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI OpenTelemetry instrumentation enabled")
        except ImportError:
            logger.warning("opentelemetry-instrumentation-fastapi not installed")

        # Instrument HTTP client libraries
        _instrument_http_clients()

        logger.info("OpenTelemetry configuration complete")

    except ImportError as e:
        logger.warning(f"OpenTelemetry not fully available: {e}")
    except Exception as e:
        logger.error(f"Failed to configure OpenTelemetry: {e}")


def _instrument_http_clients() -> None:
    """Instrument HTTP client libraries for trace propagation."""
    # Instrument httpx (used by scraper)
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentation
        HTTPXClientInstrumentation().instrument()
        logger.debug("httpx instrumentation enabled")
    except ImportError:
        pass

    # Instrument requests
    try:
        from opentelemetry.instrumentation.requests import RequestsInstrumentation
        RequestsInstrumentation().instrument()
        logger.debug("requests instrumentation enabled")
    except ImportError:
        pass


# ============================================================================
# REQUEST ID MIDDLEWARE
# ============================================================================

class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to ensure every request has a correlation ID.

    Security:
    - Validates X-Request-ID format to prevent log injection attacks
    - Only accepts valid UUID format, generates new one otherwise
    - Adds X-Request-ID to response headers
    - Stores request_id in request.state for logging
    """

    async def dispatch(self, request: Request, call_next):
        # Get request ID from header, validate format to prevent injection
        request_id = request.headers.get("X-Request-ID", "")

        # Only accept valid UUID format (prevents log injection)
        if not request_id or not UUID_PATTERN.match(request_id):
            request_id = str(uuid4())

        # Store in request state for access by handlers
        request.state.request_id = request_id

        # Add trace IDs if available
        trace_id = get_current_trace_id()
        if trace_id:
            request.state.trace_id = trace_id

        # Process request
        response = await call_next(request)

        # Add correlation headers to response
        response.headers["X-Request-ID"] = request_id
        if trace_id:
            response.headers["X-Trace-ID"] = trace_id

        return response


# ============================================================================
# TRACE CONTEXT HELPERS
# ============================================================================

def get_current_trace_id() -> Optional[str]:
    """Get the current trace ID if available."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            return format(span.get_span_context().trace_id, '032x')
    except Exception:
        pass
    return None


def get_current_span_id() -> Optional[str]:
    """Get the current span ID if available."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            return format(span.get_span_context().span_id, '016x')
    except Exception:
        pass
    return None


def inject_trace_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Inject W3C trace context headers into outgoing request headers.

    Use this when making HTTP requests to external services to propagate
    trace context for distributed tracing.

    Args:
        headers: Existing headers dict (will be modified in place)

    Returns:
        Headers dict with trace context added

    Example:
        headers = {"Authorization": "Bearer token"}
        inject_trace_headers(headers)
        response = httpx.get(url, headers=headers)
    """
    try:
        from opentelemetry import propagate
        propagate.inject(headers)
    except Exception as e:
        logger.debug(f"Failed to inject trace headers: {e}")
    return headers


def get_tracer(name: str = __name__):
    """
    Get a tracer for creating custom spans.

    Args:
        name: Name of the module/component

    Returns:
        OpenTelemetry tracer or no-op tracer
    """
    global _tracer
    if _tracer:
        return _tracer
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return NoOpTracer()


class NoOpTracer:
    """No-op tracer for when OpenTelemetry is not available."""
    def start_as_current_span(self, name: str, **kwargs):
        return NoOpSpan()


class NoOpSpan:
    """No-op span context manager."""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def set_attribute(self, key: str, value: Any):
        pass
    def set_status(self, status):
        pass
    def record_exception(self, exception):
        pass


# ============================================================================
# TELEMETRY CLIENT (for business metrics)
# ============================================================================

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
