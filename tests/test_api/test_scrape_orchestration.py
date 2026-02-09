"""
Tests for scrape job orchestration (execution.py).

These tests verify the control flow of run_scrape_job() with mocked
Scraper and database, catching:
- Job status transitions (pending → running → completed/failed)
- Progress callback wiring
- Config access at function entry (the UnboundLocalError regression)
- Database save path after scrape completes
- Cancellation handling
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.routers.scrapes._shared import _scrape_jobs

# Common patch targets after db_adapter migration
_PATCH_UPSERT = "api.routers.scrapes.execution.upsert_showings"
_PATCH_CREATE_RUN = "api.routers.scrapes.execution.create_scrape_run"
_PATCH_SAVE_PRICES = "api.routers.scrapes.execution.save_prices"
_PATCH_UPDATE_STATUS = "api.routers.scrapes.execution.update_scrape_run_status"


@pytest.fixture(autouse=True)
def clean_jobs():
    """Clear the in-memory job dict before/after each test."""
    _scrape_jobs.clear()
    yield
    _scrape_jobs.clear()


def _create_job(job_id: int, theaters: list) -> dict:
    """Create a minimal job entry in the shared dict."""
    job = {
        "status": "pending",
        "mode": "market",
        "market": "Test Market",
        "theaters": theaters,
        "dates": ["2026-02-07"],
        "progress": 0,
        "theaters_completed": 0,
        "showings_completed": 0,
        "showings_total": 0,
        "current_theater": None,
        "current_showing": None,
        "results": [],
        "error": None,
    }
    _scrape_jobs[job_id] = job
    return job


MOCK_THEATERS = [{"name": "Movie Tavern Hulen", "url": "https://fandango.com/movie-tavern-hulen"}]

MOCK_SHOWTIME_DATA = {
    "Movie Tavern Hulen": [
        {"film_title": "Mercy (2026)", "showtime": "12:30pm", "format": "Standard"},
        {"film_title": "Gladiator", "showtime": "7:00pm", "format": "IMAX"},
    ]
}

MOCK_SCRAPE_RESULT = [
    {
        "Theater Name": "Movie Tavern Hulen",
        "Film Title": "Mercy (2026)",
        "Showtime": "12:30pm",
        "Price": "$12.99",
        "Ticket Type": "Adult",
        "Format": "Standard",
        "theater_name": "Movie Tavern Hulen",
        "film_title": "Mercy (2026)",
        "showtime": "12:30pm",
        "price": "$12.99",
        "price_raw": 12.99,
        "ticket_type": "Adult",
        "format": "Standard",
    },
]


class TestJobLifecycle:
    """Test job status transitions through run_scrape_job."""

    @pytest.mark.asyncio
    @patch(_PATCH_UPDATE_STATUS)
    @patch(_PATCH_SAVE_PRICES)
    @patch(_PATCH_CREATE_RUN, return_value=100)
    @patch(_PATCH_UPSERT)
    @patch("api.routers.scrapes.execution.track_scrape_completed")
    async def test_job_transitions_to_running_then_completed(
        self, mock_track, mock_upsert, mock_create, mock_save, mock_update
    ):
        """Job should go pending → running → completed."""
        from api.routers.scrapes.execution import run_scrape_job

        job = _create_job(1, MOCK_THEATERS)

        mock_scraper = AsyncMock()
        mock_scraper.get_all_showings_for_theaters.return_value = MOCK_SHOWTIME_DATA
        mock_scraper.scrape_details.return_value = (MOCK_SCRAPE_RESULT, None)

        with patch("app.scraper.Scraper", return_value=mock_scraper):
            await run_scrape_job(
                job_id=1,
                mode="market",
                market="Test Market",
                theaters=MOCK_THEATERS,
                dates=["2026-02-07"],
            )

        assert job["status"] == "completed"
        assert job["progress"] == 100
        assert job["theaters_completed"] == 1
        assert len(job["results"]) > 0

    @pytest.mark.asyncio
    @patch(_PATCH_UPSERT)
    @patch("api.routers.scrapes.execution.track_scrape_completed")
    async def test_lineup_mode_skips_price_scraping(self, mock_track, mock_upsert):
        """Lineup mode should fetch showtimes but skip price scraping."""
        from api.routers.scrapes.execution import run_scrape_job

        job = _create_job(1, MOCK_THEATERS)

        mock_scraper = AsyncMock()
        mock_scraper.get_all_showings_for_theaters.return_value = MOCK_SHOWTIME_DATA

        with patch("app.scraper.Scraper", return_value=mock_scraper):
            await run_scrape_job(
                job_id=1,
                mode="lineup",
                market="Test Market",
                theaters=MOCK_THEATERS,
                dates=["2026-02-07"],
            )

        assert job["status"] == "completed"
        # scrape_details should NOT have been called for lineup mode
        mock_scraper.scrape_details.assert_not_called()

    @pytest.mark.asyncio
    @patch(_PATCH_UPDATE_STATUS)
    @patch(_PATCH_SAVE_PRICES)
    @patch(_PATCH_CREATE_RUN)
    @patch(_PATCH_UPSERT)
    @patch("api.routers.scrapes.execution.track_event")
    async def test_job_transitions_to_failed_on_error(
        self, mock_track, mock_upsert, mock_create, mock_save, mock_update
    ):
        """Job should transition to failed if Scraper constructor raises.

        Note: errors inside the per-theater loop are caught and logged,
        so to trigger the outer except (which sets status='failed'),
        the error must happen before the loop — e.g., Scraper() failing.
        """
        from api.routers.scrapes.execution import run_scrape_job

        job = _create_job(1, MOCK_THEATERS)

        with patch("app.scraper.Scraper", side_effect=RuntimeError("Playwright install missing")):
            await run_scrape_job(
                job_id=1,
                mode="market",
                market="Test Market",
                theaters=MOCK_THEATERS,
                dates=["2026-02-07"],
            )

        assert job["status"] == "failed"
        assert "Playwright install missing" in job["error"]

    @pytest.mark.asyncio
    @patch(_PATCH_UPSERT)
    @patch("api.routers.scrapes.execution.track_scrape_completed")
    async def test_cancelled_job_stops_early(self, mock_track, mock_upsert):
        """If job is cancelled mid-scrape, it should stop processing theaters.

        The cancel check is at the top of the theater loop, so we set
        status='cancelled' during the first theater's scrape. The second
        theater should never be scraped.
        """
        from api.routers.scrapes.execution import run_scrape_job

        theaters = [
            {"name": "Theater A", "url": "https://fandango.com/a"},
            {"name": "Theater B", "url": "https://fandango.com/b"},
        ]
        job = _create_job(1, theaters)

        call_count = 0

        mock_scraper = AsyncMock()

        async def cancel_during_scrape(theater_objs, date_str):
            nonlocal call_count
            call_count += 1
            # Cancel after first theater — next iteration should break
            job["status"] = "cancelled"
            theater_name = theater_objs[0]["name"]
            return {theater_name: MOCK_SHOWTIME_DATA["Movie Tavern Hulen"]}

        mock_scraper.get_all_showings_for_theaters.side_effect = cancel_during_scrape

        with patch("app.scraper.Scraper", return_value=mock_scraper):
            await run_scrape_job(
                job_id=1,
                mode="lineup",
                market="Test",
                theaters=theaters,
                dates=["2026-02-07"],
            )

        # Scraper should have been called only once (Theater A),
        # Theater B should have been skipped due to cancellation
        assert call_count == 1, f"Expected 1 scrape call, got {call_count}"


class TestConfigAccess:
    """Regression tests for config variable scoping."""

    @pytest.mark.asyncio
    @patch(_PATCH_UPDATE_STATUS)
    @patch(_PATCH_SAVE_PRICES)
    @patch(_PATCH_CREATE_RUN)
    @patch(_PATCH_UPSERT)
    @patch("api.routers.scrapes.execution.track_scrape_completed")
    async def test_config_accessible_at_function_entry(
        self, mock_track, mock_upsert, mock_create, mock_save, mock_update
    ):
        """config.DEFAULT_COMPANY_ID must be accessible at the top of run_scrape_job.

        Regression: `from app import config` inside the function body made Python
        treat `config` as a local variable for the entire function scope, causing
        UnboundLocalError at the line that accesses config.DEFAULT_COMPANY_ID.
        """
        from api.routers.scrapes.execution import run_scrape_job

        job = _create_job(1, MOCK_THEATERS)

        mock_scraper = AsyncMock()
        mock_scraper.get_all_showings_for_theaters.return_value = {}  # No data = fast exit

        with patch("app.scraper.Scraper", return_value=mock_scraper):
            # This should NOT raise UnboundLocalError
            await run_scrape_job(
                job_id=1,
                mode="lineup",
                market="Test",
                theaters=MOCK_THEATERS,
                dates=["2026-02-07"],
            )

        # If we get here, config was accessible (no UnboundLocalError)
        assert job["status"] == "completed"


class TestProgressTracking:
    """Test progress callback mechanics."""

    @pytest.mark.asyncio
    @patch(_PATCH_UPDATE_STATUS)
    @patch(_PATCH_SAVE_PRICES)
    @patch(_PATCH_CREATE_RUN, return_value=100)
    @patch(_PATCH_UPSERT)
    @patch("api.routers.scrapes.execution.track_scrape_completed")
    async def test_progress_updates_during_scrape(
        self, mock_track, mock_upsert, mock_create, mock_save, mock_update
    ):
        """Progress should update as showings are processed."""
        from api.routers.scrapes.execution import run_scrape_job

        job = _create_job(1, MOCK_THEATERS)

        progress_values = []

        mock_scraper = AsyncMock()
        mock_scraper.get_all_showings_for_theaters.return_value = MOCK_SHOWTIME_DATA

        async def mock_scrape_details(theaters, selected, progress_callback=None):
            # Simulate progress callbacks
            if progress_callback:
                progress_callback(1, 2)
                progress_values.append(job.get("progress", 0))
                progress_callback(2, 2)
                progress_values.append(job.get("progress", 0))
            return (MOCK_SCRAPE_RESULT, None)

        mock_scraper.scrape_details.side_effect = mock_scrape_details

        with patch("app.scraper.Scraper", return_value=mock_scraper):
            await run_scrape_job(
                job_id=1,
                mode="market",
                market="Test",
                theaters=MOCK_THEATERS,
                dates=["2026-02-07"],
            )

        # Progress should have increased
        assert len(progress_values) == 2
        assert progress_values[0] > 0  # 50% after 1/2
        assert progress_values[1] >= progress_values[0]  # Monotonically increasing

    @pytest.mark.asyncio
    @patch(_PATCH_UPDATE_STATUS)
    @patch(_PATCH_SAVE_PRICES)
    @patch(_PATCH_CREATE_RUN, return_value=100)
    @patch(_PATCH_UPSERT)
    @patch("api.routers.scrapes.execution.track_scrape_completed")
    async def test_selected_keys_lock_total(
        self, mock_track, mock_upsert, mock_create, mock_save, mock_update
    ):
        """When user provides selected_showtime_keys, total should be fixed."""
        from api.routers.scrapes.execution import run_scrape_job

        job = _create_job(1, MOCK_THEATERS)

        selected_keys = [
            "2026-02-07|Movie Tavern Hulen|Mercy (2026)|12:30pm|Standard",
        ]

        mock_scraper = AsyncMock()
        mock_scraper.get_all_showings_for_theaters.return_value = MOCK_SHOWTIME_DATA
        mock_scraper.scrape_details.return_value = (MOCK_SCRAPE_RESULT, None)

        with patch("app.scraper.Scraper", return_value=mock_scraper):
            await run_scrape_job(
                job_id=1,
                mode="market",
                market="Test",
                theaters=MOCK_THEATERS,
                dates=["2026-02-07"],
                selected_showtime_keys=selected_keys,
            )

        # Total should be locked to the number of selected keys
        assert job["showings_total"] == 1


class TestDatabaseSave:
    """Test the database save path after scrape completes."""

    @pytest.mark.asyncio
    @patch(_PATCH_UPDATE_STATUS)
    @patch(_PATCH_SAVE_PRICES)
    @patch(_PATCH_CREATE_RUN, return_value=42)
    @patch(_PATCH_UPSERT)
    @patch("api.routers.scrapes.execution.track_scrape_completed")
    async def test_results_saved_to_database(
        self, mock_track, mock_upsert, mock_create, mock_save, mock_update
    ):
        """Scrape results should be saved via create_scrape_run + save_prices."""
        from api.routers.scrapes.execution import run_scrape_job

        _create_job(1, MOCK_THEATERS)

        mock_scraper = AsyncMock()
        mock_scraper.get_all_showings_for_theaters.return_value = MOCK_SHOWTIME_DATA
        mock_scraper.scrape_details.return_value = (MOCK_SCRAPE_RESULT, None)

        with patch("app.scraper.Scraper", return_value=mock_scraper):
            await run_scrape_job(
                job_id=1,
                mode="market",
                market="Test Market",
                theaters=MOCK_THEATERS,
                dates=["2026-02-07"],
            )

        mock_create.assert_called_once_with("market", "Market: Test Market")
        mock_save.assert_called_once()
        # Verify run_id was passed correctly
        call_args = mock_save.call_args
        assert call_args[0][0] == 42  # run_id

    @pytest.mark.asyncio
    @patch(_PATCH_CREATE_RUN)
    @patch(_PATCH_SAVE_PRICES)
    @patch(_PATCH_UPSERT)
    @patch("api.routers.scrapes.execution.track_scrape_completed")
    async def test_no_results_skips_database_save(
        self, mock_track, mock_upsert, mock_save, mock_create
    ):
        """When scraper returns no results, database save should be skipped."""
        from api.routers.scrapes.execution import run_scrape_job

        _create_job(1, MOCK_THEATERS)

        mock_scraper = AsyncMock()
        mock_scraper.get_all_showings_for_theaters.return_value = {"Movie Tavern Hulen": []}

        with patch("app.scraper.Scraper", return_value=mock_scraper):
            await run_scrape_job(
                job_id=1,
                mode="market",
                market="Test",
                theaters=MOCK_THEATERS,
                dates=["2026-02-07"],
            )

        mock_create.assert_not_called()
        mock_save.assert_not_called()
