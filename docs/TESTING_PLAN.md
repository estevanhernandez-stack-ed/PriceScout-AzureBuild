# PriceScout Testing Plan

## Overview

This document outlines the comprehensive testing strategy for PriceScout, covering unit tests, integration tests, and end-to-end tests.

**Current Status:**
- 566 tests collected
- 21% code coverage (target: 80%)
- 50 test files across `tests/` directory

---

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── test_api/                # API endpoint tests
│   ├── test_admin.py
│   ├── test_cache.py
│   ├── test_circuit_benchmarks.py
│   ├── test_health.py
│   ├── test_presales.py
│   ├── test_price_alerts.py    # NEW - needs creation
│   └── test_baselines.py       # NEW - needs creation
├── test_modes/              # UI mode tests
│   ├── test_compsnipe_mode.py
│   ├── test_daily_lineup_mode.py
│   ├── test_operating_hours_mode.py
│   └── test_poster_mode.py
├── test_services/           # NEW - service layer tests
│   ├── test_alert_service.py
│   ├── test_notification_service.py
│   ├── test_baseline_discovery.py
│   └── test_film_enrichment.py
└── ... (existing test files)
```

---

## Test Categories

### 1. Unit Tests

Fast, isolated tests for individual functions/classes.

| Area | Files | Priority |
|------|-------|----------|
| Alert Service | `test_alert_service.py` | HIGH |
| Baseline Discovery | `test_baseline_discovery.py` | HIGH |
| Film Enrichment | `test_film_enrichment.py` | HIGH |
| Notification Service | `test_notification_service.py` | MEDIUM |
| OMDB Client | `test_omdb_client.py` | Exists |
| Utils | `test_utils.py` | Exists |

### 2. Integration Tests

Tests that verify components work together.

| Area | Files | Priority |
|------|-------|----------|
| Alert API Endpoints | `test_api/test_price_alerts.py` | HIGH |
| Baseline API Endpoints | `test_api/test_baselines.py` | HIGH |
| Scrape → Alert Flow | `test_scrape_alert_integration.py` | HIGH |
| DB Adapter | `test_database.py` | Exists |

### 3. End-to-End Tests

Full workflow tests with mocked external services.

| Area | Files | Priority |
|------|-------|----------|
| Market Mode Scrape | `test_market_mode.py` | Exists |
| Security E2E | `test_security_e2e.py` | Exists |
| Alert Workflow E2E | `test_alert_workflow_e2e.py` | MEDIUM |

---

## Missing Tests (Priority Order)

### HIGH Priority

1. **Alert Service** (`app/alert_service.py`)
   - `generate_alerts_for_scrape()` - price change detection
   - `_check_price_change()` - threshold logic
   - `_check_surge_pricing()` - baseline comparison
   - Alert type filtering

2. **Baseline Discovery** (`app/baseline_discovery.py`)
   - `discover_baselines()` - percentile calculation
   - `is_premium_format()` - format detection
   - `is_event_cinema()` - event detection
   - `analyze_price_patterns()` - volatility analysis

3. **Auto-Enrichment** (`app/db_adapter.py`)
   - `enrich_new_films()` - OMDB integration
   - `_enrich_films_sync()` - batch enrichment
   - Integration with `upsert_showings()`

4. **Price Alert API** (`api/routers/price_alerts.py`)
   - GET `/price-alerts` - list alerts
   - PUT `/price-alerts/{id}/acknowledge` - acknowledge
   - GET/PUT `/price-alerts/config` - configuration
   - Baseline CRUD endpoints

### MEDIUM Priority

5. **Notification Service** (`app/notification_service.py`)
   - Webhook dispatch with HMAC
   - Email notification formatting
   - Error handling and retry

6. **Scrape → Alert Integration**
   - Post-scrape hook execution
   - Alert generation after `save_prices()`

---

## Test Fixtures Needed

### conftest.py additions:

```python
# Alert fixtures
@pytest.fixture
def sample_price_alert():
    """Sample price alert data."""
    return {
        "alert_id": 1,
        "company_id": 1,
        "theater_name": "AMC Test Theater",
        "film_title": "Test Movie",
        "ticket_type": "Adult",
        "format": "Standard",
        "alert_type": "price_increase",
        "old_price": 12.50,
        "new_price": 14.00,
        "price_change_percent": 12.0,
        "is_acknowledged": False
    }

@pytest.fixture
def sample_alert_config():
    """Sample alert configuration."""
    return {
        "min_price_change_percent": 5.0,
        "min_price_change_amount": 1.00,
        "surge_threshold_percent": 20.0,
        "alert_on_increase": True,
        "alert_on_decrease": True,
        "alert_on_surge": True
    }

@pytest.fixture
def sample_price_baseline():
    """Sample price baseline."""
    return {
        "theater_name": "AMC Test Theater",
        "ticket_type": "Adult",
        "format": "Standard",
        "baseline_price": 12.50,
        "effective_from": "2025-01-01"
    }

@pytest.fixture
def sample_scrape_prices_df():
    """Sample DataFrame of scraped prices."""
    import pandas as pd
    return pd.DataFrame([
        {"Theater Name": "AMC Test", "Film Title": "Movie A",
         "Ticket Type": "Adult", "Format": "Standard", "Price": 14.00,
         "Showtime": "7:00 PM", "play_date": "2026-01-10"},
        {"Theater Name": "AMC Test", "Film Title": "Movie A",
         "Ticket Type": "Child", "Format": "Standard", "Price": 11.00,
         "Showtime": "7:00 PM", "play_date": "2026-01-10"}
    ])
```

---

## Running Tests

### Full Test Suite
```bash
pytest tests/ -v
```

### With Coverage
```bash
pytest tests/ --cov=app --cov=api --cov-report=html
```

### Specific Categories
```bash
# API tests only
pytest tests/test_api/ -v

# Mode tests only
pytest tests/test_modes/ -v

# Alert-related tests
pytest tests/ -k "alert" -v

# Fast unit tests (exclude slow integration)
pytest tests/ -m "not slow" -v
```

### Parallel Execution
```bash
pytest tests/ -n auto
```

---

## Test Markers

Add to `pytest.ini`:
```ini
[pytest]
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests requiring database
    api: marks API endpoint tests
    unit: marks fast unit tests
```

Usage:
```python
@pytest.mark.slow
def test_full_scrape_workflow():
    ...

@pytest.mark.integration
def test_database_alert_storage():
    ...
```

---

## Mock Strategy

### External Services
- **OMDB API**: Mock `OMDbClient.get_film_details()`
- **Webhooks**: Mock `httpx.AsyncClient.post()`
- **Database**: Use test fixtures or mock `get_session()`

### Example Mocking Pattern
```python
from unittest.mock import patch, MagicMock

@patch('app.omdb_client.OMDbClient.get_film_details')
def test_film_enrichment(mock_omdb):
    mock_omdb.return_value = {
        'film_title': 'Test Movie',
        'imdb_id': 'tt1234567',
        'genre': 'Action'
    }

    result = enrich_new_films(['Test Movie'])

    assert result['enriched'] == 1
    mock_omdb.assert_called_once_with('Test Movie')
```

---

## CI/CD Integration

### GitHub Actions (example)
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt -r tests/requirements-dev.txt
      - run: pytest tests/ --cov=app --cov=api --cov-fail-under=80
```

### Azure Pipelines
```yaml
trigger:
  - main
  - azure

pool:
  vmImage: 'ubuntu-latest'

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'
  - script: |
      pip install -r requirements.txt
      pip install pytest pytest-cov
      pytest tests/ --cov=app --cov=api --junitxml=test-results.xml
    displayName: 'Run tests'
  - task: PublishTestResults@2
    inputs:
      testResultsFiles: 'test-results.xml'
```

---

## Coverage Targets

| Module | Current | Target |
|--------|---------|--------|
| `app/alert_service.py` | 0% | 90% |
| `app/baseline_discovery.py` | 0% | 85% |
| `app/notification_service.py` | 0% | 80% |
| `app/db_adapter.py` | ~20% | 70% |
| `api/routers/price_alerts.py` | ~10% | 85% |
| **Overall** | **21%** | **80%** |

---

## Implementation Order

1. **Week 1**: Core service tests
   - [ ] `test_alert_service.py` - alert generation logic
   - [ ] `test_baseline_discovery.py` - baseline calculations
   - [ ] Add fixtures to `conftest.py`

2. **Week 2**: API endpoint tests
   - [ ] `test_api/test_price_alerts.py` - CRUD operations
   - [ ] `test_api/test_baselines.py` - discovery endpoints

3. **Week 3**: Integration tests
   - [ ] Scrape → Alert flow
   - [ ] Auto-enrichment integration
   - [ ] Notification dispatch

4. **Ongoing**: Maintain 80% coverage on new code
