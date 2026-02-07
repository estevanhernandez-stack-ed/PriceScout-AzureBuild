/**
 * Coverage Gaps API Hooks
 *
 * Provides hooks for analyzing price data coverage gaps for theaters.
 * Helps identify what data is missing before relying on surge detection.
 */

import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

// =============================================================================
// TYPES
// =============================================================================

export interface GapInfo {
  gap_type: 'missing_day' | 'missing_format' | 'low_samples' | 'no_data';
  severity: 'warning' | 'error';
  description: string;
  details: Record<string, unknown>;
}

export interface BaselineInfo {
  format: string;
  ticket_type: string;
  day_of_week: number;
  day_name: string;
  sample_count: number;
  avg_price: number;
  variance_pct: number;
}

export interface CoverageReport {
  theater_name: string;
  circuit_name: string | null;

  // Data summary
  total_samples: number;
  unique_ticket_types: string[];
  unique_formats: string[];
  days_with_data: number[];
  date_range_start: string | null;
  date_range_end: string | null;

  // Gaps found
  gaps: GapInfo[];
  gap_count: number;

  // Coverage scores
  day_coverage_pct: number;
  format_coverage_pct: number;
  overall_coverage_score: number;

  // Healthy baselines
  healthy_baselines: BaselineInfo[];
  healthy_count: number;
}

export interface TheaterCoverageSummary {
  theater_name: string;
  circuit_name: string | null;
  total_samples: number;
  gap_count: number;
  healthy_count: number;
  coverage_score: number;
  day_coverage_pct: number;
  days_missing: string[];
  formats: string[];
  ticket_types: string[];
}

export interface CoverageListResponse {
  total: number;
  theaters: TheaterCoverageSummary[];
}

// Hierarchical types
export interface TheaterCoverageDetail {
  theater_name: string;
  total_samples: number;
  gap_count: number;
  healthy_count: number;
  coverage_score: number;
  day_coverage_pct: number;
  days_missing: string[];
  formats: string[];
  gaps?: Array<{ type: string; severity: string; description: string }>;
  error?: string;
}

export interface MarketCoverage {
  total_theaters: number;
  total_gaps: number;
  total_samples: number;
  avg_coverage_score: number;
  theaters_with_gaps: number;
  theaters: TheaterCoverageDetail[];
}

export interface DirectorCoverage {
  total_theaters: number;
  total_gaps: number;
  avg_coverage_score: number;
  markets: Record<string, MarketCoverage>;
}

export interface CompanyCoverage {
  total_theaters: number;
  total_gaps: number;
  avg_coverage_score: number;
  directors: Record<string, DirectorCoverage>;
}

export type CoverageHierarchy = Record<string, CompanyCoverage>;

export interface MarketCoverageDetail {
  market_name: string;
  director_name: string;
  company_name: string;
  total_theaters: number;
  total_gaps: number;
  total_samples: number;
  avg_coverage_score: number;
  theaters_with_gaps: number;
  theaters: TheaterCoverageDetail[];
}

// =============================================================================
// HOOKS
// =============================================================================

/**
 * Fetch coverage report for a specific theater
 */
export function useTheaterCoverage(theaterName: string | null, options?: { lookbackDays?: number }) {
  return useQuery({
    queryKey: ['coverageGaps', 'theater', theaterName, options?.lookbackDays],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (options?.lookbackDays) params.append('lookback_days', String(options.lookbackDays));

      const response = await api.get<CoverageReport>(
        `/baselines/coverage-gaps/${encodeURIComponent(theaterName ?? '')}?${params}`
      );
      return response.data;
    },
    enabled: !!theaterName,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch coverage summaries for all theaters
 */
export function useAllTheaterCoverage(options?: { lookbackDays?: number; minSamples?: number; circuit?: string }) {
  return useQuery({
    queryKey: ['coverageGaps', 'all', options],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (options?.lookbackDays) params.append('lookback_days', String(options.lookbackDays));
      if (options?.minSamples) params.append('min_samples', String(options.minSamples));
      if (options?.circuit) params.append('circuit', options.circuit);

      const response = await api.get<CoverageListResponse>(`/baselines/coverage-gaps?${params}`);
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch coverage hierarchy organized by director -> market -> theater
 */
export function useCoverageHierarchy(options?: { lookbackDays?: number }) {
  return useQuery({
    queryKey: ['coverageGaps', 'hierarchy', options?.lookbackDays],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (options?.lookbackDays) params.append('lookback_days', String(options.lookbackDays));

      const response = await api.get<CoverageHierarchy>(`/baselines/coverage-hierarchy?${params}`);
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch detailed coverage for a specific market
 */
export function useMarketCoverage(
  directorName: string | null,
  marketName: string | null,
  options?: { lookbackDays?: number }
) {
  return useQuery({
    queryKey: ['coverageGaps', 'market', directorName, marketName, options?.lookbackDays],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (options?.lookbackDays) params.append('lookback_days', String(options.lookbackDays));

      const response = await api.get<MarketCoverageDetail>(
        `/baselines/coverage-market/${encodeURIComponent(directorName ?? '')}/${encodeURIComponent(marketName ?? '')}?${params}`
      );
      return response.data;
    },
    enabled: !!directorName && !!marketName,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// =============================================================================
// HELPERS
// =============================================================================

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/**
 * Get day name from day of week number
 */
export function getDayName(dayOfWeek: number): string {
  return DAY_NAMES[dayOfWeek] ?? 'Unknown';
}

/**
 * Get coverage level label based on score
 */
export function getCoverageLevel(score: number): 'poor' | 'fair' | 'good' | 'excellent' {
  if (score >= 90) return 'excellent';
  if (score >= 70) return 'good';
  if (score >= 50) return 'fair';
  return 'poor';
}

/**
 * Get severity color class
 */
export function getSeverityColor(severity: 'warning' | 'error'): string {
  return severity === 'error' ? 'text-red-500' : 'text-yellow-500';
}

/**
 * Get coverage score color class
 */
export function getCoverageColor(score: number): string {
  if (score >= 90) return 'text-green-600';
  if (score >= 70) return 'text-blue-600';
  if (score >= 50) return 'text-yellow-600';
  return 'text-red-600';
}

/**
 * Format days missing as comma-separated string
 */
export function formatDaysMissing(daysWithData: number[]): string {
  const missing = DAY_NAMES.filter((_, idx) => !daysWithData.includes(idx));
  return missing.length > 0 ? missing.join(', ') : 'None';
}
