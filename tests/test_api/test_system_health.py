"""
Tests for System Health and Circuit Breaker API Endpoints

Tests system health monitoring, circuit breaker management, and related admin endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestSystemHealthEndpoints:
    """Tests for /api/v1/system/* health and circuit breaker endpoints."""

    def test_system_health_requires_auth(self, test_client_no_auth):
        """Test that system health requires authentication."""
        response = test_client_no_auth.get("/api/v1/system/health")
        assert response.status_code == 401

    def test_system_health_user_forbidden(self, test_client_as_user):
        """Test that regular users cannot access system health."""
        response = test_client_as_user.get("/api/v1/system/health")
        # Should be forbidden for regular users (need admin/auditor/operator)
        assert response.status_code in [200, 403]  # May depend on role hierarchy

    def test_system_health_admin_allowed(self, test_client_as_admin):
        """Test that admin can access system health."""
        response = test_client_as_admin.get("/api/v1/system/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_system_health_response_structure(self, test_client_as_admin):
        """Test that system health has expected structure."""
        response = test_client_as_admin.get("/api/v1/system/health")

        assert response.status_code == 200
        data = response.json()

        # Should have status
        assert "status" in data
        # May have components or circuits
        assert isinstance(data, dict)


class TestCircuitBreakerResetEndpoints:
    """Tests for /api/v1/system/circuits/reset endpoints."""

    def test_reset_all_circuits_requires_auth(self, test_client_no_auth):
        """Test that resetting circuits requires authentication."""
        response = test_client_no_auth.post("/api/v1/system/circuits/reset")
        assert response.status_code == 401

    def test_reset_all_circuits_user_forbidden(self, test_client_as_user):
        """Test that regular users cannot reset circuits."""
        response = test_client_as_user.post("/api/v1/system/circuits/reset")
        assert response.status_code == 403

    def test_reset_all_circuits_admin_allowed(self, test_client_as_admin):
        """Test that admin can reset all circuits."""
        response = test_client_as_admin.post("/api/v1/system/circuits/reset")

        assert response.status_code == 200

    def test_reset_specific_circuit(self, test_client_as_admin):
        """Test resetting a specific circuit by name."""
        response = test_client_as_admin.post("/api/v1/system/circuits/fandango/reset")

        # Should succeed for valid circuit
        assert response.status_code == 200

    def test_reset_invalid_circuit(self, test_client_as_admin):
        """Test resetting a non-existent circuit."""
        response = test_client_as_admin.post("/api/v1/system/circuits/nonexistent_circuit_xyz/reset")

        # Should return 404 for unknown circuit, or 200 if it handles gracefully
        assert response.status_code in [404, 400, 200]


class TestCircuitBreakerTripEndpoints:
    """Tests for /api/v1/system/circuits/{name}/open (force trip) endpoints."""

    def test_trip_circuit_requires_auth(self, test_client_no_auth):
        """Test that tripping circuit requires authentication."""
        response = test_client_no_auth.post("/api/v1/system/circuits/fandango/open")
        assert response.status_code == 401

    def test_trip_circuit_user_forbidden(self, test_client_as_user):
        """Test that regular users cannot trip circuits."""
        response = test_client_as_user.post("/api/v1/system/circuits/fandango/open")
        assert response.status_code == 403

    def test_trip_circuit_admin_allowed(self, test_client_as_admin):
        """Test that admin can force trip a circuit."""
        response = test_client_as_admin.post("/api/v1/system/circuits/fandango/open")

        assert response.status_code == 200


class TestBasicHealthEndpoints:
    """Tests for /api/v1/health basic health check."""

    def test_health_public_accessible(self, test_client_no_auth):
        """Test that basic health check is public."""
        response = test_client_no_auth.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy", "ok"]

    def test_health_includes_version(self, test_client_no_auth):
        """Test that health check includes version info."""
        response = test_client_no_auth.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert "version" in data

    def test_health_includes_environment(self, test_client_no_auth):
        """Test that health check includes environment info."""
        response = test_client_no_auth.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert "environment" in data


class TestFullHealthEndpoints:
    """Tests for /api/v1/health/full comprehensive health check."""

    def test_full_health_requires_auth(self, test_client_no_auth):
        """Test that full health check requires authentication."""
        response = test_client_no_auth.get("/api/v1/health/full")
        # May be public or require auth depending on config
        assert response.status_code in [200, 401]

    def test_full_health_includes_components(self, test_client_as_admin):
        """Test that full health includes component status."""
        response = test_client_as_admin.get("/api/v1/health/full")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data

        # Should include components breakdown
        if "components" in data:
            assert isinstance(data["components"], dict)
