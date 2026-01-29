
import pytest
import os
import sqlite3
import json
from datetime import date, datetime, UTC
from tempfile import NamedTemporaryFile
from app.schedule_monitor_service import ScheduleMonitorService, ScheduleChange
from unittest.mock import patch

@pytest.fixture
def temp_db():
    with NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    # Initialize schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # We need to recreate the tables used by ScheduleMonitorService
    cursor.execute("""
        CREATE TABLE schedule_monitor_config (
            company_id INTEGER PRIMARY KEY,
            is_enabled BOOLEAN DEFAULT 1,
            check_frequency_hours INTEGER DEFAULT 24,
            alert_on_new_film BOOLEAN DEFAULT 1,
            alert_on_new_showtime BOOLEAN DEFAULT 1,
            alert_on_removed_showtime BOOLEAN DEFAULT 1,
            alert_on_removed_film BOOLEAN DEFAULT 1,
            alert_on_format_added BOOLEAN DEFAULT 1,
            alert_on_new_schedule BOOLEAN DEFAULT 1,
            alert_on_event BOOLEAN DEFAULT 1,
            alert_on_presale BOOLEAN DEFAULT 1
        )
    """)
    
    cursor.execute("""
        CREATE TABLE schedule_baselines (
            baseline_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            theater_name TEXT,
            film_title TEXT,
            play_date TEXT,
            showtimes TEXT,
            snapshot_at TEXT,
            source TEXT,
            effective_from TEXT,
            effective_to TEXT,
            created_by INTEGER
        )
    """)
    
    cursor.execute("""
        CREATE TABLE schedule_alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            theater_name TEXT,
            film_title TEXT,
            play_date TEXT,
            alert_type TEXT,
            old_value TEXT,
            new_value TEXT,
            change_details TEXT,
            triggered_at TEXT,
            is_acknowledged BOOLEAN DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE enttelligence_price_cache (
            cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            play_date TEXT,
            theater_name TEXT,
            film_title TEXT,
            showtime TEXT,
            format TEXT,
            ticket_type TEXT,
            price REAL,
            source TEXT,
            fetched_at TEXT,
            expires_at TEXT,
            circuit_name TEXT,
            enttelligence_theater_id TEXT,
            created_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.fixture
def service(temp_db):
    with patch("app.schedule_monitor_service.config") as mock_config:
        mock_config.DB_FILE = temp_db
        return ScheduleMonitorService(company_id=1)

def test_detect_changes_new_film(service):
    theater = "T1"
    pdate = "2026-01-15"
    
    # Baseline has no films
    # Current schedule has Film A
    current_schedule = {
        "Film A": [{"time": "19:00", "format": "2D"}]
    }
    
    changes = service.detect_changes(theater, pdate, current_schedule)
    
    # Baseline empty -> new_schedule alert AND new_film alert
    assert len(changes) == 2
    assert any(c.alert_type == "new_schedule" for c in changes)
    assert any(c.alert_type == "new_film" for c in changes)
    assert any(c.film_title == "Film A" for c in changes if c.alert_type == "new_film")

def test_detect_changes_new_showtime(service, temp_db):
    theater = "T1"
    pdate = "2026-01-15"
    film = "Film A"
    
    # Setup baseline in DB
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO schedule_baselines (company_id, theater_name, film_title, play_date, showtimes, effective_from)
        VALUES (1, 'T1', 'Film A', '2026-01-15', ?, ?)
    """, (json.dumps([{"time": "19:00", "format": "2D"}]), datetime.now(UTC).isoformat()))
    conn.commit()
    conn.close()
    
    # Current schedule adds 21:00
    current_schedule = {
        "Film A": [
            {"time": "19:00", "format": "2D"},
            {"time": "21:00", "format": "2D"}
        ]
    }
    
    changes = service.detect_changes(theater, pdate, current_schedule)
    
    assert any(c.alert_type == "new_showtime" for c in changes)
    assert any("21:00" in c.change_details for c in changes)

def test_detect_changes_removed_showtime(service, temp_db):
    theater = "T1"
    pdate = "2026-01-15"
    
    # Setup baseline with 19:00 and 21:00
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO schedule_baselines (company_id, theater_name, film_title, play_date, showtimes, effective_from)
        VALUES (1, 'T1', 'Film A', '2026-01-15', ?, ?)
    """, (json.dumps([
        {"time": "19:00", "format": "2D"},
        {"time": "21:00", "format": "2D"}
    ]), datetime.now(UTC).isoformat()))
    conn.commit()
    conn.close()
    
    # Current schedule only has 19:00
    current_schedule = {
        "Film A": [{"time": "19:00", "format": "2D"}]
    }
    
    changes = service.detect_changes(theater, pdate, current_schedule)
    
    assert any(c.alert_type == "removed_showtime" for c in changes)
    assert any("21:00" in c.change_details for c in changes)

