# PriceScout - Marcus App Accords Gap Analysis

**Application**: PriceScout React
**Schema**: `pricescout`
**Tech Stack**: Python 3.11+ / FastAPI / SQLAlchemy / React 18 + TypeScript
**ADR**: ADR-001-PYTHON-FASTAPI (Accepted)
**Assessment Date**: January 28, 2026
**Accords Version**: 1.0 (January 2026)

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Base Score** | **84 / 100** |
| **Bonus Score** | **+17** |
| **Final Score** | **100 (capped)** |
| **Maturity Level** | **Beta** (75-89%) |
| **Target Level** | **Beta+** (90-100%) |
| **Gap to Beta+** | **6 points** |
| **All Requirements Met?** | No |
| **Gold Standard Eligible?** | No |

### Key Gaps to Beta+

| Gap | Points Available | Effort |
|-----|-----------------|--------|
| Entra ID authentication (R4.1) | +3 | Medium |
| Core schema User/Company refs (R3.2, R3.4, R3.5) | +6 | High |
| Azure Repos migration (R5.1) | +2 | Low |
| CI/CD pipeline activation (R5.2, R5.3) | +3 | Medium |

---

## Pillar-by-Pillar Assessment

### R1: API-First Architecture (25/25)

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| R1.1 | REST API endpoints | **MET** | FastAPI with 24 routers in `api/routers/` |
| R1.2 | OpenAPI 3.0 spec | **MET** | `/api/v1/docs` (Swagger), `/api/v1/redoc`, `/api/v1/openapi.json` |
| R1.3 | Frontend decoupled | **MET** | React 18 + Vite in `frontend/`, separate build artifacts |
| R1.4 | RFC 7807 errors | **MET** | `api/errors.py` - full ProblemType enum, `application/problem+json` content type |
| R1.5 | API versioning | **MET** | `/api/v1/` URL prefix pattern |

**Score: 25/25** - PriceScout's API-first architecture is exemplary. FastAPI auto-generates comprehensive OpenAPI specs with detailed descriptions, server definitions, and tag organization. RFC 7807 implementation includes custom problem types, trace IDs, and timestamps.

---

### R2: Technology Stack (19/20)

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| R2.1 | .NET 8+ OR ADR exception | **MET** | ADR-001-PYTHON-FASTAPI accepted Nov 2025 |
| R2.2 | EF Core OR approved ORM | **MET** | SQLAlchemy 2.0+ (covered by ADR) |
| R2.3 | TypeScript frontend | **MET** | TypeScript 5.6.3, strict mode, `tsconfig.json` |
| R2.4 | No deprecated deps | **PARTIAL** | Streamlit pinned to 1.38.0 (documented bug); needs `pip-audit` |

**Score: 19/20** - Python/FastAPI is an approved exception with clear justification (web scraping, data science ecosystem). Frontend fully TypeScript with strict mode. Minor deduction for pinned Streamlit dependency and lack of automated dependency auditing in CI.

**Remediation**: Add `pip-audit` to CI pipeline, document Streamlit pin rationale, periodically retest against newer versions.

---

### R3: Shared Database Pattern (14/20)

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| R3.1 | Schema isolation | **MET** | All tables in `pricescout.*` schema, configurable via `DB_SCHEMA` env var |
| R3.2 | Read-only core access | **NOT MET** | Does not reference `core.*` schema at all |
| R3.3 | ORM migrations | **MET** | Alembic migrations in `migrations/` directory |
| R3.4 | FK refs to core tables | **NOT MET** | No foreign keys to core.Users or core.Locations |
| R3.5 | No duplicate ref data | **NOT MET** | Defines own `companies` and `users` tables |

**Score: 14/20** - Schema isolation is properly implemented. However, PriceScout maintains its own User and Company tables instead of referencing `core.users` and `core.companies`. This is the **largest compliance gap**.

**Nuance**: PriceScout's `TheaterMetadata` table tracks *competitor* theaters (AMC, Cinemark, Regal) which are legitimately NOT in `core.Locations` (Marcus-owned venues). This table is not duplicative - it serves a different purpose. However, `pricescout.users` and `pricescout.companies` duplicate core concepts.

**Remediation**:
1. Replace `pricescout.users` with references to `core.Users` (map user_id FK)
2. Replace `pricescout.companies` with references to `core.Companies` or create a mapping table
3. Keep `TheaterMetadata` as-is (competitive data, not core reference data) but document the rationale
4. Add read-only views or FK references to core tables where applicable

---

### R4: Security & Identity (12/15)

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| R4.1 | Entra ID authentication | **NOT MET** | MSAL in requirements.txt but zero implementation code |
| R4.2 | RBAC | **MET** | admin/manager/user roles enforced, scope-based auth |
| R4.3 | Secrets in Key Vault | **MET** | `app/azure_secrets.py`, Key Vault integration |
| R4.4 | HTTPS only | **MET** | HSTS header (prod), security headers middleware, CSP |
| R4.5 | Input validation | **MET** | Pydantic models, FastAPI validators, query constraints |

**Score: 12/15** - Strong security posture with rate limiting, security headers (X-Frame-Options, CSP, HSTS), and comprehensive input validation. The critical gap is Entra ID - MSAL dependency is installed but no auth code uses it. Current auth is JWT + API key only.

**Remediation**: Implement MSAL Python integration in `api/unified_auth.py`:
- Add Entra ID as auth option alongside JWT
- Map Entra ID roles to PriceScout RBAC roles
- Maintain JWT fallback for development mode

---

### R5: DevOps Integration (5/10)

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| R5.1 | Source in Azure Repos | **NOT MET** | Currently in local/GitHub monorepo |
| R5.2 | CI pipeline | **PARTIAL** | `azure-pipelines.yml` exists but not active |
| R5.3 | CD pipeline | **PARTIAL** | Deploy scripts exist (`azure/deploy-infrastructure.ps1`) |
| R5.4 | IaC (Bicep) | **MET** | `azure/iac/` with main.bicep, appservice.bicep, keyvault.bicep, etc. |

**Score: 5/10** - Infrastructure-as-Code is solid with comprehensive Bicep templates. The gap is operational: source control needs migration to Azure Repos, and the CI/CD pipeline needs activation. The pipeline YAML and deploy scripts exist but aren't running.

**Remediation**:
1. Mirror/migrate repo to Azure Repos
2. Activate `azure-pipelines.yml` pipeline
3. Add test gates (pytest with coverage threshold)
4. Configure multi-environment deployment (dev → staging → prod)

---

### R6: Monitoring & Operations (9/10)

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| R6.1 | App Insights | **MET** | `api/telemetry.py`, `api/metrics.py`, OpenTelemetry integration |
| R6.2 | Health check | **MET** | `GET /api/v1/health` returns status, DB connectivity, version |
| R6.3 | Structured logging | **MET** | Python logging with level, timestamp, logger name |
| R6.4 | Error tracking | **MET** | App Insights exception capture, circuit breaker monitoring |

**Score: 9/10** - Monitoring is comprehensive. Custom events track scrapes, price changes, alerts, and report generation. Prometheus-compatible `/metrics` endpoint provides counters, histograms, and gauges. Circuit breaker pattern monitors Fandango/EntTelligence service health. Minor gap: could add custom Azure Monitor dashboards and alerting rules.

---

## Bonus Requests Assessment

### Q1: Enhanced Documentation (+2/5)

| ID | Request | Status | Bonus |
|----|---------|--------|-------|
| Q1.1 | API examples in OpenAPI | **MET** | +1 |
| Q1.2 | ADRs | **MET** | +1 |
| Q1.3 | Operations runbook | **NOT MET** | 0 |
| Q1.4 | User guide with screenshots | **NOT MET** | 0 |
| Q1.5 | Video walkthrough | **NOT MET** | 0 |

### Q2: Testing Excellence (+3/10)

| ID | Request | Status | Bonus |
|----|---------|--------|-------|
| Q2.1 | Unit test coverage ≥70% | **UNKNOWN** | 0 |
| Q2.2 | Unit test coverage ≥85% | **UNKNOWN** | 0 |
| Q2.3 | Integration tests for API | **MET** | +2 |
| Q2.4 | End-to-end tests | **PARTIAL** | +1 |
| Q2.5 | Performance/load tests | **NOT MET** | 0 |

Test infrastructure exists (pytest + Vitest + Playwright) but coverage metrics aren't tracked in the repository. Test files exist in `tests/test_api/` with proper fixtures and assertions.

### Q3: User Experience Modes (+10/10)

| ID | Request | Status | Bonus |
|----|---------|--------|-------|
| Q3.1 | Admin mode with full CRUD | **MET** | +3 |
| Q3.2 | Management mode with reports | **MET** | +3 |
| Q3.3 | Standard user mode | **MET** | +2 |
| Q3.4 | Audit logging | **MET** | +2 |

PriceScout has distinct admin capabilities (user management, system config), management features (reports, dashboards, market analysis), and standard user workflows (price checks, scrapes). Audit logging tracks user actions.

### Q4: Advanced Features (+2/5)

| ID | Request | Status | Bonus |
|----|---------|--------|-------|
| Q4.1 | Feature flags | **NOT MET** | 0 |
| Q4.2 | Custom App Insights metrics | **MET** | +1 |
| Q4.3 | Alerting rules | **MET** | +1 |
| Q4.4 | APIM policies | **NOT MET** | 0 |
| Q4.5 | Offline/PWA | **NOT MET** | 0 |

**Total Bonus: +17 points**

---

## Remediation Priority

### Priority 1: Entra ID Authentication (R4.1) — +3 base points

**Impact**: Blocks Beta+ and Gold Standard eligibility
**Effort**: Medium (MSAL already in requirements.txt)
**Files**:
- `api/unified_auth.py` - Add Entra ID auth provider
- `api/main.py` - Register Entra ID middleware
- `.env.example` - Document ENTRA_* variables (already present)

**Steps**:
1. Import and configure MSAL ConfidentialClientApplication
2. Add `/auth/entra/callback` endpoint for token exchange
3. Map Entra ID groups/roles to PriceScout RBAC roles
4. Update `require_auth()` to accept Entra ID tokens
5. Maintain JWT fallback for development

---

### Priority 2: Core Schema Integration (R3.2, R3.4, R3.5) — +6 base points

**Impact**: Largest single gap (6 points)
**Effort**: High (requires schema migration)
**Files**:
- `app/db_models.py` - Replace User/Company with core refs
- `migrations/` - Add migration for FK changes
- `api/unified_auth.py` - Update user lookups

**Steps**:
1. Create read-only SQLAlchemy models mapping to `core.Users` and `core.Companies`
2. Add FK from `pricescout.*` tables to `core.Users.user_id`
3. Migrate `pricescout.companies` data to `core.Companies` mapping
4. Update auth to resolve users from core schema
5. Keep `TheaterMetadata` as-is (document: competitor data, not core ref data)
6. Add ADR documenting TheaterMetadata rationale

---

### Priority 3: Azure Repos Migration (R5.1) — +2 base points

**Impact**: Required for full DevOps compliance
**Effort**: Low
**Steps**:
1. Create Azure Repos project for PriceScout
2. Push existing Git history
3. Update any CI/CD references
4. Set up branch policies (PR required, build validation)

---

### Priority 4: CI/CD Pipeline Activation (R5.2, R5.3) — +3 base points

**Impact**: Enables automated quality gates
**Effort**: Medium
**Files**:
- `azure-pipelines.yml` - Activate and configure
- `pytest.ini` - Add coverage thresholds

**Steps**:
1. Activate pipeline in Azure DevOps
2. Add test stage with `pytest --cov --cov-fail-under=70`
3. Add `pip-audit` security scan stage
4. Configure deployment stages (dev → staging → prod)
5. Add build status badge to README

---

### Priority 5: Dependency Audit (R2.4) — +1 base point

**Impact**: Ensures no deprecated/vulnerable dependencies
**Effort**: Low
**Steps**:
1. Add `pip-audit` to CI pipeline
2. Add `npm audit` to frontend CI
3. Document Streamlit 1.38.0 pin rationale
4. Set up Dependabot or Renovate for automated updates

---

## Score Projection After Remediation

| Pillar | Current | After P1-P5 | Change |
|--------|---------|-------------|--------|
| R1: API-First | 25/25 | 25/25 | — |
| R2: Tech Stack | 19/20 | 20/20 | +1 |
| R3: Database | 14/20 | 20/20 | +6 |
| R4: Security | 12/15 | 15/15 | +3 |
| R5: DevOps | 5/10 | 10/10 | +5 |
| R6: Monitoring | 9/10 | 9/10 | — |
| **Base Total** | **84/100** | **99/100** | **+15** |
| Bonus | +17 | +20+ | +3 |

**Projected Maturity**: Beta+ (99/100 base)
**Gold Standard Eligible**: Yes (Base ≥95, Bonus ≥20, All Requirements met)

---

## What PriceScout Does Well

These strengths should be preserved and can serve as examples for other apps:

1. **RFC 7807 Implementation** - Comprehensive problem types, trace IDs, timestamps. Best in platform.
2. **Monitoring Depth** - Custom telemetry events, Prometheus metrics endpoint, circuit breaker pattern.
3. **Security Headers** - HSTS, CSP, X-Frame-Options, rate limiting with `X-RateLimit-*` headers.
4. **API Design** - 24 well-organized routers, proper pagination, filtering, status codes.
5. **Multi-DB Support** - Seamless SQLite (dev) / PostgreSQL / MSSQL (prod) switching.
6. **User Experience Modes** - Full admin, management, and standard user modes (Q3: 10/10 bonus).
7. **Health Endpoint** - Returns DB connectivity, auth status, version, environment.

---

## Comparison with December 2025 Assessment

The prior compliance chart (Dec 4, 2025) scored PriceScout at 88/100. This updated assessment scores 84/100 under the more rigorous January 2026 Accords framework. Key differences:

| Area | Dec 2025 Score | Jan 2026 Score | Reason |
|------|---------------|---------------|--------|
| Database | 20/20 | 14/20 | Accords explicitly require core schema refs (R3.2, R3.4, R3.5) |
| Security | 5/10 | 12/15 | Weight changed from 10 to 15 pts; better credit for existing controls |
| DevOps | 13/15 | 5/10 | Weight changed from 15 to 10 pts; stricter on active pipelines |

The December assessment was more generous on database compliance. The Accords explicitly require core schema references and prohibit duplicate reference data, which PriceScout's own User/Company tables violate.

---

*Generated by PriceScout Accords Gap Analysis - January 28, 2026*
