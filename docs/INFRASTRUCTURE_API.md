# PriceScout Infrastructure API Reference

Backend infrastructure endpoints for the React/FastAPI version of PriceScout.

**Base URL:** `http://localhost:8000/api/v1`
**Authentication:** Bearer token (JWT) required unless noted
**Version:** 1.0.0

---

## Table of Contents

1. [Health and Monitoring](#health-and-monitoring)
2. [Circuit Breaker Management](#circuit-breaker-management)
3. [Schedule Alerts](#schedule-alerts)
4. [Schedule Monitor](#schedule-monitor)
5. [Repair Queue](#repair-queue)
6. [Cache Maintenance](#cache-maintenance)
7. [Prometheus Metrics](#prometheus-metrics)
8. [Role Permissions](#role-permissions)
9. [Error Handling](#error-handling)

---

## Health and Monitoring

### GET /health

Basic health check. **No authentication required.**

```json
{
  "status": "ok",
  "timestamp": "2025-01-15T10:30:00Z",
  "version": "1.0.0",
  "environment": "production",
  "database_connected": true,
  "entra_id": "configured",
  "telemetry": "enabled"
}
```

### GET /health/full

Comprehensive system health with all components.

```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:30:00Z",
  "version": "1.0.0",
  "components": {
    "database": {
      "status": "ok"
    },
    "fandango_scraper": {
      "status": "ok",
      "failure_rate_percent": 2.5,
      "theaters_checked": 100,
      "theaters_failed": 2
    },
    "enttelligence": {
      "status": "ok",
      "last_sync": "2025-01-15T10:00:00Z",
      "records_synced": 1500
    },
    "alerts": {
      "price_pending": 5,
      "schedule_pending": 12
    },
    "scheduler": {
      "status": "ok",
      "last_activity": "2025-01-15T10:28:00Z",
      "age_minutes": 2
    },
    "circuit_breakers": {
      "fandango": {
        "state": "closed",
        "failures": 0,
        "failure_threshold": 5
      },
      "enttelligence": {
        "state": "closed",
        "failures": 0,
        "failure_threshold": 3
      }
    }
  }
}
```

**Status Values:**
- `healthy` - All systems operational
- `degraded` - Some issues but functional
- `unhealthy` - Critical failures

### GET /auth/health

Authentication service status.

```json
{
  "status": "ok",
  "enabled_methods": {
    "database_auth": true,
    "api_key": true,
    "entra_id": true
  },
  "jwt_configured": true,
  "token_expiry_minutes": 60
}
```

### GET /api/v1/system/health

Detailed system health with circuit breaker management.

**Required Role:** admin, auditor, operator, manager

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "circuits": {
    "fandango": {
      "name": "fandango",
      "state": "closed",
      "failures": 0,
      "failure_threshold": 5,
      "reset_timeout": 3600,
      "last_state_change": 1705312200,
      "is_open": false
    },
    "enttelligence": {
      "name": "enttelligence",
      "state": "closed",
      "failures": 1,
      "failure_threshold": 3,
      "reset_timeout": 1800,
      "is_open": false
    }
  },
  "features": {
    "celery": true,
    "redis": true,
    "entra_id": true,
    "enttelligence": true
  }
}
```

---

## Circuit Breaker Management

Circuit breakers prevent cascading failures by stopping requests to failing services.

### Circuit Breaker States

| State | Description |
|-------|-------------|
| `closed` | Normal operation, requests pass through |
| `open` | Blocked, requests fail immediately |
| `half_open` | Testing, allows one request to check recovery |

### Circuit Configuration

| Circuit | Failure Threshold | Reset Timeout |
|---------|-------------------|---------------|
| `fandango` | 5 failures | 1 hour |
| `enttelligence` | 3 failures | 30 minutes |

### POST /api/v1/system/circuits/reset

Reset all circuit breakers to closed state.

**Required Role:** operator, manager, admin

```json
{
  "success": true,
  "message": "All circuit breakers reset",
  "circuits_reset": ["fandango", "enttelligence"]
}
```

### POST /api/v1/system/circuits/{name}/reset

Reset a specific circuit breaker.

**Required Role:** operator, manager, admin

**Path:** `name` = `fandango` or `enttelligence`

```json
{
  "success": true,
  "circuit": "fandango",
  "new_state": "closed"
}
```

### POST /api/v1/system/circuits/{name}/open

Force a circuit breaker open (emergency stop).

**Required Role:** admin only

```json
{
  "success": true,
  "circuit": "fandango",
  "new_state": "open"
}
```

---

## Schedule Alerts

Alerts for schedule changes detected by the schedule monitor.

### Alert Types

| Type | Description |
|------|-------------|
| `new_film` | New film added to schedule |
| `removed_film` | Film removed from schedule |
| `new_showtime` | New showtime added |
| `removed_showtime` | Showtime removed |
| `format_change` | Format changed (IMAX, 3D, etc.) |

### GET /schedule-alerts

List alerts with pagination and filtering.

**Query Parameters:**
- `page` (int, default: 1)
- `per_page` (int, default: 20)
- `status` (string): `pending`, `acknowledged`, `all`
- `type` (string): Filter by alert type

```json
{
  "items": [
    {
      "id": 123,
      "type": "new_film",
      "theater_name": "AMC Madison 6",
      "film_title": "New Movie",
      "details": "Added for 2025-01-20",
      "status": "pending",
      "created_at": "2025-01-15T10:00:00Z"
    }
  ],
  "total": 45,
  "page": 1,
  "pages": 3
}
```

### GET /schedule-alerts/pending

Get only unacknowledged alerts.

### GET /schedule-alerts/summary

Get counts by alert type.

```json
{
  "total_pending": 17,
  "by_type": {
    "new_film": 5,
    "removed_film": 2,
    "new_showtime": 8,
    "removed_showtime": 1,
    "format_change": 1
  }
}
```

### POST /schedule-alerts/{id}/acknowledge

Acknowledge a single alert.

**Request:**
```json
{
  "notes": "Reviewed and confirmed"
}
```

**Response:**
```json
{
  "success": true,
  "alert_id": 123,
  "status": "acknowledged"
}
```

### POST /schedule-alerts/bulk-acknowledge

Acknowledge multiple alerts.

**Request:**
```json
{
  "alert_ids": [123, 124, 125],
  "notes": "Batch review"
}
```

---

## Schedule Monitor

Configuration and control for the schedule change detection system.

### GET /schedule-monitor/config

Get current configuration.

```json
{
  "enabled": true,
  "check_interval_minutes": 60,
  "theaters_per_check": 50,
  "alert_on_new_film": true,
  "alert_on_removed_film": true,
  "alert_on_showtime_changes": true,
  "alert_on_format_changes": true
}
```

### PUT /schedule-monitor/config

Update configuration.

**Required Role:** admin

### GET /schedule-monitor/status

Get current monitor status.

```json
{
  "running": true,
  "last_check": "2025-01-15T10:00:00Z",
  "next_check": "2025-01-15T11:00:00Z",
  "theaters_checked": 150,
  "alerts_generated": 3
}
```

### POST /schedule-monitor/trigger

Manually trigger a schedule check.

**Required Role:** operator, admin

---

## Repair Queue

Queue for failed theater URL repairs with exponential backoff.

### Backoff Schedule

| Attempt | Wait Time |
|---------|-----------|
| 1 | 1 hour |
| 2 | 2 hours |
| 3 | 4 hours |
| 4 | 8 hours |
| 5 | 24 hours (max) |

After 5 attempts, theater requires manual intervention.

### GET /cache/repair-queue/status

Get queue statistics.

```json
{
  "total_queued": 8,
  "due_now": 3,
  "max_attempts_reached": 2,
  "by_attempts": {
    "1": 3,
    "2": 2,
    "3": 1,
    "5": 2
  },
  "max_attempts_limit": 5
}
```

### GET /cache/repair-queue/jobs

List all queued repair jobs.

```json
[
  {
    "theater_name": "AMC Test Theater",
    "market_name": "Madison",
    "zip_code": "53703",
    "attempts": 2,
    "next_attempt_at": "2025-01-15T12:00:00Z",
    "first_failure_at": "2025-01-15T08:00:00Z",
    "last_failure_at": "2025-01-15T10:00:00Z",
    "error_message": "URL returned 404"
  }
]
```

### GET /cache/repair-queue/failed

Get permanently failed theaters (max attempts reached).

### POST /cache/repair-queue/reset

Reset a job for immediate retry.

**Required Role:** admin

**Request:**
```json
{
  "theater_name": "AMC Test Theater",
  "market_name": "Madison"
}
```

### DELETE /cache/repair-queue/failed

Clear all permanently failed jobs.

**Required Role:** admin

### POST /cache/repair-queue/process

Process all due repairs immediately.

**Required Role:** admin

```json
{
  "processed": 3,
  "success": 2,
  "failed": 1
}
```

---

## Cache Maintenance

Automated health checks and repairs for the theater cache.

### POST /cache/maintenance

Run full maintenance (health check + repairs).

**Required Role:** admin

```json
{
  "timestamp": "2025-01-15T10:30:00Z",
  "duration_seconds": 45.2,
  "overall_status": "ok",
  "health_check": {
    "checked": 10,
    "failed": 1,
    "failure_rate_percent": 10.0,
    "threshold_percent": 30
  },
  "repairs": {
    "total_failed": 5,
    "attempted": 5,
    "repaired": 3,
    "still_failed": 2
  }
}
```

### POST /cache/maintenance/run

Alias for POST /cache/maintenance.

### GET /cache/maintenance/health

Quick health check only (samples 10 theaters).

```json
{
  "status": "ok",
  "checked": 10,
  "failed": 0,
  "failure_rate_percent": 0.0,
  "threshold_percent": 30
}
```

**Alert Threshold:** If failure rate exceeds 30%, an alert is raised indicating potential Fandango site changes.

### GET /cache/maintenance/history

Get maintenance run history.

**Query:** `limit` (int, default: 10)

```json
{
  "entries": [
    {
      "timestamp": "2025-01-15T10:00:00Z",
      "overall_status": "ok",
      "checked": 10,
      "failed": 0,
      "repaired": 2
    }
  ],
  "total_count": 5
}
```

---

## Prometheus Metrics

### GET /metrics

Prometheus-format metrics export. **No authentication required.**

### Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `scrape_operations_total` | Counter | Total scrape operations |
| `scrape_duration_seconds` | Histogram | Scrape duration |
| `scrape_theaters_total` | Counter | Theaters scraped |
| `scrape_theaters_failed_total` | Counter | Failed scrapes |
| `alerts_created_total` | Counter | Alerts by type |
| `alerts_acknowledged_total` | Counter | Acknowledged alerts |
| `circuit_breaker_state` | Gauge | 0=closed, 1=open, 2=half-open |
| `circuit_breaker_failures` | Gauge | Current failure count |
| `repair_queue_size` | Gauge | Jobs in queue |
| `repair_queue_failed` | Gauge | Permanently failed |
| `http_requests_total` | Counter | Requests by endpoint |
| `http_request_duration_seconds` | Histogram | Request latency |

### Example Prometheus Config

```yaml
scrape_configs:
  - job_name: 'pricescout'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

### Example Alert Rules

```yaml
groups:
  - name: pricescout
    rules:
      - alert: CircuitBreakerOpen
        expr: circuit_breaker_state == 1
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Circuit breaker {{ $labels.name }} is OPEN"

      - alert: HighRepairQueueSize
        expr: repair_queue_size > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Repair queue has {{ $value }} jobs"
```

---

## Role Permissions

### Role Hierarchy

| Role | Level | Description |
|------|-------|-------------|
| `admin` | 5 | Full access |
| `manager` | 4 | Management access |
| `operator` | 3 | Operational access |
| `auditor` | 2 | Read-only admin access |
| `user` | 1 | Standard user |

### Endpoint Permissions

| Endpoint | user | auditor | operator | manager | admin |
|----------|------|---------|----------|---------|-------|
| GET /health | Yes | Yes | Yes | Yes | Yes |
| GET /health/full | Yes | Yes | Yes | Yes | Yes |
| GET /system/health | No | Yes | Yes | Yes | Yes |
| POST /circuits/reset | No | No | Yes | Yes | Yes |
| POST /circuits/{name}/open | No | No | No | No | Yes |
| GET /schedule-alerts | Yes | Yes | Yes | Yes | Yes |
| POST /schedule-alerts/ack | Yes | Yes | Yes | Yes | Yes |
| PUT /schedule-monitor/config | No | No | No | No | Yes |
| GET /repair-queue/* | Yes | Yes | Yes | Yes | Yes |
| POST /repair-queue/reset | No | No | No | No | Yes |
| DELETE /repair-queue/failed | No | No | No | No | Yes |
| POST /cache/maintenance | No | No | No | No | Yes |

---

## Error Handling

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request (invalid parameters) |
| 401 | Unauthorized (missing/invalid token) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |

### Common Errors

**401 Unauthorized:**
```json
{
  "detail": "Not authenticated"
}
```

**403 Forbidden:**
```json
{
  "detail": "Insufficient permissions. Required role: admin"
}
```

**404 Not Found:**
```json
{
  "detail": "Theater 'Test Theater' not found in repair queue"
}
```

---

## Authentication

### Obtaining a Token

```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### Using the Token

Include in all requests:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### Token Refresh

```bash
POST /api/v1/auth/refresh
Authorization: Bearer <current_token>
```

---

## Rate Limiting

Currently no rate limiting implemented. Consider adding for production:
- Health endpoints: No limit
- Mutation endpoints: 60/minute
- Scrape triggers: 10/hour

---

**Document Version:** 1.0.0
**Last Updated:** January 2025
**API Version:** 1.0.0
