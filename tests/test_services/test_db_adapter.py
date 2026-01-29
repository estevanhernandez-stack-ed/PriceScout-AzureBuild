
import pytest
import os
from datetime import date
from unittest.mock import patch, MagicMock
from app.db_session import get_session, init_database as sa_init_database, close_engine
from app.db_adapter import get_dates_for_theaters, get_common_films_for_theaters_dates
from app.db_models import Showing, Base, Company
from app import config

@pytest.fixture(scope="module", autouse=True)
def test_db():
    # Use in-memory SQLite for testing
    with patch("app.db_session._get_database_url", return_value="sqlite:///:memory:"):
        # Reset engine and session factory to ensure they use memory DB
        from app import db_session
        db_session._engine = None
        db_session._SessionFactory = None
        
        # Initialize database
        sa_init_database()
        
        yield
        
        # Cleanup
        close_engine()

@pytest.fixture
def sample_data(test_db):
    with get_session() as session:
        # Clear existing data
        session.query(Showing).delete()
        session.query(Company).delete()
        
        # Create company
        c = Company(company_id=1, company_name="Test Company")
        session.add(c)
        session.commit()
        
        # Add some test data
        s1 = Showing(
            company_id=1,
            theater_name="Theater 1",
            film_title="Film A",
            play_date=date(2026, 1, 15),
            showtime="19:00",
            format="Standard"
        )
        s2 = Showing(
            company_id=1,
            theater_name="Theater 2",
            film_title="Film A",
            play_date=date(2026, 1, 15),
            showtime="20:00",
            format="Standard"
        )
        s3 = Showing(
            company_id=1,
            theater_name="Theater 1",
            film_title="Film B",
            play_date=date(2026, 1, 14),
            showtime="21:00",
            format="Standard"
        )
        session.add_all([s1, s2, s3])
        session.commit()

def test_get_dates_for_theaters(sample_data):
    with patch("app.db_adapter.config") as mock_config:
        mock_config.CURRENT_COMPANY_ID = 1
        
        # Test basic retrieval
        dates = get_dates_for_theaters(["Theater 1"])
        assert date(2026, 1, 15) in dates
        assert date(2026, 1, 14) in dates
        assert len(dates) == 2
        
        # Test multiple theaters
        dates = get_dates_for_theaters(["Theater 1", "Theater 2"])
        assert date(2026, 1, 15) in dates
        assert len(dates) == 2
        
        # Test non-existent theater
        assert get_dates_for_theaters(["NonExistent"]) == []

def test_get_common_films_for_theaters_dates(sample_data):
    with patch("app.db_adapter.config") as mock_config:
        mock_config.CURRENT_COMPANY_ID = 1
        
        # Film A is in both Theater 1 and Theater 2 on 2026-01-15
        result = get_common_films_for_theaters_dates(["Theater 1", "Theater 2"], [date(2026, 1, 15)])
        assert result == ["Film A"]
        
        # Film B is only in Theater 1
        result = get_common_films_for_theaters_dates(["Theater 1", "Theater 2"], [date(2026, 1, 14)])
        print(f"DEBUG: Common films on Jan 14 for multiple theaters: {result}")
        assert result == []
        
        # Film A and B are in Theater 1
        result = get_common_films_for_theaters_dates(["Theater 1"], [date(2026, 1, 14), date(2026, 1, 15)])
        assert sorted(result) == ["Film A", "Film B"]

def test_get_dates_for_theaters_empty_input():
    assert get_dates_for_theaters([]) == []
    assert get_common_films_for_theaters_dates([], []) == []

