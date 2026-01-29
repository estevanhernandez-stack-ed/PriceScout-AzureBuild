# PriceScout Architecture Overview

Technical architecture for the PriceScout React/FastAPI infrastructure.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PriceScout System                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐   │
│  │   React     │────▶│   FastAPI   │────▶│   External Services │   │
│  │  Frontend   │◀────│   Backend   │◀────│   (Fandango, etc.)  │   │
│  └─────────────┘     └─────────────┘     └─────────────────────┘   │
│         │                   │                                       │
│         │                   ▼                                       │
│         │           ┌─────────────┐                                 │
│         │           │   SQLite    │                                 │
│         │           │  Database   │                                 │
│         │           └─────────────┘                                 │
│         │                   │                                       │
│         ▼                   ▼                                       │
│  ┌─────────────┐     ┌─────────────┐                               │
│  │  Prometheus │     │   Celery    │                               │
│  │  /Grafana   │     │  Scheduler  │                               │
│  └─────────────┘     └─────────────┘                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Architecture

### Frontend (React + TypeScript)

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/              # Shadcn/ui components
│   │   └── layout/          # Layout components
│   ├── hooks/
│   │   └── api/             # TanStack Query hooks
│   │       ├── useSystemHealth.ts
│   │       ├── useScheduleAlerts.ts
│   │       └── useRepairQueue.ts
│   ├── pages/
│   │   ├── SystemHealthPage.tsx
│   │   ├── ScheduleAlertsPage.tsx
│   │   └── RepairQueuePage.tsx
│   ├── stores/              # Zustand stores
│   └── lib/
│       ├── api.ts           # Axios client
│       └── queryClient.ts   # React Query config
```

**Key Technologies:**
- React 18 with TypeScript
- TanStack Query (React Query) for data fetching
- Shadcn/ui component library
- Zustand for state management
- Axios for HTTP requests

### Backend (FastAPI + Python)

```
api/
├── main.py                  # FastAPI app & health endpoints
├── metrics.py               # Prometheus metrics
└── routers/
    ├── auth.py              # Authentication
    ├── cache.py             # Cache & repair queue
    └── system.py            # System health & circuits

app/
├── circuit_breaker.py       # Circuit breaker implementation
├── repair_queue.py          # Repair queue with backoff
├── cache_maintenance_service.py
├── schedule_monitor.py      # Schedule change detection
└── scraper.py               # Fandango scraper
```

**Key Technologies:**
- FastAPI with async support
- SQLite for persistence
- Celery for scheduled tasks
- Prometheus client for metrics

---

## Circuit Breaker Pattern

### State Machine

```
                    failures >= threshold
    ┌──────────┐ ─────────────────────────▶ ┌──────────┐
    │  CLOSED  │                            │   OPEN   │
    │ (normal) │                            │(blocked) │
    └──────────┘                            └──────────┘
         ▲                                       │
         │                                       │ timeout
         │ success                               │ expires
         │                                       ▼
         │                                ┌────────────┐
         └────────────────────────────────│ HALF_OPEN  │
                                          │ (testing)  │
                                          └────────────┘
```

### Implementation

```python
# app/circuit_breaker.py

class CircuitBreaker:
    def __init__(self, name, failure_threshold=5, reset_timeout=3600):
        self.name = name
        self.state = "closed"
        self.failures = 0
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout  # seconds
        self.last_failure_time = None

    def call(self, func):
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half_open"
            else:
                raise CircuitOpenError(f"Circuit {self.name} is open")

        try:
            result = func()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        self.failures = 0
        self.state = "closed"

    def _on_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "open"
```

### Protected Operations

| Circuit | Operations Protected |
|---------|---------------------|
| `fandango` | Scraper requests, URL discovery, health checks |
| `enttelligence` | API sync, data fetching |

---

## Repair Queue Pattern

### Exponential Backoff

```
Attempt 1: Immediate → Fail → Wait 1 hour
Attempt 2: After 1h → Fail → Wait 2 hours
Attempt 3: After 2h → Fail → Wait 4 hours
Attempt 4: After 4h → Fail → Wait 8 hours
Attempt 5: After 8h → Fail → Wait 24 hours (max)
Attempt 6: MAX REACHED → Manual intervention required
```

### Data Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Theater    │     │   Repair     │     │    Cache     │
│  URL Fails   │────▶│    Queue     │────▶│   Updated    │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                            │ max attempts
                            ▼
                     ┌──────────────┐
                     │   Failed     │
                     │    List      │
                     └──────────────┘
```

### Queue Storage

```json
// repair_queue.json
{
  "Theater Name|Market": {
    "theater_name": "Theater Name",
    "market_name": "Market",
    "zip_code": "12345",
    "attempts": 3,
    "next_attempt_at": "2025-01-15T12:00:00Z",
    "first_failure_at": "2025-01-15T08:00:00Z",
    "last_failure_at": "2025-01-15T10:00:00Z",
    "error_message": "404 Not Found"
  }
}
```

---

## Schedule Monitor

### Detection Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Scheduler  │────▶│   Scrape    │────▶│   Compare   │
│  (hourly)   │     │  Schedules  │     │  with Cache │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               │ changes
                                               ▼
                                        ┌─────────────┐
                                        │   Create    │
                                        │   Alerts    │
                                        └─────────────┘
```

### Alert Types

| Type | Trigger |
|------|---------|
| `new_film` | Film not in previous schedule |
| `removed_film` | Film no longer in schedule |
| `new_showtime` | New showtime for existing film |
| `removed_showtime` | Showtime no longer available |
| `format_change` | Format changed (Standard→IMAX) |

---

## Health Monitoring

### Health Check Hierarchy

```
GET /health (basic)
    └── Database connection
    └── Service status

GET /health/full (comprehensive)
    └── Database
    └── Fandango Scraper
    │       └── Failure rate
    │       └── Theaters checked/failed
    └── EntTelligence
    │       └── Last sync time
    │       └── Records synced
    └── Alerts
    │       └── Price pending
    │       └── Schedule pending
    └── Scheduler
    │       └── Last activity
    │       └── Age
    └── Circuit Breakers
            └── State
            └── Failures
            └── Threshold

GET /api/v1/system/health (admin)
    └── All above
    └── Circuit management endpoints
    └── Feature flags
```

### Status Determination

```python
def determine_overall_status(components):
    statuses = [c.status for c in components.values()]

    if any(s in ['critical', 'error'] for s in statuses):
        return 'unhealthy'
    if any(s in ['degraded', 'stale'] for s in statuses):
        return 'degraded'
    return 'healthy'
```

---

## Metrics Collection

### Prometheus Integration

```python
# api/metrics.py

from prometheus_client import Counter, Histogram, Gauge

# Counters
scrape_operations = Counter(
    'scrape_operations_total',
    'Total scrape operations',
    ['status']
)

alerts_created = Counter(
    'alerts_created_total',
    'Alerts created',
    ['type']
)

# Gauges
circuit_state = Gauge(
    'circuit_breaker_state',
    'Circuit state (0=closed, 1=open, 2=half_open)',
    ['name']
)

repair_queue_size = Gauge(
    'repair_queue_size',
    'Jobs in repair queue'
)

# Histograms
scrape_duration = Histogram(
    'scrape_duration_seconds',
    'Scrape operation duration',
    buckets=[1, 5, 10, 30, 60, 120, 300]
)
```

### Metric Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Application│────▶│  /metrics   │────▶│ Prometheus  │
│   Events    │     │  Endpoint   │     │   Scraper   │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │   Grafana   │
                                        │  Dashboard  │
                                        └─────────────┘
```

---

## Role-Based Access Control

### Role Hierarchy

```
admin (level 5)
   └── All permissions
   └── Force trip circuits
   └── Manage users

manager (level 4)
   └── Reset circuits
   └── View all admin pages
   └── Company selection

operator (level 3)
   └── Reset circuits
   └── Trigger schedule checks
   └── View system health

auditor (level 2)
   └── View system health
   └── View user list
   └── Read-only access

user (level 1)
   └── View alerts
   └── Acknowledge alerts
   └── Basic operations
```

### Permission Check

```python
def require_role(*roles):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user=None, **kwargs):
            if current_user.role not in roles:
                raise HTTPException(403, "Insufficient permissions")
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

@router.post("/circuits/{name}/open")
@require_role("admin")
async def force_trip_circuit(name: str, current_user: dict):
    # Only admins can force trip
    pass
```

---

## Data Flow Diagrams

### Scrape Operation

```
User Request
     │
     ▼
┌─────────────┐     ┌─────────────┐
│   Check     │────▶│  Circuit    │
│   Circuit   │     │   Open?     │
└─────────────┘     └─────────────┘
                          │
           ┌──────────────┼──────────────┐
           │ Yes          │ No           │
           ▼              ▼              │
    ┌─────────────┐ ┌─────────────┐      │
    │ Return Fail │ │   Execute   │      │
    │   Fast      │ │   Scrape    │      │
    └─────────────┘ └─────────────┘      │
                          │              │
                    ┌─────┴─────┐        │
                    │           │        │
                    ▼           ▼        │
             ┌─────────┐ ┌─────────┐     │
             │ Success │ │ Failure │     │
             └─────────┘ └─────────┘     │
                    │           │        │
                    │           ▼        │
                    │    ┌─────────────┐ │
                    │    │  Increment  │ │
                    │    │  Failures   │ │
                    │    └─────────────┘ │
                    │           │        │
                    └─────┬─────┘        │
                          │              │
                          ▼              │
                   ┌─────────────┐       │
                   │   Update    │◀──────┘
                   │   Metrics   │
                   └─────────────┘
```

### Alert Processing

```
Schedule Check
     │
     ▼
┌─────────────┐     ┌─────────────┐
│   Detect    │────▶│   Create    │
│   Change    │     │   Alert     │
└─────────────┘     └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │   Store in  │
                   │   Database  │
                   └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │   Update    │
                   │   Metrics   │
                   └─────────────┘
                          │
            ┌─────────────┴─────────────┐
            │                           │
            ▼                           ▼
     ┌─────────────┐            ┌─────────────┐
     │  Dashboard  │            │ Notification │
     │   Update    │            │   (future)   │
     └─────────────┘            └─────────────┘
```

---

## Database Schema

### Core Tables

```sql
-- Repair Queue (JSON file)
-- See repair_queue.json structure above

-- Schedule Alerts
CREATE TABLE schedule_alerts (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    theater_name TEXT NOT NULL,
    film_title TEXT,
    details TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by TEXT,
    notes TEXT
);

-- Maintenance History
CREATE TABLE maintenance_history (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    overall_status TEXT,
    duration_seconds REAL,
    health_check JSON,
    repairs JSON
);

-- Audit Log
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT,
    action TEXT,
    resource TEXT,
    details JSON
);
```

---

## Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=sqlite:///data/pricescout.db

# Authentication
JWT_SECRET=your-secret-key
JWT_EXPIRY_MINUTES=60

# Circuit Breakers
FANDANGO_FAILURE_THRESHOLD=5
FANDANGO_RESET_TIMEOUT=3600
ENTTELLIGENCE_FAILURE_THRESHOLD=3
ENTTELLIGENCE_RESET_TIMEOUT=1800

# Scheduler
SCHEDULE_CHECK_INTERVAL=60  # minutes
MAINTENANCE_INTERVAL=1440   # minutes (daily)

# Metrics
METRICS_ENABLED=true
```

### Feature Flags

```python
FEATURES = {
    "celery": True,           # Background task scheduler
    "redis": False,           # Redis cache (optional)
    "entra_id": True,         # Azure AD authentication
    "enttelligence": True,    # EntTelligence sync
    "notifications": False,   # Push notifications (future)
}
```

---

## Deployment

### Production Stack

```
┌─────────────────────────────────────────────────────────┐
│                    Load Balancer                        │
└─────────────────────────────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  API 1   │ │  API 2   │ │  API 3   │
        └──────────┘ └──────────┘ └──────────┘
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────────┐
                    │ Database │
                    └──────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  Celery  │ │Prometheus│ │  Redis   │
        │  Worker  │ │          │ │(optional)│
        └──────────┘ └──────────┘ └──────────┘
```

---

**Document Version:** 1.0.0
**Last Updated:** January 2025
