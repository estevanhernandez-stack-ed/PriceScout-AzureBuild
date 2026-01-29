# PriceScout React

Competitive price intelligence platform for theater ticket pricing.

## Tech Stack

**Backend:**
- Python 3.11+
- FastAPI
- SQLAlchemy ORM
- Azure SQL Database

**Frontend:**
- React 18 + TypeScript
- Vite
- TanStack Query (data fetching)
- Zustand (state management)
- Tailwind CSS + shadcn/ui

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Azure SQL Database connection string

### 1. Backend Setup

```bash
# From this directory (apps/pricescout-react)

# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Or (Windows CMD)
.venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env with your database connection string
```

### 2. Frontend Setup

```bash
cd frontend
npm install
```

### 3. Start Development Servers

**Option A: Use the startup script**
```bash
# From project root
start_dev.bat
```

**Option B: Manual startup (two terminals)**

Terminal 1 - Backend:
```bash
# From apps/pricescout-react
.venv\Scripts\activate
uvicorn api.main:app --reload --port 8000
```

Terminal 2 - Frontend:
```bash
# From apps/pricescout-react/frontend
npm run dev
```

## URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/api/v1/docs |
| API Docs (ReDoc) | http://localhost:8000/api/v1/redoc |

> **Note:** The Vite dev server on port 3000 proxies `/api` requests to the backend on port 8000. Always browse the app at `http://localhost:3000`, not the API port directly.

## Project Structure

```
pricescout-react/
├── api/                        # FastAPI routes
│   ├── main.py                 # App entry point
│   └── routers/                # Endpoint modules
│       ├── price_alerts.py     # Baselines, alerts, discovery
│       ├── scrapes.py          # Scrape job management
│       ├── price_checks.py     # Price data queries
│       └── ...
├── app/                        # Business logic
│   ├── db_models.py            # SQLAlchemy models
│   ├── db_session.py           # Database connection
│   ├── alert_service.py        # Price alert engine
│   ├── baseline_discovery.py   # Fandango baseline discovery
│   ├── enttelligence_baseline_discovery.py
│   ├── scraper.py              # Price scraping
│   └── ...
├── frontend/                   # React frontend
│   ├── src/
│   │   ├── pages/              # Route components
│   │   ├── components/         # Reusable UI components
│   │   │   ├── baselines/      # Baseline-related components
│   │   │   └── ui/             # shadcn/ui components
│   │   ├── hooks/api/          # TanStack Query hooks
│   │   ├── stores/             # Zustand stores
│   │   └── lib/                # Utilities
│   └── package.json
├── tests/                      # Test suite
├── migrations/                 # Database migrations
├── requirements.txt            # Python dependencies
└── .env.example                # Environment template
```

## Key Features

### Price Baselines Mode (Sprint 5 - Current)

The Price Baselines page has four main tabs:

1. **Overview Tab** - User-centric dashboard showing:
   - Total baselines count with health indicators
   - Theater coverage metrics
   - Recent activity timeline
   - Quick actions (Discover, Deduplicate, Export)

2. **Discover Tab** - Baseline discovery from scraped data:
   - Fandango discovery (with actual daypart data)
   - EntTelligence discovery (derived dayparts)
   - Day-of-week splitting for discount day detection

3. **Baseline Details Tab** - Granular baseline management:
   - Filter by theater, ticket type, format, day of week
   - Sort by any column
   - **Deduplicate button** - Remove duplicate baselines
   - Export to CSV

4. **Company Profiles Tab** - Circuit-level configuration:
   - Discount day programs (e.g., "$5 Tuesdays")
   - Premium format definitions

### Other Features

- **CompSnipe Mode**: Real-time competitive price monitoring
- **Daily Lineup**: Theater showtime management
- **Market Mode**: Market-level analysis
- **Price Alerts**: Automated surge/drop notifications
- **Scrape Management**: Scheduled and on-demand scraping

## API Endpoints (Key)

| Endpoint | Description |
|----------|-------------|
| `GET /price-baselines` | List all baselines |
| `POST /baselines/deduplicate` | Remove duplicate baselines |
| `GET /fandango-baselines/discover` | Discover from Fandango data |
| `GET /enttelligence/baselines/discover` | Discover from EntTelligence data |
| `GET /price-checks` | Query price data |
| `POST /scrapes/trigger` | Trigger a new scrape |

## Recent Development (Sprint 5)

### UserCentricOverview Component
- Replaced generic overview with user-focused dashboard
- Shows baseline health, coverage, and recent activity
- Quick action buttons for common operations

### Baseline Deduplication
- Added `POST /baselines/deduplicate` endpoint
- Frontend "Check Duplicates" / "Remove Duplicates" buttons
- Deduplicates by: theater, ticket_type, format, day_of_week, daypart, day_type
- Keeps most recent baseline per unique combination

### Baseline Save Fix
- Fixed `save_discovered_baselines()` to check ALL key fields
- Prevents future duplicates from being created
- Proper NULL handling in SQLAlchemy filters

## Environment Variables

```env
# Database
DATABASE_URL=mssql+pyodbc://user:pass@server/database?driver=ODBC+Driver+18+for+SQL+Server

# Optional: Azure Key Vault
AZURE_KEY_VAULT_URL=https://your-vault.vault.azure.net/

# Optional: OMDB for film enrichment
OMDB_API_KEY=your_key

# Frontend API URL (for production builds)
VITE_API_URL=http://localhost:8000
```

## Testing

```bash
# Backend tests
pytest

# With coverage
pytest --cov=app --cov=api

# Frontend tests
cd frontend
npm test

# Type checking
npm run typecheck
```

## Troubleshooting

### "No Company Assigned" error
- Admin users may have null `company` field
- The app defaults to 'Marcus Theatres' for admins
- Check user's `default_company` or `company_id` in database

### Duplicate baselines showing
1. Go to **Baseline Details** tab
2. Click **Check Duplicates**
3. If duplicates found, click **Remove Duplicates**

### Database connection issues
- Ensure ODBC Driver 18 is installed
- Check connection string format in `.env`
- Verify firewall allows connection to Azure SQL

## License

Proprietary - Internal Use Only
