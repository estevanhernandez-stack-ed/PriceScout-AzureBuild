# Schedule Monitor

**Version:** 1.0.0
**Last Updated:** January 13, 2026
**Target Audience:** Administrators, Analysts

---

## Table of Contents

1. [Overview](#overview)
2. [Use Cases](#use-cases)
3. [Architecture](#architecture)
4. [Database Schema](#database-schema)
5. [Service Layer](#service-layer)
6. [API Endpoints](#api-endpoints)
7. [Usage Guide](#usage-guide)
8. [Alert Types](#alert-types)
9. [Circuit Analysis](#circuit-analysis)
10. [Scheduled Tasks](#scheduled-tasks)

---

## Overview

The Schedule Monitor tracks when movie theaters post their upcoming schedules to EntTelligence. It detects:

- **New films** appearing in theater schedules
- **New showtimes** added to existing films
- **Removed showtimes** from schedules
- **Removed films** from theater listings
- **Format additions** (IMAX, Dolby, etc.)

### Key Benefits

- Identify which circuits/theaters post schedules earliest
- Track schedule changes over time
- Detect when theaters add new release films
- Monitor forward-looking schedule availability (next week, next 2 weeks)

---

## Use Cases

### 1. Early Poster Detection
Run the monitor Monday night to see which theaters have already posted next week's schedules. Major circuits (AMC, Regal, Cinemark) typically post early, while independents may lag.

### 2. New Release Tracking
When a new film opens, detect which theaters add it to their schedules first.

### 3. Schedule Gap Analysis
Identify theaters that haven't posted schedules for upcoming dates, indicating potential data gaps.

### 4. Change Auditing
Track when schedules change - useful for identifying last-minute showtime additions or cancellations.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Schedule Monitor                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Baselines   │───▶│   Compare    │───▶│   Alerts     │  │
│  │  (Snapshots) │    │   Engine     │    │  (Changes)   │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         ▲                   ▲                               │
│         │                   │                               │
│  ┌──────┴───────────────────┴──────┐                       │
│  │      EntTelligence Cache        │                       │
│  │      (Current Schedule Data)    │                       │
│  └─────────────────────────────────┘                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Baseline Creation**: Snapshot current EntTelligence data for specific dates
2. **Check Execution**: Compare current data against baselines
3. **Change Detection**: Identify differences (new/removed films/showtimes)
4. **Alert Generation**: Create alerts for each detected change

---

## Database Schema

### schedule_baselines

Stores snapshots of theater schedules for change detection.

| Column | Type | Description |
|--------|------|-------------|
| baseline_id | INTEGER | Primary key |
| company_id | INTEGER | FK to companies |
| theater_name | VARCHAR(255) | Theater name from EntTelligence |
| film_title | VARCHAR(500) | Film title |
| play_date | DATE | Show date |
| showtimes | TEXT | JSON array of showtime strings |
| snapshot_at | TIMESTAMP | When baseline was created |
| source | VARCHAR(50) | Data source (default: 'enttelligence') |
| effective_from | TIMESTAMP | When baseline became active |
| effective_to | TIMESTAMP | NULL = current baseline |

**Indexes:**
- `(company_id, theater_name, film_title, play_date)` - Unique constraint for current baselines

### schedule_alerts

Stores detected schedule changes.

| Column | Type | Description |
|--------|------|-------------|
| alert_id | INTEGER | Primary key |
| company_id | INTEGER | FK to companies |
| theater_name | VARCHAR(255) | Theater name |
| film_title | VARCHAR(500) | Film title (nullable for theater-level alerts) |
| play_date | DATE | Affected date |
| alert_type | VARCHAR(50) | Type of change detected |
| old_value | TEXT | JSON - previous value |
| new_value | TEXT | JSON - new value |
| change_details | TEXT | Human-readable description |
| triggered_at | TIMESTAMP | When alert was created |
| is_acknowledged | BOOLEAN | Whether alert has been reviewed |

### schedule_monitor_config

Per-company monitoring configuration.

| Column | Type | Description |
|--------|------|-------------|
| config_id | INTEGER | Primary key |
| company_id | INTEGER | FK to companies (unique) |
| is_enabled | BOOLEAN | Whether monitoring is active |
| check_frequency_hours | INTEGER | How often to run checks (default: 6) |
| alert_on_new_film | BOOLEAN | Alert when new films appear |
| alert_on_new_showtime | BOOLEAN | Alert when showtimes added |
| alert_on_removed_showtime | BOOLEAN | Alert when showtimes removed |
| alert_on_removed_film | BOOLEAN | Alert when films removed |
| days_ahead | INTEGER | How many days forward to monitor (default: 14) |

---

## Service Layer

### ScheduleMonitorService

Location: `app/schedule_monitor_service.py`

```python
from app.schedule_monitor_service import get_schedule_monitor_service

# Initialize service for a company
service = get_schedule_monitor_service(company_id=1)

# Create baselines from current EntTelligence data
result = service.create_baselines_from_cache(
    theater_names=None,  # All theaters, or list of specific names
    play_dates=["2026-01-19", "2026-01-20"],
    user_id=1
)
# Returns: {'baselines_created': 74563, 'theaters_processed': 2731, 'films_processed': 572}

# Run a check to detect changes
result = service.run_check(
    theater_names=None,
    play_dates=["2026-01-19", "2026-01-20"]
)
# Returns: {'status': 'completed', 'theaters_checked': 2731, 'alerts_created': 5, 'changes': [...]}

# Get alerts
alerts = service.get_alerts(
    is_acknowledged=False,
    alert_type='new_film',
    theater_name=None,
    limit=100,
    offset=0
)

# Acknowledge an alert
service.acknowledge_alert(alert_id=123, user_id=1, notes="Reviewed")

# Get alert summary
summary = service.get_alert_summary()
# Returns: {'total_pending': 5, 'total_acknowledged': 10, 'by_type': {'new_film': 3, 'new_showtime': 2}}

# Update configuration
service.update_config({
    'is_enabled': True,
    'days_ahead': 14,
    'alert_on_new_film': True
})
```

---

## API Endpoints

All endpoints require authentication and are prefixed with `/api/v1`.

### GET /schedule-alerts

List schedule change alerts.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| is_acknowledged | boolean | null | Filter by acknowledgment status |
| alert_type | string | null | Filter by alert type |
| theater_name | string | null | Filter by theater |
| limit | integer | 100 | Max results |
| offset | integer | 0 | Pagination offset |

**Response:**
```json
{
  "alerts": [
    {
      "alert_id": 1,
      "theater_name": "AMC Empire 25",
      "film_title": "Avatar 3",
      "play_date": "2026-01-19",
      "alert_type": "new_film",
      "change_details": "New film added to schedule",
      "triggered_at": "2026-01-13T18:30:00Z",
      "is_acknowledged": false
    }
  ],
  "total": 5,
  "limit": 100,
  "offset": 0
}
```

### GET /schedule-alerts/summary

Get alert counts by type.

**Response:**
```json
{
  "total_pending": 5,
  "total_acknowledged": 10,
  "by_type": {
    "new_film": 3,
    "new_showtime": 2,
    "removed_showtime": 0,
    "removed_film": 0
  }
}
```

### PUT /schedule-alerts/{alert_id}/acknowledge

Mark an alert as acknowledged.

**Request Body:**
```json
{
  "notes": "Reviewed - expected new release"
}
```

### POST /schedule-monitor/check

Trigger a manual schedule check.

**Request Body:**
```json
{
  "theater_names": null,
  "play_dates": ["2026-01-19", "2026-01-20", "2026-01-21"]
}
```

**Response:**
```json
{
  "status": "completed",
  "theaters_checked": 2731,
  "alerts_created": 5,
  "check_duration_seconds": 45.2
}
```

### GET /schedule-monitor/status

Get current monitor status.

**Response:**
```json
{
  "is_enabled": true,
  "last_check_at": "2026-01-13T18:00:00Z",
  "last_check_alerts_count": 0,
  "baseline_count": 279219,
  "pending_alerts_count": 5
}
```

### GET /schedule-monitor/config

Get monitoring configuration.

### PUT /schedule-monitor/config

Update monitoring configuration.

**Request Body:**
```json
{
  "is_enabled": true,
  "check_frequency_hours": 6,
  "days_ahead": 14,
  "alert_on_new_film": true,
  "alert_on_new_showtime": true,
  "alert_on_removed_showtime": true,
  "alert_on_removed_film": true
}
```

### POST /schedule-baselines/snapshot

Create baselines from current EntTelligence data.

**Request Body:**
```json
{
  "theater_names": null,
  "dates": ["2026-01-19", "2026-01-20", "2026-01-21", "2026-01-22", "2026-01-23", "2026-01-24", "2026-01-25"]
}
```

**Response:**
```json
{
  "baselines_created": 74563,
  "theaters_processed": 2731,
  "films_processed": 572
}
```

---

## Usage Guide

### Initial Setup

1. **Sync EntTelligence Data**

   Ensure EntTelligence data is synced for the dates you want to monitor:
   ```
   POST /api/v1/enttelligence/sync
   {"start_date": "2026-01-19", "end_date": "2026-01-25"}
   ```

2. **Create Baselines**

   Snapshot current schedule data:
   ```
   POST /api/v1/schedule-baselines/snapshot
   {"dates": ["2026-01-19", "2026-01-20", "2026-01-21", "2026-01-22", "2026-01-23", "2026-01-24", "2026-01-25"]}
   ```

3. **Configure Monitoring**

   Set your preferences:
   ```
   PUT /api/v1/schedule-monitor/config
   {"is_enabled": true, "days_ahead": 14, "alert_on_new_film": true}
   ```

### Weekly Workflow

**Monday Night:**
1. Sync EntTelligence for next week (Mon-Sun)
2. Create baselines for next week
3. Run initial check to see current state

**Throughout Week:**
1. Run periodic checks (manually or via scheduler)
2. Review alerts for new postings
3. Acknowledge reviewed alerts

### Detecting Early Posters

To find which theaters post earliest:

1. Monday night, check which theaters have next week's data
2. Compare against total theater count
3. Theaters with data = early posters
4. Theaters without = late posters

---

## Alert Types

| Type | Description | Example |
|------|-------------|---------|
| `new_film` | Film not in baseline now appears | Theater added "Avatar 3" to Jan 19 schedule |
| `new_showtime` | Additional showtime for existing film | "Wicked" added 10:30 PM showing |
| `removed_showtime` | Showtime no longer present | 7:00 PM show cancelled |
| `removed_film` | Film completely removed from date | "Mufasa" no longer showing Jan 19 |
| `format_added` | New format added (IMAX, Dolby, etc.) | IMAX showing added for "Avatar 3" |

---

## Circuit Analysis

The monitor can track posting patterns by circuit:

### Major Circuits (Typically Early Posters)
- **AMC** - ~530 theaters, posts 1-2 weeks ahead
- **Regal** - ~410 theaters, posts 1-2 weeks ahead
- **Cinemark** - ~240 theaters, posts 1-2 weeks ahead

### Regional Circuits
- **Marcus** - ~60 theaters
- **Alamo Drafthouse** - ~45 theaters
- **B&B Theatres** - ~45 theaters
- **Harkins** - ~30 theaters

### Independents
- ~1,400 theaters
- Posting patterns vary widely
- Many post 3-7 days ahead

### Sample Analysis Output

```
Theaters with data for TODAY: 3,015
Theaters with data for NEXT WEEK: 2,731 (91%)
Theaters NOT posted for next week: 337 (11%)

By Circuit (Posted/Missing):
  AMC: 528 posted, 3 missing
  Regal: 406 posted, 1 missing
  Cinemark: 241 posted, 1 missing
  Other/Independent: 1,366 posted, 327 missing
```

---

## Scheduled Tasks

The Schedule Monitor can be integrated with APScheduler for automated checks.

### Configuration

In your scheduler setup:

```python
from apscheduler.schedulers.background import BackgroundScheduler
from app.schedule_monitor_service import get_schedule_monitor_service

def run_schedule_check():
    """Run schedule check for all companies."""
    service = get_schedule_monitor_service(company_id=1)
    config = service.get_config()

    if config.get('is_enabled'):
        # Calculate dates to check based on days_ahead
        from datetime import date, timedelta
        today = date.today()
        dates = [(today + timedelta(days=i)).isoformat()
                 for i in range(1, config.get('days_ahead', 14) + 1)]

        result = service.run_check(play_dates=dates)
        print(f"Schedule check complete: {result['alerts_created']} alerts")

# Schedule to run every 6 hours
scheduler = BackgroundScheduler()
scheduler.add_job(run_schedule_check, 'interval', hours=6)
scheduler.start()
```

### Recommended Schedule

| Task | Frequency | Description |
|------|-----------|-------------|
| EntTelligence Sync | Daily | Sync data for next 2 weeks |
| Baseline Update | Weekly (Monday) | Create baselines for upcoming week |
| Schedule Check | Every 6 hours | Detect changes against baselines |
| Alert Review | Daily | Review and acknowledge alerts |

---

## Troubleshooting

### No Alerts Generated

1. **Check config is enabled:**
   ```sql
   SELECT * FROM schedule_monitor_config WHERE company_id = 1;
   ```
   Ensure `is_enabled = 1` and alert flags are set.

2. **Verify baselines exist:**
   ```sql
   SELECT play_date, COUNT(*) FROM schedule_baselines GROUP BY play_date;
   ```

3. **Confirm EntTelligence data exists:**
   ```sql
   SELECT play_date, COUNT(*) FROM enttelligence_price_cache GROUP BY play_date;
   ```

### Missing Theaters

Some theaters may not appear in EntTelligence data due to:
- Theater not participating in EntTelligence
- Data sync timing
- Theater temporarily closed

### Performance

For large datasets:
- Create baselines in batches by date
- Run checks for specific date ranges
- Use theater_names filter for targeted checks
