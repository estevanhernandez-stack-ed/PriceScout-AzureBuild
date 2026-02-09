# PriceScout Codebase Map

**Purpose**: Quick-reference guide for AI agents and developers. Maps features → code locations, documents cross-cutting concerns and known quirks.

**Last updated**: 2026-02-08

---

## Feature → Code Location Map

### 1. Scrape Pipeline (Fandango Price Collection)

| Component | File | Key Functions/Classes |
|-----------|------|----------------------|
| Scraper engine | `app/scraper.py` | `Scraper` class — Selenium-based Fandango scraper |
| Scrape orchestration | `app/tasks/scrapes.py` | `run_scrape_job()` — background job lifecycle |
| Scrape API endpoints | `api/routers/scrapes/` | `trigger_scrape()`, `get_scrape_status()` |
| Scrape endpoint tests | `tests/test_api/test_scrape_endpoints.py` | FastAPI TestClient HTTP contract |
| Orchestration tests | `tests/test_api/test_scrape_orchestration.py` | Mock Scraper/DB, job lifecycle |
| Cookie manager | `app/cookie_manager.py` | Browser cookie persistence for Fandango |
| Rate limiter | `app/rate_limit.py`, `app/rate_limit_backend.py` | Request throttling |
| Theater URL cache | `app/theater_cache.json` | Fandango URLs per theater |

**Flow**: API trigger → `run_scrape_job()` → `Scraper.scrape()` → Fandango → parse prices → DB insert → alert generation

### 2. EntTelligence Integration (Competitor Price Cache)

| Component | File | Key Functions/Classes |
|-----------|------|----------------------|
| Cache service | `api/services/enttelligence_cache_service.py` | Theater name matching (4-tier strategy), showtime comparison |
| Market scope | `api/services/market_scope_service.py` | Market boundary resolution, theater aliases |
| Price cache model | `app/db_models.py:EntTelligencePriceCache` | Cached ENT prices per theater/film/showtime |
| Normalization tests | `tests/test_services/test_enttelligence_cache_normalization.py` | 53 tests for name/film/showtime normalization |
| API endpoints | `api/routers/cache.py` | Cache status, refresh, health checks |

**Theater Name Matching** (4-tier strategy in `enttelligence_cache_service.py`):
- Strategy 0: Known aliases (`THEATER_NAME_ALIASES` dict) — completely different names
- Strategy 1: Exact theater name match
- Strategy 1b: LIKE prefix match (`_theater_like_prefix`) — Cinema/Cine/Cinemas variants
- Strategy 1c: Brand-level LIKE + normalized comparison — "at" preposition handling
- Strategy 1d: Deep normalize (sub-brand stripping) — AMC DINE-IN vs AMC CLASSIC

### 3. Price Baselines

| Component | File | Key Functions/Classes |
|-----------|------|----------------------|
| Baseline model | `app/db_models.py:PriceBaseline` | `day_of_week`/`day_type` DEPRECATED (NULL) |
| Simplified service | `app/simplified_baseline_service.py` | `find_baseline()`, `compare_to_baseline()`, normalization functions |
| Alert service | `app/alert_service.py` | `AlertService._check_surge_pricing()`, `_find_baseline()`, `_load_baselines_cache()` |
| ENT discovery | `app/enttelligence_baseline_discovery.py` | `EntTelligenceBaselineDiscoveryService` — UPSERT pattern |
| Fandango discovery | `app/fandango_baseline_discovery.py` | `FandangoBaselineDiscoveryService` — UPSERT, `split_by_day_of_week=False` |
| Legacy discovery | `app/baseline_discovery.py` | `BaselineDiscoveryService` — already had UPSERT |
| Gap filler | `app/baseline_gap_filler.py` | `BaselineGapFillerService` — propose+apply from ENT cache or circuit avg |
| Coverage gaps | `app/coverage_gaps_service.py` | `CoverageGapsService` — identifies missing baselines |
| API endpoints | `api/routers/price_alerts.py` | Baseline CRUD, discovery triggers, browser, analysis |
| Dedup migration | `migrations/dedup_baselines.py` | One-time 292K→40K cleanup (already ran) |

**Matching hierarchy**: `theater → ticket_type → format → daypart` (wildcard fallback at each level)

**Tax status per circuit**: See [Tax Handling](#tax-handling) section below.

### 4. Surge Detection

| Component | File | Lines | Key Functions |
|-----------|------|-------|---------------|
| Post-scrape alerts | `app/alert_service.py` | 83-169 | `process_scrape_results()` — main entry |
| Surge check | `app/alert_service.py` | 691-836 | `_check_surge_pricing()` — tax-aware, discount-day-aware |
| Baseline cache | `app/alert_service.py` | 199-248 | `_load_baselines_cache()` — flat key cache |
| Baseline matching | `app/alert_service.py` | 250-289 | `_find_baseline()` — 4-tier wildcard fallback |
| Advance scanner | `api/routers/price_alerts.py` | ~2817-3212 | `scan_advance_dates_for_surges()` — ENT cache vs baselines |
| New-film monitor | `api/routers/price_alerts.py` | ~3244-3386 | `check_new_films_for_surges()` — recently posted films |
| Alert model | `app/db_models.py:PriceAlert` | 565-627 | `alert_type`: surge_detected, potential_surge_low_confidence, discount_day_overcharge |
| Alert config | `app/db_models.py:AlertConfiguration` | 629-680 | `surge_threshold_percent` default 20% |
| Discount programs | `app/db_models.py:DiscountDayProgram` | 1397-1496 | Circuit-level discount days with `applies_to()` |
| Frontend | `frontend/src/pages/BaselinesPage.tsx` | — | Surge Scanner tab (advance + new-film) |

**Surge detection flow**:
1. Scrape completes → `generate_alerts_for_scrape()` → `AlertService.process_scrape_results()`
2. For each price: check discount day → find baseline → tax-adjust → compare → emit PriceAlert
3. Advance scanner: query ENT cache for future dates → same comparison logic

### 5. Market & Theater Management

| Component | File | Key Functions/Classes |
|-----------|------|----------------------|
| Markets definition | `data/Marcus/markets.json` (or company-specific) | Market boundaries, theater lists |
| Market context | `api/services/market_context_service.py` | Theater metadata, heatmaps |
| Market scope | `api/services/market_scope_service.py` | Market resolution, aliases |
| Theater matching | `app/theater_matching_tool.py` | Fandango → DB theater name resolution |
| Theater metadata | `app/db_models.py:TheaterMetadata` | Circuit name, address, amenities |
| Company profiles | `app/db_models.py:CompanyProfile` | Per-circuit pricing profile |

### 6. Reports & Analysis

| Component | File | Key Functions/Classes |
|-----------|------|----------------------|
| Report generation | `api/routers/reports.py` | PDF, Excel, HTML market reports |
| Circuit benchmarks | `api/routers/circuit_benchmarks.py` | Cross-circuit price comparison |
| Film enrichment | `app/db/film_enrichment.py` | OMDB/IMDB metadata |
| Box office | `app/box_office_mojo_scraper.py` | Box office performance data |

### 7. Frontend (React/TypeScript)

| Component | File | Key Patterns |
|-----------|------|-------------|
| App entry | `frontend/src/App.tsx` | React Router, ErrorBoundary (two-level) |
| Pages | `frontend/src/pages/` | DailyLineupPage, MarketModePage, BaselinesPage, etc. |
| API hooks | `frontend/src/hooks/` | TanStack Query hooks |
| Error boundary | `frontend/src/components/error/ErrorBoundary.tsx` | App-level + MainLayout-level |
| State | — | Zustand stores (minimal), TanStack Query for server state |
| Tests | `frontend/src/**/*.test.tsx` | 631 tests, Vitest + React Testing Library |
| Config | `frontend/vite.config.ts` | Coverage thresholds at 70% |

---

## Cross-Cutting Concerns

### Tax Handling

**The Problem**: EntTelligence prices for some circuits are pre-tax (exclusive), while Fandango prices are always tax-inclusive. Baselines may come from either source.

**Verified Circuit Tax Status**:

| Circuit | ENT Tax Status | Evidence |
|---------|---------------|----------|
| AMC | `inclusive` (rate=0.0) | Fandango vs ENT: $0.00 difference |
| Regal | `inclusive` (rate=0.0) | Same — prices match exactly |
| Studio Movie Grill | `inclusive` (rate=0.0) | Same pattern |
| Marcus | `exclusive` (~5-8%) | Systematic gap vs Fandango |
| Movie Tavern | `exclusive` (Marcus brand) | Same as Marcus |
| Cinemark | `exclusive` (~7.6%) | Systematic gap vs Fandango |
| B&B, Emagine, Alamo, Harkins, etc. | **UNKNOWN** | Not yet tested — falls to per-state/default rate |

**Tax Config Storage**: `Company.settings_dict["tax_config"]` JSON with `per_theater`, `per_state`, `default_rate` tiers.

**Tax Estimation Service**: `api/services/tax_estimation.py`
- `get_tax_config(company_id)` → load config
- `get_tax_rate_for_theater(config, state, theater_name)` → per-theater → per-state → default
- `apply_estimated_tax(price, rate)` → `price * (1 + rate)`

**Where Tax Adjustment Happens**:
- `alert_service.py:778` — adjusts baseline UP if `tax_status='exclusive'` (for Fandango scrape comparison)
- `price_alerts.py` surge scanner — adjusts ENT cache price UP if baseline is `inclusive`; leaves raw if `exclusive`
- `enttelligence_baseline_discovery.py` — applies estimated tax before saving if `tax_enabled`

### Daypart Classification

**Canonical dayparts** (4 categories):
- **Matinee**: before 4:00 PM
- **Twilight**: 4:00 PM – 6:00 PM
- **Prime**: 6:00 PM – 9:00 PM
- **Late Night**: 9:00 PM and after

**Shared utility**: `classify_daypart(time_str)` in `app/simplified_baseline_service.py`
- Handles 12hr (7:30PM) and 24hr (19:30) formats
- Used by surge scanner, discovery services

**Normalization**: `normalize_daypart(raw)` in same file — maps legacy names:
- `'evening'` → `'Prime'`
- `'late'` → `'Late Night'`
- `'matinee'` → `'Matinee'` (case fix)

### Ticket Type Normalization

**Function**: `normalize_ticket_type(raw)` in `app/simplified_baseline_service.py`
- `'early bird'` → `'Early Bird'`
- `'general'` → `'General Admission'`
- Does NOT merge `Adult` ↔ `General Admission` (different price points)

**Equivalence mapping**: `get_equivalent_ticket_types()` in `api/routers/price_alerts.py`
- `Adult` ↔ `General Admission` (for cross-source matching only)

### Format Normalization

- `'Standard'` ↔ `'2D'` (interchangeable)
- `'3D'` and PLF formats (IMAX, Dolby, UltraScreen) are NOT interchangeable
- Fandango provides accurate PLF labels; EntTelligence only has 2D/3D

### Theater Name Aliases

Maintained in two places (must stay in sync):
- `THEATER_NAME_ALIASES` in `api/services/enttelligence_cache_service.py`
- `_KNOWN_ALIASES` in `api/services/market_scope_service.py`

---

## Database Schema (Key Tables)

| Table | Model | Purpose |
|-------|-------|---------|
| `price_baselines` | `PriceBaseline` | Normal price expectations per theater/ticket/format/daypart |
| `price_alerts` | `PriceAlert` | Surge/discount-day alerts with baseline_price, surge_multiplier |
| `alert_configurations` | `AlertConfiguration` | Per-company surge threshold (default 20%) |
| `enttelligence_price_cache` | `EntTelligencePriceCache` | Cached competitor prices from EntTelligence |
| `theater_metadata` | `TheaterMetadata` | Circuit name, address, amenities per theater |
| `company_profiles` | `CompanyProfile` | Per-circuit pricing profile with discount day config |
| `discount_day_programs` | `DiscountDayProgram` | Circuit-level discount programs (e.g., "$5 Tuesdays") |
| `scrape_runs` | `ScrapeRun` | Scrape job history and status |
| `showings` | `Showing` | Scraped showtimes |
| `prices` | `Price` | Scraped ticket prices per showing |
| `films` | `Film` | Film metadata (title, OMDB, genre, etc.) |

---

## Known Quirks & Gotchas

1. **`day_of_week` / `day_type` are DEPRECATED** in `price_baselines` — collapsed to NULL by dedup migration. Discount days handled by `DiscountDayProgram` instead.

2. **Theater names differ between Fandango and EntTelligence**: type words (Cinema/Cinemas/Cine), "at" preposition, sub-brand chaos (AMC DINE-IN vs AMC CLASSIC). Always use the 4-tier matching strategy.

3. **Fandango format is authoritative** for PLF detection. EntTelligence only knows 2D/3D. Override logic in `execution.py:207`.

4. **Discovery services use UPSERT** — update in place when `overwrite=True`. Old pattern (end-old + create-new) caused 5.4x row duplication.

5. **Mocking `builtins.open` breaks FastAPI TestClient** — use `tmp_path` + patch the file path constant instead.

6. **AST check** in tests prevents `from app import config` inside `run_scrape_job` (scoping regression).

7. **Progress counter** must count unique showings (cache_hits), not ticket-type rows (Adult+Child+Senior = 3x inflation).

8. **Pydantic V2**: Use `model_dump()` not `dict()`. JSON dict keys must be strings (`Dict[str, int]` not `Dict[int, int]`).

9. **FastAPI route ordering**: Parameterized routes (`/{id}`) shadow literal routes (`/compare`). Define literal routes first.

10. **Frontend test imports**: Must import `beforeEach`/`afterEach` from vitest explicitly (no globals in tsconfig).

---

## Test Strategy

| Layer | File Pattern | What It Tests |
|-------|-------------|---------------|
| Smoke imports | `tests/test_smoke_imports.py` | Every module imports without error |
| Backend unit | `tests/test_api/`, `tests/test_services/` | FastAPI endpoints, service logic |
| Normalization | `tests/test_services/test_enttelligence_cache_normalization.py` | 53 tests for name/film/showtime matching |
| Frontend unit | `frontend/src/**/*.test.tsx` | 631 tests, Vitest + React Testing Library |
| Coverage | `frontend/vite.config.ts` | Thresholds at 70% (lines/branches/functions/statements) |

**Run commands**:
- Backend: `python -m pytest tests/ -x -q`
- Frontend: `cd frontend && npx vitest run`
- Frontend coverage: `cd frontend && npx vitest run --coverage`

---

## File Organization

```
apps/pricescout-react/
├── api/                    # FastAPI backend
│   ├── main.py             # App factory, middleware, CORS
│   ├── auth.py             # JWT + API key auth
│   ├── entra_auth.py       # Azure Entra ID SSO
│   ├── routers/            # Route handlers (one per feature area)
│   │   ├── price_alerts.py # Baselines, surges, alerts (~3400 lines)
│   │   ├── scrapes/        # Scrape trigger + status
│   │   ├── reports.py      # Report generation
│   │   └── ...
│   └── services/           # Business logic services
│       ├── enttelligence_cache_service.py
│       ├── tax_estimation.py
│       └── market_scope_service.py
├── app/                    # Core application logic
│   ├── scraper.py          # Fandango Selenium scraper
│   ├── db_models.py        # SQLAlchemy ORM models
│   ├── db_session.py       # Database connection management
│   ├── db/                 # Database access modules (12 files)
│   ├── db_adapter.py       # Re-export hub for db/ modules
│   ├── alert_service.py    # Surge detection + discount day checking
│   ├── simplified_baseline_service.py  # Baseline matching + normalization
│   ├── *_baseline_discovery.py  # Three discovery services (ENT, Fandango, legacy)
│   ├── baseline_gap_filler.py   # Coverage gap remediation
│   └── tasks/scrapes.py    # Background scrape job
├── frontend/               # React/TypeScript SPA
│   ├── src/pages/          # Page components
│   ├── src/hooks/          # TanStack Query hooks
│   └── src/components/     # Shared components
├── tests/                  # Backend test suite (510+ tests)
├── migrations/             # Database migrations
├── docs/                   # Documentation (39+ files)
└── data/                   # Market definitions, theater configs
```
