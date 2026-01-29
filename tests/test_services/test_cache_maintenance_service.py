"""
Tests for app/cache_maintenance_service.py - Theater cache maintenance and health monitoring.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
import json
import os


class TestCacheMaintenanceServiceInit:
    """Test CacheMaintenanceService initialization."""

    def test_service_initializes_with_defaults(self):
        """CacheMaintenanceService should initialize with default cache file."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()

        assert service.cache_file is not None
        assert service.scraper is not None

    def test_service_accepts_custom_cache_file(self):
        """CacheMaintenanceService should accept custom cache file path."""
        from app.cache_maintenance_service import CacheMaintenanceService

        custom_path = "/tmp/test_cache.json"
        service = CacheMaintenanceService(cache_file=custom_path)

        assert service.cache_file == custom_path


class TestLoadCache:
    """Test cache loading functionality."""

    def test_loads_valid_cache_file(self, tmp_path):
        """Should load valid JSON cache file."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_data = {
            "metadata": {"version": "1.0"},
            "markets": {
                "Test Market": {
                    "theaters": [
                        {"name": "AMC Test", "url": "https://fandango.com/test"}
                    ]
                }
            }
        }

        cache_file = tmp_path / "test_cache.json"
        cache_file.write_text(json.dumps(cache_data))

        service = CacheMaintenanceService(cache_file=str(cache_file))
        loaded = service._load_cache()

        assert loaded is not None
        assert "markets" in loaded
        assert "Test Market" in loaded["markets"]

    def test_returns_none_for_missing_file(self, tmp_path):
        """Should return None when cache file doesn't exist."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService(cache_file=str(tmp_path / "nonexistent.json"))
        loaded = service._load_cache()

        assert loaded is None

    def test_returns_none_for_invalid_json(self, tmp_path):
        """Should return None for invalid JSON."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_file = tmp_path / "invalid.json"
        cache_file.write_text("not valid json {{{")

        service = CacheMaintenanceService(cache_file=str(cache_file))
        loaded = service._load_cache()

        assert loaded is None


class TestSaveCache:
    """Test cache saving functionality."""

    def test_saves_cache_with_backup(self, tmp_path):
        """Should save cache and create backup."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_file = tmp_path / "test_cache.json"
        original_data = {"version": "1.0"}
        cache_file.write_text(json.dumps(original_data))

        service = CacheMaintenanceService(cache_file=str(cache_file))

        new_data = {"version": "2.0", "markets": {}}
        result = service._save_cache(new_data)

        assert result is True
        assert cache_file.exists()

        # Check backup was created
        backup_file = tmp_path / "test_cache.json.maintenance_bak"
        assert backup_file.exists()

        # Verify backup contains original data
        backup_content = json.loads(backup_file.read_text())
        assert backup_content["version"] == "1.0"

        # Verify new cache contains updated data
        new_content = json.loads(cache_file.read_text())
        assert new_content["version"] == "2.0"


class TestGetFailedTheaters:
    """Test identification of failed theaters."""

    def test_identifies_theaters_without_url(self):
        """Should identify theaters with missing URLs."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()

        cache = {
            "markets": {
                "Market A": {
                    "theaters": [
                        {"name": "Good Theater", "url": "https://fandango.com/good"},
                        {"name": "Bad Theater", "url": ""},
                        {"name": "Missing URL Theater"}
                    ]
                }
            }
        }

        failed = service._get_failed_theaters(cache)

        assert len(failed) == 2
        names = [t['name'] for t in failed]
        assert "Bad Theater" in names
        assert "Missing URL Theater" in names

    def test_identifies_theaters_with_na_url(self):
        """Should identify theaters with N/A URLs."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()

        cache = {
            "markets": {
                "Market A": {
                    "theaters": [
                        {"name": "NA Theater", "url": "N/A"}
                    ]
                }
            }
        }

        failed = service._get_failed_theaters(cache)

        assert len(failed) == 1
        assert failed[0]['name'] == "NA Theater"

    def test_identifies_not_on_fandango_theaters(self):
        """Should identify theaters marked as not on Fandango."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()

        cache = {
            "markets": {
                "Market A": {
                    "theaters": [
                        {"name": "Not on Fandango", "url": "https://test.com", "not_on_fandango": True}
                    ]
                }
            }
        }

        failed = service._get_failed_theaters(cache)

        assert len(failed) == 1
        assert failed[0]['name'] == "Not on Fandango"

    def test_returns_empty_for_healthy_cache(self):
        """Should return empty list when all theaters are healthy."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()

        cache = {
            "markets": {
                "Market A": {
                    "theaters": [
                        {"name": "Good Theater 1", "url": "https://fandango.com/1"},
                        {"name": "Good Theater 2", "url": "https://fandango.com/2"}
                    ]
                }
            }
        }

        failed = service._get_failed_theaters(cache)

        assert len(failed) == 0


class TestGetRandomSample:
    """Test random sampling of theaters."""

    def test_returns_sample_of_valid_theaters(self):
        """Should return random sample of theaters with valid URLs."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()

        cache = {
            "markets": {
                "Market A": {
                    "theaters": [
                        {"name": f"Theater {i}", "url": f"https://fandango.com/{i}"}
                        for i in range(20)
                    ]
                }
            }
        }

        sample = service._get_random_sample(cache, sample_size=10)

        assert len(sample) == 10
        assert all(t['url'] for t in sample)

    def test_excludes_failed_theaters_from_sample(self):
        """Should not include failed theaters in sample."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()

        cache = {
            "markets": {
                "Market A": {
                    "theaters": [
                        {"name": "Good Theater", "url": "https://fandango.com/good"},
                        {"name": "Bad Theater", "url": ""},
                        {"name": "NA Theater", "url": "N/A"},
                        {"name": "Not on Fandango", "url": "https://test.com", "not_on_fandango": True}
                    ]
                }
            }
        }

        sample = service._get_random_sample(cache, sample_size=10)

        assert len(sample) == 1
        assert sample[0]['name'] == "Good Theater"

    def test_returns_all_when_fewer_than_sample_size(self):
        """Should return all valid theaters when fewer than sample size."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()

        cache = {
            "markets": {
                "Market A": {
                    "theaters": [
                        {"name": "Theater 1", "url": "https://fandango.com/1"},
                        {"name": "Theater 2", "url": "https://fandango.com/2"}
                    ]
                }
            }
        }

        sample = service._get_random_sample(cache, sample_size=10)

        assert len(sample) == 2


class TestCheckUrlHealth:
    """Test URL health checking."""

    @pytest.mark.asyncio
    async def test_delegates_to_scraper(self):
        """Should delegate URL check to scraper."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()
        service.scraper = MagicMock()
        service.scraper.check_url_status = AsyncMock(return_value=True)

        result = await service._check_url_health("https://fandango.com/test")

        assert result is True
        service.scraper.check_url_status.assert_called_once_with("https://fandango.com/test")

    @pytest.mark.asyncio
    async def test_handles_unhealthy_url(self):
        """Should return False for unhealthy URLs."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()
        service.scraper = MagicMock()
        service.scraper.check_url_status = AsyncMock(return_value=False)

        result = await service._check_url_health("https://fandango.com/broken")

        assert result is False


class TestAttemptRepair:
    """Test theater URL repair attempts."""

    @pytest.mark.asyncio
    async def test_returns_new_data_on_success(self):
        """Should return new theater data when discovery succeeds."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()
        service.scraper = MagicMock()
        service.scraper.discover_theater_url = AsyncMock(return_value={
            'found': True,
            'theater_name': 'AMC Test Cinema',
            'url': 'https://fandango.com/amc-test',
            'theater_code': 'AMCTEST'
        })

        result = await service._attempt_repair("AMC Test", "53703")

        assert result is not None
        assert result['name'] == 'AMC Test Cinema'
        assert result['url'] == 'https://fandango.com/amc-test'

    @pytest.mark.asyncio
    async def test_returns_none_on_not_found(self):
        """Should return None when theater not found on Fandango."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()
        service.scraper = MagicMock()
        service.scraper.discover_theater_url = AsyncMock(return_value={'found': False})

        result = await service._attempt_repair("Unknown Theater", None)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_discovery_error(self):
        """Should return None when discovery raises exception."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()
        service.scraper = MagicMock()
        service.scraper.discover_theater_url = AsyncMock(side_effect=Exception("Network error"))

        result = await service._attempt_repair("Error Theater", None)

        assert result is None


class TestRunHealthCheck:
    """Test health check execution."""

    @pytest.mark.asyncio
    async def test_returns_ok_when_below_threshold(self, tmp_path):
        """Should return ok status when failure rate is below threshold."""
        from app.cache_maintenance_service import CacheMaintenanceService

        # Create cache with valid theaters
        cache_data = {
            "markets": {
                "Market A": {
                    "theaters": [
                        {"name": f"Theater {i}", "url": f"https://fandango.com/{i}"}
                        for i in range(15)
                    ]
                }
            }
        }
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps(cache_data))

        service = CacheMaintenanceService(cache_file=str(cache_file))
        service.scraper = MagicMock()
        # 9/10 healthy = 10% failure rate
        service.scraper.check_url_status = AsyncMock(side_effect=[
            True, True, True, True, True, True, True, True, True, False
        ])

        result = await service.run_health_check()

        assert result['status'] == 'ok'
        assert result['checked'] == 10
        assert result['failed'] == 1
        assert result['failure_rate_percent'] == 10.0

    @pytest.mark.asyncio
    async def test_returns_alert_when_above_threshold(self, tmp_path):
        """Should return alert status when failure rate exceeds threshold."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_data = {
            "markets": {
                "Market A": {
                    "theaters": [
                        {"name": f"Theater {i}", "url": f"https://fandango.com/{i}"}
                        for i in range(15)
                    ]
                }
            }
        }
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps(cache_data))

        service = CacheMaintenanceService(cache_file=str(cache_file))
        service.scraper = MagicMock()
        # 5/10 healthy = 50% failure rate (above 30% threshold)
        service.scraper.check_url_status = AsyncMock(side_effect=[
            True, False, True, False, True, False, False, False, True, True
        ])

        result = await service.run_health_check()

        assert result['status'] == 'alert'
        assert result['failed'] >= 4
        assert 'alert' in result

    @pytest.mark.asyncio
    async def test_handles_missing_cache(self, tmp_path):
        """Should handle missing cache file."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService(cache_file=str(tmp_path / "missing.json"))

        result = await service.run_health_check()

        assert result['status'] == 'error'
        assert 'Cache not found' in result['message']

    @pytest.mark.asyncio
    async def test_handles_no_theaters_to_check(self, tmp_path):
        """Should handle cache with no valid theaters."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_data = {"markets": {}}
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps(cache_data))

        service = CacheMaintenanceService(cache_file=str(cache_file))

        result = await service.run_health_check()

        assert result['status'] == 'ok'
        assert result['checked'] == 0


class TestRunRepair:
    """Test repair execution."""

    @pytest.mark.asyncio
    async def test_repairs_failed_theaters(self, tmp_path):
        """Should attempt to repair failed theaters."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_data = {
            "markets": {
                "Test Market": {
                    "theaters": [
                        {"name": "Broken Theater", "url": ""}
                    ]
                }
            }
        }
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps(cache_data))

        service = CacheMaintenanceService(cache_file=str(cache_file))
        service.scraper = MagicMock()
        service.scraper.discover_theater_url = AsyncMock(return_value={
            'found': True,
            'theater_name': 'Fixed Theater',
            'url': 'https://fandango.com/fixed',
            'theater_code': 'FIXED'
        })

        with patch.object(service, '_load_markets_data', return_value={}):
            result = await service.run_repair()

        assert result['repaired'] == 1
        assert result['still_failed'] == 0
        assert len(result['repaired_theaters']) == 1
        assert result['repaired_theaters'][0]['new_name'] == 'Fixed Theater'

    @pytest.mark.asyncio
    async def test_tracks_failed_repairs(self, tmp_path):
        """Should track theaters that couldn't be repaired."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_data = {
            "markets": {
                "Test Market": {
                    "theaters": [
                        {"name": "Unknown Theater", "url": ""}
                    ]
                }
            }
        }
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps(cache_data))

        service = CacheMaintenanceService(cache_file=str(cache_file))
        service.scraper = MagicMock()
        service.scraper.discover_theater_url = AsyncMock(return_value={'found': False})

        with patch.object(service, '_load_markets_data', return_value={}):
            result = await service.run_repair()

        assert result['repaired'] == 0
        assert result['still_failed'] == 1

    @pytest.mark.asyncio
    async def test_respects_max_repair_limit(self, tmp_path):
        """Should respect maximum repair attempts per run."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_data = {
            "markets": {
                "Test Market": {
                    "theaters": [
                        {"name": f"Broken Theater {i}", "url": ""}
                        for i in range(30)
                    ]
                }
            }
        }
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps(cache_data))

        service = CacheMaintenanceService(cache_file=str(cache_file))
        service.scraper = MagicMock()
        service.scraper.discover_theater_url = AsyncMock(return_value={'found': False})

        with patch.object(service, '_load_markets_data', return_value={}):
            result = await service.run_repair(max_repairs=5)

        assert result['attempted'] == 5
        assert result['total_failed'] == 30

    @pytest.mark.asyncio
    async def test_no_repairs_when_cache_healthy(self, tmp_path):
        """Should return early when no failed theaters."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_data = {
            "markets": {
                "Test Market": {
                    "theaters": [
                        {"name": "Good Theater", "url": "https://fandango.com/good"}
                    ]
                }
            }
        }
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps(cache_data))

        service = CacheMaintenanceService(cache_file=str(cache_file))

        result = await service.run_repair()

        assert result['repaired'] == 0
        assert 'No failed theaters' in result.get('message', '')


class TestRunMaintenance:
    """Test full maintenance cycle."""

    @pytest.mark.asyncio
    async def test_runs_health_check_and_repair(self, tmp_path):
        """Should run both health check and repair."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_data = {
            "markets": {
                "Test Market": {
                    "theaters": [
                        {"name": f"Theater {i}", "url": f"https://fandango.com/{i}"}
                        for i in range(15)
                    ]
                }
            }
        }
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps(cache_data))

        service = CacheMaintenanceService(cache_file=str(cache_file))
        service.scraper = MagicMock()
        service.scraper.check_url_status = AsyncMock(return_value=True)

        result = await service.run_maintenance()

        assert 'health_check' in result
        assert 'repairs' in result
        assert 'timestamp' in result
        assert 'duration_seconds' in result
        assert result['overall_status'] in ['ok', 'alert', 'error']

    @pytest.mark.asyncio
    async def test_logs_maintenance_result(self, tmp_path):
        """Should log maintenance result to file."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_data = {"markets": {}}
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps(cache_data))

        log_file = tmp_path / "maintenance.log"

        service = CacheMaintenanceService(cache_file=str(cache_file))
        service.maintenance_log_file = str(log_file)

        await service.run_maintenance()

        assert log_file.exists()
        log_content = log_file.read_text()
        log_entry = json.loads(log_content.strip())
        assert 'timestamp' in log_entry

    @pytest.mark.asyncio
    async def test_sets_alert_status_on_high_failure_rate(self, tmp_path):
        """Should set alert status when health check fails."""
        from app.cache_maintenance_service import CacheMaintenanceService

        cache_data = {
            "markets": {
                "Test Market": {
                    "theaters": [
                        {"name": f"Theater {i}", "url": f"https://fandango.com/{i}"}
                        for i in range(15)
                    ]
                }
            }
        }
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps(cache_data))

        service = CacheMaintenanceService(cache_file=str(cache_file))
        service.scraper = MagicMock()
        # High failure rate
        service.scraper.check_url_status = AsyncMock(return_value=False)

        result = await service.run_maintenance()

        assert result['overall_status'] == 'alert'
        assert 'alert_message' in result


class TestGetMaintenanceHistory:
    """Test maintenance history retrieval."""

    def test_returns_recent_entries(self, tmp_path):
        """Should return recent maintenance log entries."""
        from app.cache_maintenance_service import CacheMaintenanceService

        log_file = tmp_path / "maintenance.log"
        entries = [
            {"timestamp": "2026-01-10T10:00:00", "overall_status": "ok"},
            {"timestamp": "2026-01-11T10:00:00", "overall_status": "ok"},
            {"timestamp": "2026-01-12T10:00:00", "overall_status": "alert"}
        ]
        log_file.write_text("\n".join(json.dumps(e) for e in entries))

        service = CacheMaintenanceService()
        service.maintenance_log_file = str(log_file)

        history = service.get_maintenance_history(limit=2)

        assert len(history) == 2
        # Most recent first
        assert history[0]['timestamp'] == "2026-01-12T10:00:00"

    def test_returns_empty_list_for_missing_log(self, tmp_path):
        """Should return empty list when log file doesn't exist."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()
        service.maintenance_log_file = str(tmp_path / "missing.log")

        history = service.get_maintenance_history()

        assert history == []

    def test_handles_invalid_log_entries(self, tmp_path):
        """Should skip invalid JSON entries in log."""
        from app.cache_maintenance_service import CacheMaintenanceService

        log_file = tmp_path / "maintenance.log"
        log_file.write_text(
            '{"timestamp": "2026-01-10", "status": "ok"}\n'
            'invalid json line\n'
            '{"timestamp": "2026-01-11", "status": "ok"}\n'
        )

        service = CacheMaintenanceService()
        service.maintenance_log_file = str(log_file)

        history = service.get_maintenance_history()

        # Should have 2 valid entries
        assert len(history) == 2


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    @pytest.mark.asyncio
    async def test_run_cache_maintenance_function(self):
        """run_cache_maintenance should run maintenance and return result."""
        from app.cache_maintenance_service import run_cache_maintenance

        with patch('app.cache_maintenance_service.CacheMaintenanceService') as MockService:
            mock_instance = MagicMock()
            mock_instance.run_maintenance = AsyncMock(return_value={'status': 'ok'})
            MockService.return_value = mock_instance

            result = await run_cache_maintenance()

            assert result['status'] == 'ok'
            mock_instance.run_maintenance.assert_called_once()

    def test_run_cache_maintenance_sync_function(self):
        """run_cache_maintenance_sync should run synchronously."""
        from app.cache_maintenance_service import run_cache_maintenance_sync

        with patch('app.cache_maintenance_service.CacheMaintenanceService') as MockService:
            mock_instance = MagicMock()
            mock_instance.run_maintenance = AsyncMock(return_value={'status': 'ok'})
            MockService.return_value = mock_instance

            result = run_cache_maintenance_sync()

            assert result['status'] == 'ok'


class TestLoadMarketsData:
    """Test markets data loading for ZIP code lookups."""

    def test_loads_markets_from_data_directory(self, tmp_path):
        """Should load markets.json files from company directories."""
        from app.cache_maintenance_service import CacheMaintenanceService

        # Create data directory structure
        data_dir = tmp_path / "data"
        company_dir = data_dir / "TestCompany"
        company_dir.mkdir(parents=True)

        markets_data = {
            "US": {
                "Midwest": {
                    "Madison": {
                        "theaters": [
                            {"name": "Marcus Madison", "zip": "53703"}
                        ]
                    }
                }
            }
        }
        (company_dir / "markets.json").write_text(json.dumps(markets_data))

        service = CacheMaintenanceService()

        with patch('app.cache_maintenance_service.PROJECT_DIR', str(tmp_path)):
            result = service._load_markets_data()

        assert "US" in result
        assert "Midwest" in result["US"]


class TestFindZipForTheater:
    """Test ZIP code lookup for theaters."""

    def test_finds_zip_code_for_theater(self):
        """Should find ZIP code from markets data."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()

        markets_data = {
            "US": {
                "Midwest": {
                    "Madison": {
                        "theaters": [
                            {"name": "Marcus Madison Cinema", "zip": "53703"}
                        ]
                    }
                }
            }
        }

        zip_code = service._find_zip_for_theater(
            "Marcus Madison Cinema", "Madison", markets_data
        )

        assert zip_code == "53703"

    def test_returns_none_when_not_found(self):
        """Should return None when theater not in markets data."""
        from app.cache_maintenance_service import CacheMaintenanceService

        service = CacheMaintenanceService()

        markets_data = {}

        zip_code = service._find_zip_for_theater(
            "Unknown Theater", "Unknown Market", markets_data
        )

        assert zip_code is None
