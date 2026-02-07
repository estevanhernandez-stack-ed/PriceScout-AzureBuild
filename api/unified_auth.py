"""
PriceScout API - Unified Authentication

Provides a unified authentication dependency that supports multiple auth methods:
- JWT Bearer tokens
- API keys
- Optional bypass for development

This allows endpoints to accept any valid authentication method without
needing to specify them individually.
"""

from typing import Optional
from pydantic import BaseModel
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Auth configuration
from app.config import (
    API_KEY_AUTH_ENABLED,
    DB_AUTH_ENABLED,
    ENTRA_ENABLED,
    SECRET_KEY,
    ALGORITHM
)

# Import auth functions
from jose import JWTError, jwt
from api.auth import verify_api_key


class AuthData(BaseModel):
    """Standardized authentication data returned by require_auth."""
    username: str
    auth_method: str  # "jwt", "api_key", "bypass"
    is_admin: bool = False
    company: Optional[str] = None
    role: Optional[str] = "user"


# Optional Bearer scheme for token extraction
bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> AuthData:
    """
    Unified authentication dependency.
    
    Accepts:
    - Bearer tokens (JWT)
    - X-API-Key headers
    - Allows bypass if no auth is configured (development mode)
    
    Args:
        authorization: Optional bearer token from Authorization header
        x_api_key: Optional API key from X-API-Key header
        
    Returns:
        AuthData with user information
        
    Raises:
        HTTPException: 401 if authentication fails
    """
    
    # Try JWT authentication first
    if authorization and authorization.scheme.lower() == "bearer":
        try:
            # Decode and validate JWT token
            payload = jwt.decode(authorization.credentials, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username:
                # Import here to avoid circular dependency
                from app import users
                user_row = users.get_user(username=username)
                if user_row:
                    user_dict = dict(user_row)
                    return AuthData(
                        username=user_dict.get("username", username),
                        auth_method="jwt",
                        is_admin=user_dict.get("is_admin", False),
                        company=user_dict.get("company"),
                        role=user_dict.get("role", "user")
                    )
        except (JWTError, Exception):
            # JWT validation failed, continue to try other methods
            pass

    # Try Entra ID token authentication
    if ENTRA_ENABLED and authorization and authorization.scheme.lower() == "bearer":
        try:
            from api.entra_auth import validate_entra_token
            entra_result = validate_entra_token(authorization.credentials)
            if entra_result:
                return AuthData(
                    username=entra_result.get("preferred_username") or entra_result.get("email") or entra_result.get("oid"),
                    auth_method="entra",
                    is_admin=False,  # Entra users default to non-admin (can be enhanced with Azure AD groups)
                    company=None,
                    role=entra_result.get("role", "user")
                )
        except ImportError:
            # Entra auth module not available
            pass
        except Exception:
            # Entra token validation failed, continue to try other methods
            pass

    # Try API key authentication
    if x_api_key and API_KEY_AUTH_ENABLED:
        api_key_valid = await verify_api_key(x_api_key)
        if api_key_valid:
            return AuthData(
                username="api_key_user",
                auth_method="api_key",
                is_admin=True,  # API keys have admin access
                role="admin"
            )
    
    # If DB auth is enabled, require authentication
    if DB_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide valid Bearer token or API key.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Development mode: allow bypass
    return AuthData(
        username="dev_user",
        auth_method="bypass",
        is_admin=True,
        role="admin"
    )
