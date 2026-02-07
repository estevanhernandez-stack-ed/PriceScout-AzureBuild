# Documentation Update Task for Claude Agent

**Generated:** February 5, 2026
**Purpose:** Fresh Claude agent session context for updating PriceScout documentation

---

## Your Task

Update PriceScout app documentation to reflect recent security enhancements and architectural changes. The existing runbooks need updating, and the new security implementation needs to be documented for operators.

---

## Application Context

**PriceScout** is a theater pricing intelligence platform for Marcus Theatres. It:
- Scrapes competitor ticket prices from Fandango
- Syncs premium/PLF data from EntTelligence API
- Detects price surges and anomalies vs baselines
- Tracks presale ticket buildup for upcoming releases
- Generates daily lineup and operating hours reports

**Tech Stack:**
- Backend: Python 3.11 + FastAPI + SQLAlchemy
- Frontend: React 18 + TypeScript + Vite + shadcn/ui
- Database: PostgreSQL (Azure SQL in production)
- Hosting: Azure App Service
- Auth: Microsoft Entra ID SSO + local username/password + API keys
- Monitoring: Azure Application Insights via OpenTelemetry

---

## Recent Changes (February 2026)

### 1. Entra ID Authentication (NEW)

**Files Created:**
- `api/entra_auth.py` (827 lines) - Full MSAL OAuth2 implementation

**Security Features Implemented:**
- JWKS token signature verification (not just decoding)
- CSRF protection with cryptographic state parameters
- Open redirect prevention via domain allowlist
- Auth code exchange pattern (tokens not in URLs)
- Thread-safe MSAL client initialization

**New Endpoints:**
- `GET /api/v1/auth/entra/login` - Initiates Entra SSO flow
- `GET /api/v1/auth/entra/callback` - OAuth callback handler
- `POST /api/v1/auth/entra/exchange` - Exchanges auth code for session JWT

**Environment Variables Added:**
```
ENTRA_ENABLED=true|false
ENTRA_CLIENT_ID=your-app-registration-id
ENTRA_TENANT_ID=your-azure-ad-tenant
ENTRA_CLIENT_SECRET=your-client-secret
ENTRA_REDIRECT_URI=https://yourapp.com/api/v1/auth/entra/callback
ALLOWED_REDIRECT_DOMAINS=localhost,127.0.0.1,yourapp.com
```

### 2. Distributed Tracing Enhanced

**Files Modified:**
- `api/telemetry.py` - Full OpenTelemetry configuration with Azure Monitor

**Features:**
- W3C Trace Context propagation (traceparent/tracestate headers)
- Request ID middleware with UUID validation (prevents log injection)
- Automatic instrumentation of FastAPI, httpx, requests
- Business telemetry: track_scrape, track_price_change, track_alert

**Key Security Fix:**
- Request ID validation now rejects malformed IDs that could enable log injection attacks
- Only valid UUID format accepted, others replaced with new UUID

### 3. Security Remediation Plan

A security audit was conducted against enterprise standards. See `docs/SECURITY_REMEDIATION_PLAN.md` for the full report.

**Issues Fixed (P0/P1):**
| ID | Issue | Status |
|----|-------|--------|
| SEC-001 | Token validation without signature verification | FIXED |
| SEC-002 | Missing CSRF protection in OAuth flow | FIXED |
| SEC-003 | Open redirect vulnerability | FIXED |
| SEC-004 | Token exposure in URL fragment | FIXED |
| SEC-005 | Missing tenant ID validation | FIXED |
| SEC-006 | Missing audience (aud) validation | FIXED |
| SEC-007 | Global mutable state (thread safety) | FIXED |
| SEC-008 | Request ID injection vulnerability | FIXED |

**Deferred (P2):**
- SEC-009: PKCE implementation
- SEC-010: Nonce for ID token replay

### 4. Frontend Fixes

**Operating Hours (DailyLineupPage.tsx):**
- Changed to show `first showtime → last showtime` (not last showtime + runtime)
- Company workflow: hours are when box office operates, not when last movie ends

**Presale Tracking (PresaleTrackingPage.tsx):**
- Trajectory chart now shows Marcus-only time series
- Filters by Marcus circuit name for cleaner data visualization
- Circuit comparisons moved to separate tab

---

## Documentation Files to Update

### Priority 1: Runbooks

**`docs/PriceScout-Runbook.md`** (lines 219-229 need update)
- Add Entra ID troubleshooting section
- Document how to check/rotate Entra client secrets
- Add new environment variables to appendix

**`docs/OPERATIONS_RUNBOOK.md`**
- Add Entra ID authentication section
- Document trace ID correlation for debugging
- Update incident response for auth failures

### Priority 2: Security Documentation

**`docs/SECURITY_CONTROLS_REPORT.md`**
- Add Entra ID security controls
- Document JWKS validation
- Document redirect URL allowlist

**`docs/development/SECURITY_CHECKLIST.md`**
- Add OAuth security checklist items
- Add distributed tracing security items

### Priority 3: Developer Guides

**`docs/REACT_AUTHENTICATION_FLOW.md`**
- Update with Entra ID SSO flow diagram
- Document frontend MSAL integration points

**`docs/API_REFERENCE.md`**
- Add new Entra auth endpoints
- Document X-Request-ID header behavior
- Document X-Trace-ID response header

### Priority 4: New Documentation (Optional)

Consider creating:
- `docs/ENTRA_ID_SETUP_GUIDE.md` - Azure AD app registration steps
- `docs/TELEMETRY_GUIDE.md` - OpenTelemetry configuration and custom events

---

## Files to Read for Context

Essential files to understand the implementation:

```
api/entra_auth.py           # New - full Entra ID implementation
api/telemetry.py            # Enhanced - OpenTelemetry setup
api/unified_auth.py         # Modified - Entra token validation path
api/routers/auth.py         # Modified - Entra endpoints added
.env.example                # Updated - new env vars documented
requirements.txt            # Updated - PyJWT added
docs/SECURITY_REMEDIATION_PLAN.md  # New - security audit results
```

---

## Documentation Standards

When updating documentation:

1. **Keep it concise** - Operators need quick answers during incidents
2. **Include commands** - Runbooks should have copy-pasteable commands
3. **Add timestamps** - Update "Last Updated" dates
4. **Cross-reference** - Link related documents

Example runbook entry format:
```markdown
### Issue: Entra ID Authentication Failing

**Symptoms:** Users see "Authentication failed" when using SSO

**Diagnosis:**
1. Check Entra client secret expiry in Azure Portal
2. Verify redirect URI matches deployment URL
3. Check Application Insights for specific error:
   ```kusto
   traces
   | where message contains "Entra token validation failed"
   | project timestamp, message
   ```

**Resolution:**
- If secret expired: Rotate in Azure Portal, update Key Vault
- If redirect mismatch: Update ENTRA_REDIRECT_URI env var
- If tenant mismatch: Verify ENTRA_TENANT_ID matches Azure AD
```

---

## Verification

After updates, verify:
- [ ] All new environment variables documented in relevant guides
- [ ] Security controls documented for compliance
- [ ] Runbooks include troubleshooting for new auth methods
- [ ] API reference includes new endpoints
- [ ] "Last Updated" dates reflect February 2026

---

## Questions for Operator (Optional)

If needed, ask:
1. Should Entra ID setup be its own guide or integrated into existing docs?
2. What compliance frameworks matter (SOC2, ISO27001, etc.)?
3. Are there specific incident scenarios you've encountered recently?

---

*This prompt was auto-generated on February 5, 2026 after completing security enhancements.*
