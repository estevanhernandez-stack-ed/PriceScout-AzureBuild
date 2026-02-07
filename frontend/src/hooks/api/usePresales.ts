import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryClient';

// ============================================================================
// Types
// ============================================================================

export interface PresaleSnapshot {
  id: number;
  circuit_name: string;
  film_title: string;
  release_date: string;
  snapshot_date: string;
  days_before_release: number;
  total_tickets_sold: number;
  total_revenue: number;
  total_showtimes: number;
  total_theaters: number;
  avg_tickets_per_show: number;
  avg_tickets_per_theater: number;
  avg_ticket_price: number;
  tickets_imax: number;
  tickets_dolby: number;
  tickets_3d: number;
  tickets_premium: number;
  tickets_standard: number;
  data_source: string;
}

export interface PresaleTrajectory {
  film_title: string;
  release_date: string;
  circuit_name: string;
  snapshots: PresaleSnapshot[];
  current_tickets: number;
  current_revenue: number;
  velocity_trend: 'accelerating' | 'steady' | 'decelerating' | 'insufficient_data';
  days_until_release: number;
}

export interface PresaleFilm {
  film_title: string;
  release_date: string;
  total_circuits: number;
  circuit_name: string | null; // populated for single-circuit films or when filtered by circuit
  current_tickets: number;
  current_revenue: number;
  days_until_release: number;
  latest_snapshot: string;
}

export interface PresaleCircuit {
  circuit_name: string;
  total_films: number;
  total_tickets: number;
  total_revenue: number;
  snapshot_count: number;
}

export interface VelocityMetrics {
  film_title: string;
  circuit_name: string;
  snapshot_date: string;
  daily_tickets: number;
  daily_revenue: number;
  velocity_change: number;
  trend: 'accelerating' | 'steady' | 'decelerating';
}

export interface CircuitPresaleComparison {
  film_title: string;
  total_circuits: number;
  total_tickets: number;
  circuits: {
    circuit_name: string;
    total_tickets: number;
    total_revenue: number;
    theaters: number;
    avg_ticket_price: number;
    days_until_release: number;
    market_share_pct: number;
  }[];
}

export type MarketScope = 'our_markets' | 'full';

export interface PresaleFilters {
  film_title?: string;
  circuit_name?: string;
  snapshot_date?: string;
  days_before_release?: number;
  limit?: number;
  offset?: number;
  market_scope?: MarketScope;
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * Fetch presale snapshots with optional filtering
 */
export function usePresales(filters: PresaleFilters = {}) {
  const scope = filters.market_scope || 'our_markets';
  return useQuery({
    queryKey: [...queryKeys.presales.list(filters), scope],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.film_title) params.append('film_title', filters.film_title);
      if (filters.circuit_name) params.append('circuit_name', filters.circuit_name);
      if (filters.snapshot_date) params.append('snapshot_date', filters.snapshot_date);
      if (filters.days_before_release !== undefined) {
        params.append('days_before_release', String(filters.days_before_release));
      }
      if (filters.limit) params.append('limit', String(filters.limit));
      if (filters.offset) params.append('offset', String(filters.offset));
      params.append('market_scope', scope);

      const response = await api.get<PresaleSnapshot[]>(
        `/presales?${params.toString()}`
      );
      return response.data;
    },
  });
}

/**
 * Fetch all films with presale data.
 * Optionally filter by circuit_name to see a specific circuit's films.
 */
export function usePresaleFilms(circuitFilter?: string, marketScope: MarketScope = 'our_markets') {
  return useQuery({
    queryKey: ['presales', 'films', circuitFilter || '__all__', marketScope],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (circuitFilter) params.append('circuit_name', circuitFilter);
      params.append('market_scope', marketScope);
      const response = await api.get<PresaleFilm[]>(`/presales/films?${params.toString()}`);
      return response.data;
    },
  });
}

/**
 * Fetch all circuits with presale data and aggregate stats.
 */
export function usePresaleCircuits(marketScope: MarketScope = 'our_markets') {
  return useQuery({
    queryKey: ['presales', 'circuits', marketScope],
    queryFn: async () => {
      const response = await api.get<PresaleCircuit[]>(
        `/presales/circuits?market_scope=${marketScope}`
      );
      return response.data;
    },
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Fetch presale trajectory for a specific film
 */
export function usePresaleTrajectory(filmTitle: string, circuitName?: string, marketScope: MarketScope = 'our_markets') {
  return useQuery({
    queryKey: [...queryKeys.presales.trajectory(filmTitle, circuitName || 'all'), marketScope],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (circuitName) params.append('circuit_name', circuitName);
      params.append('market_scope', marketScope);
      const response = await api.get<PresaleTrajectory>(
        `/presales/${encodeURIComponent(filmTitle)}?${params.toString()}`
      );
      return response.data;
    },
    enabled: !!filmTitle,
  });
}

/**
 * Fetch velocity metrics for a film
 */
export function usePresaleVelocity(filmTitle: string, marketScope: MarketScope = 'our_markets') {
  return useQuery({
    queryKey: [...queryKeys.presales.velocity({ filmTitle }), marketScope],
    queryFn: async () => {
      const response = await api.get<VelocityMetrics[]>(
        `/presales/velocity/${encodeURIComponent(filmTitle)}?market_scope=${marketScope}`
      );
      return response.data;
    },
    enabled: !!filmTitle,
  });
}

/**
 * Compare presales across circuits for a film
 */
export function usePresaleComparison(filmTitle: string, circuits?: string[], marketScope: MarketScope = 'our_markets') {
  return useQuery({
    queryKey: ['presales', 'compare', filmTitle, circuits?.join(','), marketScope],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('film_title', filmTitle);
      if (circuits && circuits.length > 0) {
        params.append('circuits', circuits.join(','));
      }
      params.append('market_scope', marketScope);

      const response = await api.get<CircuitPresaleComparison>(
        `/presales/compare?${params.toString()}`
      );
      return response.data;
    },
    enabled: !!filmTitle,
  });
}

// ============================================================================
// Compliance Types & Hook
// ============================================================================

export interface CircuitComplianceInfo {
  days_posted_ahead: number;
  total_showtimes: number;
  total_theaters: number;
  earliest_showtime_date: string | null;
}

export interface FilmComplianceData {
  film_title: string;
  release_date: string;
  days_until_release: number;
  circuits: Record<string, CircuitComplianceInfo>;
  circuit_ranking: [string, number][];
  marcus_rank: number | null;
  marcus_days_ahead: number | null;
  avg_days_ahead: number;
  marcus_delta: number | null;
  total_circuits: number;
}

export interface ComplianceResponse {
  snapshot_date: string;
  total_films: number;
  films: FilmComplianceData[];
}

/**
 * Fetch presale posting compliance data.
 * Compares how far in advance each circuit posts showtimes for upcoming films.
 */
export function usePresaleCompliance(marketScope: MarketScope = 'our_markets') {
  return useQuery({
    queryKey: ['presales', 'compliance', marketScope],
    queryFn: async () => {
      const response = await api.get<ComplianceResponse>(
        `/presales/compliance?market_scope=${marketScope}`
      );
      return response.data;
    },
    staleTime: 5 * 60 * 1000,
  });
}

// ============================================================================
// Heatmap Types & Hook
// ============================================================================

export interface PresaleHeatmapTheater {
  theater_name: string;
  circuit_name: string | null;
  market: string | null;
  latitude: number;
  longitude: number;
  total_showtimes: number;
  total_capacity: number;
  total_available: number;
  total_tickets_sold: number;
  fill_rate_pct: number;
  avg_price: number | null;
  films_count: number;
  is_marcus: boolean;
}

export interface PresaleHeatmapResponse {
  total_theaters: number;
  theaters_with_data: number;
  film_filter: string | null;
  theaters: PresaleHeatmapTheater[];
}

/**
 * Fetch presale heatmap data with per-theater geographic coordinates.
 * Returns theaters with lat/lon, presale metrics (showtimes, capacity, tickets sold, fill rate).
 *
 * Without filmTitle: aggregate presale activity across all films
 * With filmTitle: presale data for a specific film
 */
export function usePresaleHeatmapData(options?: {
  filmTitle?: string;
  circuit?: string;
  enabled?: boolean;
  marketScope?: MarketScope;
}) {
  const scope = options?.marketScope || 'our_markets';
  const params = new URLSearchParams();
  if (options?.filmTitle) params.append('film_title', options.filmTitle);
  if (options?.circuit) params.append('circuit', options.circuit);
  params.append('market_scope', scope);

  return useQuery({
    queryKey: ['presales', 'heatmap', options?.filmTitle, options?.circuit, scope],
    queryFn: async () => {
      const response = await api.get<PresaleHeatmapResponse>(
        `/presales/heatmap-data?${params.toString()}`
      );
      return response.data;
    },
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Trigger EntTelligence sync for presale data
 */
export function useSyncPresales() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<{
        status: string;
        message: string;
        task_id?: string;
      }>('/presales/sync');
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.presales.all });
    },
  });
}
