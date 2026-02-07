
import pytest
import pandas as pd
from datetime import datetime, date, timedelta, UTC
from decimal import Decimal
from unittest.mock import patch
from app.alert_service import AlertService
from app.db_session import get_session, init_database as sa_init_database, close_engine
from app.db_models import Company, Showing, Price, PriceAlert, PriceBaseline, AlertConfiguration

@pytest.fixture(scope="module", autouse=True)
def test_db():
    with patch("app.db_session._get_database_url", return_value="sqlite:///:memory:"):
        from app import db_session
        db_session._engine = None
        db_session._SessionFactory = None
        sa_init_database()
        yield
        close_engine()

@pytest.fixture
def service():
    return AlertService(company_id=1)

@pytest.fixture
def setup_data(test_db):
    with get_session() as session:
        session.query(PriceAlert).delete()
        session.query(Price).delete()
        session.query(Showing).delete()
        session.query(PriceBaseline).delete()
        session.query(Company).delete()
        
        c = Company(company_id=1, company_name="Test Co")
        session.add(c)
        session.commit()

@pytest.fixture
def sample_showing(setup_data):
    with get_session() as session:
        s = Showing(
            company_id=1, 
            theater_name="T1", 
            film_title="Movie", 
            play_date=date.today(), 
            showtime="19:00", 
            format="2D"
        )
        session.add(s)
        session.commit()
        return s.showing_id

def test_surge_detection_alert(service, sample_showing):
    """Test that price exceeding baseline triggers surge_detected alert."""
    with get_session() as session:
        # 1. Create a baseline at $10.00 (AlertService compares against baselines)
        baseline = PriceBaseline(
            company_id=1,
            theater_name="T1",
            ticket_type="Adult",
            format="2D",
            baseline_price=Decimal("10.00"),
            effective_from=date.today() - timedelta(days=10)
        )
        session.add(baseline)

        # 2. Create previous price (historical record)
        p1 = Price(
            company_id=1,
            showing_id=sample_showing,
            ticket_type="Adult",
            price=Decimal("10.00"),
            created_at=datetime.now(UTC) - timedelta(hours=1)
        )
        session.add(p1)

        # 3. Create "current" price (newly saved in DB by the scraper)
        p2 = Price(
            company_id=1,
            showing_id=sample_showing,
            ticket_type="Adult",
            price=Decimal("12.00"),
            created_at=datetime.now(UTC)
        )
        session.add(p2)
        session.commit()

        # Process results - alert service compares $12.00 against $10.00 baseline
        # 20% surge exceeds default threshold
        df = pd.DataFrame([{
            "Theater Name": "T1",
            "Ticket Type": "Adult",
            "Format": "2D",
            "Price": 12.00,
            "Film Title": "Movie",
            "play_date": date.today(),
            "Daypart": "Prime"  # Use Fandango-aligned daypart name
        }])

        alerts = service.process_scrape_results(run_id=1, prices_df=df)

        assert len(alerts) >= 1
        # Baseline comparison generates 'surge_detected' alert type
        alert = next(a for a in alerts if a.alert_type == 'surge_detected')
        assert alert.baseline_price == Decimal("10.00")
        assert alert.new_price == Decimal("12.00")
        assert alert.price_change_percent == Decimal("20.0")

def test_surge_pricing_alert(service, setup_data):
    with get_session() as session:
        # Create baseline
        b = PriceBaseline(
            company_id=1,
            theater_name="T1",
            ticket_type="Adult",
            format="2D",
            baseline_price=Decimal("10.00"),
            effective_from=date.today() - timedelta(days=10)
        )
        session.add(b)
        session.commit()
        
        # Process high price
        df = pd.DataFrame([{
            "Theater Name": "T1",
            "Ticket Type": "Adult",
            "Format": "2D",
            "Price": 15.00, # 50% surge
            "Film Title": "Blockbuster",
            "play_date": date.today(),
            "Daypart": "*"
        }])
        
        alerts = service.process_scrape_results(run_id=2, prices_df=df)
        
        assert any(a.alert_type == 'surge_detected' for a in alerts)
        surge = next(a for a in alerts if a.alert_type == 'surge_detected')
        assert surge.baseline_price == Decimal("10.00")
        assert surge.new_price == Decimal("15.00")

def test_no_alert_on_no_change(service, sample_showing):
    with get_session() as session:
        # Previous price
        p1 = Price(
            company_id=1, 
            showing_id=sample_showing, 
            ticket_type="Adult", 
            price=Decimal("10.00"), 
            created_at=datetime.now(UTC) - timedelta(hours=1)
        )
        session.add(p1)
        
        # Current price (same)
        p2 = Price(
            company_id=1, 
            showing_id=sample_showing, 
            ticket_type="Adult", 
            price=Decimal("10.00"), 
            created_at=datetime.now(UTC)
        )
        session.add(p2)
        session.commit()
        
        df = pd.DataFrame([{
            "Theater Name": "T1",
            "Ticket Type": "Adult",
            "Format": "2D",
            "Price": 10.00,
            "Film Title": "Movie",
            "play_date": date.today(),
            "Daypart": "evening"
        }])
        
        alerts = service.process_scrape_results(run_id=3, prices_df=df)
        # Should not have price_increase/decrease alerts. Might have surge if baseline is low, 
        # but here we didn't set a baseline so it falls back to 10.00 or nothing.
        assert not any(a.alert_type in ['price_increase', 'price_decrease'] for a in alerts)

