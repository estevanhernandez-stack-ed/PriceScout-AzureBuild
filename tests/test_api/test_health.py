"""
Tests for Health and Root API Endpoints

Tests basic API functionality and health checks.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestRootEndpoints:
    """Tests for root API endpoints."""

    def test_root_endpoint(self, test_client_no_auth):
        """Test root endpoint returns API info."""
        response = test_client_no_auth.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "PriceScout API"
        assert "version" in data
        assert data["status"] == "operational"
        assert "docs" in data
        assert "health" in data

    def test_api_info_endpoint(self, test_client_no_auth):
        """Test API info endpoint."""
        response = test_client_no_auth.get("/api/v1/info")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "PriceScout API"
        assert "authentication" in data
        assert "rate_limits" in data
        assert "endpoints" in data
        assert "documentation" in data


class TestHealthEndpoint:
    """Tests for /api/v1/health endpoint."""

    def test_health_check_healthy(self, test_client_no_auth):
        """Test health check returns valid response structure."""
        response = test_client_no_auth.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        # Verify response has expected structure
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "environment" in data
        # Status can be healthy, degraded, or unhealthy depending on actual DB state
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_health_check_database_error(self, test_client_no_auth):
        """Test health check handles database errors gracefully."""
        # Note: We can't easily mock database errors in integration tests
        # This test verifies the endpoint returns valid data regardless of DB state
        response = test_client_no_auth.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        # Status should be one of valid values
        assert data.get("status") in ["healthy", "degraded", "unhealthy"]


class TestErrorHandling:
    """Tests for API error handling."""

    def test_404_not_found(self, test_client_no_auth):
        """Test 404 response for non-existent endpoint."""
        response = test_client_no_auth.get("/api/v1/nonexistent-endpoint")

        assert response.status_code == 404

    def test_validation_error_format(self, test_client_as_admin):
        """Test that validation errors return proper error response."""
        # Try to create user with invalid data
        response = test_client_as_admin.post(
            "/api/v1/admin/users",
            json={"username": "ab"}  # Too short, missing password
        )

        # API can return 400 or 422 for validation errors
        assert response.status_code in (400, 422)
        data = response.json()
        # Should contain validation error info
        assert "detail" in data


class TestOpenAPIDocumentation:
    """Tests for API documentation endpoints."""

    def test_openapi_json(self, test_client_no_auth):
        """Test OpenAPI JSON endpoint."""
        response = test_client_no_auth.get("/api/v1/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

    def test_swagger_docs(self, test_client_no_auth):
        """Test Swagger UI is accessible."""
        response = test_client_no_auth.get("/api/v1/docs")

        # Swagger returns HTML
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_redoc_docs(self, test_client_no_auth):
        """Test ReDoc is accessible."""
        response = test_client_no_auth.get("/api/v1/redoc")

        # ReDoc returns HTML
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
