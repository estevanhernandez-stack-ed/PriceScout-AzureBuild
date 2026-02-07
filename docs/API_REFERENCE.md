# PriceScout API Reference

**Version:** 2.3.0
**Last Updated:** February 5, 2026
**Base URL:** `/api/v1`
**Spec Format:** OpenAPI 3.0 (auto-generated)
**Total Endpoints:** 200+

---

## Interactive Documentation

| Tool | URL | Description |
|------|-----|-------------|
| **Swagger UI** | `/api/v1/docs` | Interactive API explorer with "Try It" |
| **ReDoc** | `/api/v1/redoc` | Clean read-only documentation |
| **OpenAPI JSON** | `/api/v1/openapi.json` | Machine-readable specification |

---

## Authentication

All endpoints (except `/health` and `/token`) require authentication via one of:

| Method | Header | Example |
|--------|--------|---------|
| **JWT Bearer** | `Authorization: Bearer <token>` | `POST /api/v1/auth/token` to obtain |
| **API Key** | `X-API-Key: <key>` | Managed via admin panel |

**RBAC Roles:** `admin`, `manager`, `operator`, `viewer`

---

## Error Format

All errors follow [RFC 7807 Problem Details](https://www.rfc-editor.org/rfc/rfc7807):

```json
{
  "type": "https://pricescout.marcus.com/errors/not-found",
  "title": "Resource Not Found",
  "status": 404,
  "detail": "Theater 'Example Theater' not found",
  "instance": "/api/v1/resources/theaters/999",
  "trace_id": "abc-123-def"
}
```

---

## Request Correlation Headers (February 2026)

All API responses include correlation headers for distributed tracing:

| Header | Direction | Description |
|--------|-----------|-------------|
| `X-Request-ID` | Request (optional) | Client-provided correlation ID (must be valid UUID) |
| `X-Request-ID` | Response | Request correlation ID (client-provided or auto-generated) |
| `X-Trace-ID` | Response | OpenTelemetry trace ID (when tracing enabled) |

**Security:** Request IDs are validated against UUID format to prevent log injection attacks. Invalid or missing IDs are replaced with server-generated UUIDs.

**Usage:**
```bash
# Send request with custom correlation ID
curl -H "X-Request-ID: 550e8400-e29b-41d4-a716-446655440000" \
  https://api.pricescout.io/api/v1/theaters

# Response headers include:
# X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
# X-Trace-ID: 4bf92f3577b34da6a3ce929d0e0e4736
```

**Finding logs in Application Insights:**
```kusto
traces
| where customDimensions["request_id"] == "550e8400-e29b-41d4-a716-446655440000"
| order by timestamp asc
```

---

## Endpoint Reference

### Root & Health (main.py)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/` | API root information | None |
| `GET` | `/health` | Basic health check | None |
| `GET` | `/health/full` | Comprehensive health check with component status | None |
| `GET` | `/info` | Detailed API info and endpoint listing | None |

---

### Authentication & Users

**Router:** `auth.py` | **Tag:** Auth | **Prefix:** `/auth`

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/auth/token` | Get JWT token (username/password) | None |
| `POST` | `/auth/logout` | Logout current user | Bearer |
| `GET` | `/auth/me` | Get current user info | Bearer |
| `POST` | `/auth/refresh` | Refresh JWT token | Bearer |
| `GET` | `/auth/health` | Auth service health check (DB, API key, Entra ID status) | None |

**Entra ID SSO (February 2026)**

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/auth/entra/login` | Initiate Entra ID SSO flow | None |
| `GET` | `/auth/entra/callback` | Handle OAuth callback from Microsoft | None |
| `POST` | `/auth/entra/exchange` | Exchange auth code for session JWT | None |
| `GET` | `/auth/entra/status` | Get Entra ID configuration status | None |

**Entra ID Flow:**
1. Client calls `GET /auth/entra/login?redirect_url=https://app.example.com/dashboard`
2. Client redirects user to returned `auth_url`
3. User authenticates with Microsoft
4. Microsoft redirects to callback with authorization code
5. Callback redirects to `redirect_url` with `auth_code` parameter
6. Client calls `POST /auth/entra/exchange?auth_code=<code>` to get JWT

**Router:** `users.py` | **Tag:** Users

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/users/change-password` | Change own password | Bearer |
| `POST` | `/users/reset-password-request` | Request password reset | None |
| `POST` | `/users/reset-password-with-code` | Reset with verification code | None |

**Router:** `admin.py` | **Tag:** Admin

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/admin/users` | List all users | Admin |
| `GET` | `/admin/users/{user_id}` | Get specific user | Admin |
| `POST` | `/admin/users` | Create user | Admin |
| `PUT` | `/admin/users/{user_id}` | Update user | Admin |
| `DELETE` | `/admin/users/{user_id}` | Delete user | Admin |
| `POST` | `/admin/users/{user_id}/reset-password` | Reset user password | Admin |
| `GET` | `/admin/audit-log` | Get audit log entries | Admin |
| `GET` | `/admin/audit-log/event-types` | List audit event types | Admin |
| `GET` | `/admin/audit-log/categories` | List audit categories | Admin |

---

### Price Data & Analytics

**Router:** `price_checks.py` | **Tag:** Price Data

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/price-checks` | Query price checks with filters | Read |
| `GET` | `/price-checks/latest/{theater_name}` | Latest prices for a theater | Read |
| `GET` | `/price-history/{theater_name}` | Price history for a theater | Read |
| `GET` | `/price-comparison` | Cross-theater price comparison | Read |

**Router:** `analytics.py` | **Tag:** Analytics

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/analytics/dashboard-stats` | Dashboard statistics | Read |
| `GET` | `/analytics/scrape-activity` | Scrape activity timeline | Read |
| `GET` | `/analytics/plf-distribution` | PLF format distribution | Read |
| `GET` | `/analytics/price-trends` | Price trend analysis | Read |

**Router:** `price_tiers.py` | **Tag:** Price Tiers

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/price-tiers/discover/{theater_name}` | Discover pricing tiers | Read |
| `GET` | `/price-tiers/discover-all` | Discover tiers for all theaters | Read |
| `GET` | `/price-tiers/discount-days/{theater_name}` | Detect discount day patterns | Read |
| `GET` | `/price-tiers/recommendations` | Scrape schedule recommendations | Read |
| `GET` | `/price-tiers/analyze/{theater_name}` | Full pricing analysis | Read |
| `POST` | `/price-tiers/save-baselines` | Save discovered tiers as baselines | Operator |
| `GET` | `/price-tiers/compare-discount-programs` | Compare discount programs | Read |

---

### Price Alerts & Surge Detection

**Router:** `price_alerts.py` | **Tag:** Price Alerts

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/price-alerts` | List alerts (filterable) | Read |
| `GET` | `/price-alerts/summary` | Alert summary statistics | Read |
| `GET` | `/price-alerts/config` | Get alert configuration | Read |
| `PUT` | `/price-alerts/acknowledge-bulk` | Acknowledge selected alerts | Operator |
| `PUT` | `/price-alerts/acknowledge-all` | Acknowledge ALL pending alerts | Operator |
| `GET` | `/price-alerts/{alert_id}` | Get specific alert | Read |
| `PUT` | `/price-alerts/{alert_id}/acknowledge` | Acknowledge single alert | Operator |
| `PUT` | `/price-alerts/config` | Update alert configuration | Admin |
| `POST` | `/price-alerts/test-webhook` | Test webhook delivery | Admin |

Alert types: `price_increase`, `price_decrease`, `surge_detected`, `new_offering`, `discontinued`

**Price Baselines** (same router)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/price-baselines` | List price baselines | Read |
| `POST` | `/price-baselines` | Create baseline | Operator |
| `GET` | `/price-baselines/coverage` | Baseline coverage analysis | Read |
| `PUT` | `/price-baselines/{baseline_id}` | Update baseline | Operator |
| `DELETE` | `/price-baselines/{baseline_id}` | Delete baseline | Admin |
| `GET` | `/price-baselines/discover` | Discover baselines from data | Read |
| `POST` | `/price-baselines/refresh` | Refresh all baselines with latest price data | Operator |
| `POST` | `/price-baselines/guarded-refresh` | Guarded refresh with drift protection (flags >15% changes) | Operator |
| `GET` | `/price-baselines/health` | Data health dashboard (freshness, staleness, normalization, metadata) | Read |
| `POST` | `/price-baselines/plf-calibration` | Refresh PLF calibration thresholds from Fandango data | Operator |
| `GET` | `/price-baselines/analyze` | Analyze baseline data | Read |
| `GET` | `/price-baselines/premium-formats` | Premium format baselines | Read |

**Surge Scanner** (same router)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/surge-scanner/advance` | Scan advance dates for surge pricing | Read |
| `GET` | `/surge-scanner/new-films` | Monitor new films for surge pricing | Read |

---

### Baselines & Coverage

**Router:** `price_alerts.py` (continued) | **Tags:** Baseline Browser, Coverage Gaps

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/baselines/markets` | Market-level baseline summary | Read |
| `GET` | `/baselines/market-detail` | Detailed market baselines | Read |
| `GET` | `/baselines/theaters/{theater_name}` | Theater baselines | Read |
| `GET` | `/baselines/coverage-gaps` | All coverage gaps | Read |
| `GET` | `/baselines/coverage-gaps/{theater_name}` | Theater coverage gaps | Read |
| `GET` | `/baselines/coverage-hierarchy` | Full coverage hierarchy | Read |
| `GET` | `/baselines/coverage-market/{director}/{market}` | Market coverage detail | Read |
| `GET` | `/baselines/gap-fill/{theater_name}` | Propose gap fills from available data | Admin |
| `POST` | `/baselines/gap-fill/{theater_name}/apply` | Apply gap fill proposals as baselines | Admin |
| `GET` | `/baselines/compare-sources` | Compare Fandango vs EntTelligence | Read |
| `POST` | `/baselines/deduplicate` | Remove duplicate baselines | Operator |

---

### EntTelligence Baselines

**Router:** `price_alerts.py` (continued) | **Tag:** EntTelligence Baselines

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/enttelligence-baselines/discover` | Discover baselines from EntTelligence data | Read |
| `POST` | `/enttelligence-baselines/refresh` | Refresh EntTelligence baselines | Operator |
| `GET` | `/enttelligence-baselines/analyze` | Analyze EntTelligence prices | Read |
| `GET` | `/enttelligence-baselines/circuits` | List EntTelligence circuits | Read |
| `GET` | `/enttelligence-baselines/circuit/{circuit_name}` | Get baselines for specific circuit | Read |
| `GET` | `/enttelligence-baselines/event-cinema` | Analyze event cinema pricing | Read |
| `GET` | `/enttelligence-baselines/event-cinema/keywords` | Get event cinema keywords | Read |

---

### Fandango Baselines

**Router:** `price_alerts.py` (continued) | **Tag:** Fandango Baselines

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/fandango-baselines/discover` | Discover baselines from Fandango data | Read |
| `GET` | `/fandango-baselines/theater/{theater_name}` | Analyze pricing for a theater | Read |
| `GET` | `/fandango-baselines/discount-days` | Detect discount day patterns | Read |
| `GET` | `/fandango-baselines/theaters` | List theaters with Fandango data | Read |

---

### Market Baselines

**Router:** `price_alerts.py` (continued) | **Tag:** Market Baselines

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/market-baselines/stats` | Market baseline statistics | Read |
| `GET` | `/market-baselines/plan` | Get market scrape plan | Read |
| `POST` | `/market-baselines/scrape` | Trigger market baseline scrape | Operator |
| `GET` | `/market-baselines/scrape/{job_id}` | Get market scrape job status | Read |
| `POST` | `/market-baselines/scrape/{job_id}/cancel` | Cancel market baseline scrape | Operator |

---

### Discount Programs

**Router:** `price_alerts.py` (continued) | **Tag:** Discount Programs

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/discount-programs` | List all discount programs | Read |
| `POST` | `/discount-programs` | Create a new discount program | Operator |
| `PUT` | `/discount-programs/{program_id}` | Update a discount program | Operator |
| `DELETE` | `/discount-programs/{program_id}` | Delete a discount program | Admin |

---

### Data Sources

**Router:** `enttelligence.py` | **Tag:** EntTelligence | **Prefix:** `/enttelligence`

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/enttelligence/sync` | Sync EntTelligence pricing data | Operator |
| `GET` | `/enttelligence/cache/stats` | Cache statistics | Read |
| `POST` | `/enttelligence/cache/lookup` | Lookup specific cache entries | Read |
| `POST` | `/enttelligence/cache/cleanup` | Clean stale cache entries | Admin |
| `GET` | `/enttelligence/status` | Sync status | Read |

**Router:** `scrapes.py` | **Tag:** Scrapes

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/scrapes/active-theaters` | Currently active scrape targets | Read |
| `POST` | `/scrapes/check-collision` | Check for scrape conflicts | Read |
| `GET` | `/scrapes/jobs` | List recent scrape jobs | Read |
| `POST` | `/scrapes/trigger` | Trigger a full scrape job | Operator |
| `GET` | `/scrapes/{job_id}/status` | Get job status | Read |
| `POST` | `/scrapes/{job_id}/cancel` | Cancel a running job | Operator |
| `GET` | `/scrapes/search-theaters/fandango` | Search Fandango for theaters | Read |
| `GET` | `/scrapes/search-theaters/cache` | Search local theater cache | Read |
| `POST` | `/scrapes/fetch-showtimes` | Fetch showtimes for a theater | Operator |
| `POST` | `/scrapes/estimate-time` | Estimate scrape duration | Read |
| `POST` | `/scrapes/operating-hours` | Scrape operating hours | Operator |
| `POST` | `/scrapes/save` | Save scraped data to database | Operator |
| `POST` | `/scrape_runs` | Create a scrape run record | Operator |
| `POST` | `/scrapes/verify-prices` | Verify scraped prices against EntTelligence cache | Operator |
| `GET` | `/scrapes/{job_id}/verification` | Get price verification results for a scrape | Read |
| `POST` | `/scrapes/compare-counts` | Compare showtime counts across sources | Read |
| `POST` | `/scrapes/compare-showtimes` | Verify Fandango showtimes against EntTelligence | Read |
| `POST` | `/scrapes/zero-showtime-analysis` | Detect theaters with zero showtimes | Read |
| `POST` | `/scrapes/mark-theater-status` | Mark theater Fandango availability | Operator |

**Router:** `scrape_sources.py` | **Tag:** Scrape Sources

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/scrape-sources` | List configured scrape sources | Read |
| `POST` | `/scrape-sources` | Create new scrape source | Admin |
| `GET` | `/scrape-sources/{source_id}` | Get specific source | Read |
| `PUT` | `/scrape-sources/{source_id}` | Update scrape source | Admin |
| `DELETE` | `/scrape-sources/{source_id}` | Delete scrape source | Admin |
| `POST` | `/scrape-jobs/trigger/{source_id}` | Trigger job from source | Operator |
| `GET` | `/scrape-jobs/{run_id}/status` | Get job run status | Read |
| `GET` | `/scrape-jobs` | List scrape job runs | Read |

---

### Circuit Intelligence

**Router:** `circuit_benchmarks.py` | **Tag:** Circuit Benchmarks

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/circuit-benchmarks` | List circuit benchmarks | Read |
| `GET` | `/circuit-benchmarks/weeks` | Weekly benchmark summaries | Read |
| `GET` | `/circuit-benchmarks/{week_ending_date}` | Specific week benchmarks | Read |
| `POST` | `/circuit-benchmarks/sync` | Sync from EntTelligence | Operator |
| `GET` | `/circuit-benchmarks/compare` | Compare circuits | Read |

**Router:** `company_profiles.py` | **Tag:** Company Profiles | **Prefix:** `/company-profiles`

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/company-profiles` | List all circuit profiles | Read |
| `GET` | `/company-profiles/{circuit_name}` | Get circuit profile | Read |
| `POST` | `/company-profiles/discover` | Discover pricing profile | Operator |
| `POST` | `/company-profiles/discover-all` | Discover all profiles | Operator |
| `DELETE` | `/company-profiles/{circuit_name}` | Delete profile | Admin |
| `POST` | `/company-profiles/cleanup-duplicates` | Remove duplicates | Admin |
| `GET` | `/company-profiles/{circuit_name}/discount-day-diagnostic` | Discount day analysis | Read |
| `GET` | `/company-profiles/{circuit_name}/discount-programs` | List circuit discount programs | Read |
| `POST` | `/company-profiles/{circuit_name}/discount-programs` | Create circuit discount program | Operator |
| `DELETE` | `/company-profiles/{circuit_name}/discount-programs/{program_id}` | Delete circuit discount program | Admin |
| `GET` | `/company-profiles/{circuit_name}/gaps` | List data coverage gaps | Read |
| `POST` | `/company-profiles/{circuit_name}/gaps/{gap_id}/resolve` | Resolve a profile data gap | Operator |
| `GET` | `/company-profiles/{circuit_name}/versions` | List profile version history | Read |
| `GET` | `/company-profiles/{circuit_name}/data-coverage` | Data coverage report | Read |

**Router:** `presales.py` | **Tag:** Presales

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/presales` | Get presale snapshots | Read |
| `GET` | `/presales/circuits` | List circuits with presale data and aggregate statistics | Read |
| `GET` | `/presales/films` | List films with presale data | Read |
| `GET` | `/presales/{film_title}` | Presale trajectory for film | Read |
| `GET` | `/presales/velocity/{film_title}` | Velocity metrics | Read |
| `GET` | `/presales/compare` | Compare film presales | Read |
| `GET` | `/presales/compliance` | Presale posting compliance analysis (advance posting by circuit) | Read |
| `GET` | `/presales/heatmap-data` | Per-theater presale data with coordinates for heatmap visualization | Read |
| `GET` | `/presales/demand-lookup` | Per-showtime demand data (capacity, tickets sold, fill rate) | Read |
| `POST` | `/presales/sync` | Sync presale data | Operator |

**Demand Lookup** query params: `theaters` (comma-separated, required), `date_from` (YYYY-MM-DD, required), `date_to` (optional), `films` (comma-separated, optional). Returns `DemandMetric[]` with `theater_name`, `film_title`, `play_date`, `showtime`, `format`, `capacity`, `available`, `tickets_sold`, `fill_rate_pct`, `price`.

**Presale Watches** (same router)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/presales/watches` | List all presale watch configurations | Read |
| `POST` | `/presales/watches` | Create a new presale watch | Operator |
| `PUT` | `/presales/watches/{watch_id}` | Update a presale watch (toggle enabled, change threshold) | Operator |
| `DELETE` | `/presales/watches/{watch_id}` | Delete a presale watch and its notifications | Operator |
| `GET` | `/presales/watches/notifications` | List watch notifications (optional `unread_only` param) | Read |
| `PUT` | `/presales/watches/notifications/{notification_id}/read` | Mark a notification as read | Operator |

Watch alert types: `velocity_drop`, `velocity_spike`, `milestone`, `days_out`, `market_share`

---

### Theater Management

**Router:** `resources.py` | **Tag:** Resources

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/theaters` | List all theaters with metadata and showtime counts | Read |
| `GET` | `/films` | List films with showtime information | Read |
| `POST` | `/films/enrich` | Enrich all films missing metadata from OMDb | Operator |
| `POST` | `/films/enrich-single` | Enrich a single film from OMDb | Operator |
| `GET` | `/scrape-runs` | Get recent scrape run history with status and metrics | Read |
| `GET` | `/showtimes/search` | Flexible showtime search with multiple filter options | Read |
| `GET` | `/pricing` | Get ticket pricing data with optional filters | Read |

**Router:** `markets.py` | **Tag:** Markets

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/markets` | List all markets | Read |

**Router:** `films.py` | **Tag:** Films

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/films` | List all films with metadata | Read |
| `GET` | `/films/{film_title}` | Get specific film metadata | Read |
| `POST` | `/films/{film_title}/enrich` | Enrich film via OMDb | Operator |
| `POST` | `/films/discover/fandango` | Discover films from Fandango | Operator |

**Router:** `theater_amenities.py` | **Tag:** Theater Amenities

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/theater-amenities` | List all amenity records | Read |
| `GET` | `/theater-amenities/summary` | Amenities summary | Read |
| `GET` | `/theater-amenities/{amenity_id}` | Get specific amenity | Read |
| `POST` | `/theater-amenities` | Create amenity record | Operator |
| `PUT` | `/theater-amenities/{amenity_id}` | Update amenity | Operator |
| `DELETE` | `/theater-amenities/{amenity_id}` | Delete amenity | Admin |
| `POST` | `/theater-amenities/discover` | Discover amenities for theater | Operator |
| `POST` | `/theater-amenities/discover-all` | Discover for all theaters | Operator |
| `GET` | `/theater-amenities/format-summary` | Format distribution summary | Read |
| `GET` | `/theater-amenities/screen-counts/{theater_name}` | Estimated screen counts | Read |

**Router:** `theater_onboarding.py` | **Tag:** Theater Onboarding | **Prefix:** `/theater-onboarding`

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/theater-onboarding/status/{theater_name}` | Get onboarding status | Read |
| `GET` | `/theater-onboarding/pending` | List pending theaters | Read |
| `POST` | `/theater-onboarding/start` | Start onboarding | Operator |
| `POST` | `/theater-onboarding/bulk-start` | Bulk start onboarding | Operator |
| `POST` | `/theater-onboarding/{theater_name}/scrape` | Record initial scrape for theater | Operator |
| `POST` | `/theater-onboarding/{theater_name}/discover` | Discover theater baselines | Operator |
| `POST` | `/theater-onboarding/{theater_name}/link` | Link theater to company profile | Operator |
| `POST` | `/theater-onboarding/{theater_name}/confirm` | Confirm baseline data for theater | Operator |
| `GET` | `/theater-onboarding/{theater_name}/coverage` | Get data coverage indicators | Read |
| `GET` | `/theater-onboarding/market/{market}` | Theaters by market | Read |
| `GET` | `/theater-onboarding/amenities/missing` | Theaters missing amenities | Read |
| `POST` | `/theater-onboarding/{theater_name}/amenities` | Discover theater amenities | Operator |
| `POST` | `/theater-onboarding/amenities/backfill` | Backfill amenity data | Operator |

**Router:** `alternative_content.py` | **Tag:** Alternative Content | **Prefix:** `/alternative-content`

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/alternative-content` | List alternative content films | Read |
| `GET` | `/alternative-content/{film_id}` | Get specific AC film | Read |
| `POST` | `/alternative-content` | Create AC film entry | Operator |
| `PUT` | `/alternative-content/{film_id}` | Update AC film | Operator |
| `DELETE` | `/alternative-content/{film_id}` | Delete AC film | Admin |
| `POST` | `/alternative-content/detect` | Run AC detection | Operator |
| `GET` | `/alternative-content/detect/preview` | Preview detection | Read |
| `GET` | `/alternative-content/check/{film_title}` | Check if film is AC | Read |
| `GET` | `/alternative-content/circuit-pricing` | Circuit AC pricing summary | Read |
| `GET` | `/alternative-content/circuit-pricing/{circuit_name}` | Get pricing for specific circuit | Read |
| `PUT` | `/alternative-content/circuit-pricing/{circuit_name}` | Update circuit AC pricing | Operator |

---

### Reports

**Router:** `reports.py` | **Tag:** Reports

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/reports/selection-analysis` | Generate selection analysis | Read |
| `POST` | `/reports/showtime-view/html` | Generate showtime HTML view | Read |
| `POST` | `/reports/showtime-view/pdf` | Generate showtime PDF | Read |
| `GET` | `/reports/daily-lineup` | Get daily lineup data | Read |
| `GET` | `/reports/operating-hours` | Get operating hours comparison | Read |
| `GET` | `/reports/plf-formats` | Get PLF format data | Read |
| `POST` | `/reports/scrape-results/pdf` | Generate PDF summary of scrape results | Read |
| `GET` | `/reports/box-office-board` | Generate box office board for digital signage or printing | Read |

Query params: `theater` (required), `date` (YYYY-MM-DD, required), `resolution` (720p/1080p/4k/letter), `output_format` (html/image)

---

### Schedule Monitoring

**Router:** `schedule_monitor.py` | **Tag:** Schedule Alerts

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/schedule-alerts` | List schedule alerts | Read |
| `GET` | `/schedule-alerts/summary` | Alert summary | Read |
| `PUT` | `/schedule-alerts/{alert_id}/acknowledge` | Acknowledge alert | Operator |
| `POST` | `/schedule-alerts/acknowledge-bulk` | Bulk acknowledge | Operator |
| `POST` | `/schedule-monitor/check` | Trigger schedule check | Operator |
| `GET` | `/schedule-monitor/status` | Monitor status | Read |
| `GET` | `/schedule-monitor/config` | Get monitor configuration | Read |
| `PUT` | `/schedule-monitor/config` | Update monitor config | Admin |
| `POST` | `/schedule-baselines/snapshot` | Create schedule baseline snapshot | Operator |
| `POST` | `/schedule-posting/check` | Trigger schedule posting check | Operator |
| `GET` | `/schedule-posting/summary` | Get schedule posting summary | Read |
| `GET` | `/schedule-posting/pending-dates` | Get pending posting dates | Read |

---

### Settings

**Router:** `settings.py` | **Tag:** Settings | **Prefix:** `/settings`

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/settings/tax-config` | Get tax estimation configuration for EntTelligence price adjustment | Read |
| `PUT` | `/settings/tax-config` | Update tax estimation configuration | Admin |

---

### System & Operations

**Router:** `system.py` | **Tag:** System

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/system/health` | Detailed system health check | Admin |
| `POST` | `/system/circuits/reset` | Reset all circuit breakers | Admin |
| `POST` | `/system/circuits/{name}/reset` | Reset specific circuit | Admin |
| `POST` | `/system/circuits/{name}/open` | Force-open circuit breaker | Admin |
| `POST` | `/system/maintenance/retention` | Run data retention | Admin |
| `GET` | `/system/maintenance/status` | Maintenance status | Admin |
| `GET` | `/system/tasks/{task_id}` | Get background task status | Read |

**Router:** `cache.py` | **Tag:** Cache

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/cache/status` | Cache health status | Read |
| `GET` | `/cache/theaters` | Full theater cache with metadata | Read |
| `GET` | `/cache/markets` | Cached market data | Read |
| `POST` | `/cache/refresh` | Force cache refresh | Operator |
| `GET` | `/cache/backup` | Get cache backup status | Admin |
| `POST` | `/cache/maintenance` | Run cache maintenance operations | Admin |
| `GET` | `/cache/maintenance/health` | Check cache health status | Read |
| `GET` | `/cache/maintenance/history` | Maintenance operation history | Read |
| `POST` | `/cache/maintenance/run` | Run maintenance with specific options | Admin |
| `GET` | `/cache/repair-queue/status` | Repair queue status | Read |
| `GET` | `/cache/repair-queue/jobs` | Repair queue jobs | Read |
| `GET` | `/cache/repair-queue/failed` | List failed repair jobs | Read |
| `POST` | `/cache/repair-queue/reset` | Reset a repair job | Operator |
| `DELETE` | `/cache/repair-queue/failed` | Clear all failed repair jobs | Admin |
| `POST` | `/cache/repair-queue/process` | Process repair queue | Operator |
| `GET` | `/theaters/unmatched` | List unmatched theaters | Read |
| `POST` | `/theaters/match` | Match an unmatched theater to a profile | Operator |
| `POST` | `/theaters/discover` | Discover theater URL from name | Operator |
| `GET` | `/theaters/discover/{theater_name}` | Discover theater URL via GET | Operator |

**Router:** `tasks.py` | **Tag:** Tasks

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/tasks` | List scheduled tasks | Read |

**Router:** `market_context.py` | **Tag:** Market Context | **Prefix:** `/market-context`

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/market-context/theaters` | Theater metadata | Read |
| `GET` | `/market-context/events` | Market events | Read |
| `GET` | `/market-context/operating-hours` | Get theater operating hours | Read |
| `POST` | `/market-context/operating-hours` | Update theater operating hours | Operator |
| `POST` | `/market-context/sync/theaters` | Sync theater metadata | Operator |
| `GET` | `/market-context/theaters/heatmap-data` | Heatmap visualization data | Read |

---

### Metrics

**Router:** `metrics.py` | **Tag:** Metrics

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/metrics` | Prometheus-format metrics endpoint | None |

---

## Rate Limiting

| Tier | Requests/min | Burst |
|------|-------------|-------|
| Free | 60 | 10 |
| Premium | 300 | 50 |
| Enterprise | Unlimited | -- |

Rate limit headers: `X-RateLimit-Remaining`, `X-RateLimit-Reset`

---

## Environments

| Environment | URL |
|-------------|-----|
| Production | `https://app-pricescout-prod.azurewebsites.net/api/v1` |
| Development | `https://app-pricescout-dev.azurewebsites.net/api/v1` |
| Local | `http://localhost:8000/api/v1` |

---

*Generated February 4, 2026. For the most up-to-date spec, use the interactive Swagger UI at `/api/v1/docs`.*
