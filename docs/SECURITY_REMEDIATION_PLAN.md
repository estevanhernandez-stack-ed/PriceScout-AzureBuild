# Security Remediation Plan - Entra ID & Telemetry

**Date:** February 5, 2026
**Scope:** `api/entra_auth.py`, `api/telemetry.py`, `api/unified_auth.py`
**Review Type:** Enterprise Security Standards

---

## Executive Summary

A security review of the newly implemented Entra ID authentication and distributed tracing identified **4 critical**, **4 medium**, and **4 low** severity issues. This document provides the remediation plan.

---

## Issues by Priority

### P0 - Critical (Must Fix Before Production)

| ID | Issue | File | Lines | OWASP | Status |
|----|-------|------|-------|-------|--------|
| SEC-001 | Token validation without signature verification | `entra_auth.py` | 370-431 | A02 | ✅ Fixed |
| SEC-002 | Missing CSRF protection in OAuth flow | `entra_auth.py` | 192-254 | A01 | ✅ Fixed |
| SEC-003 | Open redirect vulnerability | `entra_auth.py` | 329-363 | A01 | ✅ Fixed |
| SEC-004 | Token exposure in URL fragment | `entra_auth.py` | 756-768 | A02 | ✅ Fixed |

### P1 - High (Fix Before Production)

| ID | Issue | File | Lines | Status |
|----|-------|------|-------|--------|
| SEC-005 | Missing tenant ID validation | `entra_auth.py` | 451-454 | ✅ Fixed |
| SEC-006 | Missing audience (aud) validation | `entra_auth.py` | 389-399 | ✅ Fixed |
| SEC-007 | Global mutable state (thread safety) | `entra_auth.py`, `telemetry.py` | 114-189 | ✅ Fixed |
| SEC-008 | Request ID injection vulnerability | `telemetry.py` | 39-43, 195-198 | ✅ Fixed |

### P2 - Medium (Fix Post-Launch)

| ID | Issue | File | Lines | Status |
|----|-------|------|-------|--------|
| SEC-009 | PKCE not implemented | `entra_auth.py` | - | 🔴 Open |
| SEC-010 | Nonce not implemented for ID token replay | `entra_auth.py` | - | 🔴 Open |

### P3 - Low (Track for Future)

| ID | Issue | File | Lines | Status |
|----|-------|------|-------|--------|
| SEC-011 | Error messages may leak internal details | `entra_auth.py` | - | ✅ Fixed |
| SEC-012 | Logging may contain sensitive data | `entra_auth.py` | - | ✅ Fixed |

---

## Detailed Remediation

### SEC-001: Token Validation Without Signature Verification

**Current Code:**
```python
# api/entra_auth.py:217-222
unverified = jose_jwt.get_unverified_claims(token)
```

**Problem:** Tokens are decoded without cryptographic signature verification. An attacker can create a forged JWT with any claims.

**Fix:** Use Microsoft's JWKS endpoint to validate signatures.

```python
from jwt import PyJWKClient
import jwt

JWKS_URL = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/discovery/v2.0/keys"
_jwks_client = None

def get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(JWKS_URL, cache_keys=True)
    return _jwks_client

def validate_entra_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        jwks_client = get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=ENTRA_CLIENT_ID,
            issuer=f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/v2.0"
        )
        return decoded
    except jwt.ExpiredSignatureError:
        logger.debug("Entra token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Entra token validation failed: {e}")
        return None
```

**Dependencies:** Add `PyJWT>=2.8.0` to requirements.txt

---

### SEC-002: Missing CSRF Protection in OAuth Flow

**Current Code:**
```python
# api/entra_auth.py:352
state_value = state or redirect_url  # No cryptographic nonce
```

**Problem:** The OAuth state parameter should be a cryptographic nonce to prevent CSRF attacks.

**Fix:** Generate and validate cryptographic state parameter.

```python
import secrets
import time
from typing import Dict

# In-memory state store (use Redis in production with multiple workers)
_oauth_state_store: Dict[str, dict] = {}
STATE_EXPIRY_SECONDS = 300  # 5 minutes

def generate_oauth_state(redirect_url: Optional[str] = None) -> str:
    """Generate cryptographic state parameter for OAuth CSRF protection."""
    state = secrets.token_urlsafe(32)
    _oauth_state_store[state] = {
        "created_at": time.time(),
        "redirect_url": redirect_url
    }
    # Cleanup expired states
    _cleanup_expired_states()
    return state

def validate_oauth_state(state: str) -> Optional[str]:
    """Validate state parameter and return redirect_url if valid."""
    if state not in _oauth_state_store:
        return None

    state_data = _oauth_state_store.pop(state)  # One-time use

    if time.time() - state_data["created_at"] > STATE_EXPIRY_SECONDS:
        return None

    return state_data.get("redirect_url")

def _cleanup_expired_states():
    """Remove expired state entries."""
    now = time.time()
    expired = [k for k, v in _oauth_state_store.items()
               if now - v["created_at"] > STATE_EXPIRY_SECONDS]
    for k in expired:
        _oauth_state_store.pop(k, None)
```

---

### SEC-003: Open Redirect Vulnerability

**Current Code:**
```python
# api/entra_auth.py:433-437
if state and state.startswith(("http://", "https://")):
    redirect_url = f"{state}#access_token=..."
```

**Problem:** Any URL is accepted as redirect target, enabling phishing.

**Fix:** Validate against allowlist of permitted domains.

```python
from urllib.parse import urlparse
import os

# Configure via environment variable
ALLOWED_REDIRECT_DOMAINS = os.getenv(
    "ALLOWED_REDIRECT_DOMAINS",
    "localhost,127.0.0.1"
).split(",")

def is_safe_redirect_url(url: str) -> bool:
    """Validate redirect URL against allowlist."""
    if not url:
        return False

    try:
        parsed = urlparse(url)

        # Must be http or https
        if parsed.scheme not in ("http", "https"):
            return False

        # Check against allowlist
        host = parsed.netloc.split(":")[0]  # Remove port

        for allowed in ALLOWED_REDIRECT_DOMAINS:
            if host == allowed or host.endswith(f".{allowed}"):
                return True

        return False
    except Exception:
        return False
```

---

### SEC-004: Token Exposure in URL Fragment

**Current Code:**
```python
redirect_url = f"{state}#access_token={session_token}&token_type=bearer"
```

**Problem:** Tokens in URLs can leak via browser history, referrer headers, logs.

**Fix:** Use a short-lived authorization code that must be exchanged server-side.

```python
import secrets

# Temporary code store (use Redis in production)
_auth_code_store: Dict[str, dict] = {}
CODE_EXPIRY_SECONDS = 60  # 1 minute

def create_auth_code(session_token: str, user_info: dict) -> str:
    """Create short-lived authorization code for token exchange."""
    code = secrets.token_urlsafe(32)
    _auth_code_store[code] = {
        "session_token": session_token,
        "user_info": user_info,
        "created_at": time.time()
    }
    return code

def exchange_auth_code(code: str) -> Optional[dict]:
    """Exchange authorization code for session token. One-time use."""
    if code not in _auth_code_store:
        return None

    code_data = _auth_code_store.pop(code)

    if time.time() - code_data["created_at"] > CODE_EXPIRY_SECONDS:
        return None

    return code_data
```

Then redirect with code instead of token:
```python
redirect_url = f"{validated_url}?code={auth_code}"
```

Frontend exchanges code:
```javascript
// Frontend exchanges code for token
const code = new URLSearchParams(window.location.search).get('code');
const response = await fetch(`/api/v1/auth/entra/exchange?code=${code}`);
const { access_token } = await response.json();
```

---

### SEC-005 & SEC-006: Missing Tenant and Audience Validation

**Fix:** Included in SEC-001 fix via PyJWT's `audience` and `issuer` parameters.

---

### SEC-007: Global Mutable State (Thread Safety)

**Current Code:**
```python
_msal_app = None

def get_msal_app():
    global _msal_app
    if _msal_app is None:
        _msal_app = msal.ConfidentialClientApplication(...)
```

**Problem:** Race condition during initialization with multiple async workers.

**Fix:** Use threading lock for initialization.

```python
import threading

_msal_app = None
_msal_lock = threading.Lock()

def get_msal_app():
    global _msal_app

    if _msal_app is not None:
        return _msal_app

    with _msal_lock:
        # Double-check after acquiring lock
        if _msal_app is None:
            _msal_app = msal.ConfidentialClientApplication(...)

    return _msal_app
```

---

### SEC-008: Request ID Injection Vulnerability

**Current Code:**
```python
request_id = request.headers.get("X-Request-ID")
if not request_id:
    request_id = str(uuid4())
```

**Problem:** Malicious request IDs can enable log injection attacks.

**Fix:** Validate format.

```python
import re

UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

def get_or_create_request_id(request: Request) -> str:
    """Get validated request ID or generate new one."""
    request_id = request.headers.get("X-Request-ID", "")

    if request_id and UUID_PATTERN.match(request_id):
        return request_id

    return str(uuid4())
```

---

## Implementation Order

1. **Phase 1 - Critical Fixes** (Today)
   - [ ] SEC-001: Add JWKS signature validation
   - [ ] SEC-002: Add CSRF state protection
   - [ ] SEC-003: Add redirect URL allowlist
   - [ ] SEC-004: Use auth code instead of token in redirect

2. **Phase 2 - High Priority** (Today)
   - [ ] SEC-005/006: Tenant and audience validation (covered by SEC-001)
   - [ ] SEC-007: Thread-safe initialization
   - [ ] SEC-008: Request ID validation

3. **Phase 3 - Post-Launch**
   - [ ] SEC-009: PKCE support
   - [ ] SEC-010: Nonce validation
   - [ ] SEC-011/012: Review error messages and logging

---

## Testing Checklist

- [ ] Valid Entra token is accepted
- [ ] Forged/unsigned token is rejected
- [ ] Expired token is rejected
- [ ] Token from wrong tenant is rejected
- [ ] Token for wrong audience is rejected
- [ ] OAuth flow with valid state succeeds
- [ ] OAuth flow with invalid/missing state fails
- [ ] Redirect to allowed domain works
- [ ] Redirect to disallowed domain fails
- [ ] Auth code exchange works within 60 seconds
- [ ] Auth code exchange fails after expiry
- [ ] Auth code cannot be reused
- [ ] Valid UUID request IDs are preserved
- [ ] Invalid request IDs are replaced with UUIDs

---

## Dependencies to Add

```
# requirements.txt
PyJWT>=2.8.0                   # JWT validation with JWKS support
```

---

## Environment Variables to Add

```
# .env
ALLOWED_REDIRECT_DOMAINS=localhost,127.0.0.1,pricescout.yourcompany.com
```
