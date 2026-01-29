# PriceScout Admin User Guide

Guide for administrators and operators using the PriceScout management interface.

---

## Getting Started

### Accessing Admin Features

Admin features are available based on your role:

| Feature | User | Auditor | Operator | Manager | Admin |
|---------|------|---------|----------|---------|-------|
| System Health Dashboard | No | View | View + Reset | View + Reset | Full |
| Schedule Alerts | View | View | View | View | Full |
| Repair Queue | View | View | View + Process | View + Process | Full |
| User Management | No | View | No | View | Full |

### Navigation

Admin pages are found in the sidebar under **Management**:

- **System Health** - Monitor system components and circuit breakers
- **Repair Queue** - Manage failed theater URL repairs
- **Schedule Alerts** - Review schedule change notifications
- **Admin** - User management (admin/manager only)

---

## System Health Dashboard

**Location:** `/admin/system-health`

### Overview

The System Health page shows real-time status of all system components.

### Status Banner

The top banner indicates overall system health:

| Color | Status | Meaning |
|-------|--------|---------|
| Green | Healthy | All systems operational |
| Yellow | Degraded | Some issues, system functional |
| Red | Unhealthy | Critical issues, action needed |

### Component Cards

#### Database
Shows database connection status.
- **OK**: Database connected and responding
- **Error**: Cannot connect to database

#### Fandango Circuit
Shows Fandango scraper circuit breaker status.
- **State**: closed (normal), open (blocked), half_open (testing)
- **Failures**: Current failure count
- **Progress bar**: Visual failure threshold indicator

**Actions (Operator+):**
- **Reset**: Clear failures, return to closed state
- **Trip** (Admin only): Force circuit open immediately

#### EntTelligence Circuit
Shows EntTelligence API sync circuit breaker status.
Same indicators and actions as Fandango circuit.

#### EntTelligence Sync
Shows last synchronization status.
- **Last Sync**: When data was last synced
- **Records**: Number of records synced

#### Pending Alerts
Shows count of unacknowledged alerts.
- **Price Alerts**: Price change alerts
- **Schedule Alerts**: Schedule change alerts

#### Scheduler
Shows background task scheduler status.
- **Last Activity**: When scheduler last ran
- **Age**: Time since last activity

### Status Legend

At the bottom, a legend explains status indicators:
- **OK** (green): Operating normally
- **Degraded** (yellow): Issues but functional
- **Error** (red): Not functioning
- **Unknown** (gray): Cannot determine status

### Auto-Refresh

The dashboard automatically refreshes every 10 seconds. Click the **Refresh** button for immediate update.

---

## Schedule Alerts

**Location:** `/schedule-alerts`

### Overview

Schedule Alerts notify you when theater schedules change. The system periodically checks schedules and creates alerts for changes.

### Alert Types

| Type | Icon | Meaning |
|------|------|---------|
| New Film | Film+ | New movie added to schedule |
| Removed Film | Film- | Movie removed from schedule |
| New Showtime | Clock+ | New showtime added |
| Removed Showtime | Clock- | Showtime removed |
| Format Change | Screen | Format changed (e.g., Standard to IMAX) |

### Summary Cards

Top of page shows counts by type:
- **Pending**: Total unacknowledged alerts
- **New Films**: New film alerts
- **New Showtimes**: New showtime alerts
- **Removed**: Removed film/showtime alerts
- **New Formats**: Format change alerts

### Alerts Table

The main table shows alert details:

| Column | Description |
|--------|-------------|
| Checkbox | Select for bulk actions |
| Type | Alert type with icon |
| Theater | Theater name |
| Film | Film title (if applicable) |
| Details | Specific change information |
| Created | When alert was created |
| Status | Pending or Acknowledged |

### Filtering

Toggle between:
- **Pending**: Only unacknowledged alerts
- **Acknowledged**: Only acknowledged alerts

### Acknowledging Alerts

**Single Alert:**
1. Find the alert in the table
2. Click the **Acknowledge** button
3. Optionally add notes
4. Click **Confirm**

**Multiple Alerts:**
1. Check boxes next to alerts
2. Click **Acknowledge Selected**
3. Add notes (applies to all)
4. Click **Confirm**

### Manual Schedule Check

Click **Trigger Check** to run an immediate schedule comparison. This may take several minutes for large theater sets.

---

## Repair Queue

**Location:** `/admin/repair-queue`

### Overview

The Repair Queue manages theaters with broken or missing Fandango URLs. Failed repairs are retried automatically with increasing wait times (exponential backoff).

### Backoff Schedule

| Attempt | Wait Before Next Retry |
|---------|----------------------|
| 1 | 1 hour |
| 2 | 2 hours |
| 3 | 4 hours |
| 4 | 8 hours |
| 5 | 24 hours |
| 6+ | Max attempts reached |

### Status Cards

| Card | Meaning |
|------|---------|
| Total Queued | All theaters in repair queue |
| Due Now | Ready for retry |
| Max Attempts | Exceeded retry limit (needs attention) |
| Max Retries | Maximum attempts allowed (5) |

### Queue Tab

Shows theaters waiting for repair:

| Column | Description |
|--------|-------------|
| Theater | Theater name |
| Market | Market/region |
| ZIP | ZIP code for location |
| Attempts | Retry attempts used |
| Next Retry | When next retry scheduled |
| Backoff | Current wait time |
| Last Error | Most recent error message |
| Actions | Reset button |

**Reset Action:** Click to clear attempts and retry immediately.

### Failed Tab

Shows theaters that exceeded max attempts:

These theaters need manual intervention:
1. Research the theater on Fandango
2. Update URL via Theater Matching if found
3. Mark as "Not on Fandango" if unavailable
4. Clear from list after resolution

**Clear All:** Remove all failed theaters from queue.

### History Tab

Shows past maintenance runs:

| Field | Description |
|-------|-------------|
| Timestamp | When maintenance ran |
| Status | ok, alert, or error |
| Checked | Theaters health-checked |
| Failed | Health checks that failed |
| Repaired | Successfully repaired |

### Actions

**Run Maintenance:** Execute full maintenance cycle (health check + repairs).

**Process Queue:** Retry all due repairs immediately.

---

## Common Tasks

### Responding to Circuit Breaker Open

1. Go to System Health page
2. Identify which circuit is open (red)
3. Check the external service manually:
   - Fandango: Visit fandango.com
   - EntTelligence: Check API status
4. If service is working:
   - Click **Reset** to close circuit
   - Monitor for recurring failures
5. If service is down:
   - Wait for recovery
   - Circuit will auto-reset after timeout

### Clearing Alert Backlog

1. Go to Schedule Alerts
2. Review pending alerts by type
3. For valid changes: Acknowledge with notes
4. For unexpected changes: Investigate and escalate if needed
5. Use bulk acknowledge for similar alerts

### Handling Failed Theaters

1. Go to Repair Queue → Failed tab
2. Review each failed theater:
   - Check error message
   - Search Fandango for theater
3. If found on Fandango:
   - Go to Theater Matching
   - Update the URL
   - Return to Repair Queue
   - Reset the job
4. If not on Fandango:
   - Mark appropriately in Theater Matching
   - Clear from failed list

### Running Manual Maintenance

1. Go to Repair Queue
2. Click **Run Maintenance**
3. Wait for completion (may take 1-2 minutes)
4. Review results in History tab
5. Check if new items added to queue

---

## Understanding Metrics

### Health Check Metrics

When maintenance runs, it samples 10 random theaters:

| Metric | Meaning |
|--------|---------|
| Checked | Theaters tested |
| Failed | Tests that failed |
| Failure Rate | Failed / Checked percentage |

**Alert Threshold:** If failure rate exceeds 30%, an alert is raised. This may indicate Fandango site changes.

### Repair Metrics

| Metric | Meaning |
|--------|---------|
| Total Failed | Theaters needing repair |
| Attempted | Repairs tried |
| Repaired | Successful repairs |
| Still Failed | Repairs that failed |

---

## Best Practices

### Daily Checks

1. Review System Health dashboard
2. Check for open circuits
3. Review pending schedule alerts
4. Monitor repair queue size

### Weekly Tasks

1. Clear acknowledged alerts if not needed
2. Review failed theaters list
3. Check maintenance history for patterns
4. Verify scheduler is running consistently

### When to Escalate

- Circuit breaker repeatedly opens
- High failure rate in maintenance (>30%)
- Large number of failed theaters
- Scheduler not running
- Database errors

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `R` | Refresh current page |
| `Esc` | Close dialog |
| `Enter` | Confirm dialog |

---

## Glossary

| Term | Definition |
|------|------------|
| Circuit Breaker | Pattern that stops requests to failing services |
| Closed | Normal circuit state, requests pass through |
| Open | Blocked circuit state, requests fail fast |
| Half-Open | Testing state, allows one request |
| Backoff | Increasing wait time between retries |
| Scrape | Fetching data from website |
| Sync | Updating data from external API |

---

## Getting Help

- **Documentation:** Check docs folder for detailed guides
- **Issues:** Report bugs via issue tracker
- **Support:** Contact IT support for access issues

---

**Document Version:** 1.0.0
**Last Updated:** January 2025
