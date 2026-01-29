"""
PriceScout API - FastAPI Application

Main entry point for the PriceScout REST API.
Provides endpoints for pricing data, reports, authentication, and management.

Run with:
    uvicorn api.main:app --reload --port 8000

API Documentation:
    - Swagger UI: http://localhost:8000/api/v1/docs
    - ReDoc: http://localhost:8000/api/v1/redoc
    - OpenAPI JSON: http://localhost:8000/api/v1/openapi.json
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
import os

# Add repo root to path so `app` package is importable when running `uvicorn api.main:app`
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import routers
from api.routers import reports, resources, auth, markets, tasks, scrapes, users
from api.routers import scrape_sources, price_checks, price_alerts, price_tiers
from api.routers import circuit_benchmarks, presales, analytics
from api.routers import admin, cache, enttelligence, schedule_monitor, system, market_context, films
from api.routers import theater_amenities, company_profiles, theater_onboarding, alternative_content
from api import metrics
from app.rate_limit import RateLimitMiddleware

# Import error handlers
from api.errors import (
    problem_response,
    ProblemType,
    validation_error,
    internal_error,
    not_found_error
)

# Import configuration
from app.config import (
    APPLICATIONINSIGHTS_CONNECTION_STRING,
    APP_NAME,
    APP_VERSION,
    DEBUG,
    is_production
)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# APPLICATION SETUP
# ============================================================================

app = FastAPI(
    title="PriceScout - Competitive Pricing Intelligence API",
    version="2.0.0",
    description="""
## PriceScout API - Theatre Operations Platform

RESTful API for competitive pricing intelligence and market analysis for theatre operations.

**Part of TheatreOps Platform** - API-First Architecture with shared database pattern.

### Key Features

- **Competitive Intelligence**: Track competitor pricing, showtimes, and market trends
- **Web Scraping**: Automated data collection from theatre websites (Fandango, etc.)
- **Price Analytics**: Historical price tracking, change detection, and trend analysis
- **Report Generation**: PDF and Excel exports for market analysis
- **Real-time Alerts**: Price change notifications and threshold monitoring
- **Multi-format Support**: Track IMAX, Dolby, PLF formats and premium pricing

### Architecture

- **Framework**: FastAPI with async/await support
- **Database**: SQLAlchemy ORM with Azure SQL / MSSQL (pricescout schema)
- **Authentication**: JWT tokens, API keys, and Microsoft Entra ID
- **Telemetry**: Application Insights with custom business metrics
- **Deployment**: Azure App Service with CI/CD pipeline

### Authentication

Most endpoints require authentication. Choose one method:

**Option 1: API Key** (Recommended for integrations)
```bash
curl -H "X-API-Key: your_api_key" https://api.pricescout.io/api/v1/price-checks
```

**Option 2: JWT Token** (For user sessions)
```bash
# Login to get token
curl -X POST https://api.pricescout.io/api/v1/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"username": "user", "password": "pass"}'

# Use token in requests
curl -H "Authorization: Bearer <token>" https://api.pricescout.io/api/v1/reports
```

**Option 3: Entra ID** (SSO for internal users)
```bash
# Obtain token from Entra ID
curl -H "Authorization: Bearer <entra_token>" https://api.pricescout.io/api/v1/resources
```

### Rate Limiting

API key tiers have different rate limits:
- **Free Tier**: 100 requests/hour
- **Premium Tier**: 1,000 requests/hour  
- **Enterprise Tier**: Unlimited (dedicated infrastructure)

Rate limit headers included in all responses:
- `X-RateLimit-Limit`: Total requests allowed per window
- `X-RateLimit-Remaining`: Requests remaining in current window
- `X-RateLimit-Reset`: Unix timestamp when limit resets

### Error Responses

All errors follow **RFC 7807 Problem Details** standard:

```json
{
  "type": "https://api.pricescout.io/problems/validation-error",
  "title": "Validation Error",
  "status": 400,
  "detail": "Invalid date format: expected YYYY-MM-DD",
  "instance": "/api/v1/reports/daily-lineup",
  "timestamp": "2025-12-04T23:30:00Z",
  "trace_id": "abc123"
}
```

### Data Models

Key business entities:
- **Showings**: Movie showtimes with pricing and format information
- **Theaters**: Competitor theatre locations and configurations
- **Price Checks**: Historical price snapshots for trend analysis
- **Scrape Runs**: Data collection job metadata and results

### Performance

- **Average Response Time**: <200ms for queries, <2s for reports
- **Uptime SLA**: 99.9% availability
- **Cache Strategy**: Redis for frequently accessed data
- **Database**: Connection pooling with automatic failover

### Support

- **Documentation**: https://docs.pricescout.io
- **Status Page**: https://status.pricescout.io  
- **Email**: support@pricescout.io
- **Internal Slack**: #pricescout-support
    """,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    contact={
        "name": "Theatre Operations Platform Team",
        "email": "platform@theatreops.com",
        "url": "https://internal.theatreops.com"
    },
    license_info={
        "name": "Internal Use Only",
        "url": "https://internal.theatreops.com/license"
    },
    servers=[
        {
            "url": "https://pricescout-api-prod.azurewebsites.net",
            "description": "Production"
        },
        {
            "url": "https://pricescout-api-dev.azurewebsites.net",
            "description": "Development"
        },
        {
            "url": "http://localhost:8000",
            "description": "Local Development"
        }
    ],
    openapi_tags=[
        {
            "name": "reports",
            "description": "Generate PDF and Excel reports for market analysis"
        },
        {
            "name": "resources",
            "description": "Access theaters, films, showtimes, and pricing data"
        },
        {
            "name": "Price Data",
            "description": "Query pricing history and trends"
        },
        {
            "name": "Scrapes",
            "description": "Manage web scraping operations"
        },
        {
            "name": "Auth",
            "description": "Authentication and token management"
        },
        {
            "name": "Users",
            "description": "User management and profile operations"
        }
    ]
)


# ============================================================================
# OPENTELEMETRY / APPLICATION INSIGHTS
# ============================================================================

if APPLICATIONINSIGHTS_CONNECTION_STRING:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("Application Insights instrumentation enabled")
    except ImportError:
        logger.warning("OpenTelemetry not available - instrumentation disabled")
    except Exception as e:
        logger.warning(f"Failed to initialize Application Insights: {e}")


# ============================================================================
# SECURITY MIDDLEWARE
# ============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    Compliant with OWASP security best practices.
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # HSTS - only in production over HTTPS
        if is_production():
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # Content Security Policy - adjust as needed for your frontend
        if is_production():
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # Needed for Swagger UI
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self' https://*.applicationinsights.azure.com https://*.monitor.azure.com; "
                "frame-ancestors 'none'"
            )

        return response

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add global rate limiting middleware
app.add_middleware(RateLimitMiddleware)


# ============================================================================
# CORS MIDDLEWARE
# ============================================================================

# Check if we're running in a test environment
# Multiple ways to detect: pytest markers, sys.argv check, or explicit env var
def _detect_testing() -> bool:
    """Detect if we're running in a test environment."""
    import sys
    # Check for pytest in sys.modules (loaded during test collection)
    if "pytest" in sys.modules:
        return True
    # Check for explicit test env var
    if os.getenv("TESTING", "").lower() in ("1", "true", "yes"):
        return True
    # Check for pytest in command line
    if any("pytest" in arg for arg in sys.argv):
        return True
    return False

_is_testing = _detect_testing()

# Get allowed origins from environment or use defaults
# In production, this should be set explicitly via ALLOWED_ORIGINS env var
ALLOWED_ORIGINS_ENV = os.getenv("ALLOWED_ORIGINS", "")

if _is_testing:
    # Testing: allow all origins for test client
    origins = ["*"]
elif ALLOWED_ORIGINS_ENV:
    # Production: use explicit list from environment
    origins = [origin.strip() for origin in ALLOWED_ORIGINS_ENV.split(",")]
elif is_production():
    # Production fallback: Azure App Service URLs only
    azure_site_name = os.getenv("WEBSITE_SITE_NAME", "pricescout")
    origins = [
        f"https://{azure_site_name}.azurewebsites.net",
        f"https://{azure_site_name}-staging.azurewebsites.net",
    ]
else:
    # Development: allow local development servers
    origins = [
        "http://localhost:8501",      # Streamlit local
        "http://localhost:3000",      # React dev
        "http://localhost:3001",      # React dev (alternate port)
        "http://localhost:8000",      # FastAPI local
        "http://127.0.0.1:8501",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:8000",
    ]

logger.info(f"CORS allowed origins: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "X-Request-ID",
        "Accept",
        "Origin",
    ],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    max_age=600,  # Cache preflight requests for 10 minutes
)


# ============================================================================
# TRUSTED HOST MIDDLEWARE (Production only)
# ============================================================================

if is_production() and not _is_testing:
    # Get allowed hosts from environment or derive from Azure
    ALLOWED_HOSTS_ENV = os.getenv("ALLOWED_HOSTS", "")

    if ALLOWED_HOSTS_ENV:
        allowed_hosts = [host.strip() for host in ALLOWED_HOSTS_ENV.split(",")]
    else:
        azure_site_name = os.getenv("WEBSITE_SITE_NAME", "pricescout")
        allowed_hosts = [
            f"{azure_site_name}.azurewebsites.net",
            f"{azure_site_name}-staging.azurewebsites.net",
            "localhost",  # For health checks from Azure
            "127.0.0.1",  # For local health checks
        ]

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts
    )
    logger.info(f"Trusted hosts: {allowed_hosts}")


# ============================================================================
# GLOBAL EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle Pydantic validation errors with RFC 7807 format.
    """
    errors = {}
    for error in exc.errors():
        loc = ".".join(str(l) for l in error["loc"])
        if loc not in errors:
            errors[loc] = []
        errors[loc].append(error["msg"])

    return validation_error(
        detail="Request validation failed",
        errors=errors,
        instance=str(request.url.path)
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Convert HTTPException to RFC 7807 format.
    """
    # Map status codes to problem types
    problem_type_map = {
        400: ProblemType.BAD_REQUEST,
        401: ProblemType.UNAUTHORIZED,
        403: ProblemType.FORBIDDEN,
        404: ProblemType.NOT_FOUND,
        409: ProblemType.CONFLICT,
        429: ProblemType.RATE_LIMITED,
        500: ProblemType.INTERNAL_ERROR,
        503: ProblemType.SERVICE_UNAVAILABLE,
    }

    problem_type = problem_type_map.get(exc.status_code, ProblemType.INTERNAL_ERROR)

    return problem_response(
        type_=problem_type,
        title=exc.detail if isinstance(exc.detail, str) else "Error",
        status=exc.status_code,
        detail=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        instance=str(request.url.path)
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch-all handler for unhandled exceptions.
    Logs the error and returns a safe RFC 7807 response.
    """
    logger.exception(f"Unhandled exception on {request.url.path}: {exc}")

    # Don't expose internal details in production
    detail = str(exc) if DEBUG else "An unexpected error occurred. Please try again."

    return internal_error(
        detail=detail,
        instance=str(request.url.path)
    )


# ============================================================================
# ROUTERS
# ============================================================================

# Authentication (must be first for token endpoint)
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])

# Reports - selection analysis, showtime views, daily lineup
app.include_router(reports.router, tags=["Reports"])

# Resources - theaters, films, showtimes, pricing
app.include_router(resources.router, tags=["Resources"])

# Markets - market data and configuration
app.include_router(markets.router, prefix="/api/v1", tags=["Markets"])

# Tasks - scheduled task management
app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks"])

# Scrapes - scrape run management
app.include_router(scrapes.router, prefix="/api/v1", tags=["Scrapes"])

# Users - user management (password changes, etc.)
app.include_router(users.router, prefix="/api/v1", tags=["Users"])

# Scrape Sources - configurable scrape source management (claude.md standard)
app.include_router(scrape_sources.router, prefix="/api/v1", tags=["Scrape Sources"])

# Price Checks - price data queries (claude.md standard)
app.include_router(price_checks.router, prefix="/api/v1", tags=["Price Data"])

# Price Alerts - price change alerts (claude.md standard)
app.include_router(price_alerts.router, prefix="/api/v1", tags=["Price Alerts"])

# Price Tiers - price tier discovery and discount day detection
app.include_router(price_tiers.router, prefix="/api/v1", tags=["Price Tiers"])

# Company Profiles - circuit pricing profile discovery
app.include_router(company_profiles.router, prefix="/api/v1", tags=["Company Profiles"])

# Theater Onboarding - baseline system onboarding workflow
app.include_router(theater_onboarding.router, prefix="/api/v1", tags=["Theater Onboarding"])

# Alternative Content - special events, Fathom, opera, etc.
app.include_router(alternative_content.router, prefix="/api/v1", tags=["Alternative Content"])

# Theater Amenities - competitor theater features
app.include_router(theater_amenities.router, prefix="/api/v1", tags=["Theater Amenities"])

# EntTelligence Integration (Circuit Benchmarks & Presales)
app.include_router(circuit_benchmarks.router, tags=["Circuit Benchmarks"])
app.include_router(presales.router, tags=["Presales"])

# Admin endpoints (user management, audit logs)
app.include_router(admin.router, prefix="/api/v1", tags=["Admin"])

# Cache management endpoints
app.include_router(cache.router, prefix="/api/v1", tags=["Cache"])

# EntTelligence cache and sync endpoints
app.include_router(enttelligence.router, prefix="/api/v1", tags=["EntTelligence"])

# Schedule monitor endpoints
app.include_router(schedule_monitor.router, prefix="/api/v1", tags=["Schedule Monitor"])

# Market Context endpoints (Heatmap & Events)
app.include_router(market_context.router, prefix="/api/v1", tags=["Market Context"])

# System administration endpoints
app.include_router(system.router, prefix="/api/v1", tags=["System"])

# Analytics - specialized analysis and charting
app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics"])

# Films - film metadata and posters
app.include_router(films.router, prefix="/api/v1", tags=["Films"])

# Prometheus metrics endpoint
app.include_router(metrics.router, tags=["Metrics"])


# ============================================================================
# ROOT ENDPOINTS
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """
    API root - returns basic information and links.
    """
    return {
        "name": "PriceScout API",
        "version": "2.0.0",
        "status": "operational",
        "docs": "/api/v1/docs",
        "openapi": "/api/v1/openapi.json",
        "health": "/api/v1/health"
    }


@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint for load balancers and monitoring.

    Returns:
        - status: 'healthy' or 'degraded'
        - timestamp: Current UTC time
        - version: API version
        - database: Database connection status
        - services: Status of dependent services
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "environment": "production" if is_production() else "development",
    }

    # Check database connection
    try:
        from app.db_session import get_session
        from sqlalchemy import text
        with get_session() as session:
            session.execute(text("SELECT 1"))
        health_status["database"] = "connected"
    except Exception as e:
        health_status["database"] = "disconnected"
        health_status["status"] = "degraded"
        logger.warning(f"Health check: database connection failed: {e}")

    # Check Entra ID status
    try:
        from api.entra_auth import is_entra_enabled
        health_status["entra_id"] = "enabled" if is_entra_enabled() else "disabled"
    except ImportError:
        health_status["entra_id"] = "not_configured"

    # Check Application Insights
    health_status["telemetry"] = "enabled" if APPLICATIONINSIGHTS_CONNECTION_STRING else "disabled"

    return health_status


@app.get("/api/v1/health/full", tags=["Health"])
async def full_health_check():
    """
    Comprehensive system health check with component-level details.

    Returns detailed status of all system components including:
    - Database connectivity
    - Fandango scraper health (from cache maintenance)
    - EntTelligence sync status
    - Pending alerts counts
    - Circuit breaker states (when implemented)

    Use this endpoint for ops dashboards and detailed monitoring.
    The basic /health endpoint is preferred for load balancer checks.
    """
    import sqlite3
    import os
    from app import config

    health = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "environment": "production" if is_production() else "development",
        "components": {}
    }

    # -------------------------------------------------------------------------
    # Database Check
    # -------------------------------------------------------------------------
    try:
        from app.db_session import get_session
        from sqlalchemy import text
        with get_session() as session:
            session.execute(text("SELECT 1"))
        health["components"]["database"] = {"status": "ok"}
    except Exception as e:
        health["components"]["database"] = {"status": "error", "message": str(e)}
        health["status"] = "degraded"

    # -------------------------------------------------------------------------
    # Fandango Scraper Health (from cache maintenance history)
    # -------------------------------------------------------------------------
    try:
        from app.cache_maintenance_service import CacheMaintenanceService
        service = CacheMaintenanceService()
        history = service.get_maintenance_history(limit=1)

        if history:
            last_run = history[0]
            health_check_result = last_run.get('health_check', {})
            failure_rate = health_check_result.get('failure_rate_percent', 0)

            status = "ok"
            if failure_rate >= 30:
                status = "degraded"
                health["status"] = "degraded"
            elif failure_rate >= 50:
                status = "critical"
                health["status"] = "unhealthy"

            health["components"]["fandango_scraper"] = {
                "status": status,
                "last_check": last_run.get('timestamp'),
                "failure_rate_percent": failure_rate,
                "theaters_checked": health_check_result.get('checked', 0),
                "theaters_failed": health_check_result.get('failed', 0)
            }
        else:
            health["components"]["fandango_scraper"] = {
                "status": "unknown",
                "message": "No maintenance history found"
            }
    except Exception as e:
        health["components"]["fandango_scraper"] = {
            "status": "unknown",
            "message": str(e)
        }

    # -------------------------------------------------------------------------
    # EntTelligence Sync Status
    # -------------------------------------------------------------------------
    try:
        db_path = getattr(config, 'DB_FILE', None) or os.path.join(config.PROJECT_DIR, 'pricescout.db')
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check last sync
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='enttelligence_sync_runs'
            """)
            if cursor.fetchone():
                cursor.execute("""
                    SELECT started_at, status, theaters_synced
                    FROM enttelligence_sync_runs
                    ORDER BY started_at DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    health["components"]["enttelligence"] = {
                        "status": "ok" if row[1] == 'success' else "degraded",
                        "last_sync": row[0],
                        "last_status": row[1],
                        "records_synced": row[2]
                    }
                else:
                    health["components"]["enttelligence"] = {
                        "status": "unknown",
                        "message": "No sync runs found"
                    }
            else:
                health["components"]["enttelligence"] = {
                    "status": "not_configured",
                    "message": "Sync table not created"
                }
            conn.close()
    except Exception as e:
        health["components"]["enttelligence"] = {
            "status": "unknown",
            "message": str(e)
        }

    # -------------------------------------------------------------------------
    # Pending Alerts
    # -------------------------------------------------------------------------
    try:
        db_path = getattr(config, 'DB_FILE', None) or os.path.join(config.PROJECT_DIR, 'pricescout.db')
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            price_pending = 0
            schedule_pending = 0

            # Price alerts
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='price_alerts'
            """)
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM price_alerts WHERE is_acknowledged = 0")
                price_pending = cursor.fetchone()[0] or 0

            # Schedule alerts
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='schedule_alerts'
            """)
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM schedule_alerts WHERE is_acknowledged = 0")
                schedule_pending = cursor.fetchone()[0] or 0

            conn.close()

            health["components"]["alerts"] = {
                "status": "ok",
                "price_pending": price_pending,
                "schedule_pending": schedule_pending,
                "total_pending": price_pending + schedule_pending
            }
    except Exception as e:
        health["components"]["alerts"] = {
            "status": "unknown",
            "message": str(e)
        }

    # -------------------------------------------------------------------------
    # Scheduler Status (check if scheduler log is recent)
    # -------------------------------------------------------------------------
    try:
        scheduler_log = os.path.join(config.PROJECT_DIR, 'scheduler.log')
        if os.path.exists(scheduler_log):
            mtime = os.path.getmtime(scheduler_log)
            last_activity = datetime.fromtimestamp(mtime, tz=timezone.utc)
            age_minutes = (datetime.now(timezone.utc) - last_activity).total_seconds() / 60

            status = "ok" if age_minutes < 5 else "degraded" if age_minutes < 30 else "stale"
            health["components"]["scheduler"] = {
                "status": status,
                "last_activity": last_activity.isoformat(),
                "age_minutes": round(age_minutes, 1)
            }
        else:
            health["components"]["scheduler"] = {
                "status": "unknown",
                "message": "Scheduler log not found"
            }
    except Exception as e:
        health["components"]["scheduler"] = {
            "status": "unknown",
            "message": str(e)
        }

    # -------------------------------------------------------------------------
    # Circuit Breakers (placeholder for Feature 5)
    # -------------------------------------------------------------------------
    try:
        from app.circuit_breaker import fandango_breaker
        health["components"]["circuit_breakers"] = {
            "fandango": fandango_breaker.get_status()
        }
    except ImportError:
        # Circuit breaker not implemented yet
        health["components"]["circuit_breakers"] = {
            "status": "not_implemented"
        }
    except Exception as e:
        health["components"]["circuit_breakers"] = {
            "status": "error",
            "message": str(e)
        }

    # Set overall status based on component statuses
    component_statuses = [
        c.get("status", "unknown")
        for c in health["components"].values()
        if isinstance(c, dict)
    ]

    if "critical" in component_statuses or "error" in component_statuses:
        health["status"] = "unhealthy"
    elif "degraded" in component_statuses:
        health["status"] = "degraded"

    return health


@app.get("/api/v1/info", tags=["Root"])
async def api_info():
    """
    Get detailed API information including available endpoints.
    """
    return {
        "name": "PriceScout API",
        "version": "2.0.0",
        "description": "Competitive pricing intelligence API",
        "authentication": {
            "methods": ["api_key", "jwt", "entra_id"],
            "api_key_header": "X-API-Key",
            "jwt_header": "Authorization: Bearer <token>",
            "token_endpoint": "/api/v1/auth/token",
            "entra_login": "/api/v1/auth/entra/login"
        },
        "rate_limits": {
            "free": {"requests_per_hour": 100, "requests_per_day": 1000},
            "premium": {"requests_per_hour": 1000, "requests_per_day": 50000},
            "enterprise": {"requests_per_hour": "unlimited", "requests_per_day": "unlimited"}
        },
        "endpoints": {
            "authentication": "/api/v1/auth/*",
            "reports": "/api/v1/reports/*",
            "theaters": "/api/v1/theaters",
            "films": "/api/v1/films",
            "showtimes": "/api/v1/showtimes/*",
            "pricing": "/api/v1/pricing",
            "markets": "/api/v1/markets",
            "tasks": "/api/v1/tasks",
            "scrapes": "/api/v1/scrapes/*"
        },
        "documentation": {
            "swagger": "/api/v1/docs",
            "redoc": "/api/v1/redoc",
            "openapi": "/api/v1/openapi.json"
        }
    }


# ============================================================================
# STARTUP / SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """
    Initialize resources on application startup.
    """
    logger.info(f"Starting PriceScout API v2.0.0")
    logger.info(f"Environment: {'production' if is_production() else 'development'}")
    logger.info(f"Debug mode: {DEBUG}")

    # Initialize database connection pool
    try:
        from app.db_session import get_engine
        engine = get_engine()
        logger.info(f"Database connection initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    # Auto-sync logic (Simulating deployment background work)
    from app import config
    if config.AUTO_SYNC_ON_STARTUP and not _is_testing:
        try:
            from api.services.enttelligence_cache_service import get_cache_service
            from datetime import date
            
            cache_service = get_cache_service()
            today = date.today().isoformat()
            
            logger.info(f"PriceScout: Triggering automatic EntTelligence sync for {today}")
            
            # Note: In production this would be a Celery task or Azure Function.
            # Here we run it during startup to ensure fresh data for the dev session.
            # We use a simple background check to avoid blocking the API server if it's already fresh.
            stats = cache_service.get_cache_stats(company_id=1)
            
            if stats["fresh_entries"] < 100 or not stats["last_fetch"]:
                logger.info("Cache appears empty or stale. Synchronizing now...")
                # We do this synchronously or in a separate thread. 
                # For dev, we'll just call it since the first request will hit it anyway.
                cache_service.sync_prices_for_dates(
                    company_id=1,
                    start_date=today
                )
                logger.info("Automatic sync completed.")
            else:
                logger.info(f"Cache is already fresh ({stats['fresh_entries']} entries). Skipping auto-sync.")
                
        except Exception as e:
            logger.warning(f"PriceScout: Automatic startup sync failed: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup resources on application shutdown.
    """
    logger.info("Shutting down PriceScout API")

    # Close database connections
    try:
        from app.db_session import close_engine
        close_engine()
        logger.info("Database connections closed")
    except Exception as e:
        logger.warning(f"Error closing database: {e}")
# force reload
# force reload
