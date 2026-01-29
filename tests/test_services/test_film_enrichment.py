"""
Tests for film enrichment functionality in app/db_adapter.py
"""
import pytest
from unittest.mock import patch, MagicMock


class TestEnrichNewFilms:
    """Test enrich_new_films() function."""

    def test_returns_empty_for_no_titles(self, set_test_company):
        """Should return empty result for empty title list."""
        from app.db_adapter import enrich_new_films

        result = enrich_new_films([])

        assert result == {'enriched': 0, 'failed': 0, 'skipped': 0}

    def test_returns_skipped_when_no_company_id(self):
        """Should return skipped when no company ID is set."""
        from app.db_adapter import enrich_new_films
        from app import config

        # Temporarily clear company ID
        original = getattr(config, 'CURRENT_COMPANY_ID', None)
        config.CURRENT_COMPANY_ID = None

        try:
            result = enrich_new_films(['Test Movie'])
            assert result['skipped'] == 1
        finally:
            config.CURRENT_COMPANY_ID = original

    def test_skips_existing_films(self, set_test_company):
        """Should skip films that already exist in database."""
        from app.db_adapter import enrich_new_films

        with patch('app.db_adapter.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Mock existing film query - film already exists
            session_mock.query().filter().all.side_effect = [
                [('Existing Movie',)],  # Existing films
                []  # Ignored films
            ]

            result = enrich_new_films(['Existing Movie'])

            # Should be skipped, not enriched
            assert result['skipped'] == 1
            assert result['enriched'] == 0

    def test_skips_ignored_films(self, set_test_company):
        """Should skip films in the ignored list."""
        from app.db_adapter import enrich_new_films

        with patch('app.db_adapter.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Mock queries - film is in ignored list
            session_mock.query().filter().all.side_effect = [
                [],  # No existing films
                [('Ignored Film',)]  # Ignored films
            ]

            result = enrich_new_films(['Ignored Film'])

            assert result['skipped'] == 1
            assert result['enriched'] == 0

    def test_enriches_new_films_with_omdb(self, set_test_company, mock_omdb_response):
        """Should enrich new films with OMDB data."""
        from app.db_adapter import enrich_new_films

        with patch('app.db_adapter.get_session') as mock_session, \
             patch('app.omdb_client.OMDbClient') as MockOMDb, \
             patch('app.db_adapter.upsert_film_details') as mock_save:

            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # No existing or ignored films
            session_mock.query().filter().all.return_value = []

            # OMDB returns data
            mock_omdb = MagicMock()
            mock_omdb.get_film_details.return_value = mock_omdb_response
            MockOMDb.return_value = mock_omdb

            result = enrich_new_films(['Avatar: The Way of Water'], async_mode=False)

            assert result['enriched'] == 1
            mock_save.assert_called_once()

    def test_logs_unmatched_films(self, set_test_company):
        """Should log films that couldn't be matched to OMDB."""
        from app.db_adapter import enrich_new_films

        with patch('app.db_adapter.get_session') as mock_session, \
             patch('app.omdb_client.OMDbClient') as MockOMDb, \
             patch('app.db_adapter.log_unmatched_film') as mock_unmatched:

            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # No existing or ignored films
            session_mock.query().filter().all.return_value = []

            # OMDB returns None (no match)
            mock_omdb = MagicMock()
            mock_omdb.get_film_details.return_value = None
            MockOMDb.return_value = mock_omdb

            result = enrich_new_films(['Unknown Movie XYZ'], async_mode=False)

            assert result['failed'] == 1
            mock_unmatched.assert_called_once_with('Unknown Movie XYZ', company_id=set_test_company)

    def test_async_mode_starts_background_thread(self, set_test_company):
        """Should start background thread in async mode."""
        from app.db_adapter import enrich_new_films

        with patch('app.db_adapter.get_session') as mock_session, \
             patch('threading.Thread') as MockThread:

            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # No existing or ignored films
            session_mock.query().filter().all.return_value = []

            mock_thread = MagicMock()
            MockThread.return_value = mock_thread

            result = enrich_new_films(['New Movie'], async_mode=True)

            assert 'pending' in result
            assert result['pending'] == 1
            mock_thread.start.assert_called_once()

    def test_deduplicates_film_titles(self, set_test_company):
        """Should deduplicate film titles before processing."""
        from app.db_adapter import enrich_new_films

        with patch('app.db_adapter.get_session') as mock_session, \
             patch('app.omdb_client.OMDbClient') as MockOMDb, \
             patch('app.db_adapter.upsert_film_details'):

            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # No existing or ignored films
            session_mock.query().filter().all.return_value = []

            mock_omdb = MagicMock()
            mock_omdb.get_film_details.return_value = {'film_title': 'Test'}
            MockOMDb.return_value = mock_omdb

            # Pass duplicate titles
            result = enrich_new_films(
                ['Same Movie', 'Same Movie', 'Same Movie'],
                async_mode=False
            )

            # Should only process once
            assert mock_omdb.get_film_details.call_count == 1


class TestEnrichFilmsSync:
    """Test _enrich_films_sync() internal function."""

    def test_cleans_film_titles_before_lookup(self, set_test_company):
        """Should clean film titles before OMDB lookup."""
        from app.db_adapter import _enrich_films_sync
        from app import config

        company_id = config.CURRENT_COMPANY_ID

        with patch('app.omdb_client.OMDbClient') as MockOMDb, \
             patch('app.db_adapter.upsert_film_details'), \
             patch('app.utils.clean_film_title') as mock_clean:

            mock_clean.return_value = 'Cleaned Title'
            mock_omdb = MagicMock()
            mock_omdb.get_film_details.return_value = {'film_title': 'Cleaned Title'}
            MockOMDb.return_value = mock_omdb

            _enrich_films_sync(['Original Title (Special Event)'], company_id=company_id)

            mock_clean.assert_called_with('Original Title (Special Event)')

    def test_preserves_original_title_in_database(self, set_test_company):
        """Should save with original title even after cleaning for OMDB lookup."""
        from app.db_adapter import _enrich_films_sync
        from app import config

        company_id = config.CURRENT_COMPANY_ID

        with patch('app.omdb_client.OMDbClient') as MockOMDb, \
             patch('app.db_adapter.upsert_film_details') as mock_save, \
             patch('app.utils.clean_film_title') as mock_clean:

            mock_clean.return_value = 'Cleaned Title'
            mock_omdb = MagicMock()
            mock_omdb.get_film_details.return_value = {
                'film_title': 'OMDB Title',
                'imdb_id': 'tt123'
            }
            MockOMDb.return_value = mock_omdb

            _enrich_films_sync(['Original Title (2024)'], company_id=company_id)

            # Should save with original title
            call_args = mock_save.call_args[0][0]
            assert call_args['film_title'] == 'Original Title (2024)'

    def test_handles_omdb_client_initialization_failure(self, set_test_company):
        """Should handle OMDB client init failure gracefully."""
        from app.db_adapter import _enrich_films_sync
        from app import config

        company_id = config.CURRENT_COMPANY_ID

        with patch('app.omdb_client.OMDbClient') as MockOMDb:
            MockOMDb.side_effect = ValueError("API key not found")

            result = _enrich_films_sync(['Test Movie'], company_id=company_id)

            assert result['failed'] == 1
            assert result['enriched'] == 0

    def test_handles_individual_film_errors(self, set_test_company):
        """Should continue processing if one film fails."""
        from app.db_adapter import _enrich_films_sync
        from app import config

        company_id = config.CURRENT_COMPANY_ID

        with patch('app.omdb_client.OMDbClient') as MockOMDb, \
             patch('app.db_adapter.upsert_film_details') as mock_save, \
             patch('app.db_adapter.log_unmatched_film'):

            mock_omdb = MagicMock()
            # First film succeeds, second fails
            mock_omdb.get_film_details.side_effect = [
                {'film_title': 'Movie 1'},
                Exception("API Error")
            ]
            MockOMDb.return_value = mock_omdb

            result = _enrich_films_sync(['Movie 1', 'Movie 2'], company_id=company_id)

            assert result['enriched'] == 1
            assert result['failed'] == 1


class TestUpsertShowingsEnrichment:
    """Test that upsert_showings triggers enrichment."""

    def test_upsert_showings_collects_film_titles(self, set_test_company):
        """upsert_showings should collect unique film titles."""
        from app.db_adapter import upsert_showings

        with patch('app.db_adapter.get_session'), \
             patch('app.db_adapter.enrich_new_films') as mock_enrich:

            all_showings = {
                'Theater 1': [
                    {'film_title': 'Movie A', 'showtime': '7:00 PM', 'format': 'Standard', 'daypart': 'Evening'},
                    {'film_title': 'Movie B', 'showtime': '9:00 PM', 'format': 'Standard', 'daypart': 'Evening'}
                ],
                'Theater 2': [
                    {'film_title': 'Movie A', 'showtime': '7:30 PM', 'format': 'IMAX', 'daypart': 'Evening'}
                ]
            }

            upsert_showings(all_showings, '2026-01-15', enrich_films=True)

            # Should call enrich with unique titles (Movie A, Movie B)
            if mock_enrich.called:
                call_args = mock_enrich.call_args[0][0]
                assert set(call_args) == {'Movie A', 'Movie B'}

    def test_upsert_showings_can_disable_enrichment(self, set_test_company):
        """upsert_showings should skip enrichment if disabled."""
        from app.db_adapter import upsert_showings

        with patch('app.db_adapter.get_session'), \
             patch('app.db_adapter.enrich_new_films') as mock_enrich:

            all_showings = {
                'Theater 1': [
                    {'film_title': 'Movie A', 'showtime': '7:00 PM', 'format': 'Standard', 'daypart': 'Evening'}
                ]
            }

            upsert_showings(all_showings, '2026-01-15', enrich_films=False)

            mock_enrich.assert_not_called()

    def test_enrichment_failure_does_not_fail_upsert(self, set_test_company):
        """Enrichment failure should not fail the upsert operation."""
        from app.db_adapter import upsert_showings

        with patch('app.db_adapter.get_session'), \
             patch('app.db_adapter.enrich_new_films') as mock_enrich:

            mock_enrich.side_effect = Exception("Enrichment failed")

            all_showings = {
                'Theater 1': [
                    {'film_title': 'Movie A', 'showtime': '7:00 PM', 'format': 'Standard', 'daypart': 'Evening'}
                ]
            }

            # Should not raise exception
            upsert_showings(all_showings, '2026-01-15', enrich_films=True)
