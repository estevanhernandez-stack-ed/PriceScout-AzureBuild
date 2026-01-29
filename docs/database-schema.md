# PriceScout: Database Schema Export

**Application:** PriceScout - Competitive Price Scraping Tool
**Export Date:** December 3, 2025
**Database:** Azure SQL (MSSQL) / SQLite (local dev)
**ORM:** SQLAlchemy 2.0 (Python equivalent of EF Core)

---

## 1. List All Entities

PriceScout uses SQLAlchemy ORM with models defined in `app/db_models.py`:

```python
# From app/db_models.py - get_table_classes()
'Company': Company,
'User': User,
'AuditLog': AuditLog,
'ScrapeRun': ScrapeRun,
'Showing': Showing,
'Price': Price,
'Film': Film,
'OperatingHours': OperatingHours,
'UnmatchedFilm': UnmatchedFilm,
'IgnoredFilm': IgnoredFilm,
'UnmatchedTicketType': UnmatchedTicketType,
```

Additional tables from migrations:
- `scrape_sources` - Configurable scrape source management
- `price_alerts` - Price change alert tracking
- `alert_configurations` - Per-company alert settings
- `api_keys` - API key management for rate limiting
- `api_key_usage` - API usage tracking

Schedule Monitor tables (added January 2026):

- `schedule_baselines` - Snapshots of theater schedules for change detection
- `schedule_alerts` - Schedule change alerts (new films, showtimes, etc.)
- `schedule_monitor_config` - Per-company monitoring configuration

---

## 2. Entity Summary

| Entity | Table Name | Purpose | Key Relationships |
|--------|------------|---------|-------------------|
| Company | `companies` | Multi-tenant company isolation | Parent of users, scrape_runs, showings, prices, films |
| User | `users` | Application users with RBAC | FK to companies (2), owns scrape_runs, audit_logs |
| AuditLog | `audit_log` | Security audit trail | FK to users, companies |
| ScrapeRun | `scrape_runs` | Data collection sessions | FK to companies, users, scrape_sources; parent of prices |
| ScrapeSource | `scrape_sources` | Configurable scrape targets | FK to companies, users |
| Showing | `showings` | Theater screening schedules | FK to companies; parent of prices |
| Price | `prices` | Ticket pricing data | FK to companies, scrape_runs, showings |
| Film | `films` | Movie metadata (OMDB enriched) | FK to companies |
| OperatingHours | `operating_hours` | Theater daily schedules | FK to companies, scrape_runs |
| PriceAlert | `price_alerts` | Price change notifications | FK to companies, prices, showings, users |
| AlertConfiguration | `alert_configurations` | Per-company alert rules | FK to companies |
| ApiKey | `api_keys` | API key management | Standalone (no FK) |
| ApiKeyUsage | `api_key_usage` | API request logging | References api_keys by prefix |
| UnmatchedFilm | `unmatched_films` | Films failing OMDB matching | FK to companies |
| IgnoredFilm | `ignored_films` | Intentionally excluded films | FK to companies, users |
| UnmatchedTicketType | `unmatched_ticket_types` | Unparseable ticket descriptions | FK to companies |
| ScheduleBaseline | `schedule_baselines` | Theater schedule snapshots for change detection | FK to companies |
| ScheduleAlert | `schedule_alerts` | Schedule change notifications | FK to companies |
| ScheduleMonitorConfig | `schedule_monitor_config` | Per-company schedule monitoring settings | FK to companies |

**Total: 19 tables**

---

## 3. Shared Data References

PriceScout maintains its **own tables** rather than referencing `core.*` tables:

- [ ] Locations (core.Locations) - **NOT USED** - Uses own `showings.theater_name`
- [ ] Users (core.Users) - **NOT USED** - Uses own `users` table
- [ ] Divisions (core.Divisions) - **NOT USED**
- [x] Other: Own `companies` table for multi-tenancy

**Gap Identified:** PriceScout does not reference shared core data. This is documented as a known deviation in `GAP_ANALYSIS_COMPANY_DEPLOYMENT.md`.

**Mitigation:** The `competitive.*` schema views provide standardized naming for cross-platform compatibility:
- `competitive.ScrapeSources`
- `competitive.ScrapeJobs`
- `competitive.PriceChecks`
- `competitive.PriceHistory`
- `competitive.PriceAlerts`
- `competitive.MarketAnalysis`
- `competitive.PricingCategories`

---

## 4. Entity Details (Top 5 Most Important)

### ENTITY: Company
**TABLE:** `companies`
**PURPOSE:** Multi-tenant isolation - all data is scoped to a company

| Column | Type | Nullable | FK Reference |
|--------|------|----------|--------------|
| company_id | INT IDENTITY | No | PRIMARY KEY |
| company_name | NVARCHAR(255) | No | UNIQUE |
| created_at | DATETIME2 | Yes | — |
| is_active | BIT | Yes | — |
| settings | NVARCHAR(MAX) | Yes | — (JSON) |

**Indexes:** `idx_companies_active`, `idx_companies_name`

---

### ENTITY: User
**TABLE:** `users`
**PURPOSE:** Application users with role-based access (admin/manager/user)

| Column | Type | Nullable | FK Reference |
|--------|------|----------|--------------|
| user_id | INT IDENTITY | No | PRIMARY KEY |
| username | NVARCHAR(100) | No | UNIQUE |
| password_hash | NVARCHAR(255) | No | — |
| role | NVARCHAR(50) | No | — (CHECK: admin/manager/user) |
| company_id | INT | Yes | FK → companies.company_id |
| default_company_id | INT | Yes | FK → companies.company_id |
| home_location_type | NVARCHAR(50) | Yes | — (CHECK: director/market/theater) |
| home_location_value | NVARCHAR(255) | Yes | — |
| allowed_modes | NVARCHAR(MAX) | Yes | — (JSON array) |
| is_admin | BIT | Yes | — |
| must_change_password | BIT | Yes | — |
| reset_code | NVARCHAR(10) | Yes | — |
| reset_code_expiry | BIGINT | Yes | — |
| reset_attempts | INT | Yes | — |
| session_token | NVARCHAR(255) | Yes | — |
| session_token_expiry | BIGINT | Yes | — |
| created_at | DATETIME2 | Yes | — |
| last_login | DATETIME2 | Yes | — |
| is_active | BIT | Yes | — |

**Indexes:** `idx_users_username`, `idx_users_company`, `idx_users_role`, `idx_users_active`

---

### ENTITY: Showing
**TABLE:** `showings`
**PURPOSE:** Theater screening schedules with movie/time/format info

| Column | Type | Nullable | FK Reference |
|--------|------|----------|--------------|
| showing_id | INT IDENTITY | No | PRIMARY KEY |
| company_id | INT | No | FK → companies.company_id (CASCADE) |
| play_date | DATE | No | — |
| theater_name | NVARCHAR(255) | No | — |
| film_title | NVARCHAR(500) | No | — |
| showtime | NVARCHAR(20) | No | — |
| format | NVARCHAR(100) | Yes | — (2D/3D/IMAX/Dolby) |
| daypart | NVARCHAR(50) | Yes | — (matinee/evening/late_night) |
| is_plf | BIT | Yes | — (Premium Large Format) |
| ticket_url | NVARCHAR(MAX) | Yes | — |
| created_at | DATETIME2 | Yes | — |

**Constraints:** `UNIQUE (company_id, play_date, theater_name, film_title, showtime, format)`
**Indexes:** `idx_showings_company`, `idx_showings_theater_date`, `idx_showings_film`, `idx_showings_date`

---

### ENTITY: Price
**TABLE:** `prices`
**PURPOSE:** Ticket pricing data by type (Adult/Senior/Child/etc)

| Column | Type | Nullable | FK Reference |
|--------|------|----------|--------------|
| price_id | INT IDENTITY | No | PRIMARY KEY |
| company_id | INT | No | FK → companies.company_id (CASCADE) |
| run_id | INT | Yes | FK → scrape_runs.run_id (SET NULL) |
| showing_id | INT | Yes | FK → showings.showing_id |
| ticket_type | NVARCHAR(100) | No | — (Adult/Senior/Child/etc) |
| price | DECIMAL(6,2) | No | — (CHECK >= 0) |
| capacity | NVARCHAR(50) | Yes | — |
| play_date | DATE | Yes | — |
| scraped_at | DATETIME2 | Yes | — |
| created_at | DATETIME2 | Yes | — |

**Indexes:** `idx_prices_company`, `idx_prices_run`, `idx_prices_showing`, `idx_prices_date`

---

### ENTITY: PriceAlert
**TABLE:** `price_alerts`
**PURPOSE:** Track and notify on significant price changes

| Column | Type | Nullable | FK Reference |
|--------|------|----------|--------------|
| alert_id | INT IDENTITY | No | PRIMARY KEY |
| company_id | INT | No | FK → companies.company_id (CASCADE) |
| price_id | INT | Yes | FK → prices.price_id (SET NULL) |
| showing_id | INT | Yes | FK → showings.showing_id |
| theater_name | NVARCHAR(255) | No | — |
| film_title | NVARCHAR(500) | Yes | — |
| ticket_type | NVARCHAR(100) | Yes | — |
| format | NVARCHAR(100) | Yes | — |
| alert_type | NVARCHAR(50) | No | — (CHECK: price_increase/decrease/new/discontinued) |
| old_price | DECIMAL(6,2) | Yes | — |
| new_price | DECIMAL(6,2) | Yes | — |
| price_change_percent | DECIMAL(5,2) | Yes | — |
| triggered_at | DATETIME2 | No | — |
| play_date | DATE | Yes | — |
| is_acknowledged | BIT | Yes | — |
| acknowledged_by | INT | Yes | FK → users.user_id (SET NULL) |
| acknowledged_at | DATETIME2 | Yes | — |
| acknowledgment_notes | NVARCHAR(MAX) | Yes | — |
| notification_sent | BIT | Yes | — |
| notification_sent_at | DATETIME2 | Yes | — |

**Indexes:** `idx_price_alerts_company`, `idx_price_alerts_theater`, `idx_price_alerts_triggered`, `idx_price_alerts_unack` (filtered)

---

## 5. Naming Conventions Check

### Standard Conventions Expected:
- PascalCase for tables and columns
- Plural table names
- `Id` suffix for foreign keys
- `Is`/`Has` prefix for booleans
- `At` suffix for timestamps

### Compliance Assessment:

| Check | Status | Issues Found |
|-------|--------|--------------|
| PascalCase Entities | ❌ | Uses snake_case (Python standard) |
| Plural Tables | ✅ | companies, users, prices, showings, films |
| FK Convention | ⚠️ | `company_id` not `CompanyId` |
| Boolean Prefix | ⚠️ | `is_active`, `is_admin`, `is_plf` (snake_case) |
| Timestamp Suffix | ⚠️ | `created_at`, `last_login` (snake_case) |

### Non-Compliant Tables/Columns:

| Table | Issue | Expected | Actual |
|-------|-------|----------|--------|
| All tables | Case convention | PascalCase | snake_case |
| companies | Column naming | CompanyId | company_id |
| users | Column naming | UserId, IsAdmin, CreatedAt | user_id, is_admin, created_at |
| prices | Column naming | PriceId, TicketType | price_id, ticket_type |
| showings | Column naming | ShowingId, PlayDate | showing_id, play_date |
| price_alerts | Column naming | AlertId, IsAcknowledged | alert_id, is_acknowledged |

### Mitigation:
The `competitive.*` schema views provide PascalCase aliases for cross-platform compatibility:

```sql
-- Example: competitive.PriceAlerts view
SELECT
    alert_id AS Id,
    company_id AS CompanyId,
    is_acknowledged AS IsAcknowledged,
    triggered_at AS TriggeredAt
    ...
```

---

## 6. Complete Schema Diagram

```
                                    ┌─────────────────┐
                                    │   companies     │
                                    │─────────────────│
                                    │ company_id (PK) │
                                    │ company_name    │
                                    │ is_active       │
                                    │ settings (JSON) │
                                    └────────┬────────┘
                                             │
           ┌─────────────────────────────────┼─────────────────────────────────┐
           │                                 │                                 │
           ▼                                 ▼                                 ▼
┌──────────────────┐              ┌──────────────────┐              ┌──────────────────┐
│      users       │              │   scrape_runs    │              │    showings      │
│──────────────────│              │──────────────────│              │──────────────────│
│ user_id (PK)     │              │ run_id (PK)      │              │ showing_id (PK)  │
│ company_id (FK)  │───┐          │ company_id (FK)  │              │ company_id (FK)  │
│ username         │   │          │ source_id (FK)   │───┐          │ theater_name     │
│ password_hash    │   │          │ user_id (FK)     │───┘          │ film_title       │
│ role             │   │          │ mode             │              │ play_date        │
│ is_admin         │   │          │ status           │              │ showtime         │
└────────┬─────────┘   │          └────────┬─────────┘              │ format           │
         │             │                   │                        └────────┬─────────┘
         │             │                   │                                 │
         │             │                   ▼                                 │
         │             │     ┌──────────────────────┐                        │
         │             │     │   scrape_sources     │                        │
         │             │     │──────────────────────│                        │
         │             │     │ source_id (PK)       │                        │
         │             │     │ company_id (FK)      │                        │
         │             │     │ name                 │                        │
         │             │     │ source_type          │                        │
         │             │     │ base_url             │                        │
         │             │     │ is_active            │                        │
         │             │     └──────────────────────┘                        │
         │             │                                                     │
         │             │                   ┌─────────────────────────────────┘
         │             │                   │
         │             │                   ▼
         │             │        ┌──────────────────┐
         │             │        │     prices       │
         │             │        │──────────────────│
         │             │        │ price_id (PK)    │
         │             │        │ company_id (FK)  │
         │             │        │ run_id (FK)      │───────────────────┐
         │             │        │ showing_id (FK)  │───────────────────┘
         │             │        │ ticket_type      │
         │             │        │ price            │
         │             │        └────────┬─────────┘
         │             │                 │
         │             │                 ▼
         │             │      ┌──────────────────────┐
         │             └─────▶│    price_alerts      │
         │                    │──────────────────────│
         └───────────────────▶│ acknowledged_by (FK) │
                              │ company_id (FK)      │
                              │ price_id (FK)        │
                              │ showing_id (FK)      │
                              │ alert_type           │
                              │ old_price/new_price  │
                              └──────────────────────┘
```

---

## 7. Views

### DBO Schema Views

| View | Purpose |
|------|---------|
| `v_recent_scrapes` | Recent scrape runs with company/user info |
| `v_pending_alerts` | Unacknowledged alerts summary by theater |

### Competitive Schema Views (PascalCase aliases)

| View | Maps To | Purpose |
|------|---------|---------|
| `competitive.ScrapeSources` | scrape_sources | Scrape source configuration |
| `competitive.ScrapeJobs` | scrape_runs | Job execution history |
| `competitive.PriceChecks` | prices + showings | Combined price/showing data |
| `competitive.PriceHistory` | (computed) | Price changes over time |
| `competitive.PriceAlerts` | price_alerts | Alert notifications |
| `competitive.MarketAnalysis` | (computed) | Market positioning analysis |
| `competitive.PricingCategories` | (computed) | Distinct ticket types |

---

## 8. Migration Files

| File | Purpose | Tables Affected |
|------|---------|-----------------|
| `schema_mssql.sql` | Full Azure SQL schema | All 16 tables |
| `schema.sql` | SQLite schema (dev) | All core tables |
| `add_scrape_sources.sql` | Scrape source management | scrape_sources, scrape_runs |
| `add_price_alerts.sql` | Price alert tracking | price_alerts, alert_configurations |
| `add_competitive_schema_views.sql` | Platform-compliant views | 7 views in competitive schema |

---

## 9. Data Model Summary

```
PriceScout Database (Azure SQL)
├── dbo (default schema)
│   ├── companies              # Multi-tenant isolation
│   ├── users                  # RBAC user management
│   ├── audit_log              # Security audit trail
│   ├── scrape_sources         # Configurable scrape targets
│   ├── scrape_runs            # Scrape job execution
│   ├── showings               # Theater schedules
│   ├── prices                 # Ticket pricing
│   ├── films                  # OMDB movie metadata
│   ├── operating_hours        # Theater hours
│   ├── price_alerts           # Change notifications
│   ├── alert_configurations   # Alert rules
│   ├── api_keys               # API key management
│   ├── api_key_usage          # Usage tracking
│   ├── unmatched_films        # OMDB match failures
│   ├── ignored_films          # Excluded films
│   └── unmatched_ticket_types # Parse failures
│
└── competitive (views schema)
    ├── ScrapeSources          # PascalCase alias
    ├── ScrapeJobs             # PascalCase alias
    ├── PriceChecks            # PascalCase alias
    ├── PriceHistory           # Computed view
    ├── PriceAlerts            # PascalCase alias
    ├── MarketAnalysis         # Computed view
    └── PricingCategories      # Computed view
```

---

**Generated by:** Claude Code
**Source Files:**
- `app/db_models.py`
- `migrations/schema_mssql.sql`
- `migrations/add_scrape_sources.sql`
- `migrations/add_price_alerts.sql`
- `migrations/add_competitive_schema_views.sql`
