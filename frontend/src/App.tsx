import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { Toaster } from '@/components/ui/toaster';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { useTokenRefresh } from '@/hooks/useTokenRefresh';
import { queryClient } from '@/lib/queryClient';

// Layouts
import { MainLayout } from '@/components/layout/MainLayout';
import { AuthLayout } from '@/components/layout/AuthLayout';

// Pages
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { MarketModePage } from '@/pages/MarketModePage';
import { OperatingHoursPage } from '@/pages/OperatingHoursPage';
import { CompSnipeModePage } from '@/pages/CompSnipeModePage';
import { DailyLineupPage } from '@/pages/DailyLineupPage';
import { CircuitBenchmarksPage } from '@/pages/CircuitBenchmarksPage';
import { PresaleTrackingPage } from '@/pages/PresaleTrackingPage';
import { HistoricalDataPage } from '@/pages/HistoricalDataPage';
import { PosterBoardPage } from '@/pages/PosterBoardPage';
import { PriceAlertsPage } from '@/pages/PriceAlertsPage';
import { PriceChecksPage } from '@/pages/PriceChecksPage';
import { ScrapesPage } from '@/pages/ScrapesPage';
import { ReportsPage } from '@/pages/ReportsPage';
import { DataManagementPage } from '@/pages/DataManagementPage';
import { TheaterMatchingPage } from '@/pages/TheaterMatchingPage';
import { AdminUsersPage } from '@/pages/admin/UsersPage';
import { AuditLogPage } from '@/pages/admin/AuditLogPage';
import { SystemHealthPage } from '@/pages/SystemHealthPage';
import { ScheduleAlertsPage } from '@/pages/ScheduleAlertsPage';
import { RepairQueuePage } from '@/pages/RepairQueuePage';
import { ExportCenterPage } from '@/pages/ExportCenterPage';
import { BaselinesPage } from '@/pages/BaselinesPage';
import { HeatmapPage } from '@/pages/HeatmapPage';
import { NotFoundPage } from '@/pages/NotFoundPage';

function AppRoutes() {
  // Set up automatic token refresh
  useTokenRefresh();

  return (
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
        <Route path="/historical-data" element={<HistoricalDataPage />} />
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
      </Route>

      {/* Redirects and fallbacks */}
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppRoutes />
        <Toaster />
      </BrowserRouter>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
