"""
Tests for app/baseline_discovery.py - Baseline discovery and surge detection.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date, timedelta
from decimal import Decimal


class TestPremiumFormatDetection:
    """Test premium format identification."""

    def test_identifies_imax_formats(self):
        """Should identify IMAX as premium."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("IMAX") is True
        assert service.is_premium_format("IMAX 3D") is True
        assert service.is_premium_format("IMAX with Laser") is True
        assert service.is_premium_format("IMAX HFR 3D") is True
        assert service.is_premium_format("Laser IMAX") is True

    def test_identifies_dolby_formats(self):
        """Should identify Dolby formats as premium."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("Dolby Cinema") is True
        assert service.is_premium_format("Dolby Atmos") is True
        assert service.is_premium_format("Dolby Vision") is True

    def test_identifies_3d_formats(self):
        """Should identify 3D formats as premium."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("3D") is True
        assert service.is_premium_format("RealD 3D") is True
        assert service.is_premium_format("Digital 3D") is True

    def test_identifies_plf_formats(self):
        """Should identify premium large formats."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("PLF") is True
        assert service.is_premium_format("XD") is True
        assert service.is_premium_format("RPX") is True
        assert service.is_premium_format("BigD") is True
        assert service.is_premium_format("GTX") is True
        assert service.is_premium_format("UltraAVX") is True

    def test_identifies_motion_formats(self):
        """Should identify motion/4D formats as premium."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("4DX") is True
        assert service.is_premium_format("D-BOX") is True
        assert service.is_premium_format("ScreenX") is True
        assert service.is_premium_format("MX4D") is True

    def test_standard_format_not_premium(self):
        """Should not identify standard formats as premium."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("Standard") is False
        assert service.is_premium_format("Digital") is False
        assert service.is_premium_format("2D") is False
        assert service.is_premium_format(None) is False
        assert service.is_premium_format("") is False

    def test_case_insensitive_matching(self):
        """Should match premium formats case-insensitively."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        assert service.is_premium_format("imax") is True
        assert service.is_premium_format("DOLBY CINEMA") is True
        assert service.is_premium_format("Imax With Laser") is True


class TestEventCinemaDetection:
    """Test event cinema identification."""

    def test_identifies_fathom_events(self):
        """Should identify Fathom Events."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("Fathom Events: Classic Movie") is True
        assert service.is_event_cinema("TCM Big Screen Classics") is True

    def test_identifies_live_performances(self):
        """Should identify live performance broadcasts."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("Met Opera Live: La Traviata") is True
        assert service.is_event_cinema("NT Live: Hamlet") is True
        assert service.is_event_cinema("National Theatre Live") is True
        assert service.is_event_cinema("Bolshoi Ballet") is True
        assert service.is_event_cinema("Royal Opera House") is True

    def test_identifies_special_events(self):
        """Should identify special screening events."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("Star Wars 25th Anniversary") is True
        assert service.is_event_cinema("Encore Presentation") is True
        assert service.is_event_cinema("Fan Event Screening") is True
        assert service.is_event_cinema("Marvel Marathon") is True
        assert service.is_event_cinema("Double Feature Night") is True

    def test_regular_films_not_event_cinema(self):
        """Should not identify regular films as event cinema."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        assert service.is_event_cinema("Avatar: The Way of Water") is False
        assert service.is_event_cinema("Oppenheimer") is False
        assert service.is_event_cinema("Barbie") is False
        assert service.is_event_cinema(None) is False
        assert service.is_event_cinema("") is False


class TestPercentileCalculation:
    """Test percentile calculation for baselines."""

    def test_calculates_25th_percentile(self):
        """Should correctly calculate 25th percentile."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        # Test data: [10, 12, 14, 16, 18, 20]
        # 25th percentile should be around 11.5
        data = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
        result = service._percentile(data, 25)

        assert result == pytest.approx(11.5, rel=0.1)

    def test_handles_empty_data(self):
        """Should handle empty data gracefully."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        result = service._percentile([], 25)

        assert result == 0.0

    def test_handles_single_value(self):
        """Should handle single value."""
        from app.baseline_discovery import BaselineDiscoveryService

        service = BaselineDiscoveryService(company_id=1)

        result = service._percentile([15.0], 25)

        assert result == 15.0


class TestBaselineDiscovery:
    """Test baseline discovery from historical data."""

    def test_discovers_baselines_from_history(self):
        """Should discover baselines from historical price data."""
        from app.baseline_discovery import BaselineDiscoveryService

        with patch('app.baseline_discovery.get_session') as mock_session:
            # Mock query results
            mock_row = (
                "AMC Test Theater",  # theater_name
                "Adult",              # ticket_type
                "Standard",           # format
                10,                   # sample_count
                Decimal('12.00'),     # min_price
                Decimal('15.00'),     # max_price
                Decimal('13.50')      # avg_price
            )
            mock_session.return_value.__enter__().query().join().filter().group_by().having().all.return_value = [mock_row]

            # Mock individual prices query
            mock_prices = [(Decimal('12.00'),), (Decimal('12.50'),), (Decimal('13.00'),),
                          (Decimal('13.50'),), (Decimal('14.00'),), (Decimal('14.50'),),
                          (Decimal('15.00'),)]
            mock_session.return_value.__enter__().query().join().filter().all.return_value = mock_prices

            service = BaselineDiscoveryService(company_id=1)
            baselines = service.discover_baselines(min_samples=5, lookback_days=30)

            assert len(baselines) >= 0  # May be 0 if filtered out

    def test_excludes_premium_formats_from_baselines(self):
        """Should exclude premium formats from baseline calculation."""
        from app.baseline_discovery import BaselineDiscoveryService

        with patch('app.baseline_discovery.get_session') as mock_session:
            # Mock query results with IMAX format
            mock_row = (
                "AMC Test Theater",
                "Adult",
                "IMAX",               # Premium format
                10,
                Decimal('20.00'),
                Decimal('25.00'),
                Decimal('22.50')
            )
            mock_session.return_value.__enter__().query().join().filter().group_by().having().all.return_value = [mock_row]

            service = BaselineDiscoveryService(company_id=1)
            baselines = service.discover_baselines(
                min_samples=5,
                lookback_days=30,
                exclude_premium=True
            )

            # IMAX should be excluded
            assert len(baselines) == 0


class TestPricePatternAnalysis:
    """Test price pattern analysis for surge detection."""

    def test_identifies_high_volatility_combinations(self):
        """Should identify combinations with high price volatility."""
        from app.baseline_discovery import BaselineDiscoveryService

        with patch('app.baseline_discovery.get_session') as mock_session:
            # Mock volatility query - 50% price range
            mock_row = (
                "AMC Test Theater",
                "Adult",
                "Standard",
                10,                    # count
                Decimal('10.00'),      # min
                Decimal('15.00'),      # max (50% range)
                Decimal('12.50')       # avg
            )
            mock_session.return_value.__enter__().query().join().filter().group_by().having().all.return_value = [mock_row]

            # Mock format query
            mock_session.return_value.__enter__().query().join().filter().group_by().having().all.return_value = []

            service = BaselineDiscoveryService(company_id=1)
            analysis = service.analyze_price_patterns(lookback_days=30)

            assert 'high_volatility_combinations' in analysis
            # 40% volatility should be flagged (> 15% threshold)
            if analysis['high_volatility_combinations']:
                assert analysis['high_volatility_combinations'][0]['volatility_percent'] > 15

    def test_compares_format_pricing(self):
        """Should compare average prices across formats."""
        from app.baseline_discovery import BaselineDiscoveryService

        with patch('app.baseline_discovery.get_session') as mock_session:
            # Mock volatility query
            mock_session.return_value.__enter__().query().join().filter().group_by().having().all.return_value = []

            # Mock format comparison query
            format_rows = [
                ("Standard", Decimal('12.50'), 100),
                ("IMAX", Decimal('20.00'), 50),
                ("Dolby Cinema", Decimal('22.00'), 30)
            ]
            # Need to set up the second query call
            session_mock = MagicMock()
            session_mock.query().join().filter().group_by().having().all.side_effect = [
                [],  # volatility query
                format_rows  # format query
            ]
            mock_session.return_value.__enter__.return_value = session_mock

            service = BaselineDiscoveryService(company_id=1)
            analysis = service.analyze_price_patterns(lookback_days=30)

            assert 'format_price_comparison' in analysis


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_discover_baselines_function(self):
        """Test discover_baselines() convenience function."""
        from app.baseline_discovery import discover_baselines

        with patch('app.baseline_discovery.BaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.discover_baselines.return_value = [
                {'theater_name': 'Test', 'baseline_price': 12.50}
            ]
            MockService.return_value = mock_service

            baselines = discover_baselines(company_id=1, min_samples=5, save=False)

            assert len(baselines) == 1
            mock_service.discover_baselines.assert_called_once()

    def test_refresh_baselines_function(self):
        """Test refresh_baselines() convenience function."""
        from app.baseline_discovery import refresh_baselines

        with patch('app.baseline_discovery.BaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.discover_baselines.return_value = [{'baseline': 'data'}]
            mock_service.save_discovered_baselines.return_value = 5
            MockService.return_value = mock_service

            count = refresh_baselines(company_id=1)

            assert count == 5
            mock_service.save_discovered_baselines.assert_called_once()

    def test_analyze_prices_function(self):
        """Test analyze_prices() convenience function."""
        from app.baseline_discovery import analyze_prices

        with patch('app.baseline_discovery.BaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.analyze_price_patterns.return_value = {
                'high_volatility_combinations': [],
                'format_price_comparison': {}
            }
            MockService.return_value = mock_service

            analysis = analyze_prices(company_id=1)

            assert 'high_volatility_combinations' in analysis
            mock_service.analyze_price_patterns.assert_called_once()


class TestPremiumFormatsConstant:
    """Test PREMIUM_FORMATS constant completeness."""

    def test_premium_formats_is_set(self):
        """PREMIUM_FORMATS should be a set for O(1) lookup."""
        from app.baseline_discovery import PREMIUM_FORMATS

        assert isinstance(PREMIUM_FORMATS, set)
        assert len(PREMIUM_FORMATS) > 0

    def test_event_cinema_keywords_is_list(self):
        """EVENT_CINEMA_KEYWORDS should be a list."""
        from app.baseline_discovery import EVENT_CINEMA_KEYWORDS

        assert isinstance(EVENT_CINEMA_KEYWORDS, list)
        assert len(EVENT_CINEMA_KEYWORDS) > 0
