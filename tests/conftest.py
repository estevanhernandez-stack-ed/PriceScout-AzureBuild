"""
Pytest configuration and fixtures.
"""
import sys
import os
from pathlib import Path
import sqlite3
import warnings
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Add the project root to Python path so tests can import from app and api
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Also ensure we're working from the correct directory
os.chdir(project_root)

# Suppress ResourceWarnings about unclosed databases during tests
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning) # Suppress unawaited coroutine warnings in tests

@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Reset all circuit breakers before each test to ensure a clean state."""
    from app.circuit_breaker import reset_all_circuits
    reset_all_circuits()
    yield

# Import API modules after path setup - these will be used by fixtures
from api.main import app as _api_app
from api.routers.auth import get_current_user as _get_current_user, create_access_token as _create_access_token
from fastapi.testclient import TestClient as _TestClient


def pytest_configure(config):
    """Configure pytest to enable strict resource cleanup and set up paths."""
    sqlite3.enable_callback_tracebacks(True)
    # Re-add path in case it was cleared
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


# ============================================================================
# FastAPI Test Client Fixtures
# ============================================================================

@pytest.fixture
def test_client():
    """Create a FastAPI TestClient for API testing."""
    # Ensure path is correct
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Import API app
    from api.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user for authentication."""
    return {
        "id": 1,
        "username": "test_admin",
        "email": "admin@test.com",
        "role": "admin",
        "company_id": 1,
        "is_active": True,
        "allowed_modes": ["all"],
        "created_at": datetime.now(timezone.utc)
    }


@pytest.fixture
def mock_regular_user():
    """Create a mock regular user for authentication."""
    return {
        "id": 2,
        "username": "test_user",
        "email": "user@test.com",
        "role": "user",
        "company_id": 1,
        "is_active": True,
        "allowed_modes": ["Market Mode", "CompSnipe Mode"],
        "created_at": datetime.now(timezone.utc)
    }


@pytest.fixture
def auth_headers_admin(mock_admin_user):
    """Create auth headers with admin JWT token."""
    import sys
    from pathlib import Path
    import importlib

    project_root = Path(__file__).parent.parent.resolve()
    project_root_str = str(project_root)

    if sys.path[0] != project_root_str:
        sys.path.insert(0, project_root_str)

    auth_module = importlib.import_module('api.routers.auth')
    create_access_token = auth_module.create_access_token

    token = create_access_token(data={
        "sub": mock_admin_user["username"],
        "user_id": mock_admin_user["id"],
        "role": mock_admin_user["role"],
        "company_id": mock_admin_user["company_id"]
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user(mock_regular_user):
    """Create auth headers with regular user JWT token."""
    import sys
    from pathlib import Path
    import importlib

    project_root = Path(__file__).parent.parent.resolve()
    project_root_str = str(project_root)

    if sys.path[0] != project_root_str:
        sys.path.insert(0, project_root_str)

    auth_module = importlib.import_module('api.routers.auth')
    create_access_token = auth_module.create_access_token

    token = create_access_token(data={
        "sub": mock_regular_user["username"],
        "user_id": mock_regular_user["id"],
        "role": mock_regular_user["role"],
        "company_id": mock_regular_user["company_id"]
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_client_authenticated(test_client, auth_headers_admin):
    """TestClient with admin auth headers pre-configured."""
    test_client.headers.update(auth_headers_admin)
    yield test_client
    # Clean up
    test_client.headers.pop("Authorization", None)


@pytest.fixture
def mock_db_session():
    """Create a mock database session for testing."""
    session = MagicMock()
    session.query = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    return session


@pytest.fixture
def sample_user_data():
    """Sample user data for creating test users."""
    return {
        "username": "new_test_user",
        "email": "newuser@test.com",
        "password": "SecurePassword123!",
        "role": "user",
        "company_id": 1,
        "allowed_modes": ["Market Mode"]
    }


@pytest.fixture
def sample_theater_data():
    """Sample theater data for testing."""
    return {
        "theater_id": "test-theater-123",
        "name": "Test Cinema 16",
        "circuit": "Marcus",
        "address": "123 Test St",
        "city": "Madison",
        "state": "WI",
        "zip_code": "53703"
    }


@pytest.fixture
def sample_circuit_benchmark():
    """Sample circuit benchmark data for testing."""
    return {
        "benchmark_id": 1,
        "circuit_name": "Marcus",
        "week_ending_date": "2026-01-02",
        "period_start_date": "2025-12-27",
        "total_showtimes": 5000,
        "total_capacity": 100000,
        "total_theaters": 50,
        "total_films": 25,
        "avg_screens_per_film": 4.5,
        "avg_showtimes_per_theater": 100.0,
        "format_standard_pct": 70.0,
        "format_imax_pct": 10.0,
        "format_dolby_pct": 15.0,
        "format_3d_pct": 5.0,
        "format_other_premium_pct": 0.0,
        "plf_total_pct": 30.0,
        "daypart_matinee_pct": 30.0,
        "daypart_evening_pct": 50.0,
        "daypart_late_pct": 20.0,
        "data_source": "enttelligence",
        "created_at": datetime.now(timezone.utc).isoformat()
    }


@pytest.fixture
def sample_presale_data():
    """Sample presale data for testing."""
    return {
        "film_title": "Avatar 3",
        "release_date": "2026-12-18",
        "circuit_name": "Marcus",
        "snapshot_date": "2026-01-06",
        "days_before_release": 346,
        "total_tickets_sold": 15000,
        "total_revenue": 225000.00,
        "theater_count": 45
    }


# ============================================================================
# Dependency Override Fixtures (for testing without database)
# ============================================================================

@pytest.fixture
def test_client_as_admin(mock_admin_user):
    """
    Create a TestClient with admin authentication mocked via dependency override.
    This allows tests to run without a live database.
    """
    # Create override function that returns mock admin user
    def override_get_current_user():
        return {
            "user_id": mock_admin_user["id"],
            "username": mock_admin_user["username"],
            "role": mock_admin_user["role"],
            "company_id": mock_admin_user["company_id"],
            "is_admin": True
        }

    # Apply dependency override using module-level imports
    _api_app.dependency_overrides[_get_current_user] = override_get_current_user

    with _TestClient(_api_app) as client:
        yield client

    # Clean up override
    _api_app.dependency_overrides.pop(_get_current_user, None)


@pytest.fixture
def test_client_as_user(mock_regular_user):
    """
    Create a TestClient with regular user authentication mocked via dependency override.
    This allows tests to run without a live database.
    """
    # Create override function that returns mock regular user
    def override_get_current_user():
        return {
            "user_id": mock_regular_user["id"],
            "username": mock_regular_user["username"],
            "role": mock_regular_user["role"],
            "company_id": mock_regular_user["company_id"],
            "is_admin": False
        }

    # Apply dependency override using module-level imports
    _api_app.dependency_overrides[_get_current_user] = override_get_current_user

    with _TestClient(_api_app) as client:
        yield client

    # Clean up override
    _api_app.dependency_overrides.pop(_get_current_user, None)


@pytest.fixture
def test_client_no_auth():
    """
    Create a TestClient without any authentication override.
    For testing unauthenticated access.
    """
    # Clear any existing overrides for this test
    existing_overrides = dict(_api_app.dependency_overrides)
    _api_app.dependency_overrides.clear()

    with _TestClient(_api_app) as client:
        yield client

    # Restore any overrides that were present (for other fixtures)
    _api_app.dependency_overrides.clear()
    _api_app.dependency_overrides.update(existing_overrides)


# ============================================================================
# Price Alert & Baseline Fixtures
# ============================================================================

@pytest.fixture
def sample_price_alert():
    """Sample price alert data for testing."""
    return {
        "alert_id": 1,
        "company_id": 1,
        "theater_name": "AMC Test Theater 16",
        "film_title": "Test Movie",
        "ticket_type": "Adult",
        "format": "Standard",
        "alert_type": "price_increase",
        "old_price": 12.50,
        "new_price": 14.00,
        "price_change_percent": 12.0,
        "baseline_price": None,
        "surge_multiplier": None,
        "triggered_at": datetime.now(timezone.utc),
        "play_date": "2026-01-15",
        "is_acknowledged": False,
        "acknowledged_by": None,
        "acknowledged_at": None,
        "acknowledgment_notes": None
    }


@pytest.fixture
def sample_surge_alert():
    """Sample surge pricing alert for testing."""
    return {
        "alert_id": 2,
        "company_id": 1,
        "theater_name": "AMC Test Theater 16",
        "film_title": "Popular Blockbuster",
        "ticket_type": "Adult",
        "format": "IMAX",
        "alert_type": "surge_detected",
        "old_price": None,
        "new_price": 28.00,
        "price_change_percent": 40.0,
        "baseline_price": 20.00,
        "surge_multiplier": 1.4,
        "triggered_at": datetime.now(timezone.utc),
        "play_date": "2026-01-15",
        "is_acknowledged": False
    }


@pytest.fixture
def sample_alert_config():
    """Sample alert configuration for testing."""
    return {
        "config_id": 1,
        "company_id": 1,
        "min_price_change_percent": 5.0,
        "min_price_change_amount": 1.00,
        "alert_on_increase": True,
        "alert_on_decrease": True,
        "alert_on_new_offering": True,
        "alert_on_discontinued": False,
        "alert_on_surge": True,
        "surge_threshold_percent": 20.0,
        "notification_enabled": True,
        "webhook_url": "https://webhook.test/alerts",
        "webhook_secret": "test_secret_key",
        "notification_email": "alerts@test.com",
        "email_frequency": "immediate",
        "theaters_filter": [],
        "ticket_types_filter": [],
        "formats_filter": []
    }


@pytest.fixture
def sample_price_baseline():
    """Sample price baseline for surge detection testing."""
    return {
        "baseline_id": 1,
        "company_id": 1,
        "theater_name": "AMC Test Theater 16",
        "ticket_type": "Adult",
        "format": "Standard",
        "daypart": None,
        "baseline_price": 12.50,
        "effective_from": "2025-01-01",
        "effective_to": None
    }


@pytest.fixture
def sample_scrape_prices_df():
    """Sample DataFrame of scraped prices for alert testing."""
    import pandas as pd
    return pd.DataFrame([
        {
            "Theater Name": "AMC Test Theater 16",
            "Film Title": "Test Movie",
            "Ticket Type": "Adult",
            "Format": "Standard",
            "Price": 14.00,
            "Showtime": "7:00 PM",
            "play_date": "2026-01-15",
            "Capacity": 200
        },
        {
            "Theater Name": "AMC Test Theater 16",
            "Film Title": "Test Movie",
            "Ticket Type": "Child",
            "Format": "Standard",
            "Price": 11.00,
            "Showtime": "7:00 PM",
            "play_date": "2026-01-15",
            "Capacity": 200
        },
        {
            "Theater Name": "AMC Test Theater 16",
            "Film Title": "Test Movie",
            "Ticket Type": "Adult",
            "Format": "IMAX",
            "Price": 22.00,
            "Showtime": "7:30 PM",
            "play_date": "2026-01-15",
            "Capacity": 300
        }
    ])


@pytest.fixture
def sample_historical_prices():
    """Sample historical price data for baseline discovery."""
    import pandas as pd
    from datetime import date, timedelta

    base_date = date.today()
    data = []

    # Generate 30 days of historical prices
    for i in range(30):
        play_date = base_date - timedelta(days=i)
        # Standard prices with some variation
        data.append({
            "theater_name": "AMC Test Theater 16",
            "ticket_type": "Adult",
            "format": "Standard",
            "price": 12.50 + (i % 3) * 0.50,  # $12.50, $13.00, $13.50
            "play_date": play_date
        })
        # IMAX prices (premium)
        data.append({
            "theater_name": "AMC Test Theater 16",
            "ticket_type": "Adult",
            "format": "IMAX",
            "price": 20.00 + (i % 2) * 2.00,  # $20.00, $22.00
            "play_date": play_date
        })

    return pd.DataFrame(data)


@pytest.fixture
def sample_film_titles():
    """Sample film titles for enrichment testing."""
    return [
        "Avatar: The Way of Water",
        "Oppenheimer",
        "Barbie",
        "The Super Mario Bros. Movie",
        "Fathom Events: Classic Movie Night"  # Event cinema
    ]


@pytest.fixture
def mock_omdb_response():
    """Mock OMDB API response for film enrichment testing."""
    return {
        "film_title": "Avatar: The Way of Water",
        "imdb_id": "tt1630029",
        "genre": "Action, Adventure, Fantasy",
        "mpaa_rating": "PG-13",
        "director": "James Cameron",
        "actors": "Sam Worthington, Zoe Saldana, Sigourney Weaver",
        "plot": "Jake Sully lives with his newfound family...",
        "poster_url": "https://example.com/poster.jpg",
        "metascore": 67,
        "imdb_rating": 7.6,
        "release_date": "2022-12-16",
        "runtime": "192 min",
        "domestic_gross": 684075767,
        "opening_weekend_domestic": None,
        "last_omdb_update": datetime.now(timezone.utc)
    }


# ============================================================================
# Database Test Fixtures
# ============================================================================

@pytest.fixture
def mock_get_session():
    """Mock database session context manager for isolated testing."""
    from contextlib import contextmanager

    @contextmanager
    def _mock_session():
        session = MagicMock()
        session.query = MagicMock()
        session.add = MagicMock()
        session.flush = MagicMock()
        session.commit = MagicMock()
        session.rollback = MagicMock()
        yield session

    return _mock_session


@pytest.fixture
def test_company_id():
    """Standard test company ID."""
    return 1


@pytest.fixture
def set_test_company(test_company_id):
    """Set the test company ID in config for database operations."""
    from app import config
    original = getattr(config, 'CURRENT_COMPANY_ID', None)
    config.CURRENT_COMPANY_ID = test_company_id
    yield test_company_id
    if original is not None:
        config.CURRENT_COMPANY_ID = original
