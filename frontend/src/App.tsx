import { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { Toaster } from '@/components/ui/toaster';
import { BackgroundJobsPanel } from '@/components/scrapes/BackgroundJobsPanel';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { ErrorBoundary } from '@/components/error/ErrorBoundary';
import { useTokenRefresh } from '@/hooks/useTokenRefresh';
import { queryClient } from '@/lib/queryClient';

// Layouts
import { MainLayout } from '@/components/layout/MainLayout';
import { AuthLayout } from '@/components/layout/AuthLayout';

// Pages
const LoginPage = lazy(() => import('@/pages/auth/LoginPage').then(m => ({ default: m.LoginPage })));
const DashboardPage = lazy(() => import('@/pages/DashboardPage').then(m => ({ default: m.DashboardPage })));
const MarketModePage = lazy(() => import('@/pages/MarketModePage').then(m => ({ default: m.MarketModePage })));
const OperatingHoursPage = lazy(() => import('@/pages/OperatingHoursPage').then(m => ({ default: m.OperatingHoursPage })));
const CompSnipeModePage = lazy(() => import('@/pages/CompSnipeModePage').then(m => ({ default: m.CompSnipeModePage })));
const DailyLineupPage = lazy(() => import('@/pages/DailyLineupPage').then(m => ({ default: m.DailyLineupPage })));
const CircuitBenchmarksPage = lazy(() => import('@/pages/CircuitBenchmarksPage').then(m => ({ default: m.CircuitBenchmarksPage })));
const PresaleTrackingPage = lazy(() => import('@/pages/PresaleTrackingPage').then(m => ({ default: m.PresaleTrackingPage })));
const PosterBoardPage = lazy(() => import('@/pages/PosterBoardPage').then(m => ({ default: m.PosterBoardPage })));
const PriceAlertsPage = lazy(() => import('@/pages/PriceAlertsPage').then(m => ({ default: m.PriceAlertsPage })));
const PriceChecksPage = lazy(() => import('@/pages/PriceChecksPage').then(m => ({ default: m.PriceChecksPage })));
const ScrapesPage = lazy(() => import('@/pages/ScrapesPage').then(m => ({ default: m.ScrapesPage })));
const ReportsPage = lazy(() => import('@/pages/ReportsPage').then(m => ({ default: m.ReportsPage })));
const DataManagementPage = lazy(() => import('@/pages/DataManagementPage').then(m => ({ default: m.DataManagementPage })));
const TheaterMatchingPage = lazy(() => import('@/pages/TheaterMatchingPage').then(m => ({ default: m.TheaterMatchingPage })));
const AdminUsersPage = lazy(() => import('@/pages/admin/UsersPage').then(m => ({ default: m.AdminUsersPage })));
const AuditLogPage = lazy(() => import('@/pages/admin/AuditLogPage').then(m => ({ default: m.AuditLogPage })));
const SystemHealthPage = lazy(() => import('@/pages/SystemHealthPage').then(m => ({ default: m.SystemHealthPage })));
const ScheduleAlertsPage = lazy(() => import('@/pages/ScheduleAlertsPage').then(m => ({ default: m.ScheduleAlertsPage })));
const RepairQueuePage = lazy(() => import('@/pages/RepairQueuePage').then(m => ({ default: m.RepairQueuePage })));
const ExportCenterPage = lazy(() => import('@/pages/ExportCenterPage').then(m => ({ default: m.ExportCenterPage })));
const BaselinesPage = lazy(() => import('@/pages/BaselinesPage').then(m => ({ default: m.BaselinesPage })));
const HeatmapPage = lazy(() => import('@/pages/HeatmapPage').then(m => ({ default: m.HeatmapPage })));
const SettingsPage = lazy(() => import('@/pages/SettingsPage').then(m => ({ default: m.SettingsPage })));
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage').then(m => ({ default: m.NotFoundPage })));

const PageLoader = () => <div className="flex h-screen items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div></div>;

function AppRoutes() {
  // Set up automatic token refresh
  useTokenRefresh();

  return (
    <Suspense fallback={<PageLoader />}>
    <Routes>
      {/* Auth routes */}
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
      </Route>

      {/* Protected routes */}
      <Route
        element={
          <ProtectedRoute>
            <MainLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />

        {/* Scraping Modes */}
        <Route path="/market-mode" element={<MarketModePage />} />
        <Route path="/operating-hours" element={<OperatingHoursPage />} />
        <Route path="/compsnipe" element={<CompSnipeModePage />} />
        <Route path="/daily-lineup" element={<DailyLineupPage />} />

        {/* Analytics */}
        <Route path="/circuit-benchmarks" element={<CircuitBenchmarksPage />} />
        <Route path="/presale-tracking" element={<PresaleTrackingPage />} />
        <Route path="/poster-board" element={<PosterBoardPage />} />
        <Route path="/export-center" element={<ExportCenterPage />} />
        <Route path="/analytics/heatmap" element={<HeatmapPage />} />

        {/* Data Views */}
        <Route path="/price-alerts" element={<PriceAlertsPage />} />
        <Route path="/baselines" element={<BaselinesPage />} />
        <Route path="/schedule-alerts" element={<ScheduleAlertsPage />} />
        <Route path="/price-checks" element={<PriceChecksPage />} />
        <Route path="/scrapes" element={<ScrapesPage />} />
        <Route path="/reports" element={<ReportsPage />} />

        {/* Admin routes */}
        <Route
          path="/admin/users"
          element={
            <ProtectedRoute requiredRole={['admin', 'auditor']}>
              <AdminUsersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/data-management"
          element={
            <ProtectedRoute requiredRole={['admin', 'operator']}>
              <DataManagementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/theater-matching"
          element={
            <ProtectedRoute requiredRole="admin">
              <TheaterMatchingPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/system-health"
          element={
            <ProtectedRoute requiredRole={['admin', 'operator', 'auditor']}>
              <SystemHealthPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/repair-queue"
          element={
            <ProtectedRoute requiredRole={['admin', 'operator']}>
              <RepairQueuePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/audit-log"
          element={
            <ProtectedRoute requiredRole={['admin', 'auditor']}>
              <AuditLogPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/settings"
          element={
            <ProtectedRoute requiredRole={['admin', 'operator']}>
              <SettingsPage />
            </ProtectedRoute>
          }
        />
      </Route>

      {/* Redirects and fallbacks */}
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
    </Suspense>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ErrorBoundary>
          <AppRoutes />
          <BackgroundJobsPanel />
          <Toaster />
        </ErrorBoundary>
      </BrowserRouter>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
