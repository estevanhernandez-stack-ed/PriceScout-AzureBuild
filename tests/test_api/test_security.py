"""
Security and Reliability Tests for PriceScout API

Tests for:
- Global Rate Limiting (429 responses)
- Circuit Breaker transitions and notifications
- RFC 7807 compliance
"""
import pytest
import time
from unittest.mock import patch, MagicMock
from fastapi import status

class TestGlobalRateLimiting:
    """Tests for global rate limiting middleware."""

    def test_rate_limit_enforced(self, test_client_no_auth):
        """
        Test that high-frequency requests trigger 429 Too Many Requests.
        
        Note: We use a low limit or many requests to trigger it.
        By default, global_limiter is 200/min.
        """
        # To avoid sitting in a loop for 200 requests, we'll mock the limiter
        with patch("app.rate_limit.global_limiter.is_allowed") as mock_allowed:
            # Mock limited state
            mock_allowed.return_value = (False, 0, int(time.time()) + 60)
            
            response = test_client_no_auth.get("/api/v1/info")
            
            assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
            data = response.json()
            
            # Verify RFC 7807 compliance
            assert data["status"] == 429
            assert data["title"] == "Rate Limit Exceeded"
            assert "detail" in data
            
            # Verify headers
            assert "Retry-After" in response.headers
            assert response.headers["X-RateLimit-Limit"] == "200" # Default
            assert response.headers["X-RateLimit-Remaining"] == "0"

    def test_rate_limit_headers_present(self, test_client_no_auth):
        """Test that rate limit headers are present on successful requests."""
        response = test_client_no_auth.get("/api/v1/info")
        
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

class TestCircuitBreakerReliability:
    """Tests for circuit breaker transitions and proactive alerting."""

    @patch("app.circuit_breaker.dispatch_system_notification_sync")
    def test_circuit_breaker_notification_on_open(self, mock_notify):
        """Test that opening a circuit breaker dispatches a system notification."""
        from app.circuit_breaker import CircuitBreaker, CircuitState
        
        # Create a fresh circuit breaker for testing
        breaker = CircuitBreaker(name="test_breaker", failure_threshold=2)
        
        # Trigger failures
        breaker.record_failure()
        assert breaker._state == CircuitState.CLOSED
        mock_notify.assert_not_called()
        
        breaker.record_failure()
        assert breaker._state == CircuitState.OPEN
        
        # Verify notification was dispatched
        mock_notify.assert_called_once()
        args, kwargs = mock_notify.call_args
        assert "Circuit Breaker 'test_breaker' OPEN" in kwargs["title"]
        assert kwargs["severity"] == "critical"

    @patch("app.circuit_breaker.dispatch_system_notification_sync")
    def test_manual_force_open_notification(self, mock_notify):
        """Test that manual 'force open' also notifies admins."""
        from app.circuit_breaker import CircuitBreaker, CircuitState
        
        breaker = CircuitBreaker(name="manual_breaker")
        breaker.force_open()
        
        assert breaker._state == CircuitState.OPEN
        mock_notify.assert_called_once()
        assert "Manual" in mock_notify.call_args[1]["title"]
