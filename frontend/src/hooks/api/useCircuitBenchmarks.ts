import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryClient';

// ============================================================================
// Types
// ============================================================================

export interface CircuitBenchmark {
  benchmark_id: number;
  circuit_name: string;
  week_ending_date: string;
  period_start_date?: string;
  total_showtimes: number;
  total_capacity: number;
  total_theaters: number;
  total_films: number;
  avg_screens_per_film: number;
  avg_showtimes_per_theater: number;
  format_standard_pct: number;
  format_imax_pct: number;
  format_dolby_pct: number;
  format_3d_pct: number;
  format_other_premium_pct: number;
  plf_total_pct: number;
  daypart_matinee_pct: number;
  daypart_evening_pct: number;
  daypart_late_pct: number;
  avg_price_general?: number;
  avg_price_child?: number;
  avg_price_senior?: number;
  data_source: string;
  created_at?: string;
}

export interface CircuitBenchmarkList {
  benchmarks: CircuitBenchmark[];
  total_count: number;
  available_weeks: string[];
}

export interface WeekSummary {
  week_ending_date: string;
  period_start_date: string;
  circuit_count: number;
  total_showtimes: number;
  data_freshness: string;
}

export interface CircuitBenchmarkFilters {
  week_ending_date?: string;
  circuit_name?: string;
  limit?: number;
  offset?: number;
}

export interface CircuitComparison {
  week_ending_date: string;
  circuits: Record<string, CircuitBenchmark>;
  metrics_comparison: {
    total_showtimes: Record<string, number>;
    plf_total_pct: Record<string, number>;
    avg_showtimes_per_theater: Record<string, number>;
  };
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * Fetch circuit benchmarks with optional filtering
 */
export function useCircuitBenchmarks(filters: CircuitBenchmarkFilters = {}) {
  return useQuery({
    queryKey: queryKeys.circuitBenchmarks.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.week_ending_date) params.append('week_ending_date', filters.week_ending_date);
      if (filters.circuit_name) params.append('circuit_name', filters.circuit_name);
      if (filters.limit) params.append('limit', String(filters.limit));
      if (filters.offset) params.append('offset', String(filters.offset));

      const response = await api.get<CircuitBenchmarkList>(
        `/circuit-benchmarks?${params.toString()}`
      );
      return response.data;
    },
  });
}

/**
 * Fetch available weeks with summary statistics
 */
export function useCircuitBenchmarkWeeks() {
  return useQuery({
    queryKey: queryKeys.circuitBenchmarks.weeks(),
    queryFn: async () => {
      const response = await api.get<WeekSummary[]>('/circuit-benchmarks/weeks');
      return response.data;
    },
  });
}

/**
 * Fetch benchmarks for a specific week
 */
export function useWeekBenchmarks(weekEndingDate: string) {
  return useQuery({
    queryKey: ['circuitBenchmarks', 'week', weekEndingDate],
    queryFn: async () => {
      const response = await api.get<{
        week_ending_date: string;
        circuit_count: number;
        total_showtimes: number;
        total_theaters: number;
        benchmarks: CircuitBenchmark[];
      }>(`/circuit-benchmarks/${weekEndingDate}`);
      return response.data;
    },
    enabled: !!weekEndingDate,
  });
}

/**
 * Compare multiple circuits
 */
export function useCircuitComparison(
  circuits: string[],
  weekEndingDate?: string
) {
  return useQuery({
    queryKey: ['circuitBenchmarks', 'compare', circuits.join(','), weekEndingDate],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('circuits', circuits.join(','));
      if (weekEndingDate) params.append('week_ending_date', weekEndingDate);

      const response = await api.get<CircuitComparison>(
        `/circuit-benchmarks/compare?${params.toString()}`
      );
      return response.data;
    },
    enabled: circuits.length >= 2,
  });
}

/**
 * Trigger EntTelligence sync for circuit benchmarks
 */
export function useSyncCircuitBenchmarks() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<{
        status: string;
        message: string;
        last_sync?: string;
        records_synced: number;
        task_id?: string;
      }>('/circuit-benchmarks/sync');
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.circuitBenchmarks.all });
    },
  });
}
