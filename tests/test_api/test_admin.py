"""
Tests for Admin API Router

Tests user management and audit log endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


class TestAdminUserEndpoints:
    """Tests for /api/v1/admin/users endpoints."""

    def test_list_users_requires_auth(self, test_client_no_auth):
        """Test that listing users requires authentication."""
        response = test_client_no_auth.get("/api/v1/admin/users")
        assert response.status_code == 401

    def test_list_users_requires_admin(self, test_client_as_user):
        """Test that non-admin users cannot list users."""
        response = test_client_as_user.get("/api/v1/admin/users")
        assert response.status_code == 403
        assert "Administrative read access required" in response.json().get("detail", "")

    @patch('api.routers.admin.get_session')
    def test_list_users_success(self, mock_get_session, test_client_as_admin):
        """Test successful user listing."""
        # Mock database session
        mock_user = MagicMock()
        mock_user.user_id = 1
        mock_user.username = "testuser"
        mock_user.role = "user"
        mock_user.company_id = None
        mock_user.default_company_id = None
        mock_user.home_location_type = None
        mock_user.home_location_value = None
        mock_user.is_admin = False
        mock_user.is_active = True
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.last_login = None

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.count.return_value = 1
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_user]
        mock_session.query.return_value = mock_query

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context

        response = test_client_as_admin.get("/api/v1/admin/users")

        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total_count" in data

    def test_get_user_not_found(self, test_client_as_admin):
        """Test getting a non-existent user."""
        with patch('api.routers.admin.get_session') as mock_get_session:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = None
            mock_session.query.return_value = mock_query

            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock(return_value=mock_session)
            mock_context.__exit__ = MagicMock(return_value=False)
            mock_get_session.return_value = mock_context

            response = test_client_as_admin.get("/api/v1/admin/users/99999")

            assert response.status_code == 404
            assert "User not found" in response.json().get("detail", "")

    def test_create_user_missing_fields(self, test_client_as_admin):
        """Test creating user with missing required fields."""
        response = test_client_as_admin.post(
            "/api/v1/admin/users",
            json={"username": "te"}  # Too short, missing password
        )
        # API returns 400 (Bad Request) for application-level validation
        assert response.status_code in (400, 422)  # Either validation error type

    @patch('api.routers.admin.users.create_user')
    @patch('api.routers.admin.get_session')
    def test_create_user_success(self, mock_get_session, mock_create_user, test_client_as_admin):
        """Test successful user creation."""
        mock_create_user.return_value = (True, "User created successfully")

        # Mock fetching created user
        mock_user = MagicMock()
        mock_user.user_id = 10
        mock_user.username = "newuser"
        mock_user.role = "user"
        mock_user.company_id = None
        mock_user.default_company_id = None
        mock_user.home_location_type = None
        mock_user.home_location_value = None
        mock_user.is_admin = False
        mock_user.is_active = True
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.last_login = None

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_user
        mock_session.query.return_value = mock_query

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context

        response = test_client_as_admin.post(
            "/api/v1/admin/users",
            json={
                "username": "newuser",
                "password": "SecurePassword123!"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"

    @patch('api.routers.admin.users.delete_user')
    def test_delete_user_self_deletion_prevented(self, mock_delete, test_client_as_admin):
        """Test that admins cannot delete themselves."""
        # The admin user has id=1, so try to delete id=1
        response = test_client_as_admin.delete("/api/v1/admin/users/1")

        assert response.status_code == 400
        assert "Cannot delete your own account" in response.json().get("detail", "")

    def test_update_user_invalid_role(self, test_client_as_admin):
        """Test updating user with invalid role."""
        response = test_client_as_admin.put(
            "/api/v1/admin/users/1",
            json={"role": "superuser"}  # Invalid role
        )
        # API returns 400 (Bad Request) for application-level validation
        assert response.status_code in (400, 422)  # Either validation error type


class TestAuditLogEndpoints:
    """Tests for /api/v1/admin/audit-log endpoints."""

    def test_list_audit_logs_requires_auth(self, test_client_no_auth):
        """Test that audit log requires authentication."""
        response = test_client_no_auth.get("/api/v1/admin/audit-log")
        assert response.status_code == 401

    def test_list_audit_logs_requires_admin(self, test_client_as_user):
        """Test that non-admin users cannot view audit logs."""
        response = test_client_as_user.get("/api/v1/admin/audit-log")
        assert response.status_code == 403

    @patch('api.routers.admin.get_session')
    def test_list_audit_logs_success(self, mock_get_session, test_client_as_admin):
        """Test successful audit log listing."""
        mock_log = MagicMock()
        mock_log.log_id = 1
        mock_log.timestamp = datetime.now(timezone.utc)
        mock_log.username = "admin"
        mock_log.event_type = "LOGIN"
        mock_log.event_category = "AUTH"
        mock_log.severity = "INFO"
        mock_log.details = "Successful login"
        mock_log.ip_address = "127.0.0.1"

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.count.return_value = 1
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_log]
        mock_session.query.return_value = mock_query

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context

        response = test_client_as_admin.get("/api/v1/admin/audit-log")

        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total_count" in data

    def test_list_audit_logs_with_filters(self, test_client_as_admin):
        """Test audit log filtering parameters."""
        with patch('api.routers.admin.get_session') as mock_get_session:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.count.return_value = 0
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.offset.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.all.return_value = []
            mock_session.query.return_value = mock_query

            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock(return_value=mock_session)
            mock_context.__exit__ = MagicMock(return_value=False)
            mock_get_session.return_value = mock_context

            response = test_client_as_admin.get(
                "/api/v1/admin/audit-log",
                params={
                    "event_type": "LOGIN",
                    "severity": "INFO",
                    "date_from": "2026-01-01"
                }
            )

            assert response.status_code == 200

    def test_list_audit_logs_invalid_date(self, test_client_as_admin):
        """Test audit log with invalid date format."""
        with patch('api.routers.admin.get_session') as mock_get_session:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.count.return_value = 0
            mock_query.filter.return_value = mock_query
            mock_session.query.return_value = mock_query

            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock(return_value=mock_session)
            mock_context.__exit__ = MagicMock(return_value=False)
            mock_get_session.return_value = mock_context

            response = test_client_as_admin.get(
                "/api/v1/admin/audit-log",
                params={"date_from": "not-a-date"}
            )

            assert response.status_code == 400
            assert "Invalid date_from format" in response.json().get("detail", "")

    @patch('api.routers.admin.get_session')
    def test_list_event_types(self, mock_get_session, test_client_as_admin):
        """Test listing distinct event types."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = [("LOGIN",), ("LOGOUT",), ("USER_CREATE",)]
        mock_session.query.return_value = mock_query

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context

        response = test_client_as_admin.get("/api/v1/admin/audit-log/event-types")

        assert response.status_code == 200
        data = response.json()
        assert "event_types" in data

    @patch('api.routers.admin.get_session')
    def test_list_categories(self, mock_get_session, test_client_as_admin):
        """Test listing distinct categories."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = [("AUTH",), ("ADMIN",), ("DATA",)]
        mock_session.query.return_value = mock_query

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_get_session.return_value = mock_context

        response = test_client_as_admin.get("/api/v1/admin/audit-log/categories")

        assert response.status_code == 200
        data = response.json()
        assert "categories" in data


class TestPasswordReset:
    """Tests for password reset functionality."""

    def test_reset_password_requires_admin(self, test_client_as_user):
        """Test that password reset requires admin access."""
        response = test_client_as_user.post(
            "/api/v1/admin/users/1/reset-password",
            json={"new_password": "NewPassword123!"}
        )
        assert response.status_code == 403

    def test_reset_password_user_not_found(self, test_client_as_admin):
        """Test resetting password for non-existent user."""
        with patch('api.routers.admin.get_session') as mock_get_session:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = None
            mock_session.query.return_value = mock_query

            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock(return_value=mock_session)
            mock_context.__exit__ = MagicMock(return_value=False)
            mock_get_session.return_value = mock_context

            response = test_client_as_admin.post(
                "/api/v1/admin/users/99999/reset-password",
                json={"new_password": "NewPassword123!"}
            )

            assert response.status_code == 404

    def test_reset_password_weak_password(self, test_client_as_admin):
        """Test resetting with weak password (too short)."""
        response = test_client_as_admin.post(
            "/api/v1/admin/users/1/reset-password",
            json={"new_password": "short"}  # Less than 8 chars
        )
        # API returns 400 (Bad Request) for application-level validation
        assert response.status_code in (400, 422)  # Either validation error type
