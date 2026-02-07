# EntTelligence Price Data Analysis

Analysis of pricing patterns, variations, and data quality findings from the EntTelligence cache data. This document captures key discoveries made during the shift from Fandango-primary to EntTelligence-primary pricing.

**Analysis date:** January 2026
**Data range:** January 13 - February 6, 2026

---

## Data Overview

| Metric | Value |
|--------|-------|
| Total price records | 3,987,647 |
| Unique theaters | 2,635 |
| Unique circuits | 177 |
| Unique films | 1,315 |
| Active EntTelligence baselines | 18,697 |
| Active Fandango baselines | 8,340 |

### Ticket Type Distribution

| Type | Records | Avg Price | Range |
|------|---------|-----------|-------|
| Adult | 2,497,217 | $12.88 | $0.94 - $402.00 |
| Child | 745,227 | $11.02 | $0.94 - $185.00 |
| Senior | 745,203 | $11.46 | $0.94 - $185.00 |

---

## Data Source Overlap

| Category | Theaters |
|----------|----------|
| EntTelligence only | 3,037 |
| Fandango only | 87 |
| Both sources | 102 |

EntTelligence provides **30x more theater coverage** than Fandango scraping. The 102 overlapping theaters were used for showtime-level price matching to derive tax rates and validate accuracy.

---

## Tax Behavior by Circuit

Showtime-level price matching (7,360 matched showtimes across 95 theaters) revealed two distinct tax models:

### Tax-Inclusive Circuits (EntTelligence price = Fandango price)

These circuits report prices that already include tax. No adjustment needed.

| Circuit | Theaters Matched | Implied Tax Rate |
|---------|-----------------|-----------------|
| AMC | 36 | 0.0% (tax-inclusive) |
| Regal | 8 | 0.0% (tax-inclusive) |
| Cinemark | 1 of 2 | 0.0% (tax-inclusive) |

### Tax-Exclusive Circuits (EntTelligence price + tax = Fandango price)

These circuits report pre-tax prices. Per-theater tax rates were derived and stored.

| Circuit | Theaters Matched | Avg Implied Rate | Rate Range |
|---------|-----------------|-----------------|------------|
| Marcus | 32 | 5.8% | 0% - 8.9% |
| Movie Tavern | 10 | 4.9% | 0% - 11.5% |
| Emagine | 1 | 8.1% | 8.1% |
| Other independents | 5 | 3.5% | 0% - 7.5% |

Tax rates are stored per-theater in `Company.settings_dict["tax_config"]["per_theater"]` and applied automatically during baseline discovery and cache-hit price assembly.

### Tax Rate Resolution Priority

1. **Per-theater rate** (most precise, derived from showtime matching)
2. **Per-state rate** (fallback for unmatched theaters)
3. **Default rate** (7.5%, last resort)

---

## Child Pricing Patterns

### Overview

Of 2,625 theaters with both Adult and Child data:

| Category | Count | Percentage |
|----------|-------|-----------|
| Real child discount (>= $1.00) | 2,010 | 76.6% |
| No child discount (< $1.00) | 602 | 22.9% |
| Child higher than adult | 13 | 0.5% |

**Average child discount:** $2.31 (where a real discount exists)

### Dine-In Circuits: Same Price for All Ages

Dine-in theater concepts charge the same ticket price regardless of age. The ticket is effectively a "seat fee" for a food-and-beverage experience.

**Affected circuits:**
- Flix Brewhouse (10 locations) - Child avg within $0.50 of Adult at all locations
- Alamo Drafthouse (44 locations) - Consistent same-price pattern chain-wide
- Studio Movie Grill (18 locations)
- iPic Entertainment (13 locations)
- Cinepolis Luxury, Cinebistro, Look Dine-In

**Handling:** These Child/Senior baselines are filtered out during discovery (see `DINE_IN_CIRCUITS` in `enttelligence_baseline_discovery.py`). This prevents comparison panels from showing misleading $0.00 differences.

**Filter result:** 850 baselines removed (from 19,547 to 18,697)

### R-Rated Films: No Child Tickets

R-rated films typically don't offer Child tickets at the POS level. EntTelligence only returns Adult and Senior prices for these showtimes. This is self-correcting -- Child baselines are built only from PG/PG-13/G films where Child tickets genuinely exist.

**Verified at:** Movie Tavern Crossroads Cinema
- PG-13 film ("Mercy"): General $12.50, Child $9.50, Senior $10.00
- R-rated film ("Send Help"): General $10.00, Senior $8.00 (no Child option)

### Understated Child Discounts

Some circuits report Child prices that are compressed vs. what Fandango shows:

| Circuit | Theaters Affected | EntTelligence Discount | Fandango Discount |
|---------|-------------------|----------------------|-------------------|
| Marcus | 40 | < $1.00 | $2-3 |
| Cinemark | 33 | < $1.00 | $2-4 |
| Galaxy | 14 | < $1.00 | varies |
| Movie Tavern | 12 | < $1.00 | $2-3 |
| Emagine | 11 | < $1.00 | $2-3 |

**Likely cause:** EntTelligence pulls from a different POS/API layer that may not differentiate Child pricing the same way the consumer-facing ticketing does.

**Current handling:** These baselines are kept but may show smaller discounts than Fandango. Future improvement could prefer Fandango's child baseline when both sources are available.

---

## Discount Day Patterns

Several circuits run deep-discount days (typically Tuesdays). The baseline discovery service detects and excludes these to prevent dragging down standard baselines.

### Marcus Theatres: $5 Tuesdays

| Day | Avg Adult Price | Sample |
|-----|----------------|--------|
| Mon | $12.52 | 167 |
| **Tue** | **$7.50** | **287** |
| Wed | $12.96 | 202 |
| Thu | $12.89 | 118 |
| Fri | $12.66 | 237 |
| Sat | $12.74 | 215 |
| Sun | $12.51 | 186 |

Tuesday is ~40% below the standard rate. This pattern is consistent across Marcus locations.

### Movie Tavern: Discount Tuesdays

| Day | Avg Adult Price |
|-----|----------------|
| Mon | $15.16 |
| **Tue** | **$7.94** |
| Wed | $15.60 |

Tuesday is ~48% below the standard rate at Movie Tavern locations.

### Emagine: No Discount Days

| Day | Avg Adult Price |
|-----|----------------|
| Mon-Sun | $11.79 - $11.99 |

Emagine shows consistent pricing across all days of the week. No discount day pattern detected.

**Detection method:** The `_detect_discount_days()` method compares each day's median to the upper 5-of-7 day reference. Days >30% below are flagged and excluded from baseline calculation.

---

## Circuit Pricing Overview (Adult, Top 20)

| Circuit | Theaters | Avg Adult Price |
|---------|----------|----------------|
| Ipic Entertainment | 13 | $19.17 |
| Regal Entertainment Group | 407 | $15.07 |
| Cinepolis - USA | 26 | $15.22 |
| CMX Cinemas | 23 | $14.40 |
| Landmark Cinemas | 34 | $14.36 |
| Galaxy Theatres | 15 | $14.22 |
| AMC Entertainment Inc | 532 | $14.12 |
| National Amusements - US | 14 | $14.30 |
| Cineplex Entertainment | 154 | $13.89 |
| Landmark Theatres | 26 | $13.90 |
| Alamo Drafthouse | 44 | $13.26 |
| Malco Theatres | 31 | $12.63 |
| Angelika Cinemas | 8 | $15.22 |
| Harkins Theatres | 31 | $12.14 |
| Emagine Entertainment | 27 | $12.05 |
| B & B Theatres | 49 | $11.91 |
| Studio Movie Grill | 18 | $11.83 |
| Marcus Theatres Corporation | 78 | $11.55 |
| Flix Brewhouse | 10 | $11.42 |
| Cinemark Theatres | 303 | $10.93 |

---

## Baseline Alignment: EntTelligence vs. Fandango

After applying per-theater tax rates, comparison of matched baselines:

| Match Quality | Count | Percentage |
|--------------|-------|-----------|
| Exact (< $0.05) | 78 | 15.0% |
| Close ($0.05 - $0.50) | 157 | 30.2% |
| Moderate ($0.50 - $1.50) | 229 | 44.0% |
| Divergent (> $1.50) | 56 | 10.8% |

- **Average difference:** $0.00 (perfectly centered -- no systematic bias)
- **Average absolute difference:** $0.67

Divergent baselines are primarily from:
- Child/Senior ticket type compression (see above)
- Premium format pricing differences
- Discount day handling differences between sources

---

## Event Cinema Exclusion

Event cinema (Fathom Events, Met Opera, concerts, etc.) uses distributor-set pricing unrelated to theater base rates. These are excluded from baseline calculations.

**Detection keywords:** Fathom, Met Opera, NT Live, Concert, TCM, Anniversary, Fan Event, WWE, Crunchyroll, and others.

See `EVENT_CINEMA_KEYWORDS` in `enttelligence_baseline_discovery.py` for the full list.

---

## Implementation Files

| File | Purpose |
|------|---------|
| `app/enttelligence_baseline_discovery.py` | Baseline discovery with dine-in filter, discount day detection, event cinema exclusion |
| `api/services/tax_estimation.py` | Per-theater tax rate storage and application |
| `api/services/enttelligence_cache_service.py` | EntTelligence data sync and cache lookup |
| `api/routers/scrapes.py` | Scrape endpoints with cache-hit tax application |
