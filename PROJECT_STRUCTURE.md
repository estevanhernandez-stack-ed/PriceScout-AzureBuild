# PriceScout - Complete Project Structure

## Quick Start

```bash
# One command to start everything:
start_dev.bat
```

This opens two terminal windows:
- **API** at http://localhost:8000 (FastAPI)
- **Frontend** at http://localhost:3000 (React)

---

## Required Files for Full Stack

### Backend (FastAPI + Python)

```
Price Scout/
├── .env                      # Environment variables (DB connection, API keys)
├── requirements.txt          # Python dependencies
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   └── routers/
│       ├── __init__.py
│       ├── markets.py
│       ├── price_alerts.py   # Alert endpoints
│       ├── price_checks.py
│       ├── reports.py
│       ├── scrape_sources.py
│       ├── scrapes.py        # Scrape job endpoints
│       ├── tasks.py
│       └── users.py
├── app/
│   ├── __init__.py
│   ├── config.py            # Configuration
│   ├── db_models.py         # SQLAlchemy ORM models
│   ├── db_session.py        # Database connection
│   ├── db_adapter.py        # Data access layer
│   ├── alert_service.py     # Price alert logic
│   ├── baseline_discovery.py # Auto-baseline detection
│   ├── notification_service.py # Webhooks/email
│   ├── omdb_client.py       # Film metadata API
│   └── utils.py             # Utilities
└── tests/                   # Test suite
    ├── conftest.py
    ├── test_api/
    └── test_services/
```

### Frontend (React + TypeScript)

```
frontend-react/
├── package.json             # Node dependencies
├── vite.config.ts           # Dev server + API proxy
├── tsconfig.json            # TypeScript config
├── tailwind.config.js       # Styling
├── index.html               # Entry HTML
└── src/
    ├── main.tsx             # React entry
    ├── App.tsx              # Routes
    ├── types/index.ts       # TypeScript interfaces
    ├── services/            # API client layer
    │   ├── api.ts           # Axios setup
    │   ├── alerts.ts
    │   ├── baselines.ts
    │   ├── prices.ts
    │   └── scrapes.ts
    ├── components/layout/   # Sidebar, Header
    ├── pages/               # Dashboard, Prices, Alerts, etc.
    └── styles/index.css     # Tailwind styles
```

---

## Setup Instructions

### 1. Backend Setup (one time)

```bash
# Create virtual environment
python -m venv .venv

# Activate it
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
copy .env.example .env
# Edit .env with your database connection string
```

### 2. Frontend Setup (one time)

```bash
cd frontend-react
npm install
```

### 3. Run Both

```bash
# From project root:
start_dev.bat
```

Or manually in separate terminals:

```bash
# Terminal 1 - Backend
.venv\Scripts\activate
uvicorn api.main:app --reload --port 8000

# Terminal 2 - Frontend
cd frontend-react
npm run dev
```

---

## Key URLs

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | React app |
| API | http://localhost:8000 | FastAPI backend |
| API Docs | http://localhost:8000/docs | Swagger UI |
| API Redoc | http://localhost:8000/redoc | ReDoc |

---

## Environment Variables (.env)

```env
# Database
DATABASE_URL=mssql+pyodbc://...
CURRENT_COMPANY_ID=1

# API Keys
OMDB_API_KEY=your_key_here

# Optional
LOG_LEVEL=INFO
```

---

## Git Upload

To upload a clean version, include these folders:

```
Price Scout/
├── api/                 # Backend API routes
├── app/                 # Backend business logic
├── frontend-react/      # React frontend (new)
├── tests/               # Test suite
├── migrations/          # Database migrations
├── .env.example         # Environment template
├── requirements.txt     # Python deps
├── start_dev.bat        # Dev startup script
└── README.md            # Project docs
```

Exclude (via .gitignore):
- `.venv/` - Python virtual environment
- `node_modules/` - Node packages
- `.env` - Secrets
- `__pycache__/` - Python cache
- `.coverage` - Test coverage data
