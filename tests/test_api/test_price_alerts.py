"""
Tests for API price alert endpoints in api/routers/price_alerts.py
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


class TestListPriceAlerts:
    """Tests for GET /price-alerts endpoint."""

    def test_requires_authentication(self, test_client_no_auth):
        """Should require authentication."""
        response = test_client_no_auth.get("/api/v1/price-alerts")
        assert response.status_code in [401, 403]

    def test_returns_alerts_list(self, test_client_as_admin):
        """Should return list of alerts for authenticated user."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Mock ORM query chain for alert list
            query_mock = MagicMock()
            session_mock.query.return_value = query_mock
            query_mock.filter.return_value = query_mock
            query_mock.count.return_value = 0
            query_mock.order_by.return_value = query_mock
            query_mock.offset.return_value = query_mock
            query_mock.limit.return_value = query_mock
            query_mock.all.return_value = []

            response = test_client_as_admin.get("/api/v1/price-alerts")

            assert response.status_code == 200
            data = response.json()
            assert 'alerts' in data
            assert 'total' in data

    def test_filters_by_acknowledged_status(self, test_client_as_admin):
        """Should filter alerts by acknowledged status."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            query_mock = MagicMock()
            session_mock.query.return_value = query_mock
            query_mock.filter.return_value = query_mock
            query_mock.count.return_value = 0
            query_mock.order_by.return_value = query_mock
            query_mock.offset.return_value = query_mock
            query_mock.limit.return_value = query_mock
            query_mock.all.return_value = []

            response = test_client_as_admin.get("/api/v1/price-alerts?acknowledged=false")

            assert response.status_code == 200

    def test_filters_by_alert_type(self, test_client_as_admin):
        """Should filter alerts by type."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            query_mock = MagicMock()
            session_mock.query.return_value = query_mock
            query_mock.filter.return_value = query_mock
            query_mock.count.return_value = 0
            query_mock.order_by.return_value = query_mock
            query_mock.offset.return_value = query_mock
            query_mock.limit.return_value = query_mock
            query_mock.all.return_value = []

            response = test_client_as_admin.get("/api/v1/price-alerts?alert_type=surge_detected")

            assert response.status_code == 200

    def test_filters_by_theater_name(self, test_client_as_admin):
        """Should filter alerts by theater name."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            query_mock = MagicMock()
            session_mock.query.return_value = query_mock
            query_mock.filter.return_value = query_mock
            query_mock.count.return_value = 0
            query_mock.order_by.return_value = query_mock
            query_mock.offset.return_value = query_mock
            query_mock.limit.return_value = query_mock
            query_mock.all.return_value = []

            response = test_client_as_admin.get("/api/v1/price-alerts?theater_name=AMC")

            assert response.status_code == 200

    def test_supports_pagination(self, test_client_as_admin):
        """Should support limit and offset pagination."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            query_mock = MagicMock()
            session_mock.query.return_value = query_mock
            query_mock.filter.return_value = query_mock
            query_mock.count.return_value = 100
            query_mock.order_by.return_value = query_mock
            query_mock.offset.return_value = query_mock
            query_mock.limit.return_value = query_mock
            query_mock.all.return_value = []

            response = test_client_as_admin.get("/api/v1/price-alerts?limit=10&offset=20")

            assert response.status_code == 200


class TestGetAlertSummary:
    """Tests for GET /price-alerts/summary endpoint."""

    def test_returns_summary_statistics(self, test_client_as_admin):
        """Should return alert summary statistics."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Mock scalar queries for counts
            query_mock = MagicMock()
            session_mock.query.return_value = query_mock
            query_mock.filter.return_value = query_mock
            query_mock.scalar.return_value = 0
            query_mock.group_by.return_value = query_mock
            query_mock.order_by.return_value = query_mock
            query_mock.limit.return_value = query_mock
            query_mock.all.return_value = []

            response = test_client_as_admin.get("/api/v1/price-alerts/summary")

            assert response.status_code == 200
            data = response.json()
            assert 'total_pending' in data
            assert 'total_acknowledged' in data
            assert 'by_type' in data
            assert 'by_theater' in data


class TestAcknowledgeAlert:
    """Tests for PUT /price-alerts/{id}/acknowledge endpoint."""

    def test_requires_authentication(self, test_client_no_auth):
        """Should require authentication."""
        response = test_client_no_auth.put("/api/v1/price-alerts/1/acknowledge")
        assert response.status_code in [401, 403]

    def test_acknowledges_alert(self, test_client_as_admin):
        """Should acknowledge an alert."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Mock execute for SELECT check
            check_result = MagicMock()
            check_result.fetchone.return_value = (False,)  # Not yet acknowledged

            # Mock execute for UPDATE
            update_result = MagicMock()
            update_result.rowcount = 1

            session_mock.execute.side_effect = [check_result, update_result]
            session_mock.commit = MagicMock()

            response = test_client_as_admin.put(
                "/api/v1/price-alerts/1/acknowledge",
                json={"notes": "Reviewed and accepted"}
            )

            assert response.status_code == 200

    def test_returns_404_for_nonexistent_alert(self, test_client_as_admin):
        """Should return 404 for non-existent alert."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Mock execute - returns None (alert not found)
            check_result = MagicMock()
            check_result.fetchone.return_value = None

            session_mock.execute.return_value = check_result

            response = test_client_as_admin.put("/api/v1/price-alerts/999/acknowledge")

            assert response.status_code == 404


class TestAlertConfiguration:
    """Tests for alert configuration endpoints."""

    def test_get_config_returns_defaults(self, test_client_as_admin):
        """Should return default config if none exists."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            query_mock = MagicMock()
            session_mock.query.return_value = query_mock
            query_mock.filter.return_value = query_mock
            query_mock.first.return_value = None  # No config exists

            response = test_client_as_admin.get("/api/v1/price-alerts/config")

            assert response.status_code == 200
            data = response.json()
            assert data['min_price_change_percent'] == 5.0
            assert data['surge_threshold_percent'] == 20.0

    def test_update_config(self, test_client_as_admin):
        """Should update alert configuration."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Mock existing config
            mock_config = MagicMock()
            mock_config.config_id = 1
            mock_config.company_id = 1
            mock_config.min_price_change_percent = 5.0
            mock_config.min_price_change_amount = 1.0
            mock_config.alert_on_increase = True
            mock_config.alert_on_decrease = True
            mock_config.alert_on_new_offering = True
            mock_config.alert_on_discontinued = False
            mock_config.alert_on_surge = True
            mock_config.surge_threshold_percent = 20.0
            mock_config.notification_enabled = True
            mock_config.webhook_url = None
            mock_config.notification_email = None
            mock_config.email_frequency = 'immediate'
            mock_config.updated_at = datetime.now(timezone.utc)

            query_mock = MagicMock()
            session_mock.query.return_value = query_mock
            query_mock.filter.return_value = query_mock
            query_mock.first.return_value = mock_config
            session_mock.flush = MagicMock()

            response = test_client_as_admin.put(
                "/api/v1/price-alerts/config",
                json={
                    "min_price_change_percent": 10.0,
                    "alert_on_surge": True,
                    "surge_threshold_percent": 25.0
                }
            )

            assert response.status_code == 200


class TestPriceBaselines:
    """Tests for price baseline endpoints."""

    def test_list_baselines(self, test_client_as_admin):
        """Should list price baselines."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            query_mock = MagicMock()
            session_mock.query.return_value = query_mock
            query_mock.filter.return_value = query_mock
            query_mock.order_by.return_value = query_mock
            query_mock.all.return_value = []

            response = test_client_as_admin.get("/api/v1/price-baselines")

            assert response.status_code == 200

    def test_create_baseline(self, test_client_as_admin, sample_price_baseline):
        """Should create a new baseline."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Mock PriceBaseline to be added
            def mock_add(obj):
                obj.baseline_id = 1
                obj.created_at = datetime.now(timezone.utc)

            session_mock.add = mock_add
            session_mock.flush = MagicMock()

            response = test_client_as_admin.post(
                "/api/v1/price-baselines",
                json={
                    "theater_name": sample_price_baseline["theater_name"],
                    "ticket_type": sample_price_baseline["ticket_type"],
                    "format": sample_price_baseline["format"],
                    "baseline_price": sample_price_baseline["baseline_price"],
                    "effective_from": sample_price_baseline["effective_from"]
                }
            )

            assert response.status_code in [200, 201]


class TestBaselineDiscovery:
    """Tests for baseline discovery endpoints."""

    def test_discover_baselines_endpoint(self, test_client_as_admin):
        """Should discover baselines from historical data."""
        # Patch at source module since import is done inside function
        with patch('app.baseline_discovery.BaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.discover_baselines.return_value = [
                {
                    'theater_name': 'Test Theater',
                    'ticket_type': 'Adult',
                    'format': 'Standard',
                    'baseline_price': 12.50,
                    'sample_count': 10,
                    'min_price': 12.00,
                    'max_price': 13.50,
                    'avg_price': 12.75,
                    'volatility_percent': 8.5,
                    'is_premium': False
                }
            ]
            MockService.return_value = mock_service

            response = test_client_as_admin.get(
                "/api/v1/price-baselines/discover?min_samples=5&lookback_days=30"
            )

            assert response.status_code == 200
            data = response.json()
            assert 'discovered_count' in data
            assert 'baselines' in data

    def test_analyze_price_patterns(self, test_client_as_admin):
        """Should analyze price patterns."""
        # Patch at source module since import is done inside function
        with patch('app.baseline_discovery.BaselineDiscoveryService') as MockService:
            mock_service = MagicMock()
            mock_service.analyze_price_patterns.return_value = {
                'high_volatility_combinations': [],
                'format_price_comparison': {}
            }
            MockService.return_value = mock_service

            response = test_client_as_admin.get("/api/v1/price-baselines/analyze")

            assert response.status_code == 200
            data = response.json()
            assert 'high_volatility_combinations' in data

    def test_list_premium_formats(self, test_client_as_admin):
        """Should list known premium formats."""
        response = test_client_as_admin.get("/api/v1/price-baselines/premium-formats")

        assert response.status_code == 200
        data = response.json()
        assert 'premium_formats' in data
        assert 'event_cinema_keywords' in data
        assert 'IMAX' in data['premium_formats']

    def test_refresh_baselines(self, test_client_as_admin):
        """Should refresh all baselines."""
        # Patch at source module since import is done inside function
        with patch('app.baseline_discovery.refresh_baselines') as mock_refresh:
            mock_refresh.return_value = 10

            response = test_client_as_admin.post("/api/v1/price-baselines/refresh")

            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True
            assert data['baselines_updated'] == 10


class TestWebhookTesting:
    """Tests for webhook test endpoint."""

    def test_test_webhook_requires_webhook_url(self, test_client_as_admin):
        """Should return 400 if no webhook URL is configured."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Mock config with no webhook URL
            mock_config = MagicMock()
            mock_config.webhook_url = None

            query_mock = MagicMock()
            session_mock.query.return_value = query_mock
            query_mock.filter.return_value = query_mock
            query_mock.first.return_value = mock_config

            response = test_client_as_admin.post("/api/v1/price-alerts/test-webhook")

            # Should return 400 when no webhook configured
            assert response.status_code == 400

    def test_test_webhook_requires_config(self, test_client_as_admin):
        """Should return 400 if no config exists."""
        with patch('api.routers.price_alerts.get_session') as mock_session:
            session_mock = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=session_mock)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Mock no config
            query_mock = MagicMock()
            session_mock.query.return_value = query_mock
            query_mock.filter.return_value = query_mock
            query_mock.first.return_value = None

            response = test_client_as_admin.post("/api/v1/price-alerts/test-webhook")

            # Should return 400 when no config
            assert response.status_code == 400
