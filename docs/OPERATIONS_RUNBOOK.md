# PriceScout Operations Runbook

Step-by-step procedures for common operational tasks and incident response.

---

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Incident Response](#incident-response)
3. [Circuit Breaker Management](#circuit-breaker-management)
4. [Repair Queue Management](#repair-queue-management)
5. [Schedule Alert Management](#schedule-alert-management)
6. [Maintenance Procedures](#maintenance-procedures)
7. [Monitoring and Alerting](#monitoring-and-alerting)
8. [Troubleshooting Guide](#troubleshooting-guide)

---

## Daily Operations

### Morning Health Check

**Frequency:** Daily, 8:00 AM

1. Navigate to `/admin/system-health`
2. Verify overall status is **healthy** (green banner)
3. Check each component:
   - Database: Status should be "ok"
   - Fandango Circuit: Should be "closed"
   - EntTelligence Circuit: Should be "closed"
   - Pending Alerts: Review count
   - Scheduler: Last activity < 30 minutes ago
4. If any issues, follow [Incident Response](#incident-response)

### Review Schedule Alerts

**Frequency:** Daily or as needed

1. Navigate to `/schedule-alerts`
2. Review pending alerts by type:
   - **New Films**: Verify expected releases
   - **Removed Films**: Check if intentional
   - **Showtime Changes**: Spot check accuracy
3. Acknowledge reviewed alerts with notes
4. Escalate unexpected changes to management

### Monitor Repair Queue

**Frequency:** Daily

1. Navigate to `/admin/repair-queue`
2. Check status cards:
   - **Total Queued**: Should be < 20
   - **Due Now**: Should be < 10
   - **Max Attempts**: Should be 0
3. If "Max Attempts" > 0:
   - Review failed theaters in "Failed" tab
   - Determine if manual intervention needed
   - Either reset for retry or clear after resolution

---

## Incident Response

### Severity Levels

| Level | Criteria | Response Time |
|-------|----------|---------------|
| P1 - Critical | System down, all users affected | Immediate |
| P2 - High | Major feature broken, many users affected | < 1 hour |
| P3 - Medium | Feature degraded, some users affected | < 4 hours |
| P4 - Low | Minor issue, workaround available | < 24 hours |

### P1: System Unhealthy

**Symptoms:** Red "unhealthy" banner on System Health page

**Steps:**

1. **Identify failing component**
   - Check each component card for "error" or "critical" status

2. **If Database failing:**
   ```bash
   # Check database file
   ls -la data/pricescout.db

   # Check disk space
   df -h

   # Restart API server
   systemctl restart pricescout-api
   ```

3. **If Circuit Breaker open:**
   - See [Circuit Breaker Open](#circuit-breaker-open) procedure

4. **If Scheduler stale:**
   ```bash
   # Check Celery worker
   systemctl status celery-worker

   # Restart if needed
   systemctl restart celery-worker
   ```

5. **Notify stakeholders** via appropriate channel

6. **Document incident** in incident log

### P2: Circuit Breaker Open

**Symptoms:** Circuit breaker card shows "open" state (red)

**Steps:**

1. **Assess impact**
   - Fandango circuit: Scraping disabled
   - EntTelligence circuit: Sync disabled

2. **Check external service**
   - Fandango: Try https://www.fandango.com manually
   - EntTelligence: Check API status

3. **If external service is down:**
   - Wait for recovery
   - Circuit will auto-reset after timeout (1 hour for Fandango)

4. **If external service is up:**
   - Possible transient issue
   - Click "Reset" button on circuit card
   - Monitor for recurring failures

5. **If failures continue after reset:**
   - Investigate logs for specific errors
   - May indicate site change (Fandango) or API change

### P3: High Repair Queue

**Symptoms:** Repair queue > 20 jobs or "Max Attempts" > 5

**Steps:**

1. **Review failed theaters**
   - Go to `/admin/repair-queue` → "Failed" tab
   - Check error messages for patterns

2. **Common patterns:**
   - "404 Not Found": Theater URL changed or removed
   - "Timeout": Site slow, may resolve
   - "Blocked": Possible IP block

3. **For URL changes:**
   - Go to Theater Matching page
   - Search for theater on Fandango manually
   - Update URL if found

4. **For persistent failures:**
   - Mark theater as "Not on Fandango" if appropriate
   - Clear from failed list after resolution

---

## Circuit Breaker Management

### Reset a Circuit

**When:** Circuit stuck open after external service recovered

**Via UI:**
1. Go to `/admin/system-health`
2. Find the circuit card (Fandango or EntTelligence)
3. Click "Reset" button
4. Confirm toast notification appears

**Via API:**
```bash
curl -X POST https://api.pricescout.com/api/v1/system/circuits/fandango/reset \
  -H "Authorization: Bearer <token>"
```

### Force Trip a Circuit (Admin Only)

**When:** Need to stop requests to external service immediately

**Warning:** This will cause all related operations to fail fast.

**Via UI:**
1. Go to `/admin/system-health`
2. Find the circuit card
3. Click "Trip" button (admin only)
4. Circuit will remain open until manually reset or timeout

**Via API:**
```bash
curl -X POST https://api.pricescout.com/api/v1/system/circuits/fandango/open \
  -H "Authorization: Bearer <token>"
```

### Reset All Circuits

**When:** After major incident recovery

```bash
curl -X POST https://api.pricescout.com/api/v1/system/circuits/reset \
  -H "Authorization: Bearer <token>"
```

---

## Repair Queue Management

### Process Queue Manually

**When:** Want to retry due repairs immediately

1. Go to `/admin/repair-queue`
2. Click "Process Queue" button
3. Review results in toast notification

### Reset a Specific Job

**When:** Theater was fixed and needs retry

1. Go to `/admin/repair-queue`
2. Find theater in queue table
3. Click reset icon (circular arrow)
4. Job will be scheduled for immediate retry

### Clear Failed Jobs

**When:** Failed theaters have been manually resolved or are no longer needed

1. Go to `/admin/repair-queue` → "Failed" tab
2. Review each failed theater
3. Ensure resolution documented
4. Click "Clear All" button
5. Confirm in dialog

### Add Theater to Queue (Manual)

**When:** Need to repair a specific theater

```bash
# Via maintenance endpoint
curl -X POST https://api.pricescout.com/api/v1/cache/maintenance \
  -H "Authorization: Bearer <token>"
```

---

## Schedule Alert Management

### Bulk Acknowledge Alerts

**When:** Many alerts reviewed at once

1. Go to `/schedule-alerts`
2. Use checkboxes to select alerts
3. Click "Acknowledge Selected"
4. Add notes if applicable
5. Confirm

### Trigger Manual Schedule Check

**When:** Need immediate schedule update

1. Go to `/schedule-alerts`
2. Click "Trigger Check" button
3. Wait for completion (may take several minutes)
4. Refresh page to see new alerts

### Filter and Export Alerts

**When:** Need report of schedule changes

1. Go to `/schedule-alerts`
2. Use filters to narrow results:
   - Status: pending/acknowledged
   - Type: new_film/removed_film/etc.
   - Date range
3. Export to CSV if needed (future feature)

---

## Maintenance Procedures

### Run Cache Maintenance

**When:** Scheduled daily or on-demand

**Via UI:**
1. Go to `/admin/repair-queue`
2. Click "Run Maintenance" button
3. Wait for completion
4. Review results

**Via API:**
```bash
curl -X POST https://api.pricescout.com/api/v1/cache/maintenance \
  -H "Authorization: Bearer <token>"
```

### View Maintenance History

1. Go to `/admin/repair-queue` → "History" tab
2. Review past maintenance runs
3. Check for patterns:
   - High failure rates may indicate site changes
   - Low repair success may indicate data issues

### Theater Cache Rebuild

**When:** Major data issues or after long downtime

```bash
# Full cache refresh (takes time)
curl -X POST https://api.pricescout.com/api/v1/cache/refresh \
  -H "Authorization: Bearer <token>" \
  -d '{"force_full_refresh": true}'
```

---

## Monitoring and Alerting

### Prometheus Queries

**Circuit Breaker Status:**
```promql
# Check if any circuit is open
circuit_breaker_state{state="open"} == 1
```

**Repair Queue Size:**
```promql
# Current queue size
repair_queue_size

# Failed jobs
repair_queue_failed
```

**Scrape Performance:**
```promql
# Average scrape duration (last hour)
rate(scrape_duration_seconds_sum[1h]) / rate(scrape_duration_seconds_count[1h])

# Failure rate
rate(scrape_theaters_failed_total[1h]) / rate(scrape_theaters_total[1h])
```

### Recommended Alerts

```yaml
groups:
  - name: pricescout
    rules:
      # Circuit breaker open
      - alert: CircuitBreakerOpen
        expr: circuit_breaker_state == 1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Circuit {{ $labels.name }} is OPEN"

      # High repair queue
      - alert: HighRepairQueue
        expr: repair_queue_size > 20
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Repair queue has {{ $value }} jobs"

      # Failed repairs need attention
      - alert: FailedRepairs
        expr: repair_queue_failed > 5
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "{{ $value }} theaters at max attempts"

      # High scrape failure rate
      - alert: HighScrapeFailureRate
        expr: rate(scrape_theaters_failed_total[1h]) / rate(scrape_theaters_total[1h]) > 0.3
        for: 15m
        labels:
          severity: critical
        annotations:
          summary: "Scrape failure rate > 30%"

      # Scheduler stale
      - alert: SchedulerStale
        expr: time() - scheduler_last_activity_timestamp > 3600
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Scheduler hasn't run in over 1 hour"
```

### Dashboard Panels

**System Health Overview:**
- Overall status (healthy/degraded/unhealthy)
- Component status grid
- Circuit breaker states

**Operations:**
- Repair queue size over time
- Maintenance run results
- Alert creation rate

**Performance:**
- Scrape duration histogram
- Failure rates by type
- API latency

---

## Troubleshooting Guide

### "Circuit Breaker Open" but External Service Working

**Possible Causes:**
1. Recent transient failures triggered threshold
2. IP rate limiting
3. Authentication issues

**Resolution:**
1. Check recent error logs
2. Verify API credentials
3. Reset circuit manually
4. Monitor for recurring failures

### High Failure Rate in Maintenance

**Possible Causes:**
1. Fandango site structure changed
2. Network issues
3. Rate limiting

**Resolution:**
1. Manually test a few theater URLs
2. Check for HTML changes in scraper
3. Wait and retry if transient
4. Escalate if persistent

### Scheduler Not Running

**Possible Causes:**
1. Celery worker crashed
2. Redis connection lost (if used)
3. Resource exhaustion

**Resolution:**
```bash
# Check worker status
systemctl status celery-worker

# Check logs
journalctl -u celery-worker -f

# Restart worker
systemctl restart celery-worker
```

### Database Locked

**Possible Causes:**
1. Long-running transaction
2. Multiple writers
3. Disk full

**Resolution:**
```bash
# Check disk space
df -h

# Check for locks
sqlite3 data/pricescout.db ".tables"

# If locked, may need to restart API
systemctl restart pricescout-api
```

### Missing Schedule Alerts

**Possible Causes:**
1. Schedule monitor not running
2. No changes detected
3. Filter hiding results

**Resolution:**
1. Check scheduler status
2. Trigger manual check
3. Clear filters on alerts page
4. Check alert configuration

---

## Emergency Contacts

| Role | Contact | When to Contact |
|------|---------|-----------------|
| On-Call Engineer | Slack #pricescout-oncall | P1/P2 incidents |
| Database Admin | database-team@company.com | Database issues |
| Security | security@company.com | Security incidents |
| Management | Slack #pricescout-mgmt | Major outages |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-01 | Initial | First release |

---

**Document Version:** 1.0.0
**Last Updated:** January 2025
**Review Frequency:** Monthly
