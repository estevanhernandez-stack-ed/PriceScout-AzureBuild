# React Authentication Flow

**Project:** PriceScout React Migration
**Date:** 2026-01-07

---

## Overview

PriceScout supports three authentication methods:
1. **JWT Token Auth** - Username/password login (OAuth2 password grant)
2. **Entra ID SSO** - Microsoft enterprise single sign-on
3. **API Key Auth** - For programmatic access (X-API-Key header)

The React frontend will primarily use JWT Token Auth with optional Entra ID SSO.

---

## Current Backend Implementation

### JWT Configuration

| Setting | Value | Source |
|---------|-------|--------|
| Algorithm | HS256 | `app/config.py` |
| Token Expiration | 30 minutes | `ACCESS_TOKEN_EXPIRE_MINUTES` |
| Token URL | `/api/v1/auth/token` | OAuth2 endpoint |
| Header Format | `Authorization: Bearer <token>` | Standard OAuth2 |

### Rate Limiting

| Parameter | Value |
|-----------|-------|
| Max Attempts | 5 per 5 minutes |
| Lockout Duration | 15 minutes |
| Tracked By | IP address + Username |

---

## Authentication Flow Diagrams

### 1. Login Flow (JWT)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         LOGIN FLOW                                   │
└─────────────────────────────────────────────────────────────────────┘

User                    React App                   API Server
 │                          │                           │
 │  Enter credentials       │                           │
 │─────────────────────────>│                           │
 │                          │                           │
 │                          │  POST /api/v1/auth/token  │
 │                          │  (form: username, pass)   │
 │                          │──────────────────────────>│
 │                          │                           │
 │                          │                           │ Validate creds
 │                          │                           │ Check rate limit
 │                          │                           │ Generate JWT
 │                          │                           │
 │                          │  { access_token, type }   │
 │                          │<──────────────────────────│
 │                          │                           │
 │                          │  Store token              │
 │                          │  (localStorage or memory) │
 │                          │                           │
 │                          │  GET /api/v1/auth/me      │
 │                          │  Authorization: Bearer    │
 │                          │──────────────────────────>│
 │                          │                           │
 │                          │  { user profile }         │
 │                          │<──────────────────────────│
 │                          │                           │
 │  Redirect to dashboard   │                           │
 │<─────────────────────────│                           │
 │                          │                           │
```

### 2. Token Refresh Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                      TOKEN REFRESH FLOW                              │
└─────────────────────────────────────────────────────────────────────┘

React App                                         API Server
    │                                                  │
    │  (Token near expiration - 5 min remaining)       │
    │                                                  │
    │  POST /api/v1/auth/refresh                       │
    │  Authorization: Bearer <current_token>           │
    │─────────────────────────────────────────────────>│
    │                                                  │
    │                                                  │ Validate current token
    │                                                  │ Generate new JWT
    │                                                  │
    │  { access_token, token_type }                    │
    │<─────────────────────────────────────────────────│
    │                                                  │
    │  Replace stored token                            │
    │                                                  │
```

### 3. Entra ID SSO Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                      ENTRA ID SSO FLOW                               │
└─────────────────────────────────────────────────────────────────────┘

User          React App         API Server         Microsoft Entra
 │                │                  │                    │
 │ Click SSO      │                  │                    │
 │───────────────>│                  │                    │
 │                │                  │                    │
 │                │ GET /auth/entra/login                 │
 │                │─────────────────>│                    │
 │                │                  │                    │
 │                │ Redirect URL     │                    │
 │                │<─────────────────│                    │
 │                │                  │                    │
 │                │ Redirect to Microsoft                 │
 │<───────────────│─────────────────────────────────────>│
 │                │                  │                    │
 │ Login at Microsoft                │                    │
 │──────────────────────────────────────────────────────>│
 │                │                  │                    │
 │ Redirect back with auth code      │                    │
 │<──────────────────────────────────────────────────────│
 │                │                  │                    │
 │                │ GET /auth/entra/callback?code=xxx    │
 │                │─────────────────>│                    │
 │                │                  │                    │
 │                │                  │ Exchange code      │
 │                │                  │───────────────────>│
 │                │                  │                    │
 │                │                  │ User info + tokens │
 │                │                  │<───────────────────│
 │                │                  │                    │
 │                │                  │ Create/update user │
 │                │                  │ Generate our JWT   │
 │                │                  │                    │
 │                │ { access_token } │                    │
 │                │<─────────────────│                    │
 │                │                  │                    │
 │ Dashboard      │                  │                    │
 │<───────────────│                  │                    │
```

---

## React Implementation

### Token Storage Strategy

**Recommendation: In-Memory + Refresh Token Cookie**

| Storage | Use Case | Security |
|---------|----------|----------|
| **In-Memory (useState/Zustand)** | Access token | Most secure - not in storage |
| **httpOnly Cookie** | Refresh token | Secure from XSS |
| **localStorage** | Fallback / "Remember me" | Less secure, but persists |

For initial implementation, we'll use **localStorage** with XSS protections, upgrading to httpOnly cookies when backend supports refresh tokens in cookies.

### Auth Store (Zustand)

```typescript
// stores/authStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { UserResponse, Token } from '@/types';

interface AuthState {
  // State
  token: string | null;
  user: UserResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  login: (username: string, password: string) => Promise<void>;
  loginWithEntra: () => void;
  logout: () => void;
  refreshToken: () => Promise<void>;
  fetchUser: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      // Login with username/password
      login: async (username: string, password: string) => {
        set({ isLoading: true, error: null });

        try {
          const formData = new URLSearchParams();
          formData.append('username', username);
          formData.append('password', password);

          const response = await fetch('/api/v1/auth/token', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData,
          });

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
          }

          const data: Token = await response.json();
          set({ token: data.access_token, isAuthenticated: true });

          // Fetch user profile
          await get().fetchUser();
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : 'Login failed',
            isAuthenticated: false,
            token: null,
          });
          throw error;
        } finally {
          set({ isLoading: false });
        }
      },

      // Initiate Entra ID login
      loginWithEntra: () => {
        const returnUrl = encodeURIComponent(window.location.origin + '/auth/callback');
        window.location.href = `/api/v1/auth/entra/login?redirect_after=${returnUrl}`;
      },

      // Logout
      logout: async () => {
        const { token } = get();

        try {
          if (token) {
            await fetch('/api/v1/auth/logout', {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${token}`,
              },
            });
          }
        } finally {
          set({
            token: null,
            user: null,
            isAuthenticated: false,
            error: null,
          });
        }
      },

      // Refresh token
      refreshToken: async () => {
        const { token } = get();
        if (!token) return;

        try {
          const response = await fetch('/api/v1/auth/refresh', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          });

          if (response.ok) {
            const data: Token = await response.json();
            set({ token: data.access_token });
          } else {
            // Token expired, logout
            get().logout();
          }
        } catch {
          get().logout();
        }
      },

      // Fetch current user
      fetchUser: async () => {
        const { token } = get();
        if (!token) return;

        try {
          const response = await fetch('/api/v1/auth/me', {
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          });

          if (response.ok) {
            const user: UserResponse = await response.json();
            set({ user });
          }
        } catch {
          // Silent fail - user fetch is optional
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'pricescout-auth',
      partialize: (state) => ({
        token: state.token,
        // Don't persist user - fetch fresh on load
      }),
    }
  )
);
```

### Axios Interceptor Setup

```typescript
// lib/api.ts
import axios from 'axios';
import { useAuthStore } from '@/stores/authStore';

export const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - add auth token
api.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().token;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle 401 and token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If 401 and we haven't retried yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // Try to refresh token
        await useAuthStore.getState().refreshToken();

        // Retry original request with new token
        const token = useAuthStore.getState().token;
        if (token) {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        }
      } catch {
        // Refresh failed, logout
        useAuthStore.getState().logout();
      }
    }

    return Promise.reject(error);
  }
);
```

### Protected Route Component

```typescript
// components/ProtectedRoute.tsx
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: 'admin' | 'manager' | 'user';
}

export function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const { isAuthenticated, user, isLoading } = useAuthStore();
  const location = useLocation();

  // Show loading while checking auth
  if (isLoading) {
    return <div>Loading...</div>; // Replace with proper loading component
  }

  // Not authenticated - redirect to login
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Check role requirement
  if (requiredRole && user) {
    const roleHierarchy = { admin: 3, manager: 2, user: 1 };
    const userLevel = roleHierarchy[user.role as keyof typeof roleHierarchy] || 0;
    const requiredLevel = roleHierarchy[requiredRole] || 0;

    if (userLevel < requiredLevel) {
      return <Navigate to="/unauthorized" replace />;
    }
  }

  return <>{children}</>;
}
```

### Login Page Component

```typescript
// pages/Login.tsx
import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const { login, loginWithEntra, isLoading, error, clearError } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/dashboard';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();

    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch {
      // Error is handled in store
    }
  };

  return (
    <div className="login-container">
      <h1>PriceScout Login</h1>

      {error && (
        <div className="error-message" role="alert">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="username">Username</label>
          <input
            id="username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoComplete="username"
          />
        </div>

        <div>
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </div>

        <button type="submit" disabled={isLoading}>
          {isLoading ? 'Logging in...' : 'Login'}
        </button>
      </form>

      <div className="sso-divider">
        <span>or</span>
      </div>

      <button onClick={loginWithEntra} className="sso-button">
        Sign in with Microsoft
      </button>
    </div>
  );
}
```

### Token Refresh Timer

```typescript
// hooks/useTokenRefresh.ts
import { useEffect, useRef } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { jwtDecode } from 'jwt-decode';

interface JWTPayload {
  exp: number;
  sub: string;
}

export function useTokenRefresh() {
  const { token, refreshToken, logout } = useAuthStore();
  const timeoutRef = useRef<NodeJS.Timeout>();

  useEffect(() => {
    if (!token) {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      return;
    }

    try {
      const decoded = jwtDecode<JWTPayload>(token);
      const expiresAt = decoded.exp * 1000; // Convert to milliseconds
      const now = Date.now();

      // Refresh 5 minutes before expiration
      const refreshIn = expiresAt - now - 5 * 60 * 1000;

      if (refreshIn <= 0) {
        // Token already expired or about to expire
        refreshToken();
      } else {
        // Schedule refresh
        timeoutRef.current = setTimeout(() => {
          refreshToken();
        }, refreshIn);
      }
    } catch {
      // Invalid token
      logout();
    }

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [token, refreshToken, logout]);
}
```

### Router Setup with Protected Routes

```typescript
// App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { useTokenRefresh } from '@/hooks/useTokenRefresh';

// Pages
import { LoginPage } from '@/pages/Login';
import { DashboardPage } from '@/pages/Dashboard';
import { PriceAlertsPage } from '@/pages/PriceAlerts';
import { AdminUsersPage } from '@/pages/admin/Users';
import { UnauthorizedPage } from '@/pages/Unauthorized';

const queryClient = new QueryClient();

function AppRoutes() {
  // Set up token refresh
  useTokenRefresh();

  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<EntraCallback />} />
      <Route path="/unauthorized" element={<UnauthorizedPage />} />

      {/* Protected routes - any authenticated user */}
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/price-alerts"
        element={
          <ProtectedRoute>
            <PriceAlertsPage />
          </ProtectedRoute>
        }
      />

      {/* Admin only routes */}
      <Route
        path="/admin/users"
        element={
          <ProtectedRoute requiredRole="admin">
            <AdminUsersPage />
          </ProtectedRoute>
        }
      />

      {/* Default redirect */}
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

---

## Security Considerations

### XSS Protection

1. **Never store tokens in cookies without httpOnly** (accessible to JS)
2. **Sanitize all user inputs** before rendering
3. **Use Content Security Policy** headers (already configured in API)
4. **Avoid innerHTML** - use React's JSX rendering

### CSRF Protection

1. **SameSite cookies** for any cookie-based auth
2. **Origin validation** in API (already configured)
3. **CSRF tokens** for state-changing operations (if using cookies)

### Token Security

1. **Short expiration** (30 minutes) limits damage if stolen
2. **Refresh tokens** should be rotated on each use
3. **Logout** should invalidate server-side session
4. **Secure transmission** - HTTPS only in production

---

## API Endpoints Reference

| Endpoint | Method | Auth Required | Description |
|----------|--------|---------------|-------------|
| `/auth/token` | POST | No | Login with username/password |
| `/auth/logout` | POST | Yes | Logout current session |
| `/auth/me` | GET | Yes | Get current user info |
| `/auth/refresh` | POST | Yes | Refresh access token |
| `/auth/health` | GET | No | Auth service health check |
| `/auth/entra/login` | GET | No | Initiate Entra ID SSO |
| `/auth/entra/callback` | GET | No | Handle Entra ID callback |
| `/auth/entra/status` | GET | No | Check Entra ID configuration |

---

## Error Handling

### Rate Limiting Response

```json
{
  "detail": "Too many login attempts. Please try again in 15 minutes.",
  "status": 429
}
```

Headers:
- `Retry-After: 900` (seconds)
- `X-RateLimit-Reset: 1704672000` (unix timestamp)

### Invalid Credentials Response

```json
{
  "detail": "Incorrect username or password. 3 attempts remaining.",
  "status": 401
}
```

Headers:
- `WWW-Authenticate: Bearer`
- `X-RateLimit-Remaining: 3`

---

## Environment Variables

```env
# Frontend (.env)
VITE_API_BASE_URL=/api/v1
VITE_ENTRA_ENABLED=true

# Backend (already configured)
SECRET_KEY=<production-secret>
ACCESS_TOKEN_EXPIRE_MINUTES=30
DB_AUTH_ENABLED=true
ENTRA_ENABLED=true
```

---

## Testing Authentication

### Unit Test Example

```typescript
// __tests__/auth.test.ts
import { renderHook, act } from '@testing-library/react';
import { useAuthStore } from '@/stores/authStore';

describe('Auth Store', () => {
  beforeEach(() => {
    useAuthStore.getState().logout();
  });

  it('should login successfully', async () => {
    // Mock fetch
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ access_token: 'test-token', token_type: 'bearer' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ username: 'testuser', role: 'user' }),
      });

    const { result } = renderHook(() => useAuthStore());

    await act(async () => {
      await result.current.login('testuser', 'password');
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe('test-token');
  });

  it('should handle login failure', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: 'Invalid credentials' }),
    });

    const { result } = renderHook(() => useAuthStore());

    await expect(
      act(async () => {
        await result.current.login('baduser', 'badpass');
      })
    ).rejects.toThrow();

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.error).toBe('Invalid credentials');
  });
});
```

---

## Next Steps

1. [ ] Implement auth store with Zustand
2. [ ] Create login page component
3. [ ] Set up Axios interceptors
4. [ ] Add protected route wrapper
5. [ ] Implement token refresh logic
6. [ ] Test Entra ID SSO flow
7. [ ] Add "Remember me" functionality
8. [ ] Implement password reset flow
