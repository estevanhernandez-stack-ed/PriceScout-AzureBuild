# Theater Cache Maintenance

**Version:** 1.0.0
**Last Updated:** January 13, 2026
**Target Audience:** Administrators, DevOps

---

## Table of Contents

1. [Overview](#overview)
2. [How It Works](#how-it-works)
3. [Configuration](#configuration)
4. [API Endpoints](#api-endpoints)
5. [Scheduler Integration](#scheduler-integration)
6. [Troubleshooting](#troubleshooting)
7. [Manual Operations](#manual-operations)

---

## Overview

The Cache Maintenance Service automatically monitors and repairs the theater cache (`theater_cache.json`). It detects broken Fandango URLs and attempts to re-match theaters, ensuring the scraper continues to work even when Fandango changes their site structure.

### Key Features

- **Health Monitoring** - Randomly samples theaters to detect URL failures
- **Auto-Repair** - Automatically fixes broken theater URLs
- **Site Change Detection** - Alerts when failure rate exceeds threshold (Fandango restructure)
- **Scheduled Runs** - Daily automated maintenance at 3:00 AM UTC
- **History Logging** - Maintains audit trail of all maintenance runs

---

## How It Works

### Daily Maintenance Cycle

```
┌─────────────────────────────────────────────────────────────┐
│                    3:00 AM UTC Daily                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. HEALTH CHECK                                            │
│     └─ Select 10 random theaters from cache                 │
│     └─ Check each URL with HEAD request                     │
│     └─ Calculate failure rate                               │
│     └─ If > 30% fail → ALERT (site may have changed)        │
│                                                             │
│  2. AUTO-REPAIR                                             │
│     └─ Find theaters with broken/missing URLs               │
│     └─ Attempt to re-match via Fandango search              │
│     └─ Update cache with successful matches                 │
│     └─ Log failures for manual review                       │
│                                                             │
│  3. SAVE & LOG                                              │
│     └─ Save updated cache (with backup)                     │
│     └─ Append results to cache_maintenance.log              │
│     └─ Update cache metadata                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### URL Health Check

The health check samples random theaters to detect issues:

```python
# Sample 10 random theaters with valid URLs
sample = random.sample(valid_theaters, 10)

# Check each URL
for theater in sample:
    is_healthy = await check_url_status(theater['url'])
    # HEAD request to Fandango URL

# Calculate failure rate
failure_rate = failed_count / total_checked * 100

# Alert if too many failures
if failure_rate > 30:
    alert("Fandango may have changed site structure")
```

### Auto-Repair Process

```python
# Find broken theaters
broken = [t for t in cache if not t['url'] or t['url'] == 'N/A']

# Attempt repair for each (max 20 per run)
for theater in broken[:20]:
    # Search Fandango for theater name
    result = await discover_theater_url(theater['name'])

    if result['found']:
        theater['url'] = result['url']
        theater['name'] = result['theater_name']
```

---

## Configuration

### Constants (in `cache_maintenance_service.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `RANDOM_SAMPLE_SIZE` | 10 | Theaters to check per health check |
| `FAILURE_THRESHOLD_PERCENT` | 30 | Alert if this % of sample fails |
| `MAX_REPAIR_ATTEMPTS` | 20 | Max theaters to repair per run |

### File Locations

| File | Purpose |
|------|---------|
| `app/theater_cache.json` | Theater URL cache |
| `cache_maintenance.log` | Maintenance history log |
| `theater_cache.json.maintenance_bak` | Auto-created backup |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_EXPIRATION_DAYS` | 7 | Days before cache is considered stale |

---

## API Endpoints

All endpoints require authentication. Admin role required for maintenance operations.

### POST /api/v1/cache/maintenance

Run full maintenance cycle (health check + repairs).

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| background | boolean | false | Run async (returns immediately) |

**Response (synchronous):**
```json
{
  "timestamp": "2026-01-13T03:00:00Z",
  "duration_seconds": 45.2,
  "overall_status": "ok",
  "alert_message": null,
  "health_check": {
    "status": "ok",
    "checked": 10,
    "failed": 1,
    "failure_rate_percent": 10.0,
    "failed_theaters": ["AMC Example 12"]
  },
  "repairs": {
    "status": "ok",
    "total_failed": 5,
    "attempted": 5,
    "repaired": 3,
    "still_failed": 2,
    "repaired_theaters": [
      {
        "original_name": "Regal Test",
        "new_name": "Regal Test Cinema",
        "market": "Test Market",
        "url": "https://www.fandango.com/..."
      }
    ]
  }
}
```

### GET /api/v1/cache/maintenance/health

Run quick health check only (no repairs).

**Response:**
```json
{
  "status": "ok",
  "checked": 10,
  "failed": 0,
  "failure_rate_percent": 0.0,
  "failed_theaters": [],
  "threshold_percent": 30
}
```

### GET /api/v1/cache/maintenance/history

Get recent maintenance run history.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | integer | 10 | Number of entries to return |

**Response:**
```json
{
  "entries": [
    {
      "timestamp": "2026-01-13T03:00:00Z",
      "overall_status": "ok",
      "checked": 10,
      "failed": 0,
      "repaired": 2
    }
  ],
  "total_count": 1
}
```

---

## Scheduler Integration

The maintenance job is configured in `scheduler_service.py`:

```python
from apscheduler.schedulers.blocking import BlockingScheduler

scheduler = BlockingScheduler(timezone=pytz.utc)

# Run cache maintenance daily at 3:00 AM UTC
scheduler.add_job(
    run_cache_maintenance,
    'cron',
    hour=3,
    minute=0,
    id='cache_maintenance',
    name='Theater Cache Maintenance'
)
```

### Changing the Schedule

To modify the schedule, edit `scheduler_service.py`:

```python
# Example: Run twice daily at 3 AM and 3 PM UTC
scheduler.add_job(
    run_cache_maintenance,
    'cron',
    hour='3,15',
    minute=0,
    id='cache_maintenance'
)

# Example: Run every 6 hours
scheduler.add_job(
    run_cache_maintenance,
    'interval',
    hours=6,
    id='cache_maintenance'
)
```

### Running the Scheduler

```bash
# Start scheduler service
python scheduler_service.py

# Output:
# Scheduler service started.
#   - Scrape task check: every 1 minute
#   - Cache maintenance: daily at 03:00 UTC
# Press Ctrl+C to exit.
```

---

## Troubleshooting

### High Failure Rate Alert

**Symptom:** Alert message "High failure rate detected (X%). Fandango may have changed their site structure."

**Causes:**
1. Fandango changed their HTML/URL structure
2. Fandango is experiencing downtime
3. Rate limiting by Fandango

**Actions:**
1. Wait 1 hour and run health check again
2. If persists, manually check Fandango website
3. Review `debug_*.html` files in DEBUG_DIR for HTML changes
4. May need to update scraper selectors

### No Repairs Attempted

**Symptom:** `repairs.attempted = 0` but known broken theaters exist.

**Causes:**
1. Theaters marked as `not_on_fandango` are skipped
2. Theaters marked as "Permanently Closed" are skipped
3. No ZIP codes available for re-matching

**Actions:**
1. Check cache for `not_on_fandango` flags
2. Verify markets.json has ZIP codes
3. Manually review in Theater Matching mode

### Repairs Failing

**Symptom:** `repairs.still_failed` is high.

**Causes:**
1. Theater genuinely not on Fandango
2. Theater name doesn't match Fandango's naming
3. Theater permanently closed

**Actions:**
1. Use Theater Matching mode for manual intervention
2. Mark as `not_on_fandango` if confirmed
3. Update theater name in markets.json

---

## Manual Operations

### Run Maintenance via API

```bash
# Full maintenance
curl -X POST http://localhost:8000/api/v1/cache/maintenance \
  -H "Authorization: Bearer <token>"

# Quick health check only
curl http://localhost:8000/api/v1/cache/maintenance/health \
  -H "Authorization: Bearer <token>"

# View history
curl http://localhost:8000/api/v1/cache/maintenance/history?limit=5 \
  -H "Authorization: Bearer <token>"
```

### Run Maintenance via Python

```python
import asyncio
from app.cache_maintenance_service import CacheMaintenanceService

async def main():
    service = CacheMaintenanceService()

    # Full maintenance
    result = await service.run_maintenance()
    print(f"Status: {result['overall_status']}")
    print(f"Repaired: {result['repairs']['repaired']}")

    # Health check only
    health = await service.run_health_check()
    print(f"Failure rate: {health['failure_rate_percent']}%")

    # Repair only
    repairs = await service.run_repair()
    print(f"Fixed: {repairs['repaired']} theaters")

asyncio.run(main())
```

### View Maintenance Log

```bash
# View last 10 entries
tail -10 cache_maintenance.log

# View all entries for today
grep "2026-01-13" cache_maintenance.log

# Parse as JSON
python -c "
import json
with open('cache_maintenance.log') as f:
    for line in f:
        entry = json.loads(line)
        print(f\"{entry['timestamp']}: {entry['overall_status']}\")
"
```

### Force Re-check Specific Theater

```python
from app.cache_maintenance_service import CacheMaintenanceService

async def check_specific():
    service = CacheMaintenanceService()

    # Check single URL
    is_healthy = await service._check_url_health(
        "https://www.fandango.com/amc-empire-25-AAPCR/theater-page"
    )
    print(f"URL healthy: {is_healthy}")

asyncio.run(check_specific())
```

---

## Log Format

Each maintenance run appends a JSON line to `cache_maintenance.log`:

```json
{
  "timestamp": "2026-01-13T03:00:00.123456",
  "duration_seconds": 45.2,
  "overall_status": "ok",
  "health_check": {
    "status": "ok",
    "checked": 10,
    "failed": 1,
    "failure_rate_percent": 10.0,
    "failed_theaters": ["AMC Example"],
    "threshold_percent": 30
  },
  "repairs": {
    "status": "ok",
    "total_failed": 3,
    "attempted": 3,
    "repaired": 2,
    "still_failed": 1,
    "repaired_theaters": [...],
    "still_failed_theaters": [...]
  }
}
```

---

## Related Documentation

- [ADMIN_GUIDE.md](ADMIN_GUIDE.md) - Theater cache administration
- [API_REFERENCE.md](API_REFERENCE.md) - Full API documentation
- [SCHEDULE_MONITOR.md](SCHEDULE_MONITOR.md) - Schedule monitoring feature
