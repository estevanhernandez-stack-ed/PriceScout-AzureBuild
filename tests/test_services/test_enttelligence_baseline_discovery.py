"""
Tests for app/enttelligence_baseline_discovery.py - EntTelligence baseline discovery.

These tests mirror the structure of test_baseline_discovery.py but focus on
the EntTelligence-specific service that queries the enttelligence_price_cache table.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date, timedelta
from decimal import Decimal


class TestEntTelligencePremiumFormatDetection:
    """Test premium format identification in EntTelligence service."""

    def test_identifies_imax_formats(self):
        """Should identify IMAX as premium."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("IMAX") is True
        assert service.is_premium_format("IMAX 3D") is True
        assert service.is_premium_format("IMAX with Laser") is True

    def test_identifies_dolby_formats(self):
        """Should identify Dolby formats as premium."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("Dolby Cinema") is True
        assert service.is_premium_format("Dolby Atmos") is True

    def test_identifies_3d_formats(self):
        """Should identify 3D formats as premium."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("3D") is True
        assert service.is_premium_format("RealD 3D") is True

    def test_identifies_plf_formats(self):
        """Should identify premium large formats."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("PLF") is True
        assert service.is_premium_format("XD") is True
        assert service.is_premium_format("RPX") is True

    def test_standard_format_not_premium(self):
        """Should not identify standard formats as premium."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("2D") is False
        assert service.is_premium_format("Standard") is False
        assert service.is_premium_format("Digital") is False
        assert service.is_premium_format(None) is False
        assert service.is_premium_format("") is False

    def test_case_insensitive_matching(self):
        """Should match premium formats case-insensitively."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("imax") is True
        assert service.is_premium_format("DOLBY CINEMA") is True
        assert service.is_premium_format("Imax With Laser") is True


class TestEntTelligencePercentileCalculation:
    """Test percentile calculation for baselines."""

    def test_calculates_25th_percentile(self):
        """Should correctly calculate 25th percentile."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        # Test data: [10, 12, 14, 16, 18, 20]
        # 25th percentile should be around 11.5
        data = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
        result = service._percentile(data, 25)

        assert result == pytest.approx(11.5, rel=0.1)

    def test_calculates_50th_percentile(self):
        """Should correctly calculate 50th percentile (median)."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        data = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
        result = service._percentile(data, 50)

        assert result == pytest.approx(15.0, rel=0.1)

    def test_handles_empty_data(self):
        """Should handle empty data gracefully."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        result = service._percentile([], 25)

        assert result == 0.0

    def test_handles_single_value(self):
        """Should handle single value."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        result = service._percentile([15.0], 25)

        assert result == 15.0

    def test_handles_two_values(self):
        """Should handle two values correctly."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        result = service._percentile([10.0, 20.0], 25)

        # 25th percentile of [10, 20] should be 12.5
        assert result == pytest.approx(12.5, rel=0.1)


class TestEntTelligenceBaselineDiscovery:
    """Test baseline discovery from EntTelligence cache data."""

    def test_discovers_baselines_from_cache(self):
        """Should discover baselines from EntTelligence cache."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        with patch('app.enttelligence_baseline_discovery.get_session') as mock_session:
            # Mock query results - individual records (6 fields each)
            # The updated code queries individual records, not aggregated groups
            mock_rows = [
                ("AMC Test Theater", "Adult", "2D", "AMC Entertainment", "Test Movie", Decimal('12.00')),
                ("AMC Test Theater", "Adult", "2D", "AMC Entertainment", "Test Movie", Decimal('12.50')),
                ("AMC Test Theater", "Adult", "2D", "AMC Entertainment", "Test Movie", Decimal('13.00')),
                ("AMC Test Theater", "Adult", "2D", "AMC Entertainment", "Test Movie", Decimal('13.50')),
                ("AMC Test Theater", "Adult", "2D", "AMC Entertainment", "Test Movie", Decimal('14.00')),
                ("AMC Test Theater", "Adult", "2D", "AMC Entertainment", "Test Movie", Decimal('14.50')),
                ("AMC Test Theater", "Adult", "2D", "AMC Entertainment", "Test Movie", Decimal('15.00')),
            ]

            session_ctx = MagicMock()
            session_ctx.query().filter().all.return_value = mock_rows
            mock_session.return_value.__enter__.return_value = session_ctx

            service = EntTelligenceBaselineDiscoveryService(company_id=1)
            baselines = service.discover_baselines(min_samples=5, lookback_days=30)

            # Should have queried the database and found 1 baseline
            assert mock_session.called
            assert len(baselines) == 1
            assert baselines[0]['theater_name'] == "AMC Test Theater"
            assert baselines[0]['ticket_type'] == "Adult"
            assert baselines[0]['format'] == "2D"
            assert baselines[0]['circuit_name'] == "AMC Entertainment"

    def test_excludes_premium_formats_from_baselines(self):
        """Should exclude premium formats from baseline calculation."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        with patch('app.enttelligence_baseline_discovery.get_session') as mock_session:
            # Mock query results with IMAX format (premium)
            mock_rows = [
                ("AMC Test Theater", "Adult", "IMAX", "AMC Entertainment", "Test Movie", Decimal('20.00')),
                ("AMC Test Theater", "Adult", "IMAX", "AMC Entertainment", "Test Movie", Decimal('21.00')),
                ("AMC Test Theater", "Adult", "IMAX", "AMC Entertainment", "Test Movie", Decimal('22.00')),
                ("AMC Test Theater", "Adult", "IMAX", "AMC Entertainment", "Test Movie", Decimal('23.00')),
                ("AMC Test Theater", "Adult", "IMAX", "AMC Entertainment", "Test Movie", Decimal('24.00')),
                ("AMC Test Theater", "Adult", "IMAX", "AMC Entertainment", "Test Movie", Decimal('25.00')),
            ]

            session_ctx = MagicMock()
            session_ctx.query().filter().all.return_value = mock_rows
            mock_session.return_value.__enter__.return_value = session_ctx

            service = EntTelligenceBaselineDiscoveryService(company_id=1)
            baselines = service.discover_baselines(
                min_samples=5,
                lookback_days=30,
                exclude_premium=True
            )

            # IMAX should be excluded
            assert len(baselines) == 0

    def test_filters_by_circuit(self):
        """Should filter baselines by circuit when specified."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        with patch('app.enttelligence_baseline_discovery.get_session') as mock_session:
            session_ctx = MagicMock()
            session_ctx.query().filter().group_by().having().all.return_value = []
            mock_session.return_value.__enter__.return_value = session_ctx

            service = EntTelligenceBaselineDiscoveryService(company_id=1)
            baselines = service.discover_baselines(
                min_samples=5,
                lookback_days=30,
                circuit_filter=["AMC Entertainment"]
            )

            # Should have applied circuit filter
            assert mock_session.called


class TestEntTelligenceCircuitAnalysis:
    """Test circuit-level analysis from EntTelligence data."""

    def test_analyzes_by_circuit(self):
        """Should provide circuit-level analysis."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        with patch('app.enttelligence_baseline_discovery.get_session') as mock_session:
            # Mock circuit query result (6 values)
            circuit_row = MagicMock()
            circuit_row.__iter__ = lambda self: iter([
                "AMC Entertainment",  # circuit_name
                1000,                 # record_count
                50,                   # theater_count
                Decimal('13.50'),     # avg_price
                Decimal('10.00'),     # min_price
                Decimal('20.00')      # max_price
            ])

            # Mock format query result (3 values)
            format_row = MagicMock()
            format_row.__iter__ = lambda self: iter([
                "2D",                 # format
                5000,                 # count
                Decimal('12.50')      # avg_price
            ])

            # Mock overall stats query
            overall_row = MagicMock()
            overall_row.total_records = 10000
            overall_row.total_theaters = 100
            overall_row.total_circuits = 10
            overall_row.min_date = date(2026, 1, 1)
            overall_row.max_date = date(2026, 1, 15)
            overall_row.overall_avg_price = Decimal('13.00')

            # Mock coverage query
            coverage_row = MagicMock()
            coverage_row.play_date = date(2026, 1, 10)
            coverage_row.count = 500

            session_ctx = MagicMock()

            # Use side_effect to return different results for different .all() calls
            # Order: circuit query, format query, coverage query
            all_results = [[circuit_row], [format_row], [coverage_row]]
            call_count = [0]

            def mock_all():
                idx = call_count[0]
                call_count[0] += 1
                if idx < len(all_results):
                    return all_results[idx]
                return []

            query_mock = session_ctx.query()
            query_mock.filter().group_by().order_by().all.side_effect = mock_all
            query_mock.filter().first.return_value = overall_row

            mock_session.return_value.__enter__.return_value = session_ctx

            service = EntTelligenceBaselineDiscoveryService(company_id=1)
            analysis = service.analyze_by_circuit(lookback_days=30)

            assert 'circuits' in analysis
            assert 'format_breakdown' in analysis
            assert 'overall_stats' in analysis
            assert 'data_coverage' in analysis

    def test_get_circuit_baselines(self):
        """Should get baselines for specific circuit."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        with patch.object(EntTelligenceBaselineDiscoveryService, 'discover_baselines') as mock_discover:
            mock_discover.return_value = [
                {'theater_name': 'AMC Test', 'baseline_price': 12.50, 'circuit_name': 'AMC Entertainment'}
            ]

            service = EntTelligenceBaselineDiscoveryService(company_id=1)
            baselines = service.get_circuit_baselines(
                circuit_name="AMC Entertainment",
                min_samples=3,
                lookback_days=30
            )

            mock_discover.assert_called_once_with(
                min_samples=3,
                lookback_days=30,
                circuit_filter=["AMC Entertainment"]
            )
            assert len(baselines) == 1


class TestEntTelligenceConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_discover_enttelligence_baselines_function(self):
        """Test discover_enttelligence_baselines() convenience function."""
        from app.enttelligence_baseline_discovery import discover_enttelligence_baselines

        with patch('app.enttelligence_baseline_discovery.EntTelligenceBaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.discover_baselines.return_value = [
                {'theater_name': 'Test', 'baseline_price': 12.50, 'circuit_name': 'AMC'}
            ]
            MockService.return_value = mock_service

            baselines = discover_enttelligence_baselines(
                company_id=1,
                min_samples=5,
                lookback_days=30,
                save=False
            )

            assert len(baselines) == 1
            mock_service.discover_baselines.assert_called_once()

    def test_discover_with_save(self):
        """Test discover_enttelligence_baselines() with save=True."""
        from app.enttelligence_baseline_discovery import discover_enttelligence_baselines

        with patch('app.enttelligence_baseline_discovery.EntTelligenceBaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.discover_baselines.return_value = [
                {'theater_name': 'Test', 'baseline_price': 12.50}
            ]
            mock_service.save_discovered_baselines.return_value = 1
            MockService.return_value = mock_service

            baselines = discover_enttelligence_baselines(
                company_id=1,
                min_samples=5,
                save=True
            )

            mock_service.save_discovered_baselines.assert_called_once()

    def test_discover_with_circuit_filter(self):
        """Test discover_enttelligence_baselines() with circuit filter."""
        from app.enttelligence_baseline_discovery import discover_enttelligence_baselines

        with patch('app.enttelligence_baseline_discovery.EntTelligenceBaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.discover_baselines.return_value = []
            MockService.return_value = mock_service

            baselines = discover_enttelligence_baselines(
                company_id=1,
                circuit_filter=["AMC Entertainment", "Regal"]
            )

            mock_service.discover_baselines.assert_called_once()
            call_kwargs = mock_service.discover_baselines.call_args[1]
            assert call_kwargs['circuit_filter'] == ["AMC Entertainment", "Regal"]

    def test_analyze_enttelligence_prices_function(self):
        """Test analyze_enttelligence_prices() convenience function."""
        from app.enttelligence_baseline_discovery import analyze_enttelligence_prices

        with patch('app.enttelligence_baseline_discovery.EntTelligenceBaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.analyze_by_circuit.return_value = {
                'circuits': {},
                'format_breakdown': {},
                'overall_stats': {},
                'data_coverage': {}
            }
            MockService.return_value = mock_service

            analysis = analyze_enttelligence_prices(company_id=1, lookback_days=30)

            assert 'circuits' in analysis
            mock_service.analyze_by_circuit.assert_called_once_with(lookback_days=30)

    def test_refresh_enttelligence_baselines_function(self):
        """Test refresh_enttelligence_baselines() convenience function."""
        from app.enttelligence_baseline_discovery import refresh_enttelligence_baselines

        with patch('app.enttelligence_baseline_discovery.EntTelligenceBaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.discover_baselines.return_value = [
                {'baseline': 'data1'},
                {'baseline': 'data2'}
            ]
            mock_service.save_discovered_baselines.return_value = 2
            MockService.return_value = mock_service

            count = refresh_enttelligence_baselines(company_id=1)

            assert count == 2
            mock_service.save_discovered_baselines.assert_called_once()


class TestEntTelligenceSaveBaselines:
    """Test saving discovered baselines to database."""

    def test_saves_new_baselines(self):
        """Should save new baselines to database."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        with patch('app.enttelligence_baseline_discovery.get_session') as mock_session:
            session_ctx = MagicMock()
            session_ctx.query().filter().first.return_value = None  # No existing baseline
            mock_session.return_value.__enter__.return_value = session_ctx

            service = EntTelligenceBaselineDiscoveryService(company_id=1)
            baselines = [
                {
                    'theater_name': 'AMC Test',
                    'ticket_type': 'Adult',
                    'format': '2D',
                    'baseline_price': 12.50,
                    'is_premium': False
                }
            ]

            count = service.save_discovered_baselines(baselines)

            # Should have added the baseline
            assert session_ctx.add.called
            assert session_ctx.flush.called

    def test_skips_premium_formats_when_saving(self):
        """Should skip premium formats when saving baselines."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        with patch('app.enttelligence_baseline_discovery.get_session') as mock_session:
            session_ctx = MagicMock()
            mock_session.return_value.__enter__.return_value = session_ctx

            service = EntTelligenceBaselineDiscoveryService(company_id=1)
            baselines = [
                {
                    'theater_name': 'AMC Test',
                    'ticket_type': 'Adult',
                    'format': 'IMAX',
                    'baseline_price': 20.00,
                    'is_premium': True  # Premium - should skip
                }
            ]

            count = service.save_discovered_baselines(baselines)

            assert count == 0
            assert not session_ctx.add.called

    def test_skips_existing_baselines_without_overwrite(self):
        """Should skip existing baselines when overwrite=False."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        with patch('app.enttelligence_baseline_discovery.get_session') as mock_session:
            existing_baseline = MagicMock()
            session_ctx = MagicMock()
            session_ctx.query().filter().first.return_value = existing_baseline
            mock_session.return_value.__enter__.return_value = session_ctx

            service = EntTelligenceBaselineDiscoveryService(company_id=1)
            baselines = [
                {
                    'theater_name': 'AMC Test',
                    'ticket_type': 'Adult',
                    'format': '2D',
                    'baseline_price': 12.50,
                    'is_premium': False
                }
            ]

            count = service.save_discovered_baselines(baselines, overwrite=False)

            assert count == 0
            assert not session_ctx.add.called


class TestPremiumFormatsConstant:
    """Test PREMIUM_FORMATS constant in EntTelligence module."""

    def test_premium_formats_is_set(self):
        """PREMIUM_FORMATS should be a set for O(1) lookup."""
        from app.enttelligence_baseline_discovery import PREMIUM_FORMATS

        assert isinstance(PREMIUM_FORMATS, set)
        assert len(PREMIUM_FORMATS) > 0

    def test_contains_expected_formats(self):
        """PREMIUM_FORMATS should contain common premium format names."""
        from app.enttelligence_baseline_discovery import PREMIUM_FORMATS

        expected = ['IMAX', 'Dolby Cinema', '3D', '4DX', 'RPX']
        for fmt in expected:
            assert fmt in PREMIUM_FORMATS, f"Expected {fmt} in PREMIUM_FORMATS"


class TestEventCinemaDetection:
    """Test event cinema identification for EntTelligence data."""

    def test_identifies_fathom_events(self):
        """Should identify Fathom Events."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("Fathom Events: Classic Movie") is True
        assert service.is_event_cinema("Star Trek: Fathom 25th Anniversary") is True
        assert service.is_event_cinema("TCM Big Screen Classics") is True
        assert service.is_event_cinema("Turner Classic Movies Presents") is True

    def test_identifies_live_performances(self):
        """Should identify live performance broadcasts."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("Met Opera Live: La Traviata") is True
        assert service.is_event_cinema("NT Live: Hamlet") is True
        assert service.is_event_cinema("National Theatre Live") is True
        assert service.is_event_cinema("Bolshoi Ballet: Swan Lake") is True
        assert service.is_event_cinema("Royal Opera House") is True
        assert service.is_event_cinema("Royal Ballet: The Nutcracker") is True

    def test_identifies_concert_events(self):
        """Should identify concert and music events."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("Taylor Swift: The Eras Tour Concert Film") is True
        assert service.is_event_cinema("BTS: Live in Concert") is True
        assert service.is_event_cinema("Coldplay: Live Event Special") is True

    def test_identifies_special_presentations(self):
        """Should identify special screening events."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("Star Wars 25th Anniversary") is True
        assert service.is_event_cinema("Jurassic Park Encore Presentation") is True
        assert service.is_event_cinema("Marvel Fan Event Screening") is True
        assert service.is_event_cinema("MCU Marathon Event") is True
        assert service.is_event_cinema("Double Feature Night") is True
        assert service.is_event_cinema("Lord of the Rings Triple Feature") is True

    def test_identifies_sports_events(self):
        """Should identify sports and wrestling events."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("WWE WrestleMania") is True
        assert service.is_event_cinema("UFC 300 Live") is True
        assert service.is_event_cinema("Boxing Championship") is True

    def test_identifies_anime_events(self):
        """Should identify anime theatrical events."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("Crunchyroll Movie Night: Demon Slayer") is True
        assert service.is_event_cinema("Funimation Presents: One Piece Film Red") is True

    def test_regular_films_not_event_cinema(self):
        """Should not identify regular films as event cinema."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("Avatar: The Way of Water") is False
        assert service.is_event_cinema("Oppenheimer") is False
        assert service.is_event_cinema("Barbie") is False
        assert service.is_event_cinema("The Batman") is False
        assert service.is_event_cinema("Top Gun: Maverick") is False
        assert service.is_event_cinema("Mission: Impossible - Dead Reckoning") is False
        assert service.is_event_cinema(None) is False
        assert service.is_event_cinema("") is False

    def test_case_insensitive_matching(self):
        """Should match event cinema keywords case-insensitively."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("FATHOM EVENTS: TEST") is True
        assert service.is_event_cinema("met opera live") is True
        assert service.is_event_cinema("Marathon Event") is True


class TestEventCinemaKeywords:
    """Test EVENT_CINEMA_KEYWORDS constant and helper function."""

    def test_keywords_is_list(self):
        """EVENT_CINEMA_KEYWORDS should be a list."""
        from app.enttelligence_baseline_discovery import EVENT_CINEMA_KEYWORDS

        assert isinstance(EVENT_CINEMA_KEYWORDS, list)
        assert len(EVENT_CINEMA_KEYWORDS) > 0

    def test_get_keywords_function(self):
        """get_event_cinema_keywords() should return a copy of keywords."""
        from app.enttelligence_baseline_discovery import get_event_cinema_keywords, EVENT_CINEMA_KEYWORDS

        keywords = get_event_cinema_keywords()

        assert keywords == EVENT_CINEMA_KEYWORDS
        # Should be a copy, not the same object
        assert keywords is not EVENT_CINEMA_KEYWORDS

    def test_keywords_include_major_distributors(self):
        """Should include major event cinema distributors."""
        from app.enttelligence_baseline_discovery import EVENT_CINEMA_KEYWORDS

        keywords_upper = [k.upper() for k in EVENT_CINEMA_KEYWORDS]

        assert 'FATHOM' in keywords_upper
        assert 'TRAFALGAR' in keywords_upper

    def test_keywords_include_opera_broadcasts(self):
        """Should include opera and theatre broadcasts."""
        from app.enttelligence_baseline_discovery import EVENT_CINEMA_KEYWORDS

        keywords_upper = [k.upper() for k in EVENT_CINEMA_KEYWORDS]

        assert 'MET OPERA' in keywords_upper
        assert 'NT LIVE' in keywords_upper
        assert 'BOLSHOI' in keywords_upper


class TestDayTypeDetection:
    """Test day type (weekday/weekend) detection."""

    def test_monday_is_weekday(self):
        """Monday should be classified as weekday."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)
        # 2024-01-08 is a Monday
        assert service._get_day_type(date(2024, 1, 8)) == 'weekday'

    def test_tuesday_is_weekday(self):
        """Tuesday should be classified as weekday."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)
        # 2024-01-09 is a Tuesday
        assert service._get_day_type(date(2024, 1, 9)) == 'weekday'

    def test_wednesday_is_weekday(self):
        """Wednesday should be classified as weekday."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)
        # 2024-01-10 is a Wednesday
        assert service._get_day_type(date(2024, 1, 10)) == 'weekday'

    def test_thursday_is_weekday(self):
        """Thursday should be classified as weekday."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)
        # 2024-01-11 is a Thursday
        assert service._get_day_type(date(2024, 1, 11)) == 'weekday'

    def test_friday_is_weekend(self):
        """Friday should be classified as weekend."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)
        # 2024-01-12 is a Friday
        assert service._get_day_type(date(2024, 1, 12)) == 'weekend'

    def test_saturday_is_weekend(self):
        """Saturday should be classified as weekend."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)
        # 2024-01-13 is a Saturday
        assert service._get_day_type(date(2024, 1, 13)) == 'weekend'

    def test_sunday_is_weekend(self):
        """Sunday should be classified as weekend."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)
        # 2024-01-14 is a Sunday
        assert service._get_day_type(date(2024, 1, 14)) == 'weekend'


class TestDaypartDetection:
    """Test daypart detection from showtimes.

    Uses Fandango-aligned daypart conventions:
    - Matinee: Before 4:00 PM
    - Twilight: 4:00 PM - 6:00 PM
    - Prime: 6:00 PM - 9:00 PM
    - Late Night: After 9:00 PM
    """

    def test_matinee_before_4pm(self):
        """Showtimes before 4 PM should be Matinee."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service._get_daypart("10:30 AM") == 'Matinee'
        assert service._get_daypart("12:00 PM") == 'Matinee'
        assert service._get_daypart("2:15 PM") == 'Matinee'
        assert service._get_daypart("3:45 PM") == 'Matinee'
        assert service._get_daypart("3:59 PM") == 'Matinee'

    def test_twilight_4pm_to_6pm(self):
        """Showtimes 4 PM to 6 PM should be Twilight."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service._get_daypart("4:00 PM") == 'Twilight'
        assert service._get_daypart("4:30 PM") == 'Twilight'
        assert service._get_daypart("5:00 PM") == 'Twilight'
        assert service._get_daypart("5:45 PM") == 'Twilight'
        assert service._get_daypart("5:59 PM") == 'Twilight'

    def test_prime_6pm_to_9pm(self):
        """Showtimes 6 PM to 9 PM should be Prime."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service._get_daypart("6:00 PM") == 'Prime'
        assert service._get_daypart("6:30 PM") == 'Prime'
        assert service._get_daypart("7:15 PM") == 'Prime'
        assert service._get_daypart("8:45 PM") == 'Prime'
        assert service._get_daypart("8:59 PM") == 'Prime'

    def test_late_night_after_9pm(self):
        """Showtimes after 9 PM should be Late Night."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service._get_daypart("9:00 PM") == 'Late Night'
        assert service._get_daypart("9:30 PM") == 'Late Night'
        assert service._get_daypart("10:15 PM") == 'Late Night'
        assert service._get_daypart("11:00 PM") == 'Late Night'

    def test_handles_various_time_formats(self):
        """Should handle various time string formats."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        # Various formats that might appear in data
        assert service._get_daypart("3:15p") == 'Matinee'      # Before 4pm
        assert service._get_daypart("4:15p") == 'Twilight'     # 4-6pm
        assert service._get_daypart("7:30P") == 'Prime'        # 6-9pm
        assert service._get_daypart("10:00PM") == 'Late Night' # After 9pm
        assert service._get_daypart("2:30pm") == 'Matinee'     # Before 4pm

    def test_handles_empty_and_invalid(self):
        """Should return None for empty or invalid showtimes."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service._get_daypart("") is None
        assert service._get_daypart(None) is None
        assert service._get_daypart("invalid") is None


class TestTimeNormalization:
    """Test time string normalization."""

    def test_normalizes_short_format(self):
        """Should normalize shortened time formats."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service._normalize_time_string("4:15p") == "04:15PM"
        assert service._normalize_time_string("7:30a") == "07:30AM"

    def test_normalizes_lowercase(self):
        """Should normalize lowercase am/pm."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service._normalize_time_string("10:30am") == "10:30AM"
        assert service._normalize_time_string("7:45pm") == "07:45PM"

    def test_handles_spaces(self):
        """Should handle spaces in time strings."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service._normalize_time_string("10:30 AM") == "10:30AM"
        assert service._normalize_time_string("7:45 pm") == "07:45PM"

    def test_handles_empty_input(self):
        """Should handle empty or None input."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        service = EntTelligenceBaselineDiscoveryService(company_id=1)

        assert service._normalize_time_string("") == ""
        assert service._normalize_time_string(None) == ""


class TestEventCinemaAnalysis:
    """Test event cinema analysis functionality."""

    def test_analyze_event_cinema_returns_expected_structure(self):
        """analyze_event_cinema() should return expected structure."""
        from app.enttelligence_baseline_discovery import EntTelligenceBaselineDiscoveryService

        with patch('app.enttelligence_baseline_discovery.get_session') as mock_session:
            session_ctx = MagicMock()
            session_ctx.query().filter().all.return_value = []
            mock_session.return_value.__enter__.return_value = session_ctx

            service = EntTelligenceBaselineDiscoveryService(company_id=1)
            analysis = service.analyze_event_cinema(lookback_days=30)

            assert 'event_films' in analysis
            assert 'summary' in analysis
            assert 'price_variations' in analysis
            assert 'total_event_cinema_records' in analysis['summary']
            assert 'total_regular_records' in analysis['summary']
            assert 'unique_films' in analysis['summary']
            assert 'circuits_with_event_cinema' in analysis['summary']

    def test_analyze_event_cinema_convenience_function(self):
        """Test analyze_event_cinema() convenience function."""
        from app.enttelligence_baseline_discovery import analyze_event_cinema

        with patch('app.enttelligence_baseline_discovery.EntTelligenceBaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.analyze_event_cinema.return_value = {
                'event_films': [],
                'summary': {
                    'total_event_cinema_records': 0,
                    'total_regular_records': 1000,
                    'unique_films': 0,
                    'circuits_with_event_cinema': [],
                    'avg_event_price': None,
                    'avg_regular_price': 12.50,
                    'price_premium_percent': None,
                },
                'price_variations': []
            }
            MockService.return_value = mock_service

            analysis = analyze_event_cinema(company_id=1, lookback_days=30, circuit_filter=['AMC'])

            mock_service.analyze_event_cinema.assert_called_once_with(
                lookback_days=30,
                circuit_filter=['AMC']
            )
            assert 'event_films' in analysis


class TestDiscoverWithSplits:
    """Test baseline discovery with day_type, daypart, and day_of_week splitting."""

    def test_discover_with_day_type_split(self):
        """Test discover function with day_type splitting enabled."""
        from app.enttelligence_baseline_discovery import discover_enttelligence_baselines

        with patch('app.enttelligence_baseline_discovery.EntTelligenceBaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.discover_baselines.return_value = []
            MockService.return_value = mock_service

            discover_enttelligence_baselines(
                company_id=1,
                split_by_day_type=True
            )

            mock_service.discover_baselines.assert_called_with(
                min_samples=5,
                lookback_days=30,
                circuit_filter=None,
                split_by_day_type=True,
                split_by_daypart=False,
                split_by_day_of_week=False
            )

    def test_discover_with_daypart_split(self):
        """Test discover function with daypart splitting enabled."""
        from app.enttelligence_baseline_discovery import discover_enttelligence_baselines

        with patch('app.enttelligence_baseline_discovery.EntTelligenceBaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.discover_baselines.return_value = []
            MockService.return_value = mock_service

            discover_enttelligence_baselines(
                company_id=1,
                split_by_daypart=True
            )

            mock_service.discover_baselines.assert_called_with(
                min_samples=5,
                lookback_days=30,
                circuit_filter=None,
                split_by_day_type=False,
                split_by_daypart=True,
                split_by_day_of_week=False
            )

    def test_discover_with_day_of_week_split(self):
        """Test discover function with day_of_week splitting enabled."""
        from app.enttelligence_baseline_discovery import discover_enttelligence_baselines

        with patch('app.enttelligence_baseline_discovery.EntTelligenceBaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.discover_baselines.return_value = []
            MockService.return_value = mock_service

            discover_enttelligence_baselines(
                company_id=1,
                split_by_day_of_week=True
            )

            mock_service.discover_baselines.assert_called_with(
                min_samples=5,
                lookback_days=30,
                circuit_filter=None,
                split_by_day_type=False,
                split_by_daypart=False,
                split_by_day_of_week=True
            )

    def test_discover_with_all_splits(self):
        """Test discover function with all splitting options enabled."""
        from app.enttelligence_baseline_discovery import discover_enttelligence_baselines

        with patch('app.enttelligence_baseline_discovery.EntTelligenceBaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.discover_baselines.return_value = []
            MockService.return_value = mock_service

            discover_enttelligence_baselines(
                company_id=1,
                split_by_day_type=True,
                split_by_daypart=True,
                split_by_day_of_week=True
            )

            mock_service.discover_baselines.assert_called_with(
                min_samples=5,
                lookback_days=30,
                circuit_filter=None,
                split_by_day_type=True,
                split_by_daypart=True,
                split_by_day_of_week=True
            )
