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
  current_tickets: number;
  current_revenue: number;
  days_until_release: number;
  latest_snapshot: string;
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

export interface PresaleFilters {
  film_title?: string;
  circuit_name?: string;
  snapshot_date?: string;
  days_before_release?: number;
  limit?: number;
  offset?: number;
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * Fetch presale snapshots with optional filtering
 */
export function usePresales(filters: PresaleFilters = {}) {
  return useQuery({
    queryKey: queryKeys.presales.list(filters),
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

      const response = await api.get<PresaleSnapshot[]>(
        `/presales?${params.toString()}`
      );
      return response.data;
    },
  });
}

/**
 * Fetch all films with presale data
 */
export function usePresaleFilms() {
  return useQuery({
    queryKey: ['presales', 'films'],
    queryFn: async () => {
      const response = await api.get<PresaleFilm[]>('/presales/films');
      return response.data;
    },
  });
}

/**
 * Fetch presale trajectory for a specific film
 */
export function usePresaleTrajectory(filmTitle: string, circuitName?: string) {
  return useQuery({
    queryKey: queryKeys.presales.trajectory(filmTitle, circuitName || 'all'),
    queryFn: async () => {
      const params = circuitName
        ? `?circuit_name=${encodeURIComponent(circuitName)}`
        : '';
      const response = await api.get<PresaleTrajectory>(
        `/presales/${encodeURIComponent(filmTitle)}${params}`
      );
      return response.data;
    },
    enabled: !!filmTitle,
  });
}

/**
 * Fetch velocity metrics for a film
 */
export function usePresaleVelocity(filmTitle: string) {
  return useQuery({
    queryKey: queryKeys.presales.velocity({ filmTitle }),
    queryFn: async () => {
      const response = await api.get<VelocityMetrics[]>(
        `/presales/velocity/${encodeURIComponent(filmTitle)}`
      );
      return response.data;
    },
    enabled: !!filmTitle,
  });
}

/**
 * Compare presales across circuits for a film
 */
export function usePresaleComparison(filmTitle: string, circuits?: string[]) {
  return useQuery({
    queryKey: ['presales', 'compare', filmTitle, circuits?.join(',')],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('film_title', filmTitle);
      if (circuits && circuits.length > 0) {
        params.append('circuits', circuits.join(','));
      }

      const response = await api.get<CircuitPresaleComparison>(
        `/presales/compare?${params.toString()}`
      );
      return response.data;
    },
    enabled: !!filmTitle,
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
