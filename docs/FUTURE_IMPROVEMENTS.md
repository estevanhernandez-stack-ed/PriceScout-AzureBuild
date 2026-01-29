# PriceScout Future Improvements

Tracked improvements and technical debt items for future development.

---

## API & Backend

### Baseline Discovery Parameter Naming

**Priority:** Low
**Added:** 2026-01-24

The `lookback_days` parameter in baseline discovery endpoints is misleading:

- Current behavior: Filters by `Price.created_at` (when price was scraped)
- Name implies: Looking at past movie dates

**Affected endpoints:**

- `/fandango-baselines/discover`
- `/enttelligence-baselines/discover`
- `/price-baselines/discover`

**Recommendation:** Rename to `scrape_age_days` or `data_freshness_days` to clarify it filters by when data was collected, not when movies are showing.

**Location:** [fandango_baseline_discovery.py](../app/fandango_baseline_discovery.py) line 116

---

## Frontend

### Operations Dashboard - Weather/Closure Monitoring

**Priority:** Medium
**Added:** 2026-01-24

A dedicated dashboard for monitoring theater operations during weather events or other disruptions.

**Use Case:** During severe weather, operators need to quickly see which theaters are:

- Posting fewer showtimes than normal (partial closure)
- Not posting any showtimes (full closure)
- Operating normally

**Features:**

- Table view: Theater | Showtimes Today | vs Yesterday | vs Normal | Status
- Visual indicators: ✅ Normal, ⚠️ Reduced, 🔴 Closed
- Filter by director/market
- Historical comparison (vs baseline average)
- Auto-refresh capability for real-time monitoring

**Data Requirements:**

- Showtime counts per theater per day (already captured in `showings` table)
- Baseline showtime counts for "normal" operations (needs to be calculated/stored)

**Related:** Depends on showtime count logging during scrapes (see Database section)

---

## Database

### Theater Showtime Count Snapshots (for Operations Dashboard)

**Priority:** Medium
**Added:** 2026-01-24
**Status:** Data already captured ✅

The `showings` table already captures per-theater, per-day showtime data during Fandango scrapes.

**Current query capability:**

```sql
SELECT theater_name, play_date,
       COUNT(*) as showtime_count,
       COUNT(DISTINCT film_title) as film_count
FROM showings
WHERE play_date >= '2026-01-23'
GROUP BY theater_name, play_date
```

**Optional enhancement:** Create a lightweight `theater_daily_stats` table for faster queries:

```sql
CREATE TABLE theater_daily_stats (
    stat_id INTEGER PRIMARY KEY,
    theater_name TEXT NOT NULL,
    play_date DATE NOT NULL,
    captured_at DATETIME NOT NULL,
    showtime_count INTEGER,
    film_count INTEGER,
    source TEXT DEFAULT 'fandango',
    UNIQUE(theater_name, play_date, captured_at)
);
```

This would allow tracking multiple snapshots per day (to see when theaters start removing showtimes during weather events).

---

## Documentation

No items yet.
