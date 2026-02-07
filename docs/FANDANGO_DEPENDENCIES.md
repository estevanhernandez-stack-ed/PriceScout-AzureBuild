# Fandango Dependencies & Optimization Strategy

## Key Takeaways

- **EntTelligence** is the primary pricing source (2,700+ theaters, Adult/Child/Senior, automated daily sync). It provides overnight bulk data but **updates showtimes only once per day**.
- **Fandango** remains essential for **real-time schedules** (daily lineups, competitor monitoring, operating hours) and **PLF format identification**. It is the only source that reflects same-day schedule changes.
- Price scraping reduced **~80%** via EntTelligence cache -- only cache misses hit Fandango.
- Theater discovery reduced **~95%** via local cache -- Fandango only needed for new markets.
- Baseline discovery requires **zero live Fandango calls** -- runs against stored historical data.
- **PLF detection by price inference** from EntTelligence is feasible but not yet implemented. Fandango remains the confirmed PLF source for now.
- Verification is **manual only** -- no automated scheduling yet.

---

PriceScout was originally built entirely on Fandango scraping. With the integration of EntTelligence as a data provider, we have significantly reduced our reliance on Fandango while retaining it for specific capabilities only Fandango can provide. This document catalogs every remaining Fandango dependency, how each has been optimized, and the overall strategy.

---

## Architecture Overview

PriceScout now operates on a **dual-source model**:

| Source | Strengths | Limitations |
|--------|-----------|-------------|
| **EntTelligence** (API) | Breadth (2,700+ theaters), all ticket types (Adult/Child/Senior), fast API, no browser needed | Prices are tax-exclusive, format vocabulary limited to 2D/3D/70MM/35MM, cannot identify PLF, **updates once per day** |
| **Fandango** (scraping) | Consumer-facing prices (tax-inclusive), identifies Premium Large Format, **real-time showtime data** reflecting same-day schedule changes | Requires browser automation (Playwright), slower, rate-limited, only returns selected ticket types per page |

### Data Freshness: A Critical Distinction

EntTelligence is believed to refresh its showtime/pricing data **once per day** (pending vendor confirmation). This means:

- **EntTelligence data reflects the schedule as of its last overnight crawl.** If a theater manager adds, removes, or changes showtimes during the day, EntTelligence will not reflect those changes until the next refresh cycle.
- **Fandango data is real-time.** When PriceScout scrapes a Fandango theater page, it sees the current live schedule -- including any same-day changes by theater management.

This distinction is the primary reason Fandango remains essential for schedule-sensitive workflows like daily lineup reports, operating hours paperwork, and competitor showtime monitoring. EntTelligence is the overnight bulk pricing source; Fandango is the intraday real-time source.

| Use Case | Required Freshness | Best Source |
|----------|-------------------|-------------|
| Price baselines & surge detection | Overnight is sufficient | EntTelligence |
| Daily pricing reports | Overnight is sufficient | EntTelligence (with tax estimation) |
| Daily lineup / schedule printing | Must reflect same-day changes | **Fandango** |
| Competitor showtime monitoring | Must reflect same-day changes | **Fandango** |
| Operating hours for staff scheduling | Must reflect same-day changes | **Fandango** |
| PLF identification | N/A (format labeling, not timing) | **Fandango** (or price-based inference from EntTelligence) |
| Discount day detection | Historical pattern analysis | Either source |

---

## Remaining Fandango Dependencies

### 1. Showtime Discovery (fetch-showtimes)

**What it does:** Fetches all showtimes for selected theaters and dates from Fandango theater pages.

**Where:** `app/scraper.py` (`_get_movies_from_theater_page`), exposed via `POST /scrapes/fetch-showtimes`

**Why still needed:** This is the first step of every Market Mode workflow and is **the most critical Fandango dependency**. The user needs to see what films and showtimes are playing to select which ones to scrape prices for. While EntTelligence does contain showtime data in its cache, it only updates once per day. Theater managers routinely make same-day schedule changes (adding late shows, cancelling matinees, adjusting times), and those changes must be reflected immediately in:

- **Daily lineup reports** -- used to print paperwork with correct times
- **Competitor showtime monitoring** -- tracking when competitors post new schedules
- **Operating hours derivation** -- earliest/latest showtimes determine open/close

EntTelligence's overnight data is sufficient for pricing analysis but **not reliable enough for schedule accuracy**. Fandango provides the real-time, consumer-facing schedule.

**Optimization applied:** After showtime fetch, an automatic **showtime verification** (`POST /scrapes/compare-showtimes`) runs in the background. This cross-references the fetched Fandango showtimes against the EntTelligence cache, showing the user how many showtimes already have cached pricing. This lets users choose EntTelligence mode and skip Fandango price scraping for most showtimes -- even though the showtime listing itself came from Fandango.

**Frequency:** Once per Market Mode session (before price scraping begins). Also triggered by daily lineup and operating hours workflows.

---

### 2. Price Scraping (scrape-details)

**What it does:** Navigates to individual Fandango ticket pages and extracts ticket type names, prices, and seating capacity from the Commerce JSON embedded in the page.

**Where:** `app/scraper.py` (`_get_prices_and_capacity`, `scrape_details`), triggered via `POST /scrapes/trigger`

**Why still needed:** Fandango prices are the ground truth -- they are tax-inclusive, consumer-facing prices with PLF identification. EntTelligence prices are wholesale/tax-exclusive and require tax estimation.

**Optimization applied -- Three Scrape Modes:**

| Mode | Fandango Usage | When to Use |
|------|---------------|-------------|
| **EntTelligence** (default) | Only for cache misses | Day-to-day pricing. Pre-checks EntTelligence cache; only scrapes Fandango for showtimes not found in cache. Typically eliminates 60-80% of Fandango page visits. |
| **Fresh Fandango** | Every showtime | Monthly PLF refresh, new markets, or when cache data is stale. Scrapes Fandango for every selected showtime regardless of cache. |
| **Verify Prices** | Every showtime | Spot-check validation. Scrapes Fandango for every showtime, then compares each price against EntTelligence + tax estimation to validate accuracy. |

**EntTelligence mode flow (default):**

1. For each selected showtime, build a cache lookup key: `date|theater|film|time`
2. Query `enttelligence_price_cache` for all ticket types matching that key (max age: 6 hours)
3. **Cache hit:** Use cached price directly (with tax estimation applied), mark source as `enttelligence_cache`
4. **Cache miss:** Add to `showings_to_scrape` list, scrape via Fandango, mark source as `fandango`

This means in a typical market scrape of 200 showtimes, if 160 are cached, only 40 Fandango page visits happen instead of 200.

---

### 3. Theater Discovery & Search

**What it does:** Finds theater names and Fandango URLs by searching Fandango's site via ZIP code pages or name search.

**Where:** `app/scraper.py` (`_get_theaters_from_zip_page`, `live_search_by_name`, `discover_theater_url`), exposed via `GET /scrapes/search-theaters/fandango`

**Why still needed:** Theater URLs are Fandango-specific (`/amc-northpark-15-AATZH/theater-page`) and required for showtime/price scraping. EntTelligence identifies theaters by name but doesn't provide Fandango URLs.

**Optimization applied:** A local **theater cache** (`CACHE_FILE`) stores previously discovered theater names and URLs. The `GET /scrapes/search-theaters/cache` endpoint searches this cache first, avoiding live Fandango lookups for known theaters. The cache is rebuilt only when adding new markets.

**Frequency:** Rare -- only when onboarding new theaters or markets. Cached theaters persist indefinitely.

---

### 4. Operating Hours Calculation

**What it does:** For a date range, scrapes all showtimes from Fandango and derives operating hours (earliest showtime = open, latest = close) per theater per day. Compares week-over-week to detect schedule changes.

**Where:** `POST /scrapes/operating-hours` in `api/routers/scrapes.py`, uses `app/scraper.py` (`get_all_showings_for_theaters`)

**Why still needed:** Operating hours are used to generate printed paperwork for theater staff scheduling. When a manager changes the schedule during the day (adds a late show, cancels an early matinee), the operating hours must update immediately. EntTelligence could theoretically provide operating hours via its cached showtimes, but since it only refreshes once per day, it would miss intraday schedule changes. For a report that drives staffing decisions and gets printed, stale data is unacceptable.

**Optimization applied:** Results are saved to the `operating_hours` database table with a high-water-mark strategy (never overwrite with shorter hours). Subsequent views read from database, not live scrape. Week-over-week comparison detects changes without re-scraping previous weeks.

**Frequency:** Weekly per market (typically automated).

---

### 5. Fandango Baseline Discovery

**What it does:** Analyzes historical Fandango scrape data (Price + Showing tables) to establish price baselines per theater/format/ticket-type/daypart. Uses 25th percentile pricing as the baseline (conservative).

**Where:** `app/fandango_baseline_discovery.py`, triggered via `POST /price-baselines/fandango/discover` and `POST /price-baselines/refresh`

**Why still needed:** Fandango is the **only source for PLF (Premium Large Format) baselines**. EntTelligence labels all PLF showtimes as `2D`, making it impossible to distinguish standard from premium pricing. Only Fandango correctly labels formats as `Premium Format`, `IMAX`, `Dolby Cinema`, etc. Fandango baselines are also tax-inclusive, matching consumer reality.

**Optimization applied:** Discovery runs against already-stored historical data -- it does NOT trigger a live Fandango scrape. It queries the `prices` and `showings` tables where previous Fandango scrapes were saved. The `Standard` format label is normalized to `2D` during discovery to align with EntTelligence convention.

**Frequency:** On-demand or monthly. The baseline refresh button on the Baselines page triggers this.

**Future optimization -- PLF inference by price:** Because EntTelligence provides accurate pricing even though it mislabels PLF as `2D`, we can potentially infer PLF showtimes without Fandango. If a showtime's EntTelligence price for Adult Prime significantly exceeds the theater's established 2D baseline for the same ticket type and daypart (e.g., 20-30% premium), it is likely a PLF showing. This approach would allow PLF detection from EntTelligence data alone, with periodic Fandango scrapes to validate the inference threshold and confirm format labels. Not yet implemented.

---

### 6. Price Verification Mode

**What it does:** Scrapes Fandango for selected showtimes (never uses cache), then compares each Fandango price against the EntTelligence cache + estimated tax. Reports matches, mismatches, and missing data.

**Where:** `POST /scrapes/verify-prices` in `api/routers/scrapes.py` (`_run_verification_task`)

**Why still needed:** This is the trust-but-verify mechanism. Since EntTelligence prices require tax estimation to be comparable, periodic verification ensures the tax rates and EntTelligence data are accurate.

**Optimization applied:** Verification is an explicit user action (not automatic). It scrapes Fandango intentionally as the ground truth to validate, so there is no cache bypass to optimize -- the whole point is live comparison.

**Current frequency:** Entirely manual and ad-hoc. The user must select "Verify Prices" mode in the Market Mode UI and run it. There is no scheduled or automated verification. Recommended cadence is monthly per market, but this is not enforced.

**Future optimization:** A Celery Beat task could rotate through markets on a weekly schedule, automatically verifying one market at a time and surfacing mismatches as alerts. Not yet implemented.

---

### 7. Film Metadata Discovery

**What it does:** Searches Fandango for film details (runtime, rating, genre, poster) as a fallback when OMDb doesn't have the data.

**Where:** `app/scraper.py` (`search_fandango_for_film_url`, `get_film_details_from_fandango_url`, `get_coming_soon_films`, `discover_films_from_main_page`)

**Why still needed:** New releases may not appear in OMDb immediately. Fandango has same-day metadata for all films it sells tickets for.

**Optimization applied:** OMDb is the primary metadata source. Fandango is only queried when OMDb returns incomplete data (e.g., missing runtime). Film metadata is cached in the database after first retrieval.

**Frequency:** Rare -- only for brand-new releases not yet in OMDb.

---

### 8. Zero-Showtime Detection

**What it does:** Identifies theaters that return zero showtimes from Fandango, which may indicate the theater has left the Fandango platform or is temporarily closed.

**Where:** `POST /scrapes/zero-showtime-analysis` in `api/routers/scrapes.py`

**Why still needed:** Theaters occasionally stop listing on Fandango (switch to independent ticketing, temporary closures, etc.). Detecting this avoids wasted scrape attempts and alerts users to coverage gaps.

**Optimization applied:** Analysis runs against the `operating_hours` database table, not live scraping. It counts consecutive zero-showtime entries and classifies theaters as `normal`, `warning` (2 consecutive zeros), or `likely_off_fandango` (3+ zeros).

**Frequency:** Runs on existing data, no Fandango calls.

---

## Summary: What EntTelligence Replaced vs. What It Can't

### Replaced by EntTelligence

| Capability | Before | After |
|-----------|--------|-------|
| **Daily pricing data** | Full Fandango scrape for every showtime | EntTelligence cache provides 60-80% of prices; Fandango only for misses |
| **Multi-ticket-type pricing** | Had to click through Fandango UI per showtime | EntTelligence returns Adult/Child/Senior in one API call |
| **Baseline discovery (2D/3D)** | Fandango-only | EntTelligence baseline discovery covers 2D and 3D formats across 2,700+ theaters |
| **Discount day detection** | Fandango historical analysis | EntTelligence price-based discovery detects discount patterns automatically |
| **Theater coverage breadth** | Limited to manually cached Fandango URLs | EntTelligence covers full circuits without URL discovery |

### Still Requires Fandango

| Capability | Why EntTelligence Can't Substitute |
|-----------|-----------------------------------|
| **Real-time showtime discovery** | EntTelligence updates once/day; Fandango reflects same-day schedule changes by managers |
| **Daily lineup reports** | Must show current schedule for printing; stale overnight data is unacceptable |
| **Competitor schedule monitoring** | Need to see when competitors post new times, not yesterday's snapshot |
| **Operating hours** | Drives staff scheduling paperwork; must reflect intraday changes |
| **PLF identification** | EntTelligence labels all PLF as `2D`; only Fandango distinguishes Premium Format, IMAX, Dolby (though price-based inference from EntTelligence is feasible -- see section 5) |
| **PLF baselines** | Without format identification, can't build PLF-specific baselines from EntTelligence |
| **Tax-inclusive prices** | EntTelligence prices are tax-exclusive; Fandango prices match what consumers pay |
| **Seating capacity** | ~~Only available from Fandango Commerce JSON~~ **CORRECTION: EntTelligence provides capacity, available, and blocked seat counts. This is the primary source for presale/demand tracking.** |
| **Price verification** | Fandango is the ground truth for validating EntTelligence + tax accuracy |
| **Theater URL discovery** | Fandango-specific URLs needed for scraping (supplemented by local cache) |

---

## Fandango Call Reduction Estimate

| Workflow | Calls Before EntTelligence | Calls After | Reduction |
|----------|---------------------------|-------------|-----------|
| Market scrape (200 showtimes) | ~200 ticket page visits | ~40 (cache misses only) | **~80%** |
| Theater discovery | Every session | Once, then cached | **~95%** |
| Baseline discovery | Required live scrapes | Uses stored historical data | **100% (no live calls)** |
| Operating hours | Weekly live scrape | Weekly, results cached in DB | Same frequency, but DB lookup for views |
| Film metadata | Every new film | OMDb primary, Fandango fallback | **~90%** |

The primary remaining Fandango bottleneck is **showtime discovery** (Step 1 of Market Mode), which still requires a live Fandango page visit per theater per date. This is not a limitation of PriceScout's architecture -- it is a deliberate design choice. EntTelligence has showtime data in its cache, but it only refreshes once per day. For schedule-sensitive workflows (daily lineups, competitor monitoring, operating hours), same-day accuracy is required and only Fandango provides it.

---

## EntTelligence Sync Automation

PriceScout automatically keeps the EntTelligence cache fresh through two mechanisms:

1. **Startup auto-sync** (`api/main.py`): When the API server starts, a background thread checks cache freshness. If stale (<100 fresh entries), it syncs today + 7 days from EntTelligence. Non-blocking -- the API is available immediately.

2. **Celery Beat daily sync** (`app/celery_app.py`): If Celery is running, `sync-enttelligence-daily` fires at 4 AM and refreshes the cache. The schedule monitor also runs every 6 hours to detect showtime changes against stored baselines.

3. **On-demand sync** (`POST /api/v1/enttelligence/sync`): Users or automated systems can trigger a manual sync for specific date ranges or circuits.

The cache has a 6-hour TTL. Between syncs, lookups return cached data. Cache misses during a Market Mode scrape fall through to Fandango automatically.

**Important:** These syncs pull from EntTelligence's API, which itself only refreshes its data approximately once per day. Syncing more frequently than daily from our side does not yield fresher data -- it just ensures our local cache stays populated.
