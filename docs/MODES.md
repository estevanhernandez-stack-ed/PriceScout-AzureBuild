# PriceScout Operational Modes

This document describes all operational modes in PriceScout, their purposes, workflows, and data collection patterns.

---

## Overview

PriceScout operates in multiple modes, each designed for specific data collection scenarios:

| Mode | Purpose | Trigger |
|------|---------|---------|
| Market Mode | Competitive pricing across a market | Manual / Scheduled |
| CompSnipe Mode | Targeted competitor monitoring | Manual |
| Operating Hours Mode | Theater schedule collection | Manual |
| Poster Board Mode | Currently showing films | Manual |
| Daily Lineup Mode | Full daily showtime schedule | Manual |
| Circuit Benchmarks Mode | Own circuit pricing analysis | Manual / Scheduled |
| Presale Trajectory Mode | Presale tracking over time | Scheduled |
| Analysis Mode | Data analysis and reporting | Manual |

---

## Mode Details

### 1. Market Mode

**Purpose:** Collect competitive pricing data across all theaters in a geographic market.

**Use Case:** Understanding market positioning, identifying pricing opportunities, competitive intelligence.

**Workflow:**
1. Select target market (e.g., "Dallas", "Los Angeles")
2. System loads all theaters in that market from configuration
3. For each theater:
   - Fetch all showtimes for specified date range
   - Navigate to each showtime's ticket purchase page
   - Extract all ticket types and prices
4. Save results to database with scrape run context

**Data Collected:**
- Theater name and location
- Film titles and showtimes
- All ticket types (Adult, Child, Senior, Matinee, etc.)
- Formats (Standard, IMAX, Dolby, 3D, etc.)
- Prices for each ticket type/format combination

**Key Files:**
- [scraper.py](../app/scraper.py) - `get_all_showings_for_theaters()`, `scrape_details()`
- [scrapes.py](../api/routers/scrapes.py) - `run_scrape_job()`
- [markets.py](../api/routers/markets.py) - Market configuration

**Scrape Flow:**
```
Market Selected → Load Theaters → For Each Theater:
  → get_all_showings_for_theaters() → Build showtime selection
  → scrape_details() → Extract prices → Save to DB
```

---

### 2. CompSnipe Mode

**Purpose:** Targeted scraping of specific competitor theaters for quick competitive checks.

**Use Case:** Quick price check on specific competitors, ad-hoc competitive analysis.

**Workflow:**
1. Select specific theater(s) to monitor
2. Optionally filter by specific films or dates
3. Scrape only selected theaters
4. Compare against own pricing

**Data Collected:**
- Same as Market Mode but for selected theaters only
- Optimized for speed with targeted selection

**Key Differences from Market Mode:**
- Selective theater targeting vs. full market
- Often paired with specific film filtering
- Used for responsive competitive checks

---

### 3. Operating Hours Mode

**Purpose:** Collect theater operating schedules and hours.

**Use Case:** Understanding competitor operating patterns, staffing analysis.

**Workflow:**
1. Navigate to theater information pages
2. Extract operating hours by day of week
3. Identify special hours (holidays, events)

**Data Collected:**
- Daily operating hours
- Box office hours
- Special event schedules

---

### 4. Poster Board Mode

**Purpose:** Capture currently showing films at theaters.

**Use Case:** Film availability tracking, release monitoring.

**Workflow:**
1. Navigate to theater's main showtime page
2. Extract list of all films currently showing
3. Capture basic film metadata (title, format availability)

**Data Collected:**
- Film titles
- Available formats per film
- Theater-film availability matrix

---

### 5. Daily Lineup Mode

**Purpose:** Comprehensive daily showtime schedule collection.

**Use Case:** Schedule analysis, showtime pattern recognition.

**Workflow:**
1. Select date range
2. For each theater, fetch complete showtime grid
3. Capture all showtimes without navigating to pricing

**Data Collected:**
- Complete showtime schedule
- Auditorium assignments (where available)
- Format schedules

**Key Difference:** Collects showtimes only, not prices (faster execution).

---

### 6. Circuit Benchmarks Mode

**Purpose:** Analyze pricing across own theater circuit for consistency and optimization.

**Use Case:** Internal pricing audits, format premium analysis, regional consistency checks.

**Workflow:**
1. Load own circuit theaters from configuration
2. Scrape pricing across all own locations
3. Generate benchmark analysis:
   - Format premiums (IMAX vs Standard, etc.)
   - Regional price variations
   - Ticket type differentials

**Data Collected:**
- Own circuit pricing data
- Format premium calculations
- Regional price comparisons

**Key Files:**
- [price_alerts.py](../api/routers/price_alerts.py) - Benchmark endpoints
- [baseline_discovery.py](../app/baseline_discovery.py) - Price pattern analysis

**API Endpoints:**
```
GET /api/v1/circuit-benchmarks
GET /api/v1/circuit-benchmarks/format-premiums
GET /api/v1/circuit-benchmarks/regional-analysis
```

---

### 7. Presale Trajectory Mode

**Purpose:** Track presale performance over time for upcoming releases.

**Use Case:** Demand forecasting, marketing effectiveness, release performance prediction.

**Workflow:**
1. Identify films in presale period
2. Schedule periodic scrapes (e.g., daily)
3. Track:
   - Available showtimes over time
   - Sold-out showtime progression
   - Price changes during presale

**Data Collected:**
- Presale availability snapshots
- Sellout progression
- Price trajectory during presale period

**Key Files:**
- [price_alerts.py](../api/routers/price_alerts.py) - Presale tracking endpoints

**API Endpoints:**
```
GET /api/v1/presales
GET /api/v1/presales/{film}/trajectory
```

---

### 8. Analysis Mode

**Purpose:** Generate insights and reports from collected data.

**Sub-Modes:**

#### Price Change Analysis
- Compare prices across scrapes
- Identify significant changes
- Generate alerts for threshold breaches

#### Surge Pricing Detection
- Compare against baselines
- Identify premium vs surge pricing
- Alert on unexpected price increases

#### Market Position Analysis
- Calculate market averages
- Determine competitive position
- Generate recommendations

**Key Files:**
- [alert_service.py](../app/alert_service.py) - Price change detection
- [baseline_discovery.py](../app/baseline_discovery.py) - Surge analysis
- [reports.py](../api/routers/reports.py) - Report generation

---

## Common Infrastructure

### Scraper Core

All scraping modes share the common `Scraper` class infrastructure:

```python
from app.scraper import Scraper

scout = Scraper(headless=True, devtools=False)

# Get showtimes for theaters
showings = await scout.get_all_showings_for_theaters(theaters, date)

# Scrape detailed pricing
results, errors = await scout.scrape_details(theaters, selected_showtimes)
```

### Database Integration

All modes save data through the database adapter:

```python
from app import db_adapter as database

# Create scrape run
run_id = database.create_scrape_run(mode, context)

# Save price data
database.save_prices(run_id, prices_df)
```

### Automatic Film Enrichment

When showings are saved via `upsert_showings()`, any newly discovered films are **automatically enriched** with OMDB metadata in the background:

```python
# Automatically triggered when saving showings
database.upsert_showings(all_showings, play_date, enrich_films=True)

# Or manually enrich films
from app.db_adapter import enrich_new_films
result = enrich_new_films(['Film Title 1', 'Film Title 2'])
# Returns: {'enriched': 2, 'failed': 0, 'skipped': 0}
```

**Enrichment includes:**
- IMDB ID, genre, MPAA rating
- Director, actors, plot summary
- Poster URL, Metascore, IMDB rating
- Release date, runtime, box office data

Films that can't be matched are logged to `UnmatchedFilm` table for manual review.

### Post-Scrape Hooks

After each scrape, the system automatically:
1. Generates price change alerts
2. Checks for surge pricing
3. Dispatches notifications (webhook/email)

```python
# In scrapes.py after save_prices()
from app.alert_service import generate_alerts_for_scrape
from app.notification_service import dispatch_alerts_sync

alerts = generate_alerts_for_scrape(company_id, run_id, df)
if alerts:
    dispatch_alerts_sync(company_id, alerts)
```

---

## Mode Selection Flow

```
User Request
    │
    ├─► Market Mode ────────► Full market competitive analysis
    │
    ├─► CompSnipe Mode ─────► Targeted competitor check
    │
    ├─► Operating Hours ────► Schedule collection
    │
    ├─► Poster Board ───────► Film availability
    │
    ├─► Daily Lineup ───────► Showtime schedules (no prices)
    │
    ├─► Circuit Benchmarks ─► Own circuit analysis
    │
    ├─► Presale Trajectory ─► Presale tracking
    │
    └─► Analysis Mode ──────► Reports and insights
```

---

## Data Flow Summary

| Mode | Input | Scrape Target | Output |
|------|-------|---------------|--------|
| Market | Market name | All market theaters | Prices DB |
| CompSnipe | Theater selection | Selected theaters | Prices DB |
| Operating Hours | Theater list | Theater info pages | Hours DB |
| Poster Board | Theater list | Main pages | Films DB |
| Daily Lineup | Date range | Showtime pages | Showtimes DB |
| Circuit Benchmarks | Circuit config | Own theaters | Benchmarks |
| Presale Trajectory | Film + dates | Presale pages | Trajectory DB |
| Analysis | Scrape data | N/A (DB queries) | Reports |

---

## Configuration

Modes are configured via:

1. **Market Configuration** - `data/{Company}/markets.json`
2. **Theater Lists** - `data/{Company}/theaters.json`
3. **Company Settings** - `app/config.py`
4. **Alert Thresholds** - `AlertConfiguration` table

---

## API Trigger Endpoints

| Mode | Endpoint |
|------|----------|
| Market/CompSnipe | `POST /api/v1/scrapes/trigger` |
| Scrape Status | `GET /api/v1/scrapes/{job_id}/status` |
| Circuit Benchmarks | `GET /api/v1/circuit-benchmarks` |
| Presales | `GET /api/v1/presales` |
| Analysis | `GET /api/v1/reports/*` |
