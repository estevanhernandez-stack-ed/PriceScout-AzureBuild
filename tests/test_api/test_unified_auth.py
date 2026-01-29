
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from api.unified_auth import require_auth, AuthData
from jose import jwt

# Sample data for tests
SECRET_KEY = "test_secret_key"
ALGORITHM = "HS256"

@pytest.fixture
def mock_jwt_token():
    payload = {"sub": "testuser"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

@pytest.mark.asyncio
async def test_require_auth_jwt_success(mock_jwt_token):
    # Mock payload decoding
    with patch("api.unified_auth.SECRET_KEY", SECRET_KEY), \
         patch("api.unified_auth.ALGORITHM", ALGORITHM), \
         patch("app.users.get_user") as mock_get_user:
        
        mock_get_user.return_value = {
            "username": "testuser",
            "is_admin": False,
            "company": "TestCo",
            "role": "editor"
        }
        
        # Simulating HTTPBearer credentials
        auth_creds = MagicMock()
        auth_creds.scheme = "bearer"
        auth_creds.credentials = mock_jwt_token
        
        result = await require_auth(authorization=auth_creds)
        
        assert result.username == "testuser"
        assert result.auth_method == "jwt"
        assert result.is_admin is False
        assert result.company == "TestCo"
        assert result.role == "editor"

@pytest.mark.asyncio
async def test_require_auth_api_key_success():
    with patch("api.unified_auth.API_KEY_AUTH_ENABLED", True), \
         patch("api.unified_auth.verify_api_key", return_value=True):
        
        result = await require_auth(authorization=None, x_api_key="valid_key")
        
        assert result.username == "api_key_user"
        assert result.auth_method == "api_key"
        assert result.is_admin is True

@pytest.mark.asyncio
async def test_require_auth_bypass_success():
    # Dev mode: No auth headers, DB_AUTH_ENABLED=False
    with patch("api.unified_auth.DB_AUTH_ENABLED", False):
        result = await require_auth(authorization=None, x_api_key=None)
        
        assert result.username == "dev_user"
        assert result.auth_method == "bypass"
        assert result.is_admin is True

@pytest.mark.asyncio
async def test_require_auth_failure():
    # Auth required (DB_AUTH_ENABLED=True) but none provided
    with patch("api.unified_auth.DB_AUTH_ENABLED", True):
        with pytest.raises(HTTPException) as exc:
            await require_auth(authorization=None, x_api_key=None)
        assert exc.value.status_code == 401
        assert "Authentication required" in exc.value.detail

@pytest.mark.asyncio
async def test_require_auth_invalid_jwt():
    # Invalid JWT should fall through to other methods (or fail if DB_AUTH enabled)
    auth_creds = MagicMock()
    auth_creds.scheme = "bearer"
    auth_creds.credentials = "invalid.token.here"
    
    with patch("api.unified_auth.DB_AUTH_ENABLED", True):
        with pytest.raises(HTTPException) as exc:
            await require_auth(authorization=auth_creds, x_api_key=None)
        assert exc.value.status_code == 401
