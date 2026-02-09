# PriceScout Architecture Overview

Technical architecture for the PriceScout React/FastAPI platform.

**Last Updated:** February 2026

---

## System Overview

```
                          PriceScout System
 +-----------+     +-------------+     +-------------------+
 |  React    |---->|   FastAPI   |---->| External Services |
 | Frontend  |<----|   Backend   |<----| Fandango, ENT API |
 +-----------+     +-------------+     +-------------------+
                         |
                         v
                   +------------+
                   | PostgreSQL |
                   |  Database  |
                   +------------+
```

**Stack:**
- **Frontend**: React 18 + TypeScript, Vite, TanStack Query, Zustand, Tailwind CSS
- **Backend**: Python 3.13, FastAPI, SQLAlchemy 2.0 (ORM), Pydantic V2
- **Database**: PostgreSQL (production) / SQLite (local dev)
- **Scraping**: Playwright (Chromium) for Fandango price collection
- **External API**: EntTelligence REST API (Tableau-backed competitor pricing)
- **Auth**: JWT tokens + API keys + Azure Entra ID (SSO)
- **CI/CD**: Azure DevOps Pipelines (4-stage: test, build, package, deploy)
- **Monitoring**: Azure Application Insights (traces, exceptions, custom events)
- **Background tasks**: Python threading (daemon threads for auto-sync)

---

## Backend Architecture

```
api/                          # FastAPI application layer
  main.py                     # App factory, CORS, CSP, security headers
  auth.py                     # JWT + API key auth (get_current_user)
  entra_auth.py               # Azure Entra ID SSO integration
  routers/
    price_alerts.py           # Baselines, surge detection, alerts (~4500 lines)
    scrapes/                  # Scrape trigger, execution, status (decomposed)
    reports.py                # PDF/Excel/HTML market reports
    circuit_benchmarks.py     # Cross-circuit price comparison
    cache.py                  # EntTelligence cache management
    films.py, markets.py      # CRUD endpoints
  services/
    enttelligence_cache_service.py  # 4-tier theater name matching
    tax_estimation.py               # Per-theater/state/default tax rates
    market_scope_service.py         # Market boundary resolution

app/                          # Core business logic
  scraper.py                  # Fandango Selenium/Playwright scraper
  alert_service.py            # Post-scrape surge detection
  simplified_baseline_service.py  # Baseline matching + normalization utilities
  *_baseline_discovery.py     # Three discovery services (ENT/Fandango/legacy)
  db_models.py                # SQLAlchemy ORM models (~1700 lines)
  db_session.py               # Connection pool, engine management
  db/                         # Modular database access (12 files)
  db_adapter.py               # Re-export hub (backward compat)
  tasks/scrapes.py            # Background scrape job runner
```

### Key Design Decisions

1. **No Celery** - Background tasks use Python daemon threads. Simpler than Celery for our single-server Azure App Service deployment.

2. **No Prometheus** - Monitoring via Azure Application Insights SDK. Custom events tracked in `api/telemetry.py`.

3. **SQLAlchemy ORM throughout** - All database access via ORM models. No raw SQL in application code.

4. **db_adapter as re-export hub** - Legacy import compatibility layer. New code should import directly from `app.db_session`, `app.db_models`, or `app.db.*` submodules.

---

## Frontend Architecture

```
frontend/src/
  App.tsx                     # Router, ErrorBoundary (two-level)
  pages/
    MarketModePage.tsx         # Wizard-style scrape workflow
    DailyLineupPage.tsx        # Schedule viewer
    BaselinesPage.tsx          # Baseline browser + Surge Scanner tab
    ...
  hooks/                      # TanStack Query hooks (server state)
  stores/                     # Zustand (minimal client state)
  components/
    ui/                       # Shadcn/ui components
    error/ErrorBoundary.tsx   # App + layout level error boundaries
  lib/
    api.ts                    # Axios client with auth interceptor
```

---

## Data Flow: Scrape Pipeline

```
API trigger (POST /scrapes/trigger)
  -> run_scrape_job() [daemon thread]
    -> Scraper.get_all_showings_for_theaters()  [Playwright/Fandango]
    -> Scraper.scrape_details()                 [per-showing prices]
    -> upsert_showings() + save_prices()        [PostgreSQL]
    -> AlertService.process_scrape_results()    [surge detection]
    -> track_scrape_completed()                 [App Insights]
```

## Data Flow: Surge Detection

```
Post-scrape:
  For each price:
    1. Check discount day program (DiscountDayProgram.applies_to())
    2. Find baseline (theater -> ticket_type -> format -> daypart, wildcard fallback)
    3. Tax-adjust if baseline.tax_status == 'exclusive'
    4. Compare: if price > baseline * (1 + threshold%) -> emit PriceAlert

Advance scanner (on-demand):
    Query EntTelligence cache for future dates
    -> Same comparison logic against baselines
    -> Returns potential surges before they happen
```

---

## Database

**Engine**: PostgreSQL 16 (Azure Flexible Server)

**Connection Pool**: SQLAlchemy `create_engine()` with:
- `pool_size=20`, `max_overflow=30`, `pool_recycle=1800s`
- `pool_pre_ping=True` (connection health check)

**Key Tables**: See `docs/CODEBASE_MAP.md` for full schema map.

---

## Authentication

Three auth methods (at least one must be enabled):

| Method | Config | Use Case |
|--------|--------|----------|
| **JWT + DB users** | `DB_AUTH_ENABLED=true` | Local dev, standalone |
| **API Keys** | `API_KEY_AUTH_ENABLED=true` | Service-to-service |
| **Azure Entra ID** | `ENTRA_ENABLED=true` | Production SSO |

---

## Role-Based Access Control

| Role | Level | Capabilities |
|------|-------|-------------|
| `admin` | 5 | Full access, user management, force circuit trips |
| `director` | 4 | Company selection, all operational pages |
| `manager` | 3 | Reset circuits, trigger scrapes |
| `analyst` | 2 | View reports, baselines, alerts |
| `viewer` | 1 | Read-only dashboard access |

---

## Cross-Cutting Concerns

Detailed in `docs/CODEBASE_MAP.md`:
- **Tax handling**: per-theater -> per-state -> default rate estimation
- **Daypart classification**: 4 canonical dayparts (Matinee/Twilight/Prime/Late Night)
- **Theater name matching**: 4-tier strategy for Fandango vs EntTelligence names
- **Ticket type normalization**: Adult != General Admission (different price points)

---

## Deployment

**Target**: Azure App Service (Linux, Python 3.13)

```
Azure DevOps Pipeline (4 stages):
  1. test-backend    - pytest (510+ tests), pip-audit, Bandit SAST, mypy
  2. test-frontend   - vitest (631+ tests), TypeScript check, ESLint
  3. build-artifacts - pip install, npm build, package
  4. deploy          - Azure App Service (gunicorn + uvicorn)
```
