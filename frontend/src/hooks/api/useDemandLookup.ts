import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ============================================================================
// Types
// ============================================================================

export interface DemandMetric {
  theater_name: string;
  film_title: string;
  play_date: string;
  showtime: string;
  format: string | null;
  circuit_name: string | null;
  ticket_type: string;
  price: number;
  capacity: number;
  available: number;
  tickets_sold: number;
  fill_rate_pct: number;
}

export interface DemandSummary {
  totalShowtimes: number;
  showtimesWithSales: number;
  avgFillRate: number;
  highDemandCount: number; // > 70% fill rate
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Build a lookup key for matching demand data to scrape results.
 * Matches on theater + film + showtime (date is implicit from the query).
 */
export function demandKey(theaterName: string, filmTitle: string, showtime: string): string {
  return `${theaterName}|${filmTitle}|${showtime}`;
}

/**
 * Get fill rate color based on thresholds.
 * Green < 50%, Yellow 50-75%, Red > 75%
 */
export function getFillRateColor(fillRate: number): string {
  if (fillRate >= 75) return 'text-red-400';
  if (fillRate >= 50) return 'text-yellow-400';
  return 'text-green-400';
}

/**
 * Get fill rate badge variant for shadcn Badge component.
 */
export function getFillRateBadgeVariant(fillRate: number): 'destructive' | 'default' | 'secondary' {
  if (fillRate >= 75) return 'destructive';
  if (fillRate >= 50) return 'default';
  return 'secondary';
}

/**
 * Compute summary statistics from demand metrics.
 */
export function computeDemandSummary(metrics: DemandMetric[]): DemandSummary {
  const withSales = metrics.filter(m => m.tickets_sold > 0);
  const avgFill = metrics.length > 0
    ? metrics.reduce((sum, m) => sum + m.fill_rate_pct, 0) / metrics.length
    : 0;
  return {
    totalShowtimes: metrics.length,
    showtimesWithSales: withSales.length,
    avgFillRate: Math.round(avgFill * 10) / 10,
    highDemandCount: metrics.filter(m => m.fill_rate_pct >= 70).length,
  };
}

/**
 * Build a Map for O(1) lookup of demand data by theater|film|showtime key.
 */
export function buildDemandMap(metrics: DemandMetric[]): Map<string, DemandMetric> {
  const map = new Map<string, DemandMetric>();
  for (const m of metrics) {
    map.set(demandKey(m.theater_name, m.film_title, m.showtime), m);
  }
  return map;
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Fetch per-showtime demand data from EntTelligence cache.
 *
 * Used by:
 * - Market Mode: overlay competitor sales data on scrape results
 * - Daily Lineup: show presale fill rates for a theater's daily schedule
 *
 * @param theaters - List of theater names to look up
 * @param dateFrom - Start date (YYYY-MM-DD)
 * @param dateTo - End date (YYYY-MM-DD), defaults to dateFrom
 * @param films - Optional list of film titles to filter
 * @param enabled - Whether the query should run
 */
export function useDemandLookup(
  theaters: string[],
  dateFrom: string,
  dateTo?: string,
  films?: string[],
  enabled: boolean = true,
) {
  return useQuery({
    queryKey: ['presales', 'demand-lookup', theaters.join(','), dateFrom, dateTo || dateFrom, films?.join(',') || ''],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('theaters', theaters.join(','));
      params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);
      if (films && films.length > 0) params.append('films', films.join(','));

      const response = await api.get<DemandMetric[]>(
        `/presales/demand-lookup?${params.toString()}`
      );
      return response.data;
    },
    enabled: enabled && theaters.length > 0 && !!dateFrom,
    staleTime: 5 * 60 * 1000, // 5 min — data updates daily
  });
}
