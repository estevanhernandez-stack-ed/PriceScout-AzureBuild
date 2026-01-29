# React Tech Stack Decisions

**Project:** PriceScout React Migration
**Date:** 2026-01-07
**Status:** Pending Decisions

---

## Overview

This document outlines technology choices for the PriceScout React frontend migration. Each section presents options with pros/cons to facilitate decision-making.

---

## 1. State Management

### Option A: TanStack Query + Zustand (Recommended)

**TanStack Query** for server state (API data), **Zustand** for client state (UI, filters, user preferences).

| Pros | Cons |
|------|------|
| Automatic caching, refetching, and background updates | Two libraries to learn |
| Built-in loading/error states | Zustand is less opinionated |
| Optimistic updates out of the box | |
| Minimal boilerplate | |
| Perfect fit for API-heavy apps like PriceScout | |
| DevTools for both libraries | |

**Use Cases:**
- TanStack Query: Price checks, alerts, scrape jobs, theater data
- Zustand: Current user, selected filters, UI state, theme

```typescript
// Example: TanStack Query for price alerts
const { data, isLoading, error } = useQuery({
  queryKey: ['price-alerts', { acknowledged: false }],
  queryFn: () => api.get('/price-alerts?acknowledged=false'),
  staleTime: 30_000, // 30 seconds
});

// Example: Zustand for UI state
const useFilterStore = create((set) => ({
  selectedMarket: null,
  dateRange: { from: null, to: null },
  setMarket: (market) => set({ selectedMarket: market }),
}));
```

---

### Option B: Redux Toolkit + RTK Query

Full Redux ecosystem with integrated data fetching.

| Pros | Cons |
|------|------|
| Single source of truth | More boilerplate than alternatives |
| Predictable state updates | Steeper learning curve |
| Excellent DevTools | Can be overkill for simpler apps |
| Large ecosystem and community | |
| RTK Query handles caching well | |

**Use Cases:**
- Complex state interdependencies
- Need for middleware (logging, persistence)
- Team already familiar with Redux

---

### Option C: TanStack Query + React Context

Minimal approach using built-in React features for client state.

| Pros | Cons |
|------|------|
| No additional client state library | Context can cause unnecessary re-renders |
| Simple mental model | Manual optimization needed |
| Smaller bundle size | Less structured for complex state |

**Use Cases:**
- Smaller apps with limited client state
- Team prefers minimal dependencies

---

### Recommendation: **Option A (TanStack Query + Zustand)**

**Rationale:**
- PriceScout is heavily API-driven (58 endpoints)
- TanStack Query's caching is perfect for price data that updates frequently
- Zustand is tiny (~1KB) and simple for UI state
- Both have excellent TypeScript support
- Matches modern React patterns

---

## 2. CSS Framework / UI Components

### Option A: shadcn/ui + Tailwind CSS (Recommended)

Copy-paste component library built on Radix UI primitives with Tailwind styling.

| Pros | Cons |
|------|------|
| Full control - components live in your codebase | More initial setup |
| Highly customizable | Need to build some components yourself |
| Accessible (Radix primitives) | Less "batteries included" |
| No vendor lock-in | |
| Excellent for data-heavy UIs | |
| Great dark mode support | |
| Active development and community | |

**Included Components:**
- Tables (with sorting, filtering)
- Forms (with validation)
- Dialogs, Dropdowns, Tooltips
- Charts (via Recharts integration)
- Date pickers

---

### Option B: Material UI (MUI)

Comprehensive component library following Material Design.

| Pros | Cons |
|------|------|
| Complete component set | Larger bundle size |
| Data Grid component is excellent | Harder to customize away from Material Design |
| Well-documented | Can look "generic" |
| Enterprise support available | |

**Best For:**
- Teams wanting complete solution
- Apps that fit Material Design aesthetic

---

### Option C: Chakra UI

Accessible component library with good defaults.

| Pros | Cons |
|------|------|
| Great accessibility | Smaller ecosystem than MUI |
| Clean API | Less advanced data components |
| Good theming system | |
| Reasonable bundle size | |

---

### Option D: Ant Design

Enterprise-focused component library.

| Pros | Cons |
|------|------|
| Excellent data tables | Very opinionated styling |
| Complete component set | Large bundle size |
| Enterprise features (Pro components) | Customization can be difficult |

---

### Recommendation: **Option A (shadcn/ui + Tailwind)**

**Rationale:**
- PriceScout needs heavy customization for theater industry
- Data tables are critical - shadcn's table + TanStack Table is powerful
- Tailwind enables rapid styling iteration
- Components are owned by us, not a dependency
- Easy to match existing Streamlit styling if needed

---

## 3. Data Tables

### Option A: TanStack Table + shadcn/ui (Recommended)

Headless table library with custom UI.

| Pros | Cons |
|------|------|
| Full control over rendering | More setup required |
| Excellent sorting, filtering, pagination | Need to build UI yourself |
| Virtual scrolling support | |
| TypeScript-first | |
| Works with any UI library | |

---

### Option B: AG Grid (Community or Enterprise)

Professional data grid solution.

| Pros | Cons |
|------|------|
| Feature-rich out of the box | Enterprise features require license |
| Excel-like functionality | Can be heavy |
| Built-in export to Excel | Styling can be challenging |

---

### Option C: MUI DataGrid

Material UI's data grid component.

| Pros | Cons |
|------|------|
| Good MUI integration | Pro features require license |
| Decent feature set | Tied to MUI ecosystem |

---

### Recommendation: **Option A (TanStack Table)**

**Rationale:**
- Free and highly flexible
- Perfect for our custom price comparison tables
- Integrates well with shadcn/ui
- Virtual scrolling for large datasets (scrape results)

---

## 4. Charts & Visualization

### Option A: Recharts (Recommended)

React-specific charting library built on D3.

| Pros | Cons |
|------|------|
| React-native API | Less powerful than raw D3 |
| Good defaults | Limited chart types |
| Responsive | |
| shadcn/ui has Recharts integration | |

---

### Option B: Chart.js + react-chartjs-2

Popular charting library with React wrapper.

| Pros | Cons |
|------|------|
| Wide variety of charts | Not React-native |
| Good animation | Canvas-based (less flexible) |
| Large community | |

---

### Option C: Nivo

D3-based React charts with great defaults.

| Pros | Cons |
|------|------|
| Beautiful defaults | Larger bundle |
| Many chart types | Less customizable |
| Server-side rendering support | |

---

### Recommendation: **Option A (Recharts)**

**Rationale:**
- Simple API for common charts (line, bar, area)
- Good for price trend visualization
- shadcn/ui provides styled chart components
- Lightweight

---

## 5. Form Handling

### Option A: React Hook Form + Zod (Recommended)

Performant form library with schema validation.

| Pros | Cons |
|------|------|
| Minimal re-renders | Learning curve for Zod |
| Excellent TypeScript support | |
| Zod schemas can be shared with backend | |
| Small bundle size | |
| Great DevTools | |

```typescript
// Example: Login form with validation
const loginSchema = z.object({
  username: z.string().min(3, 'Username must be at least 3 characters'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
});

const { register, handleSubmit, formState: { errors } } = useForm({
  resolver: zodResolver(loginSchema),
});
```

---

### Option B: Formik + Yup

Established form solution.

| Pros | Cons |
|------|------|
| Well-documented | More re-renders |
| Large community | Larger bundle |
| Familiar to many devs | |

---

### Recommendation: **Option A (React Hook Form + Zod)**

**Rationale:**
- Best performance
- Zod types can match our TypeScript interfaces
- shadcn/ui forms are built on React Hook Form

---

## 6. Routing

### Option A: React Router v6 (Recommended)

Standard React routing library.

| Pros | Cons |
|------|------|
| Industry standard | Data loading patterns less elegant |
| Well-documented | |
| Nested routes | |
| Protected route patterns established | |

---

### Option B: TanStack Router

Type-safe router with data loading.

| Pros | Cons |
|------|------|
| Excellent TypeScript support | Newer, smaller community |
| Built-in data loading | Learning curve |
| File-based routing option | |

---

### Recommendation: **Option A (React Router v6)**

**Rationale:**
- Mature and stable
- Team familiarity
- Simple protected route implementation
- Good enough for our needs

---

## 7. HTTP Client

### Option A: Axios (Recommended)

Popular HTTP client with interceptors.

| Pros | Cons |
|------|------|
| Request/response interceptors | Additional dependency |
| Automatic JSON parsing | |
| Request cancellation | |
| Good TypeScript support | |

```typescript
// Example: Axios instance with auth
const api = axios.create({
  baseURL: '/api/v1',
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

---

### Option B: Native Fetch + Wrapper

Use browser fetch with custom wrapper.

| Pros | Cons |
|------|------|
| No dependency | More manual setup |
| Modern browsers support it | No interceptors built-in |

---

### Recommendation: **Option A (Axios)**

**Rationale:**
- Interceptors perfect for auth token injection
- Easy error handling
- Works well with TanStack Query

---

## 8. Testing

### Recommendation: Vitest + React Testing Library + Playwright

| Tool | Purpose |
|------|---------|
| **Vitest** | Unit tests (fast, Vite-native) |
| **React Testing Library** | Component tests |
| **Playwright** | E2E tests |
| **MSW** | API mocking |

---

## Summary: Recommended Stack

| Category | Choice |
|----------|--------|
| **Build Tool** | Vite |
| **State (Server)** | TanStack Query |
| **State (Client)** | Zustand |
| **UI Components** | shadcn/ui |
| **Styling** | Tailwind CSS |
| **Data Tables** | TanStack Table |
| **Charts** | Recharts |
| **Forms** | React Hook Form + Zod |
| **Routing** | React Router v6 |
| **HTTP Client** | Axios |
| **Testing** | Vitest + RTL + Playwright |

---

## Package Estimates

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.x",
    "@tanstack/react-query": "^5.x",
    "@tanstack/react-table": "^8.x",
    "zustand": "^4.x",
    "axios": "^1.x",
    "react-hook-form": "^7.x",
    "zod": "^3.x",
    "@hookform/resolvers": "^3.x",
    "recharts": "^2.x",
    "date-fns": "^3.x",
    "clsx": "^2.x",
    "tailwind-merge": "^2.x"
  },
  "devDependencies": {
    "vite": "^5.x",
    "typescript": "^5.x",
    "tailwindcss": "^3.x",
    "vitest": "^1.x",
    "@testing-library/react": "^14.x",
    "playwright": "^1.x",
    "msw": "^2.x"
  }
}
```

---

## Decision Log

| Date | Decision | Rationale | Decided By |
|------|----------|-----------|------------|
| | | | |

---

## Next Steps

1. [ ] Review and approve tech stack choices
2. [ ] Initialize Vite project with TypeScript
3. [ ] Set up Tailwind CSS + shadcn/ui
4. [ ] Configure TanStack Query
5. [ ] Implement authentication flow
6. [ ] Build first page (Dashboard or Login)
