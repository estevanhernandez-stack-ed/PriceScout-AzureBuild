import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ============================================================================
// DASHBOARD TYPES & HOOKS
// ============================================================================

export interface DashboardStats {
  total_price_checks: number;
  price_checks_change_pct: number;
  active_alerts: number;
  alerts_change: number;
  avg_price: number;
  price_change_pct: number;
  total_theaters: number;
  total_films: number;
}

export interface ScrapeActivityEntry {
  day_name: string;
  day_index: number;
  scrape_count: number;
  records_scraped: number;
}

/**
 * Fetch dashboard overview statistics
 */
export function useDashboardStats(days: number = 30) {
  return useQuery({
    queryKey: ['dashboard', 'stats', days],
    queryFn: async () => {
      const response = await api.get<DashboardStats>(
        `/analytics/dashboard-stats?days=${days}`
      );
      return response.data;
    },
    staleTime: 60 * 1000, // 1 minute
    refetchInterval: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch scrape activity by day of week
 */
export function useScrapeActivity(days: number = 30) {
  return useQuery({
    queryKey: ['dashboard', 'scrape-activity', days],
    queryFn: async () => {
      const response = await api.get<ScrapeActivityEntry[]>(
        `/analytics/scrape-activity?days=${days}`
      );
      return response.data;
    },
    staleTime: 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

