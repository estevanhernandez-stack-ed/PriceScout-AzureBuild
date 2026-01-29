# PriceScout Price Baselines Mode Redesign

**Status:** Planning
**Created:** 2026-01-25
**Last Updated:** 2026-01-25

## Overview

Redesign the Price Baselines mode to support surge detection on NEW movie postings by building company-specific pricing profiles that capture each circuit's unique structure.

**Core Insight:** Surge pricing in theaters isn't dynamic like Uber - it's applied when new movies are posted with higher-than-normal prices based on expected demand. We need baselines that let us detect "this new Avatar showing is $2 above normal for this theater/ticket-type/time."

---

## User Requirements Summary

1. **Ticket-type based baselines** - Daypart info comes FROM the ticket type itself (e.g., "Matinee" ticket = all ages same price)
2. **Company profiles** - Discover each circuit's unique pricing structure for apples-to-apples comparison
3. **Coverage gaps visibility** - See what data is missing (PLF formats, certain days, etc.)
4. **Granular data first, averages later** - Verify specific baselines before aggregating
5. **Discount day detection** - Identify "$5 Tuesdays" and similar programs
6. **Don't fully trust EntTelligence yet** - Compare against Fandango baselines first

---

## Phase 1: Company Profiles Discovery

### 1.1 New Data Model: CompanyProfile

Create a new table to store discovered pricing characteristics per company/circuit:

```sql
CREATE TABLE company_profiles (
    profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL UNIQUE,
    discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Ticket type patterns discovered
    ticket_types JSON,           -- ["Adult", "Child", "Senior", "Matinee", "Early Bird", "Twilight"]
    daypart_scheme TEXT,         -- "time-based" | "ticket-type-based" | "hybrid"
    daypart_boundaries JSON,     -- {"Matinee": "before 4pm", "Prime": "4pm-8pm", ...}

    -- Pricing structure
    has_flat_matinee BOOLEAN,    -- True if Matinee = all ages same price
    has_discount_days BOOLEAN,
    discount_days JSON,          -- [{"day": "Tuesday", "price": 5.00, "program": "$5 Tuesdays"}]
    premium_formats JSON,        -- ["IMAX", "Dolby Cinema", "ScreenX", "4DX"]
    premium_surcharges JSON,     -- {"IMAX": 5.00, "Dolby": 4.00}

    -- Data quality
    theater_count INTEGER,
    sample_count INTEGER,
    date_range_start DATE,
    date_range_end DATE,
    confidence_score REAL        -- 0-1 based on sample size and consistency
);
```

### 1.2 Profile Discovery Algorithm

For each company, analyze their price data to discover:

1. **Ticket Type Inventory** - Extract all unique ticket_type values, categorize as age-based vs daypart-based
2. **Daypart Scheme Detection** - Determine if "ticket-type-based" (matinee = flat price) vs "time-based" (matinee has age splits)
3. **Discount Day Detection** - Use existing algorithm (≤3% variance + ≥15% below average)
4. **Premium Format Analysis** - List formats beyond Standard with calculated surcharges

### 1.3 API Endpoint

```
POST /company-profiles/discover
GET /company-profiles/{company_name}
GET /company-profiles/list
```

### 1.4 Tasks

- [ ] Create `company_profiles` table migration
- [ ] Build `CompanyProfileDiscoveryService` class in `app/company_profile_discovery.py`
- [ ] Add `/company-profiles/discover` endpoint in `api/routers/company_profiles.py`
- [ ] Add CompanyProfile model to `app/db_models.py`
- [ ] Create React Query hooks in `frontend/src/hooks/api/useCompanyProfiles.ts`

---

## Phase 2: Granular Baselines View

### 2.1 New "Baseline Details" Tab

Replace current aggregated view with granular baseline browser showing ALL individual baselines:

| Ticket Type | Format   | Day | Samples | Price  | Variance |
|-------------|----------|-----|---------|--------|----------|
| Matinee     | Standard | Mon | 45      | $9.50  | 2.1%     |
| Matinee     | Standard | Tue | 42      | $5.00  | 0.0% 🏷️  |
| Adult       | Standard | Mon | 52      | $13.75 | 3.2%     |
| Adult       | IMAX     | Mon | 28      | $18.50 | 2.8%     |

🏷️ = Detected discount day (flat pricing)

**Features:**

- Sortable/filterable table
- Discount day badges with program names
- Export to CSV for review
- Inline editing to override baselines

### 2.2 Coverage Gaps Panel

Show what's missing for selected theater(s):

```
⚠️ Missing Days: Saturday, Sunday (0 samples)
⚠️ Missing Formats: 4DX, ScreenX (no data)
⚠️ Low Samples: IMAX Child (only 3 samples, need 10+)
✅ Good Coverage: Standard Adult/Child/Senior (50+ samples each)
```

### 2.3 Tasks

- [ ] Create `frontend/src/pages/BaselineDetailsPage.tsx`
- [ ] Add coverage gaps endpoint to `api/routers/price_alerts.py`
- [ ] Create `frontend/src/components/CoverageGapsPanel.tsx`
- [ ] Add discount day badges to baseline table
- [ ] Add CSV export functionality
- [ ] Create `frontend/src/hooks/api/useBaselineDetails.ts`

---

## Phase 3: My Markets Tab Improvements

### 3.1 Theater Cards with Profile Summary

Update theater display to show profile status instead of just baseline counts:

```
Marcus Arnold Cinemas
├─ Profile: ✅ Discovered
├─ Discount Days: Tue ($5)
├─ Formats: Std, IMAX, UltraScreen
├─ Baselines: 156 ✅
└─ Gaps: 2 missing days
```

### 3.2 Competitor Comparison View

Side-by-side comparison within a market:

|                | Marcus  | AMC     | Regal   |
|----------------|---------|---------|---------|
| Adult Standard | $13.75  | $14.99  | $14.25  |
| Adult IMAX     | $18.50  | $19.99  | $19.50  |
| Matinee        | $9.50   | $11.99  | $10.75  |
| Discount Day   | Tue $5  | Tue $5  | None    |

### 3.3 Tasks

- [ ] Update `frontend/src/pages/BaselinesPage.tsx` - Theater cards with profiles
- [ ] Create `frontend/src/components/CompetitorComparison.tsx`
- [ ] Add "Discover Profile" button per theater
- [ ] Show profile status in theater list

---

## Phase 4: Surge Detection Enhancement

### 4.1 Profile-Aware Surge Detection

Update alert system to use company profiles for baseline selection:

```python
def detect_surge(new_price, theater_name, ticket_type, format, showtime):
    profile = get_company_profile(theater_name)

    # Check if this is a discount day - use discount baseline
    if profile.is_discount_day(showtime.date()):
        baseline = get_baseline(..., day_type="discount", day_of_week=showtime.weekday())
    else:
        baseline = get_baseline(..., day_type="regular")

    # Compare and return alert if above threshold
```

### 4.2 New Film Monitoring

```
GET /surge-detection/check-new-films
```

Returns films posted in last 24h with prices above baseline.

### 4.3 Tasks

- [ ] Update `api/routers/price_alerts.py` - Profile-aware surge detection
- [ ] Update `app/alert_service.py` - Profile-aware baseline lookup
- [ ] Add `/surge-detection/check-new-films` endpoint
- [ ] Create surge alerts dashboard component

---

## Phase 5: EntTelligence Comparison (Future)

### 5.1 Data Source Comparison View

Before trusting EntTelligence, show side-by-side:

| Ticket Type    | Fandango       | EntTelligence  | Diff        |
|----------------|----------------|----------------|-------------|
| Adult Standard | $13.75 (n=52)  | $13.79 (n=120) | +$0.04 ✅   |
| Matinee        | $9.50 (n=38)   | N/A            | ⚠️ Missing  |

### 5.2 Trust Score

Calculate trust per theater based on price alignment. Auto-fill gaps from EntTelligence once trust > 80%.

### 5.3 Tasks

- [ ] Create data comparison view component
- [ ] Implement trust score calculation
- [ ] Add auto-fill from EntTelligence option

---

## Files to Create

| File | Description |
|------|-------------|
| `api/routers/company_profiles.py` | Profile discovery endpoints |
| `app/company_profile_discovery.py` | Discovery service class |
| `frontend/src/pages/BaselineDetailsPage.tsx` | Granular baseline view |
| `frontend/src/components/CoverageGapsPanel.tsx` | Gaps display |
| `frontend/src/components/CompetitorComparison.tsx` | Side-by-side view |
| `frontend/src/hooks/api/useCompanyProfiles.ts` | React Query hooks |
| `migrations/add_company_profiles.sql` | Schema migration |

## Files to Modify

| File | Changes |
|------|---------|
| `app/db_models.py` | Add CompanyProfile model |
| `frontend/src/pages/BaselinesPage.tsx` | Add new tabs/views |
| `api/routers/price_alerts.py` | Profile-aware surge detection + coverage gaps |
| `frontend/src/hooks/api/useBaselines.ts` | Coverage gaps hook |

---

## Key Design Decisions

1. **Ticket-type as source of daypart** - Baseline key is (theater, ticket_type, format, day_of_week). The ticket_type itself carries daypart semantics.

2. **Company profiles stored separately** - Profiles are aggregated insights shared across theaters in same company. Individual baselines remain per-theater.

3. **Granular first, aggregated later** - Users must see and approve individual baselines before showing averages.

4. **Discount days are special** - Separate baseline rows (day_type="discount" vs "regular") to avoid skewing comparisons.

5. **EntTelligence is supplementary** - Fandango baselines are primary. EntTelligence fills gaps once trust is established.

---

## Progress Tracking

**Last Updated:** 2026-01-26

### Sprint 1: Foundation ✅ COMPLETE
| Task | Status | Notes |
|------|--------|-------|
| Create company_profiles table | ✅ Complete | Added to db_models.py + migration SQL |
| Build CompanyProfileDiscoveryService | ✅ Complete | app/company_profile_discovery.py |
| Add /company-profiles/discover endpoint | ✅ Complete | api/routers/company_profiles.py |
| Create React Query hooks | ✅ Complete | frontend/src/hooks/api/useCompanyProfiles.ts |
| Create Baseline Details table view | ✅ Complete | BaselineDetailsPanel.tsx with filters, sort, export |

### Sprint 2: Granular View ✅ COMPLETE
| Task | Status | Notes |
|------|--------|-------|
| Coverage gaps detection algorithm | ✅ Complete | In coverage hooks and services |
| Coverage gaps endpoint | ✅ Complete | /theater-onboarding/{theater}/coverage |
| Coverage Gaps Panel component | ✅ Complete | CoverageGapsPanel.tsx with dual views |
| Discount day badges | ✅ Complete | In BaselineDetailsPanel + ProfileCard |

### Sprint 3: My Markets ✅ COMPLETE
| Task | Status | Notes |
|------|--------|-------|
| Theater cards with profiles | ✅ Complete | TheaterProfileCard.tsx |
| Competitor comparison view | ✅ Complete | CompetitorComparisonPanel.tsx |
| Discover Profile button | ✅ Complete | In CompanyProfilesPanel + MyMarketsPanel |

### Sprint 4: Surge Detection 🔄 PARTIAL
| Task | Status | Notes |
|------|--------|-------|
| Profile-aware surge detection | ✅ Complete | SimplifiedBaselineService uses profiles |
| New film monitoring endpoint | ⬜ Not Started | |
| Surge alerts dashboard | ⬜ Not Started | |

### Sprint 5: Theater Onboarding ✅ COMPLETE
| Task | Status | Notes |
|------|--------|-------|
| TheaterOnboardingStatus model | ✅ Complete | db_models.py line 1455 |
| TheaterOnboardingService | ✅ Complete | app/theater_onboarding_service.py |
| theater_onboarding.py router | ✅ Complete | All 7 endpoints |
| TheaterOnboardingWizard | ✅ Complete | 5-step wizard UI |
| CoverageIndicators component | ✅ Complete | Visual coverage metrics |

### Sprint 6: Discount Programs ✅ COMPLETE
| Task | Status | Notes |
|------|--------|-------|
| DiscountDayProgram model | ✅ Complete | db_models.py line 1269 |
| Discount program endpoints | ✅ Complete | In company_profiles.py |
| DiscountProgramsManager UI | ✅ Complete | Full CRUD operations |

### Sprint 7: Data Source Comparison ✅ COMPLETE
| Task | Status | Notes |
|------|--------|-------|
| EntTelligence vs Fandango view | ✅ Complete | DataSourceComparisonPanel.tsx |
| Tax detection | ✅ Complete | Auto-detects inclusive/exclusive |
| Trust scoring | ⬜ Not Started | |

---

## Component Status Summary

### Frontend Components (9/9 Complete)
| Component | Status | Location |
|-----------|--------|----------|
| BaselineBrowser | ✅ Complete | components/baselines/BaselineBrowser.tsx |
| CoverageGapsPanel | ✅ Complete | components/baselines/CoverageGapsPanel.tsx |
| CompetitorComparisonPanel | ✅ Complete | components/baselines/CompetitorComparisonPanel.tsx |
| DataSourceComparisonPanel | ✅ Complete | components/baselines/DataSourceComparisonPanel.tsx |
| BaselineDetailsPanel | ✅ Complete | components/baselines/BaselineDetailsPanel.tsx |
| UserCentricOverview | ✅ Complete | components/baselines/UserCentricOverview.tsx |
| TheaterProfileCard | ✅ Complete | components/baselines/TheaterProfileCard.tsx |
| MyMarketsPanel | ✅ Complete | components/baselines/MyMarketsPanel.tsx |
| CompanyProfilesPanel | ✅ Complete | components/baselines/CompanyProfilesPanel.tsx |
| DiscountProgramsManager | ✅ Complete | components/profiles/DiscountProgramsManager.tsx |
| TheaterOnboardingWizard | ✅ Complete | components/onboarding/TheaterOnboardingWizard.tsx |
| CoverageIndicators | ✅ Complete | components/onboarding/CoverageIndicators.tsx |

### API Routers (4/4 Complete)
| Router | Status | Key Endpoints |
|--------|--------|---------------|
| company_profiles.py | ✅ Complete | discover, discover-all, cleanup-duplicates, discount-programs, gaps |
| theater_onboarding.py | ✅ Complete | status, pending, start, scrape, discover, link, confirm, coverage |
| price_tiers.py | ✅ Complete | discover, discount-days, recommendations, analyze, save-baselines |
| price_alerts.py | ✅ Complete | alerts, surge detection, threshold configuration |

### Database Models (5/5 Complete)
| Model | Status | Key Fields |
|-------|--------|------------|
| PriceBaseline | ✅ Complete | theater, ticket_type, format, daypart, price, samples |
| CompanyProfile | ✅ Complete | circuit_name, ticket_types, daypart_scheme, discount_days, premium_formats |
| DiscountDayProgram | ✅ Complete | day_of_week, program_name, discount_type, discount_value |
| TheaterOnboardingStatus | ✅ Complete | 5 step flags, coverage data, progress tracking |
| CompanyProfileGap | ✅ Complete | gap_type, expected_value, resolution tracking |

### Services (3/3 Complete)
| Service | Status | Key Methods |
|---------|--------|-------------|
| CompanyProfileDiscoveryService | ✅ Complete | discover_profile, detect ticket types, discount days, premium formats |
| TheaterOnboardingService | ✅ Complete | 5-step workflow, coverage calculation |
| SimplifiedBaselineService | ✅ Complete | find_baseline (3-level hierarchy), check_discount_day |

---

## What's Working

1. ✅ **Company Profile Discovery** - Discovers ticket types, daypart schemes, discount days, premium formats
2. ✅ **Profile Consolidation** - Marcus/Marcus Theatres/Movie Tavern now consolidate correctly (keeps most theaters)
3. ✅ **Baseline Browser** - Hierarchical market/circuit/theater navigation
4. ✅ **Coverage Analysis** - Identifies gaps in formats, ticket types, dayparts
5. ✅ **Competitor Comparison** - Side-by-side pricing across market
6. ✅ **Data Source Comparison** - EntTelligence vs Fandango with tax detection
7. ✅ **Theater Onboarding** - 5-step wizard for new theaters
8. ✅ **Discount Programs** - CRUD for recurring discount days

---

## What Needs Work

1. ⬜ **New Film Surge Detection** - Need endpoint to check new films against baselines
2. ⬜ **Trust Scoring for EntTelligence** - Calculate trust based on price alignment
3. ⬜ **Auto-fill from EntTelligence** - Fill gaps when trust > threshold
4. ⬜ **Surge Alerts Dashboard** - Visual dashboard for detected surges
5. ✅ **Database Population** - Company profiles discovered for 10 circuits (Updated 2026-01-26)
6. ✅ **Discount Program Population** - 8 programs created: 6 auto-discovered + 2 manual (AMC Stubs)

---

## Verification Checklist

- [x] Company profile discovery runs and detects correct ticket types
- [x] Baseline details view shows all individual baselines
- [x] Coverage gaps correctly identify missing days/formats
- [x] Discount day badges appear on detected discount baselines
- [x] Competitor comparison shows side-by-side pricing
- [ ] Surge detection correctly identifies above-baseline prices on new films
- [ ] EntTelligence trust scoring calculates correctly
- [ ] Auto-fill from EntTelligence works when trust threshold met

---

## Current Database State (2026-01-26)

### Company Profiles (10)
| Circuit | Theaters | Ticket Types | Daypart Scheme | Premium Formats |
|---------|----------|--------------|----------------|-----------------|
| AMC | 61 | Adult, Child, Senior | time-based | IMAX, Dolby Cinema, Prime |
| Cinemark | 112 | Adult, Child, Senior | time-based | XD, 3D |
| Marcus Theatres | 78 | Adult, Child, Senior, Matinee, Loyalty | ticket-type-based | UltraScreen, IMAX |
| Regal | 145 | Adult, Child, Senior | time-based | IMAX, RPX, 4DX |
| Studio Movie Grill | 12 | Adult, Child, Senior | time-based | Standard |
| Alamo Drafthouse | 8 | Adult, Child, Senior | time-based | Standard |
| Harkins | 23 | Adult, Child, Senior | time-based | CINÉ 1, Ultimate Lounger |
| Landmark | 5 | Adult, Child, Senior | time-based | Standard |
| ShowBiz | 3 | Adult, Child, Senior | time-based | Standard |
| Galaxy | 4 | Adult, Child, Senior | time-based | DFX |

### Price Baselines
- **Total**: 61,235 baselines
- **Coverage**: All major markets with 90+ day history

### Discount Day Programs (8)
| Circuit | Day | Program | Type | Source |
|---------|-----|---------|------|--------|
| AMC | Tue | AMC Stubs 50% Off Tuesdays | 50% off | manual |
| AMC | Wed | AMC Stubs 50% Off Wednesdays | 50% off | manual |
| Cinemark | Tue | $6.46 Tuesdays | $6.46 flat | auto |
| Cinemark | Tue | $9.64 Tuesdays (3D) | $9.64 flat | auto |
| Marcus | Tue | $7.05 Tuesdays (Loyalty) | $7.05 flat | auto |
| Marcus | Tue | $14.93 Tuesdays (Ac Loyalty) | $14.93 flat | auto |
| Regal | Tue | $9.65 Tuesdays (RCC Value) | $9.65 flat | auto |
| Studio Movie Grill | Tue | $6.36 Tuesdays | $6.36 flat | auto |

### Theater Onboarding Status
- **Pending**: 0
- **In Progress**: 0
- **Complete**: 0 (theaters were added before onboarding feature)

---

## Known Limitations

1. **Member-Only Pricing Not Captured**: The Fandango scraper only captures public (non-member) pricing. Discount programs like AMC Stubs require manual entry.

2. **Discount Day Detection Requires Consistency**: Auto-discovery needs ≤8% price variance and ≥8% below weekday average. Member programs with variable pricing won't be detected.

3. **Day-of-Week Baselines Still Exist**: The simplified baseline model was planned but not fully migrated. Current baselines still include day_of_week granularity.

4. **EntTelligence Trust Scoring**: Not implemented yet. Currently requires manual verification before using EntTelligence data.
