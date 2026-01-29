"""
Authentication Router for PriceScout API

Provides:
- OAuth2 Password flow (username/password → JWT token)
- Entra ID SSO endpoints (enterprise authentication)
- Token validation and user lookup
- Rate limiting on sensitive endpoints

Usage:
    # Get token
    POST /api/v1/auth/token
    Content-Type: application/x-www-form-urlencoded
    username=user&password=pass

    # Use token
    GET /api/v1/some-endpoint
    Authorization: Bearer <token>

    # Entra ID login (if enabled)
    GET /api/v1/auth/entra/login
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from collections import defaultdict
import time
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)


from app.audit_service import audit_service


# ============================================================================
# RATE LIMITING FOR AUTH ENDPOINTS
# ============================================================================

class AuthRateLimiter:
    """
    Simple in-memory rate limiter for authentication endpoints.
    Tracks failed login attempts per IP and username.

    For production with multiple instances, consider using Redis.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,  # 5 minutes
        lockout_seconds: int = 900  # 15 minutes
    ):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self.attempts = defaultdict(list)  # key -> list of timestamps
        self.lockouts = {}  # key -> lockout_until timestamp

    def _cleanup_old_attempts(self, key: str) -> None:
        """Remove attempts older than the window."""
        cutoff = time.time() - self.window_seconds
        self.attempts[key] = [t for t in self.attempts[key] if t > cutoff]

    def is_locked_out(self, key: str) -> tuple[bool, int]:
        """
        Check if a key (IP or username) is locked out.
        Returns (is_locked, seconds_remaining).
        """
        if key in self.lockouts:
            if time.time() < self.lockouts[key]:
                remaining = int(self.lockouts[key] - time.time())
                return True, remaining
            else:
                # Lockout expired
                del self.lockouts[key]
                self.attempts[key] = []
        return False, 0

    def record_attempt(self, key: str, success: bool) -> None:
        """Record a login attempt."""
        if success:
            # Clear attempts on successful login
            self.attempts[key] = []
            if key in self.lockouts:
                del self.lockouts[key]
        else:
            self._cleanup_old_attempts(key)
            self.attempts[key].append(time.time())

            # Check if we should lock out
            if len(self.attempts[key]) >= self.max_attempts:
                self.lockouts[key] = time.time() + self.lockout_seconds
                logger.warning(f"Rate limit lockout triggered for: {key[:20]}...")

    def get_remaining_attempts(self, key: str) -> int:
        """Get remaining attempts before lockout."""
        self._cleanup_old_attempts(key)
        return max(0, self.max_attempts - len(self.attempts[key]))


# Global rate limiter instance
auth_rate_limiter = AuthRateLimiter()


async def check_auth_rate_limit(request: Request) -> None:
    """
    FastAPI dependency to check rate limits before auth attempts.
    Raises HTTPException if rate limited.
    """
    # Get client IP (handle proxy headers for Azure)
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"

    # Check IP-based lockout
    is_locked, remaining = auth_rate_limiter.is_locked_out(f"ip:{client_ip}")
    if is_locked:
        logger.warning(f"Rate limited login attempt from IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Please try again in {remaining // 60} minutes.",
            headers={
                "Retry-After": str(remaining),
                "X-RateLimit-Reset": str(int(time.time()) + remaining)
            }
        )

from app import users
from app.config import (
    OAUTH2_SCHEME, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES,
    DB_AUTH_ENABLED, ENTRA_ENABLED, API_KEY_AUTH_ENABLED
)

# Import RFC 7807 error helpers
from api.errors import (
    unauthorized_error,
    validation_error,
    internal_error,
    ProblemType
)

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    auth_method: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


class User(BaseModel):
    username: str
    is_admin: bool
    company: Optional[str] = None
    default_company: Optional[str] = None
    role: str


# ============================================================================
# TOKEN FUNCTIONS
# ============================================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload data (must include 'sub' for username)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "auth_method": data.get("auth_method", "password")
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(OAUTH2_SCHEME)) -> dict:
    """
    Validate JWT token and return user data.

    This is a FastAPI dependency that extracts and validates the JWT token
    from the Authorization header.

    Args:
        token: JWT token from Authorization header

    Returns:
        User dict with username, role, company_id, etc.

    Raises:
        HTTPException 401 if token is invalid or user not found
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token_data = TokenData(
            username=username,
            role=payload.get("role"),
            auth_method=payload.get("auth_method")
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_row = users.get_user(username=token_data.username)
    if user_row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Convert sqlite3.Row to dict so we can modify it
    user = dict(user_row)
    # Add auth_method to user dict
    user["auth_method"] = token_data.auth_method
    return user


async def require_admin(current_user: dict = Depends(get_current_user)):
    """Dependency that requires admin role."""
    if current_user.get("role") != "admin" and not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def require_operator(current_user: dict = Depends(get_current_user)):
    """Dependency that requires operator or higher role."""
    allowed = ["admin", "operator", "manager"]
    if current_user.get("role") not in allowed and not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator access required"
        )
    return current_user


async def require_auditor(current_user: dict = Depends(get_current_user)):
    """Dependency that requires auditor or higher role."""
    allowed = ["admin", "auditor"]
    if current_user.get("role") not in allowed and not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Auditor access required"
        )
    return current_user


async def require_read_admin(current_user: dict = Depends(get_current_user)):
    """Dependency that requires admin/auditor/operator/manager for read-only admin tasks."""
    allowed = ["admin", "auditor", "operator", "manager"]
    if current_user.get("role") not in allowed and not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative read access required"
        )
    return current_user


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@router.post("/token", response_model=Token, tags=["Authentication"])
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    _rate_limit: None = Depends(check_auth_rate_limit)
):
    """
    OAuth2 Password Grant - Exchange credentials for access token.

    This is the standard OAuth2 password flow. Send username and password
    as form data to receive a JWT access token.

    **Rate Limited:** 5 attempts per 5 minutes, then 15-minute lockout.

    **Note:** This endpoint can be disabled by setting `DB_AUTH_ENABLED=false`.
    When disabled, use Entra ID SSO instead.

    **Request:**
    ```
    POST /api/v1/auth/token
    Content-Type: application/x-www-form-urlencoded

    username=your_username&password=your_password
    ```

    **Response:**
    ```json
    {
        "access_token": "eyJ...",
        "token_type": "bearer"
    }
    ```
    """
    # Get client IP for rate limiting tracking
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"

    # Check if database auth is enabled
    if not DB_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Database authentication is disabled. Use Entra ID SSO instead. "
                   "Contact your administrator if you need access.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    # Authenticate user
    user_row = users.verify_user(form_data.username, form_data.password)

    if not user_row:
        # Record failed attempt for both IP and username
        auth_rate_limiter.record_attempt(f"ip:{client_ip}", success=False)
        auth_rate_limiter.record_attempt(f"user:{form_data.username}", success=False)

        # Get remaining attempts for user feedback
        remaining = auth_rate_limiter.get_remaining_attempts(f"ip:{client_ip}")

        audit_service.security_event(
            event_type="login_failure",
            severity="warning",
            username=form_data.username,
            details={
                "reason": "invalid_credentials",
                "remaining_attempts": remaining
            },
            request=request
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Incorrect username or password. {remaining} attempts remaining.",
            headers={
                "WWW-Authenticate": "Bearer",
                "X-RateLimit-Remaining": str(remaining)
            },
        )
    
    # Convert Row to dict for easier access
    auth_user = dict(user_row)

    # Record successful login (clears rate limit counters)
    auth_rate_limiter.record_attempt(f"ip:{client_ip}", success=True)
    auth_rate_limiter.record_attempt(f"user:{form_data.username}", success=True)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": auth_user["username"],
            "role": auth_user["role"],
            "auth_method": "password"
        },
        expires_delta=access_token_expires
    )

    logger.info(f"Successful login for user: {auth_user['username']} from IP: {client_ip}")

    # Audit successful login
    audit_service.security_event(
        event_type="login_success",
        user_id=auth_user.get("id"), # SQLite uses id
        username=auth_user["username"],
        company_id=auth_user.get("company_id"),
        details={"auth_method": "password"},
        request=request
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout", tags=["Authentication"])
async def logout(current_user: dict = Depends(get_current_user)):
    """
    Logout current user.

    Clears the user's session token on the server side.
    The client should also discard the access token.
    """
    try:
        username = current_user.get('username')
        users.clear_session_token(username)
        
        audit_service.security_event(
            event_type="logout",
            user_id=current_user.get("user_id"),
            username=username,
            company_id=current_user.get("company_id")
        )
        
        return {"message": "Logout successful"}
    except Exception as e:
        # Don't fail logout even if session clear fails
        return {"message": "Logout successful", "note": "Session may persist"}


@router.get("/me", tags=["Authentication"])
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    Get information about the currently authenticated user.

    Returns user profile data including role, company, and permissions.
    """
    return {
        "username": current_user.get("username"),
        "role": current_user.get("role"),
        "is_admin": current_user.get("is_admin", False),
        "company": current_user.get("company"),
        "company_id": current_user.get("company_id"),
        "auth_method": current_user.get("auth_method", "password"),
        "allowed_modes": current_user.get("allowed_modes", []),
        "home_location_type": current_user.get("home_location_type"),
        "home_location_value": current_user.get("home_location_value"),
    }


@router.post("/refresh", response_model=Token, tags=["Authentication"])
async def refresh_token(current_user: dict = Depends(get_current_user)):
    """
    Refresh access token.

    Exchange a valid (but possibly near-expiry) token for a fresh one.
    The old token remains valid until its original expiry.
    """
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": current_user["username"],
            "role": current_user.get("role", "user"),
            "auth_method": current_user.get("auth_method", "password")
        },
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


# ============================================================================
# ENTRA ID SSO ENDPOINTS
# ============================================================================

# Register Entra ID routes if available
try:
    from api.entra_auth import register_entra_routes, is_entra_enabled
    register_entra_routes(router)
except ImportError:
    # Entra auth module not available
    pass


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health", tags=["Authentication"])
async def auth_health():
    """
    Authentication service health check.

    Returns status of authentication services including which methods are enabled.
    """
    entra_status = {"enabled": ENTRA_ENABLED, "available": False}

    try:
        from api.entra_auth import is_entra_enabled, get_entra_status
        entra_status = get_entra_status()
    except ImportError:
        pass

    return {
        "status": "healthy",
        "auth_methods": {
            "database_auth": {
                "enabled": DB_AUTH_ENABLED,
                "endpoint": "/api/v1/auth/token" if DB_AUTH_ENABLED else None
            },
            "api_key_auth": {
                "enabled": API_KEY_AUTH_ENABLED,
                "header": "X-API-Key" if API_KEY_AUTH_ENABLED else None
            },
            "entra_id": entra_status
        },
        "jwt_configured": bool(SECRET_KEY),
        "token_expiry_minutes": ACCESS_TOKEN_EXPIRE_MINUTES,
        # Compliance note
        "compliance_note": "Set DB_AUTH_ENABLED=false and API_KEY_AUTH_ENABLED=false for Entra-only mode"
    }
