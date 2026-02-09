# PriceScout Development Guide

## Prerequisites

- Python 3.13+
- Node.js 20+
- PostgreSQL 16 (or SQLite for local dev)
- Playwright Chromium (`playwright install chromium`)

## Local Setup

```bash
# Clone and navigate
cd apps/pricescout-react

# Backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt
playwright install chromium

# Frontend
cd frontend
npm install
cd ..
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Database (SQLite for local dev)
DB_TYPE=sqlite

# Or PostgreSQL
# DATABASE_URL=postgresql://user:pass@localhost:5432/pricescout_db

# Auth (at least one must be true)
DB_AUTH_ENABLED=true
API_KEY_AUTH_ENABLED=false
ENTRA_ENABLED=false

# EntTelligence (optional - for competitor price sync)
ENTTELLIGENCE_ENABLED=false
# ENTTELLIGENCE_TOKEN_NAME=PriceScoutAzure
# ENTTELLIGENCE_TOKEN_SECRET=<your-token>
```

## Running Locally

```bash
# Backend API (port 8000)
uvicorn api.main:app --reload --port 8000

# Frontend dev server (port 5173)
cd frontend && npm run dev
```

## Running Tests

```bash
# Backend
python -m pytest tests/ -x -q

# Frontend
cd frontend && npx vitest run

# With coverage
python -m pytest tests/ --cov=app --cov=api
cd frontend && npx vitest run --coverage
```

## Project Structure

See `docs/CODEBASE_MAP.md` for the full feature-to-code mapping, cross-cutting concerns (tax handling, daypart classification, theater name matching), database schema, and known quirks.

See `docs/ARCHITECTURE.md` for system overview, deployment architecture, and design decisions.
