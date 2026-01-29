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

// ============================================================================
// ANALYTICS TYPES & HOOKS
// ============================================================================

export interface PLFDistributionEntry {
  theater_name: string;
  format_group: string;
  specific_format: string;
  avg_price: number;
  showing_count: number;
  pct_of_total: number;
}

export interface PriceTrendPoint {
  date: string;
  standard_avg?: number;
  plf_avg?: number;
  imax_avg?: number;
  dolby_avg?: number;
  showing_count: number;
}

/**
 * Fetch PLF distribution for a market or theater scope
 */
export function usePLFDistribution(filters: { market?: string; days?: number } = {}) {
  return useQuery({
    queryKey: ['analytics', 'plf-distribution', filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.market) params.append('market', filters.market);
      if (filters.days) params.append('days', String(filters.days));

      const response = await api.get<PLFDistributionEntry[]>(
        `/analytics/plf-distribution?${params.toString()}`
      );
      return response.data;
    },
  });
}

/**
 * Fetch price trends for a theater
 */
export function useAnalyticsPriceTrends(theaterName: string, days: number = 30) {
  return useQuery({
    queryKey: ['analytics', 'price-trends', theaterName, days],
    queryFn: async () => {
      const response = await api.get<PriceTrendPoint[]>(
        `/analytics/price-trends?theater_name=${encodeURIComponent(theaterName)}&days=${days}`
      );
      return response.data;
    },
    enabled: !!theaterName,
  });
}
