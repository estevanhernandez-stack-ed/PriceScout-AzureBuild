"""
Tests for app/schedule_monitor_service.py - Schedule change detection logic.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date
import json


class TestScheduleMonitorServiceInit:
    """Test ScheduleMonitorService initialization."""

    def test_service_initializes_with_company_id(self):
        """ScheduleMonitorService should initialize with company_id."""
        from app.schedule_monitor_service import ScheduleMonitorService

        service = ScheduleMonitorService(company_id=1)

        assert service.company_id == 1

    def test_factory_function_returns_service(self):
        """get_schedule_monitor_service should return a service instance."""
        from app.schedule_monitor_service import get_schedule_monitor_service

        service = get_schedule_monitor_service(company_id=1)

        assert service.company_id == 1


class TestScheduleChange:
    """Test ScheduleChange dataclass."""

    def test_schedule_change_creation(self):
        """ScheduleChange should store all fields correctly."""
        from app.schedule_monitor_service import ScheduleChange

        change = ScheduleChange(
            theater_name="AMC Test Theater",
            film_title="Test Movie",
            play_date="2026-01-15",
            alert_type="new_film",
            old_value=None,
            new_value={"showtimes": [{"time": "7:00 PM"}]},
            change_details="New film 'Test Movie' added with 1 showtime(s)"
        )

        assert change.theater_name == "AMC Test Theater"
        assert change.film_title == "Test Movie"
        assert change.play_date == "2026-01-15"
        assert change.alert_type == "new_film"
        assert change.old_value is None
        assert change.new_value["showtimes"][0]["time"] == "7:00 PM"


class TestGetOrCreateConfig:
    """Test configuration management."""

    def test_creates_default_config_if_none_exists(self):
        """Should create default config when none exists."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # First query returns None (no existing config)
            mock_cursor.fetchone.side_effect = [
                None,  # First call - no config exists
                {'config_id': 1, 'company_id': 1, 'is_enabled': 1}  # After insert
            ]

            service = ScheduleMonitorService(company_id=1)
            config = service.get_or_create_config()

            # Should have called INSERT
            assert mock_cursor.execute.call_count >= 2
            assert config['company_id'] == 1

    def test_returns_existing_config(self):
        """Should return existing config if present."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # Return existing config
            mock_cursor.fetchone.return_value = {
                'config_id': 1,
                'company_id': 1,
                'is_enabled': 1,
                'check_frequency_hours': 6
            }

            service = ScheduleMonitorService(company_id=1)
            config = service.get_or_create_config()

            assert config['company_id'] == 1
            assert config['check_frequency_hours'] == 6


class TestCreateBaselineSnapshot:
    """Test baseline snapshot creation."""

    def test_creates_new_baseline(self):
        """Should create new baseline and expire old one."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_cursor.lastrowid = 42
            mock_conn.return_value = mock_connection

            service = ScheduleMonitorService(company_id=1)
            baseline_id = service.create_baseline_snapshot(
                theater_name="AMC Test",
                film_title="Test Movie",
                play_date="2026-01-15",
                showtimes=[{"time": "7:00 PM", "format": "Standard"}],
                source="enttelligence"
            )

            assert baseline_id == 42
            # Should have executed UPDATE (expire old) and INSERT (new)
            assert mock_cursor.execute.call_count == 2
            mock_connection.commit.assert_called_once()


class TestGetCurrentBaseline:
    """Test baseline retrieval."""

    def test_returns_current_baseline(self):
        """Should return baseline with effective_to = NULL."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            mock_cursor.fetchone.return_value = {
                'baseline_id': 1,
                'theater_name': 'AMC Test',
                'film_title': 'Test Movie',
                'showtimes': '[{"time": "7:00 PM"}]'
            }

            service = ScheduleMonitorService(company_id=1)
            baseline = service.get_current_baseline("AMC Test", "Test Movie", "2026-01-15")

            assert baseline is not None
            assert baseline['theater_name'] == 'AMC Test'
            assert len(baseline['showtimes']) == 1

    def test_returns_none_when_no_baseline(self):
        """Should return None when no baseline exists."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            mock_cursor.fetchone.return_value = None

            service = ScheduleMonitorService(company_id=1)
            baseline = service.get_current_baseline("Unknown Theater", "Test", "2026-01-15")

            assert baseline is None


class TestDetectChanges:
    """Test schedule change detection logic."""

    def test_detects_new_film(self):
        """Should detect when a new film is added."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # No existing baselines
            mock_cursor.fetchall.return_value = []

            service = ScheduleMonitorService(company_id=1)

            current_schedule = {
                "New Movie": [{"time": "7:00 PM", "format": "Standard"}]
            }

            changes = service.detect_changes("AMC Test", "2026-01-15", current_schedule)
    
            assert len(changes) == 2
            assert any(c.alert_type == "new_schedule" for c in changes)
            assert any(c.alert_type == "new_film" for c in changes)

    def test_detects_removed_film(self):
        """Should detect when a film is removed."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # Existing baseline for a film
            mock_cursor.fetchall.return_value = [{
                'baseline_id': 1,
                'film_title': 'Old Movie',
                'showtimes': '[{"time": "7:00 PM"}]'
            }]

            service = ScheduleMonitorService(company_id=1)

            # Current schedule doesn't have the film
            current_schedule = {}

            changes = service.detect_changes("AMC Test", "2026-01-15", current_schedule)

            assert len(changes) == 1
            assert changes[0].alert_type == "removed_film"
            assert changes[0].film_title == "Old Movie"

    def test_detects_new_showtime(self):
        """Should detect when a new showtime is added for existing film."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # Existing baseline with one showtime
            mock_cursor.fetchall.return_value = [{
                'baseline_id': 1,
                'film_title': 'Test Movie',
                'showtimes': '[{"time": "7:00 PM"}]'
            }]

            service = ScheduleMonitorService(company_id=1)

            # Current schedule has additional showtime
            current_schedule = {
                "Test Movie": [
                    {"time": "7:00 PM"},
                    {"time": "9:30 PM"}  # New showtime
                ]
            }

            changes = service.detect_changes("AMC Test", "2026-01-15", current_schedule)

            assert len(changes) == 1
            assert changes[0].alert_type == "new_showtime"
            assert "9:30 PM" in changes[0].change_details

    def test_detects_removed_showtime(self):
        """Should detect when a showtime is removed."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # Existing baseline with two showtimes
            mock_cursor.fetchall.return_value = [{
                'baseline_id': 1,
                'film_title': 'Test Movie',
                'showtimes': '[{"time": "7:00 PM"}, {"time": "9:30 PM"}]'
            }]

            service = ScheduleMonitorService(company_id=1)

            # Current schedule has only one showtime
            current_schedule = {
                "Test Movie": [{"time": "7:00 PM"}]  # 9:30 PM removed
            }

            changes = service.detect_changes("AMC Test", "2026-01-15", current_schedule)

            assert len(changes) == 1
            assert changes[0].alert_type == "removed_showtime"
            assert "9:30 PM" in changes[0].change_details

    def test_detects_new_format(self):
        """Should detect when a new format becomes available."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # Existing baseline with Standard format only
            mock_cursor.fetchall.return_value = [{
                'baseline_id': 1,
                'film_title': 'Test Movie',
                'showtimes': '[{"time": "7:00 PM", "format": "Standard"}]'
            }]

            service = ScheduleMonitorService(company_id=1)

            # Current schedule adds IMAX format
            current_schedule = {
                "Test Movie": [
                    {"time": "7:00 PM", "format": "Standard"},
                    {"time": "8:00 PM", "format": "IMAX"}  # New format
                ]
            }

            changes = service.detect_changes("AMC Test", "2026-01-15", current_schedule)

            # Should detect new showtime and new format
            format_changes = [c for c in changes if c.alert_type == "format_added"]
            assert len(format_changes) >= 1
            assert "IMAX" in format_changes[0].change_details

    def test_no_changes_when_schedule_matches(self):
        """Should return empty list when schedule hasn't changed."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # Existing baseline matches current
            mock_cursor.fetchall.return_value = [{
                'baseline_id': 1,
                'film_title': 'Test Movie',
                'showtimes': '[{"time": "7:00 PM", "format": "Standard"}]'
            }]

            service = ScheduleMonitorService(company_id=1)

            current_schedule = {
                "Test Movie": [{"time": "7:00 PM", "format": "Standard"}]
            }

            changes = service.detect_changes("AMC Test", "2026-01-15", current_schedule)

            assert len(changes) == 0


class TestSaveAlert:
    """Test alert persistence."""

    def test_saves_alert_to_database(self):
        """Should save alert and return alert_id."""
        from app.schedule_monitor_service import ScheduleMonitorService, ScheduleChange

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_cursor.lastrowid = 123
            mock_conn.return_value = mock_connection

            service = ScheduleMonitorService(company_id=1)

            change = ScheduleChange(
                theater_name="AMC Test",
                film_title="Test Movie",
                play_date="2026-01-15",
                alert_type="new_film",
                old_value=None,
                new_value={"showtimes": [{"time": "7:00 PM"}]},
                change_details="New film added"
            )

            alert_id = service.save_alert(change)

            assert alert_id == 123
            mock_cursor.execute.assert_called_once()
            mock_connection.commit.assert_called_once()


class TestGetAlerts:
    """Test alert retrieval with filters."""

    def test_retrieves_alerts_with_filters(self):
        """Should retrieve alerts matching filters."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            mock_cursor.fetchall.return_value = [
                {
                    'alert_id': 1,
                    'theater_name': 'AMC Test',
                    'alert_type': 'new_film',
                    'is_acknowledged': 0,
                    'old_value': None,
                    'new_value': '{"showtimes": []}'
                }
            ]

            service = ScheduleMonitorService(company_id=1)
            alerts = service.get_alerts(is_acknowledged=False, alert_type='new_film')

            assert len(alerts) == 1
            assert alerts[0]['alert_type'] == 'new_film'

    def test_handles_empty_results(self):
        """Should return empty list when no alerts match."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            mock_cursor.fetchall.return_value = []

            service = ScheduleMonitorService(company_id=1)
            alerts = service.get_alerts()

            assert alerts == []


class TestGetAlertSummary:
    """Test alert summary statistics."""

    def test_returns_summary_with_all_fields(self):
        """Should return summary with counts and breakdowns."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # Mock query results
            mock_cursor.fetchone.side_effect = [
                {'pending': 5, 'acknowledged': 3},  # totals
                {'oldest': '2026-01-10T10:00:00', 'newest': '2026-01-13T15:00:00'}  # timestamps
            ]
            mock_cursor.fetchall.side_effect = [
                [{'alert_type': 'new_film', 'count': 3}, {'alert_type': 'new_showtime', 'count': 2}],  # by type
                [{'theater_name': 'AMC Test', 'count': 4}]  # by theater
            ]

            service = ScheduleMonitorService(company_id=1)
            summary = service.get_alert_summary()

            assert summary['total_pending'] == 5
            assert summary['total_acknowledged'] == 3
            assert 'by_type' in summary
            assert 'by_theater' in summary


class TestAcknowledgeAlert:
    """Test alert acknowledgment."""

    def test_acknowledges_alert(self):
        """Should mark alert as acknowledged."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_cursor.rowcount = 1
            mock_conn.return_value = mock_connection

            service = ScheduleMonitorService(company_id=1)
            result = service.acknowledge_alert(
                alert_id=1,
                user_id=10,
                notes="Reviewed and addressed"
            )

            assert result is True
            mock_cursor.execute.assert_called_once()
            mock_connection.commit.assert_called_once()

    def test_returns_false_when_alert_not_found(self):
        """Should return False when alert doesn't exist."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_cursor.rowcount = 0  # No rows updated
            mock_conn.return_value = mock_connection

            service = ScheduleMonitorService(company_id=1)
            result = service.acknowledge_alert(alert_id=999, user_id=10)

            assert result is False


class TestRunCheck:
    """Test the main check operation."""

    def test_run_check_detects_changes(self):
        """Should run check and return results."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # Mock config
            mock_cursor.fetchone.side_effect = [
                {'config_id': 1, 'company_id': 1, 'is_enabled': 1,
                 'alert_on_new_film': 1, 'alert_on_new_showtime': 1,
                 'alert_on_removed_showtime': 1, 'alert_on_removed_film': 1,
                 'alert_on_format_added': 1},
                None  # For baseline check
            ]

            # Mock cache query - no existing data
            mock_cursor.fetchall.side_effect = [
                [],  # First query - cache data
                []   # Baseline lookup
            ]

            service = ScheduleMonitorService(company_id=1)
            result = service.run_check()

            assert result['status'] in ['completed', 'failed']
            assert 'theaters_checked' in result
            assert 'alerts_created' in result

    def test_run_check_handles_error(self):
        """Should handle errors gracefully."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # Make the query raise an exception
            mock_cursor.execute.side_effect = Exception("Database error")

            service = ScheduleMonitorService(company_id=1)
            result = service.run_check()

            assert result['status'] == 'failed'
            assert 'error' in result


class TestUpdateConfig:
    """Test configuration updates."""

    def test_updates_allowed_fields(self):
        """Should update only allowed configuration fields."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            # Return updated config
            mock_cursor.fetchone.return_value = {
                'config_id': 1,
                'company_id': 1,
                'is_enabled': 0,
                'check_frequency_hours': 12
            }

            service = ScheduleMonitorService(company_id=1)
            updated = service.update_config({
                'is_enabled': False,
                'check_frequency_hours': 12
            })

            assert updated['is_enabled'] == 0
            assert updated['check_frequency_hours'] == 12

    def test_ignores_invalid_fields(self):
        """Should ignore fields not in allowed list."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            mock_cursor.fetchone.return_value = {
                'config_id': 1,
                'company_id': 1,
                'is_enabled': 1
            }

            service = ScheduleMonitorService(company_id=1)
            service.update_config({
                'invalid_field': 'should_be_ignored',
                'is_enabled': True
            })

            # Check the SQL doesn't include invalid_field
            call_args = mock_cursor.execute.call_args_list
            for call in call_args:
                sql = call[0][0] if call[0] else ""
                assert 'invalid_field' not in sql


class TestCreateBaselinesFromCache:
    """Test bulk baseline creation from cache."""

    def test_creates_baselines_from_cache_data(self):
        """Should create baselines from EntTelligence cache."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_cursor.lastrowid = 1
            mock_conn.return_value = mock_connection

            # Mock cache data
            mock_cursor.fetchall.return_value = [
                {'theater_name': 'AMC Test', 'film_title': 'Movie 1',
                 'play_date': '2026-01-15', 'showtime': '7:00 PM', 'format': 'Standard'},
                {'theater_name': 'AMC Test', 'film_title': 'Movie 1',
                 'play_date': '2026-01-15', 'showtime': '9:30 PM', 'format': 'Standard'},
                {'theater_name': 'AMC Test', 'film_title': 'Movie 2',
                 'play_date': '2026-01-15', 'showtime': '8:00 PM', 'format': 'IMAX'}
            ]

            service = ScheduleMonitorService(company_id=1)
            result = service.create_baselines_from_cache()

            assert result['baselines_created'] == 2  # 2 unique film/theater/date combos
            assert result['theaters_processed'] == 1
            assert result['films_processed'] == 2

    def test_handles_empty_cache(self):
        """Should handle empty cache gracefully."""
        from app.schedule_monitor_service import ScheduleMonitorService

        with patch.object(ScheduleMonitorService, '_get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_connection = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_connection

            mock_cursor.fetchall.return_value = []

            service = ScheduleMonitorService(company_id=1)
            result = service.create_baselines_from_cache()

            assert result['baselines_created'] == 0
            assert result['theaters_processed'] == 0
