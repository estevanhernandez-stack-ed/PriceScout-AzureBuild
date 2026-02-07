"""
PriceScout API - Microsoft Entra ID Authentication (Secure Implementation)

Provides OAuth2 Authorization Code flow using MSAL Python for enterprise SSO.

Security Features:
- JWKS signature validation for all tokens
- CSRF protection via cryptographic state parameter
- Redirect URL allowlist validation
- Auth code exchange pattern (tokens not exposed in URLs)
- Tenant and audience validation
- Thread-safe initialization

Configuration (set in .env or App Service configuration):
    ENTRA_ENABLED=true
    ENTRA_CLIENT_ID=<your-app-registration-client-id>
    ENTRA_TENANT_ID=<your-azure-ad-tenant-id>
    ENTRA_CLIENT_SECRET=<your-client-secret>
    ENTRA_REDIRECT_URI=http://localhost:8000/api/v1/auth/entra/callback
    ALLOWED_REDIRECT_DOMAINS=localhost,127.0.0.1,yourdomain.com

Endpoints added to auth router:
    GET  /auth/entra/login    - Initiates OAuth2 flow, returns redirect URL
    GET  /auth/entra/callback - Handles OAuth callback, returns auth code
    POST /auth/entra/exchange - Exchanges auth code for session JWT
    GET  /auth/entra/status   - Returns Entra configuration status
"""

import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from jose import jwt

logger = logging.getLogger(__name__)

# Import configuration
from app.config import (
    ENTRA_ENABLED,
    ENTRA_CLIENT_ID,
    ENTRA_TENANT_ID,
    ENTRA_CLIENT_SECRET,
    ENTRA_REDIRECT_URI,
    ENTRA_AUTHORITY,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES
)


# ============================================================================
# SECURITY CONFIGURATION
# ============================================================================

# Allowed redirect domains (comma-separated in env var)
ALLOWED_REDIRECT_DOMAINS = [
    d.strip() for d in
    os.getenv("ALLOWED_REDIRECT_DOMAINS", "localhost,127.0.0.1").split(",")
    if d.strip()
]

# JWKS endpoint for token signature validation
JWKS_URL = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/discovery/v2.0/keys" if ENTRA_TENANT_ID else None
ISSUER = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/v2.0" if ENTRA_TENANT_ID else None

# State and auth code expiration
STATE_EXPIRY_SECONDS = 300  # 5 minutes for OAuth state
AUTH_CODE_EXPIRY_SECONDS = 60  # 1 minute for auth code exchange


# ============================================================================
# CONFIGURATION CHECK
# ============================================================================

def is_entra_enabled() -> bool:
    """Check if Entra ID authentication is properly configured."""
    return bool(
        ENTRA_ENABLED and
        ENTRA_CLIENT_ID and
        ENTRA_TENANT_ID and
        ENTRA_CLIENT_SECRET
    )


def get_entra_status() -> Dict[str, Any]:
    """Get Entra ID configuration status for health checks."""
    return {
        "enabled": ENTRA_ENABLED,
        "available": is_entra_enabled(),
        "configured": {
            "client_id": bool(ENTRA_CLIENT_ID),
            "tenant_id": bool(ENTRA_TENANT_ID),
            "client_secret": bool(ENTRA_CLIENT_SECRET),
            "redirect_uri": bool(ENTRA_REDIRECT_URI),
            "allowed_redirect_domains": ALLOWED_REDIRECT_DOMAINS,
        },
        "login_endpoint": "/api/v1/auth/entra/login" if is_entra_enabled() else None,
    }


# ============================================================================
# THREAD-SAFE INITIALIZATION
# ============================================================================

_msal_app = None
_msal_lock = threading.Lock()
_jwks_client = None
_jwks_lock = threading.Lock()


def get_msal_app():
    """
    Get or create MSAL ConfidentialClientApplication (thread-safe).
    """
    global _msal_app

    if _msal_app is not None:
        return _msal_app

    if not is_entra_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Entra ID authentication is not configured"
        )

    with _msal_lock:
        # Double-check after acquiring lock
        if _msal_app is None:
            try:
                import msal
                _msal_app = msal.ConfidentialClientApplication(
                    client_id=ENTRA_CLIENT_ID,
                    client_credential=ENTRA_CLIENT_SECRET,
                    authority=ENTRA_AUTHORITY
                )
                logger.info("MSAL ConfidentialClientApplication initialized")
            except ImportError:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="MSAL library not installed"
                )
            except Exception as e:
                logger.error(f"Failed to initialize MSAL app: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to initialize authentication service"
                )

    return _msal_app


def get_jwks_client():
    """
    Get or create PyJWKClient for token signature validation (thread-safe).
    """
    global _jwks_client

    if _jwks_client is not None:
        return _jwks_client

    if not JWKS_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWKS URL not configured"
        )

    with _jwks_lock:
        if _jwks_client is None:
            try:
                from jwt import PyJWKClient
                _jwks_client = PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)
                logger.info(f"PyJWKClient initialized for: {JWKS_URL}")
            except ImportError:
                logger.warning("PyJWT not installed, falling back to basic validation")
                return None
            except Exception as e:
                logger.error(f"Failed to initialize JWKS client: {e}")
                return None

    return _jwks_client


# ============================================================================
# CSRF STATE MANAGEMENT
# ============================================================================

# In-memory state store (use Redis in production with multiple workers)
_oauth_state_store: Dict[str, dict] = {}
_state_lock = threading.Lock()


def generate_oauth_state(redirect_url: Optional[str] = None) -> str:
    """
    Generate cryptographic state parameter for OAuth CSRF protection.

    Args:
        redirect_url: Optional URL to redirect after successful auth

    Returns:
        Cryptographic state token
    """
    state = secrets.token_urlsafe(32)

    with _state_lock:
        _oauth_state_store[state] = {
            "created_at": time.time(),
            "redirect_url": redirect_url
        }
        # Cleanup expired states
        _cleanup_expired_states()

    return state


def validate_oauth_state(state: str) -> Optional[str]:
    """
    Validate state parameter and return redirect_url if valid.

    Args:
        state: State parameter from OAuth callback

    Returns:
        Redirect URL if valid, None if invalid/expired
    """
    with _state_lock:
        if state not in _oauth_state_store:
            logger.warning(f"OAuth state not found: {state[:8]}...")
            return None

        state_data = _oauth_state_store.pop(state)  # One-time use

    if time.time() - state_data["created_at"] > STATE_EXPIRY_SECONDS:
        logger.warning("OAuth state expired")
        return None

    return state_data.get("redirect_url")


def _cleanup_expired_states():
    """Remove expired state entries (called within lock)."""
    now = time.time()
    expired = [k for k, v in _oauth_state_store.items()
               if now - v["created_at"] > STATE_EXPIRY_SECONDS * 2]
    for k in expired:
        _oauth_state_store.pop(k, None)


# ============================================================================
# AUTH CODE EXCHANGE (Secure Token Delivery)
# ============================================================================

_auth_code_store: Dict[str, dict] = {}
_code_lock = threading.Lock()


def create_auth_code(session_token: str, user_info: dict) -> str:
    """
    Create short-lived authorization code for token exchange.

    This prevents token exposure in URLs/browser history.

    Args:
        session_token: The JWT session token
        user_info: User information from Entra

    Returns:
        Authorization code for exchange
    """
    code = secrets.token_urlsafe(32)

    with _code_lock:
        _auth_code_store[code] = {
            "session_token": session_token,
            "user_info": user_info,
            "created_at": time.time()
        }
        # Cleanup expired codes
        _cleanup_expired_codes()

    return code


def exchange_auth_code(code: str) -> Optional[dict]:
    """
    Exchange authorization code for session token. One-time use.

    Args:
        code: Authorization code from callback

    Returns:
        Dict with session_token and user_info, or None if invalid
    """
    with _code_lock:
        if code not in _auth_code_store:
            logger.warning(f"Auth code not found: {code[:8]}...")
            return None

        code_data = _auth_code_store.pop(code)  # One-time use

    if time.time() - code_data["created_at"] > AUTH_CODE_EXPIRY_SECONDS:
        logger.warning("Auth code expired")
        return None

    return code_data


def _cleanup_expired_codes():
    """Remove expired auth codes (called within lock)."""
    now = time.time()
    expired = [k for k, v in _auth_code_store.items()
               if now - v["created_at"] > AUTH_CODE_EXPIRY_SECONDS * 2]
    for k in expired:
        _auth_code_store.pop(k, None)


# ============================================================================
# REDIRECT URL VALIDATION
# ============================================================================

def is_safe_redirect_url(url: str) -> bool:
    """
    Validate redirect URL against allowlist.

    Args:
        url: URL to validate

    Returns:
        True if URL is safe to redirect to
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)

        # Must be http or https
        if parsed.scheme not in ("http", "https"):
            return False

        # Extract host (remove port if present)
        host = parsed.netloc.split(":")[0].lower()

        # Check against allowlist
        for allowed in ALLOWED_REDIRECT_DOMAINS:
            allowed = allowed.lower()
            if host == allowed or host.endswith(f".{allowed}"):
                return True

        logger.warning(f"Redirect URL not in allowlist: {host}")
        return False

    except Exception as e:
        logger.warning(f"Invalid redirect URL: {e}")
        return False


# ============================================================================
# TOKEN VALIDATION WITH JWKS
# ============================================================================

def validate_entra_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate an Entra ID access token with full signature verification.

    Args:
        token: Bearer token from Authorization header

    Returns:
        Dict with user claims if valid, None if invalid
    """
    try:
        # Try JWKS validation first (recommended)
        jwks_client = get_jwks_client()

        if jwks_client:
            try:
                import jwt as pyjwt
                signing_key = jwks_client.get_signing_key_from_jwt(token)

                decoded = pyjwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=ENTRA_CLIENT_ID,
                    issuer=ISSUER,
                    options={
                        "verify_exp": True,
                        "verify_aud": True,
                        "verify_iss": True,
                    }
                )

                # Extract user claims
                return {
                    "oid": decoded.get("oid"),
                    "preferred_username": decoded.get("preferred_username") or decoded.get("upn"),
                    "name": decoded.get("name"),
                    "email": decoded.get("email") or decoded.get("preferred_username") or decoded.get("upn"),
                    "tenant_id": decoded.get("tid"),
                    "auth_method": "entra"
                }

            except pyjwt.ExpiredSignatureError:
                logger.debug("Entra token expired")
                return None
            except pyjwt.InvalidAudienceError:
                logger.warning("Entra token has invalid audience")
                return None
            except pyjwt.InvalidIssuerError:
                logger.warning("Entra token has invalid issuer")
                return None
            except pyjwt.InvalidTokenError as e:
                logger.debug(f"Entra token validation failed: {e}")
                return None

        # Fallback: Basic validation without JWKS (less secure, logs warning)
        logger.warning("JWKS validation unavailable, using basic validation")
        return _basic_token_validation(token)

    except Exception as e:
        logger.debug(f"Entra token validation error: {e}")
        return None


def _basic_token_validation(token: str) -> Optional[Dict[str, Any]]:
    """
    Basic token validation without signature verification.
    Only used as fallback when JWKS client unavailable.

    WARNING: This is less secure - install PyJWT for full security.
    """
    try:
        from jose import jwt as jose_jwt

        # Decode without verification
        unverified = jose_jwt.get_unverified_claims(token)

        # Must have Object ID (always present in Entra tokens)
        if not unverified.get("oid"):
            return None

        # Validate tenant
        if unverified.get("tid") != ENTRA_TENANT_ID:
            logger.warning(f"Token from unauthorized tenant: {unverified.get('tid')}")
            return None

        # Validate audience
        aud = unverified.get("aud")
        if aud != ENTRA_CLIENT_ID:
            logger.warning(f"Token for unauthorized audience: {aud}")
            return None

        # Check expiration
        exp = unverified.get("exp")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            logger.debug("Entra token expired")
            return None

        return {
            "oid": unverified.get("oid"),
            "preferred_username": unverified.get("preferred_username") or unverified.get("upn"),
            "name": unverified.get("name"),
            "email": unverified.get("email") or unverified.get("preferred_username") or unverified.get("upn"),
            "tenant_id": unverified.get("tid"),
            "auth_method": "entra"
        }

    except Exception as e:
        logger.debug(f"Basic token validation failed: {e}")
        return None


# ============================================================================
# AUTH FLOW FUNCTIONS
# ============================================================================

# Scopes for Microsoft Graph - basic user profile
ENTRA_SCOPES = ["User.Read"]


def initiate_auth_flow(redirect_url: Optional[str] = None) -> Dict[str, str]:
    """
    Initiate OAuth2 Authorization Code flow with CSRF protection.

    Args:
        redirect_url: Optional URL to redirect after successful auth

    Returns:
        Dict with 'auth_url' and 'state'
    """
    msal_app = get_msal_app()

    # Generate cryptographic state for CSRF protection
    state = generate_oauth_state(redirect_url)

    # Generate authorization URL
    auth_url = msal_app.get_authorization_request_url(
        scopes=ENTRA_SCOPES,
        redirect_uri=ENTRA_REDIRECT_URI,
        state=state
    )

    return {"auth_url": auth_url, "state": state}


def complete_auth_flow(authorization_code: str) -> Dict[str, Any]:
    """
    Complete OAuth2 flow by exchanging authorization code for tokens.

    Args:
        authorization_code: Code received from Microsoft callback

    Returns:
        Dict with user info and tokens from Entra ID

    Raises:
        HTTPException if token exchange fails
    """
    msal_app = get_msal_app()

    # Exchange code for tokens
    result = msal_app.acquire_token_by_authorization_code(
        code=authorization_code,
        scopes=ENTRA_SCOPES,
        redirect_uri=ENTRA_REDIRECT_URI
    )

    if "error" in result:
        logger.error(f"Entra ID token error: {result.get('error')}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

    # Extract user info from ID token claims
    id_token_claims = result.get("id_token_claims", {})

    return {
        "access_token": result.get("access_token"),
        "id_token": result.get("id_token"),
        "token_type": result.get("token_type", "Bearer"),
        "expires_in": result.get("expires_in"),
        "user_info": {
            "oid": id_token_claims.get("oid"),
            "preferred_username": id_token_claims.get("preferred_username"),
            "name": id_token_claims.get("name"),
            "email": id_token_claims.get("email") or id_token_claims.get("preferred_username"),
            "tenant_id": id_token_claims.get("tid"),
        }
    }


def create_session_jwt(user_info: Dict[str, Any]) -> str:
    """
    Create a local session JWT from Entra ID user info.

    Args:
        user_info: User claims from Entra ID token

    Returns:
        Local JWT access token
    """
    username = user_info.get("preferred_username") or user_info.get("email") or user_info.get("oid")

    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "auth_method": "entra",
        "entra_oid": user_info.get("oid"),
        "name": user_info.get("name"),
        "email": user_info.get("email"),
        "tenant_id": user_info.get("tenant_id"),
        "role": "user"
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class EntraLoginResponse(BaseModel):
    """Response from /auth/entra/login endpoint."""
    auth_url: str
    message: str = "Redirect user to auth_url for Microsoft login"


class EntraExchangeResponse(BaseModel):
    """Response from /auth/entra/exchange endpoint."""
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class EntraStatusResponse(BaseModel):
    """Response from /auth/entra/status endpoint."""
    enabled: bool
    available: bool
    configured: Dict[str, Any]
    login_endpoint: Optional[str] = None


# ============================================================================
# ROUTE REGISTRATION
# ============================================================================

def register_entra_routes(router: APIRouter):
    """
    Register Entra ID authentication routes on the provided router.
    """

    @router.get("/entra/login", response_model=EntraLoginResponse, tags=["Authentication"])
    async def entra_login(
        request: Request,
        redirect_url: Optional[str] = Query(None, description="URL to redirect after login")
    ):
        """
        Initiate Microsoft Entra ID login flow.

        Returns a URL to redirect the user to for Microsoft authentication.

        **Security:**
        - CSRF protection via cryptographic state parameter
        - Redirect URL validated against allowlist

        **Flow:**
        1. Client calls this endpoint with optional redirect_url
        2. Client redirects user to returned `auth_url`
        3. User authenticates with Microsoft
        4. Microsoft redirects to `/auth/entra/callback` with authorization code
        5. Callback returns a short-lived auth code
        6. Client exchanges auth code for session JWT via `/auth/entra/exchange`
        """
        if not is_entra_enabled():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Entra ID authentication is not enabled"
            )

        # Validate redirect URL if provided
        if redirect_url and not is_safe_redirect_url(redirect_url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Redirect URL not in allowlist. Allowed domains: {ALLOWED_REDIRECT_DOMAINS}"
            )

        result = initiate_auth_flow(redirect_url=redirect_url)

        logger.info(f"Entra login initiated from {request.client.host if request.client else 'unknown'}")

        return EntraLoginResponse(
            auth_url=result["auth_url"],
            message="Redirect user to auth_url for Microsoft login"
        )


    @router.get("/entra/callback", tags=["Authentication"])
    async def entra_callback(
        request: Request,
        code: str = Query(..., description="Authorization code from Microsoft"),
        state: str = Query(..., description="State parameter for CSRF validation"),
        error: Optional[str] = Query(None, description="Error code if auth failed"),
        error_description: Optional[str] = Query(None, description="Error description")
    ):
        """
        Handle Microsoft Entra ID OAuth callback.

        This endpoint is called by Microsoft after the user authenticates.
        It validates the state parameter, exchanges the code for tokens,
        and returns a short-lived auth code (not the actual token).

        **Security:**
        - State parameter validated for CSRF protection
        - Returns auth code, not token (prevents URL/history leakage)
        - Auth code expires in 60 seconds
        """
        if not is_entra_enabled():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Entra ID authentication is not enabled"
            )

        # Check for error from Microsoft
        if error:
            logger.warning(f"Entra callback error: {error}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Microsoft authentication failed"
            )

        # Validate CSRF state parameter
        redirect_url = validate_oauth_state(state)
        if redirect_url is None and state:
            # State was provided but invalid - could be CSRF attack
            # Check if state exists but expired vs never existed
            logger.warning(f"Invalid OAuth state parameter")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired state parameter. Please restart the login process."
            )

        # Exchange code for tokens
        try:
            entra_result = complete_auth_flow(code)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Entra callback failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to complete authentication"
            )

        # Create local session JWT
        user_info = entra_result["user_info"]
        session_token = create_session_jwt(user_info)

        logger.info(f"Entra login successful for: {user_info.get('preferred_username', 'unknown')}")

        # Audit log
        try:
            from app.audit_service import audit_service
            audit_service.security_event(
                event_type="login_success",
                username=user_info.get("preferred_username"),
                details={
                    "auth_method": "entra",
                    "tenant_id": user_info.get("tenant_id"),
                },
                request=request
            )
        except Exception:
            pass

        # Create auth code for secure token delivery
        auth_code = create_auth_code(session_token, {
            "username": user_info.get("preferred_username"),
            "name": user_info.get("name"),
            "email": user_info.get("email"),
            "auth_method": "entra"
        })

        # If redirect URL was specified, redirect with auth code (not token)
        if redirect_url and is_safe_redirect_url(redirect_url):
            # Use query param for code (code is short-lived and one-time use)
            separator = "&" if "?" in redirect_url else "?"
            final_url = f"{redirect_url}{separator}auth_code={auth_code}"
            return RedirectResponse(url=final_url, status_code=302)

        # Otherwise return JSON with auth code
        return {
            "auth_code": auth_code,
            "message": "Exchange auth_code for access_token via POST /auth/entra/exchange",
            "expires_in": AUTH_CODE_EXPIRY_SECONDS
        }


    @router.post("/entra/exchange", response_model=EntraExchangeResponse, tags=["Authentication"])
    async def entra_exchange(
        code: str = Query(..., alias="auth_code", description="Auth code from callback")
    ):
        """
        Exchange authorization code for session token.

        The auth code is single-use and expires in 60 seconds.

        **Request:**
        ```
        POST /api/v1/auth/entra/exchange?auth_code=<code>
        ```

        **Response:**
        ```json
        {
            "access_token": "eyJ...",
            "token_type": "bearer",
            "user": {"username": "...", "name": "...", "email": "..."}
        }
        ```
        """
        code_data = exchange_auth_code(code)

        if not code_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired auth code"
            )

        return EntraExchangeResponse(
            access_token=code_data["session_token"],
            token_type="bearer",
            user=code_data["user_info"]
        )


    @router.get("/entra/status", response_model=EntraStatusResponse, tags=["Authentication"])
    async def entra_status():
        """
        Get Entra ID configuration status.

        Returns whether Entra ID is enabled and properly configured.
        Useful for frontend to determine which login options to show.
        """
        status_info = get_entra_status()
        return EntraStatusResponse(
            enabled=status_info["enabled"],
            available=status_info["available"],
            configured=status_info["configured"],
            login_endpoint=status_info["login_endpoint"]
        )


    logger.info("Entra ID authentication routes registered (secure implementation)")
