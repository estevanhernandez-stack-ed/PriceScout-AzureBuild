# PriceScout React Frontend - Accords Remediation Checklist

**Application**: PriceScout React Frontend
**Current Location**: `C:\Projects\ENTAzurePricescout\PriceScoutENTReact\frontend\`
**Target Location**: `apps/pricescout/frontend/` (Theatre Operations Platform monorepo)
**Date**: January 2026

---

## Current Assessment

| Metric | Current | Target (Beta+) | Gap |
|--------|---------|----------------|-----|
| **Architecture Compliance** | 100% | 90%+ | ✅ Exceeds |
| **Feature Completion** | ~75-80% | 90%+ | ~15% |
| **Test Coverage** | ~5% | 70%+ | **65%** |
| **Documentation** | ~40% | 100% Required | ~60% |

**Primary Blocker**: Test coverage (5% → 70%)

---

## Phase 1: Test Infrastructure Verification (Day 1)

Your test setup is already excellent. Verify it's working:

### Checklist

- [ ] **Vitest runs**: `npm run test`
- [ ] **Coverage reports**: `npm run test:coverage`
- [ ] **Playwright E2E runs**: `npm run test:e2e`
- [ ] **MSW mocks working**: Check `src/test/setup.ts`

### Commands to Run
```bash
# Verify test infrastructure
npm run test              # Should run existing tests
npm run test:coverage     # Should generate coverage report
npm run test:e2e          # Should run Playwright tests
```

---

## Phase 2: Unit Test Priority List (Days 2-7)

Focus on high-value, high-coverage targets first.

### Tier 1: API Hooks (19 hooks - Highest ROI)

These are pure logic, easy to test, and cover your entire data layer.

| Hook File | Priority | Est. Tests | Est. Coverage Impact |
|-----------|----------|------------|---------------------|
| `useAuth` (in authStore) | 🔴 Critical | 8-10 | +3% |
| `useMarkets.ts` | 🔴 Critical | 6-8 | +2% |
| `useTheaters.ts` | 🔴 Critical | 6-8 | +2% |
| `usePriceAlerts.ts` | 🟠 High | 5-6 | +1.5% |
| `usePriceChecks.ts` | 🟠 High | 5-6 | +1.5% |
| `usePresales.ts` | 🟠 High | 5-6 | +1.5% |
| `useScrapes.ts` | 🟡 Medium | 4-5 | +1% |
| `useReports.ts` | 🟡 Medium | 4-5 | +1% |
| `useSystemHealth.ts` | 🟡 Medium | 4-5 | +1% |
| `useUsers.ts` | 🟡 Medium | 4-5 | +1% |
| `useAuditLog.ts` | 🟢 Low | 3-4 | +0.5% |
| `useCache.ts` | 🟢 Low | 3-4 | +0.5% |
| `useSync.ts` | 🟢 Low | 3-4 | +0.5% |
| Remaining 6 hooks | 🟢 Low | 3-4 each | +3% |

**Subtotal**: ~60-70 tests, ~+20% coverage

#### Example Test Template for Hooks
```typescript
// hooks/api/__tests__/useMarkets.test.ts
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { useMarkets } from '../useMarkets';

const server = setupServer(
  http.get('/api/v1/markets', () => {
    return HttpResponse.json([
      { id: 1, name: 'Milwaukee', code: 'MKE' },
      { id: 2, name: 'Chicago', code: 'CHI' },
    ]);
  })
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const wrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
};

describe('useMarkets', () => {
  it('fetches markets successfully', async () => {
    const { result } = renderHook(() => useMarkets(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(2);
    expect(result.current.data[0].name).toBe('Milwaukee');
  });

  it('handles error state', async () => {
    server.use(
      http.get('/api/v1/markets', () => {
        return HttpResponse.error();
      })
    );

    const { result } = renderHook(() => useMarkets(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
```

---

### Tier 2: Zustand Store (authStore.ts)

Critical for security testing.

| Test Case | Priority |
|-----------|----------|
| Login success flow | 🔴 Critical |
| Login failure handling | 🔴 Critical |
| Token refresh | 🔴 Critical |
| Logout clears state | 🔴 Critical |
| Persistence works | 🟠 High |
| Role extraction from JWT | 🟠 High |
| isAuthenticated computed | 🟡 Medium |
| hasRole helper | 🟡 Medium |

**Subtotal**: ~10-12 tests, ~+5% coverage

#### Example Test
```typescript
// stores/__tests__/authStore.test.ts
import { act } from '@testing-library/react';
import { useAuthStore } from '../authStore';

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.getState().logout();
    localStorage.clear();
  });

  it('starts with unauthenticated state', () => {
    const { isAuthenticated, user } = useAuthStore.getState();
    expect(isAuthenticated).toBe(false);
    expect(user).toBeNull();
  });

  it('sets tokens and user on login', () => {
    act(() => {
      useAuthStore.getState().setTokens('access-token', 'refresh-token');
      useAuthStore.getState().setUser({ id: 1, email: 'test@test.com' });
    });

    const { isAuthenticated, user } = useAuthStore.getState();
    expect(isAuthenticated).toBe(true);
    expect(user?.email).toBe('test@test.com');
  });

  it('clears state on logout', () => {
    act(() => {
      useAuthStore.getState().setTokens('token', 'refresh');
      useAuthStore.getState().logout();
    });

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
```

---

### Tier 3: Utility Functions (lib/)

Pure functions = easy wins.

| File | Functions to Test | Est. Tests |
|------|-------------------|------------|
| `lib/utils.ts` | cn(), formatters | 5-8 |
| `lib/api.ts` | Error handlers, interceptors | 8-10 |
| `lib/queryClient.ts` | Default options | 3-4 |

**Subtotal**: ~15-20 tests, ~+5% coverage

---

### Tier 4: UI Components (components/ui/)

shadcn/ui components are pre-tested, but your custom wrappers need tests.

| Component | Priority | Est. Tests |
|-----------|----------|------------|
| `ProtectedRoute.tsx` | 🔴 Critical | 4-5 |
| `MainLayout.tsx` | 🟠 High | 3-4 |
| `AuthLayout.tsx` | 🟠 High | 2-3 |
| `PriceAlertsTable.tsx` | 🟡 Medium | 5-6 |
| `MarketHeatmap.tsx` | 🟡 Medium | 4-5 |
| `TrainingCenter.tsx` | 🟢 Low | 2-3 |

**Subtotal**: ~20-25 tests, ~+10% coverage

#### Example Component Test
```typescript
// components/auth/__tests__/ProtectedRoute.test.tsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProtectedRoute } from '../ProtectedRoute';
import { useAuthStore } from '@/stores/authStore';

// Mock the store
vi.mock('@/stores/authStore');

describe('ProtectedRoute', () => {
  it('renders children when authenticated', () => {
    vi.mocked(useAuthStore).mockReturnValue({
      isAuthenticated: true,
      user: { roles: ['user'] },
    });

    render(
      <MemoryRouter>
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    );

    expect(screen.getByText('Protected Content')).toBeInTheDocument();
  });

  it('redirects when not authenticated', () => {
    vi.mocked(useAuthStore).mockReturnValue({
      isAuthenticated: false,
      user: null,
    });

    render(
      <MemoryRouter>
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    );

    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
  });
});
```

---

### Tier 5: Page Components (Selective)

Don't test every page. Focus on complex logic.

| Page | Priority | Rationale |
|------|----------|-----------|
| `LoginPage.tsx` | 🔴 Critical | Auth flow |
| `DashboardPage.tsx` | 🟠 High | Entry point |
| `MarketModePage.tsx` | 🟡 Medium | Complex (1,478 lines) |
| `SystemHealthPage.tsx` | 🟡 Medium | Admin critical |

**Subtotal**: ~15-20 tests, ~+10% coverage

---

## Phase 3: E2E Tests (Days 8-10)

Expand Playwright tests for critical user flows.

### Priority Flows

| Flow | File | Est. Time |
|------|------|-----------|
| Login → Dashboard | `e2e/auth.spec.ts` | 2 hours |
| Price Alerts CRUD | `e2e/price-alerts.spec.ts` | 3 hours |
| Market Mode navigation | `e2e/market-mode.spec.ts` | 2 hours |
| Admin user management | `e2e/admin-users.spec.ts` | 3 hours |
| Report generation | `e2e/reports.spec.ts` | 2 hours |

**Subtotal**: 5 E2E test files, ~+10% coverage

---

## Phase 4: Coverage Targets by Day

| Day | Focus | Cumulative Coverage |
|-----|-------|---------------------|
| 1 | Infrastructure verification | 5% (baseline) |
| 2 | Auth store + 3 critical hooks | 15% |
| 3 | 6 more hooks | 25% |
| 4 | Remaining hooks + utilities | 40% |
| 5 | ProtectedRoute + layouts | 50% |
| 6 | Data table components | 55% |
| 7 | 4 page components | 65% |
| 8 | E2E: Auth + Dashboard | 70% ✅ |
| 9 | E2E: Price Alerts + Market Mode | 75% |
| 10 | E2E: Admin flows + buffer | 80% |

---

## Test File Structure

Create this structure:

```
src/
├── test/
│   └── setup.ts                    # (exists)
├── hooks/
│   └── api/
│       └── __tests__/              # NEW
│           ├── useMarkets.test.ts
│           ├── useTheaters.test.ts
│           ├── usePriceAlerts.test.ts
│           └── ...
├── stores/
│   └── __tests__/                  # NEW
│       └── authStore.test.ts
├── lib/
│   └── __tests__/                  # NEW
│       ├── utils.test.ts
│       └── api.test.ts
├── components/
│   ├── auth/
│   │   └── __tests__/              # NEW
│   │       └── ProtectedRoute.test.ts
│   └── layout/
│       └── __tests__/              # NEW
│           └── MainLayout.test.ts
└── pages/
    └── __tests__/                  # NEW
        ├── LoginPage.test.tsx
        └── DashboardPage.test.tsx

e2e/
├── auth.spec.ts                    # NEW
├── price-alerts.spec.ts            # NEW
├── market-mode.spec.ts             # (exists, expand)
├── admin-users.spec.ts             # NEW
└── reports.spec.ts                 # NEW
```

---

## Quick Wins Checklist (Do These First)

- [ ] **Create `hooks/api/__tests__/` folder**
- [ ] **Write `useMarkets.test.ts`** (template above)
- [ ] **Write `authStore.test.ts`** (template above)
- [ ] **Write `ProtectedRoute.test.tsx`** (template above)
- [ ] **Run coverage**: `npm run test:coverage`
- [ ] **Verify baseline**: Should jump from 5% to ~15% with just these

---

## MSW Mock Handlers (Create Once, Reuse)

Create a shared mock handlers file:

```typescript
// src/test/handlers.ts
import { http, HttpResponse } from 'msw';

export const handlers = [
  // Markets
  http.get('/api/v1/markets', () => {
    return HttpResponse.json([
      { id: 1, name: 'Milwaukee', code: 'MKE' },
      { id: 2, name: 'Chicago', code: 'CHI' },
    ]);
  }),

  // Theaters
  http.get('/api/v1/theaters', () => {
    return HttpResponse.json([
      { id: 1, name: 'Marcus Majestic', marketId: 1 },
    ]);
  }),

  // Auth
  http.post('/api/v1/auth/login', async ({ request }) => {
    const body = await request.json();
    if (body.email === 'test@test.com') {
      return HttpResponse.json({
        access_token: 'mock-token',
        refresh_token: 'mock-refresh',
      });
    }
    return HttpResponse.json({ error: 'Invalid credentials' }, { status: 401 });
  }),

  // Add more as needed...
];
```

```typescript
// src/test/setup.ts (update)
import '@testing-library/jest-dom';
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

---

## Definition of Done

### Beta+ Certification Requirements

- [ ] **Test coverage ≥70%** (verified via `npm run test:coverage`)
- [ ] **All tests passing** (`npm run test` exits 0)
- [ ] **E2E tests for critical flows** (auth, core features)
- [ ] **No skipped tests** (remove `.skip` before submission)
- [ ] **Coverage report included** in PR

### Bonus Points (75%+ coverage)

- [ ] Unit tests for all 19 API hooks
- [ ] Integration tests for auth flow
- [ ] E2E tests for admin features
- [ ] Test documentation in `docs/testing.md`

---

## Commands Reference

```bash
# Run all tests
npm run test

# Run with UI
npm run test:ui

# Run with coverage
npm run test:coverage

# Run specific file
npm run test -- useMarkets.test.ts

# Run E2E tests
npm run test:e2e

# Run E2E with UI (debugging)
npm run test:e2e:ui

# Run E2E headed (see browser)
npm run test:e2e:headed
```

---

## Need Help?

- **Vitest docs**: https://vitest.dev/
- **Testing Library**: https://testing-library.com/docs/react-testing-library/intro
- **MSW docs**: https://mswjs.io/docs/
- **Playwright docs**: https://playwright.dev/docs/intro

---

**Estimated Total Effort**: 8-10 focused days to reach 70%+ coverage

**You've got this!** The hardest part (architecture) is already done. Testing is just documenting what already works.
