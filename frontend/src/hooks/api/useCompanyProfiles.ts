/**
 * Company Profiles API Hooks
 *
 * Provides hooks for discovering and managing company/circuit pricing profiles.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// =============================================================================
// TYPES
// =============================================================================

export interface DiscountDayInfo {
  day_of_week: number;
  day: string;
  price: number;
  program: string;
  sample_count: number;
  variance_pct: number;
  below_avg_pct: number;
}

export interface CompanyProfile {
  profile_id: number;
  circuit_name: string;
  discovered_at: string;
  last_updated_at: string | null;

  // Ticket types
  ticket_types: string[];

  // Daypart scheme
  daypart_scheme: 'ticket-type-based' | 'time-based' | 'hybrid' | 'unknown';
  daypart_boundaries: Record<string, string>;
  has_flat_matinee: boolean;

  // Discount days
  has_discount_days: boolean;
  discount_days: DiscountDayInfo[];

  // Premium formats
  premium_formats: string[];
  premium_surcharges: Record<string, number>;

  // Data quality
  theater_count: number;
  sample_count: number;
  date_range_start: string | null;
  date_range_end: string | null;
  confidence_score: number;
}

export interface ProfileListResponse {
  total: number;
  profiles: CompanyProfile[];
}

export interface DiscoverRequest {
  circuit_name: string;
  theater_names?: string[];
  lookback_days?: number;
  min_samples?: number;
}

export interface DiscoverResponse {
  profile: CompanyProfile;
  message: string;
}

// =============================================================================
// HOOKS
// =============================================================================

/**
 * Fetch all company profiles
 */
export function useCompanyProfiles() {
  return useQuery({
    queryKey: ['companyProfiles'],
    queryFn: async () => {
      const response = await api.get<ProfileListResponse>('/company-profiles');
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch a specific company profile by circuit name
 */
export function useCompanyProfile(circuitName: string | null) {
  return useQuery({
    queryKey: ['companyProfiles', circuitName],
    queryFn: async () => {
      const response = await api.get<CompanyProfile>(
        `/company-profiles/${encodeURIComponent(circuitName ?? '')}`
      );
      return response.data;
    },
    enabled: !!circuitName,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Discover or update a company profile for a circuit
 */
export function useDiscoverProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: DiscoverRequest) => {
      const response = await api.post<DiscoverResponse>(
        '/company-profiles/discover',
        request
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companyProfiles'] });
    },
  });
}

/**
 * Discover profiles for all known circuits
 */
export function useDiscoverAllProfiles() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (options?: { lookbackDays?: number; minSamples?: number }) => {
      const params = new URLSearchParams();
      if (options?.lookbackDays) params.append('lookback_days', String(options.lookbackDays));
      if (options?.minSamples) params.append('min_samples', String(options.minSamples));

      const response = await api.post<ProfileListResponse>(
        `/company-profiles/discover-all?${params}`
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companyProfiles'] });
    },
  });
}

/**
 * Delete a company profile
 */
export function useDeleteProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (circuitName: string) => {
      await api.delete(`/company-profiles/${encodeURIComponent(circuitName)}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companyProfiles'] });
    },
  });
}

interface ProfileSummary {
  name: string;
  theaters: number;
}

interface CleanupDuplicatesResponse {
  message: string;
  deleted: string[];
  kept: string[];
  existing_before: ProfileSummary[];
  remaining_after: ProfileSummary[];
  note: string;
}

/**
 * Clean up duplicate circuit profiles by keeping the one with most theaters
 */
export function useCleanupDuplicateProfiles() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<CleanupDuplicatesResponse>(
        '/company-profiles/cleanup-duplicates'
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companyProfiles'] });
    },
  });
}

// =============================================================================
// DIAGNOSTIC TYPES AND HOOKS
// =============================================================================

export interface DayPriceAnalysis {
  day_of_week: number;
  day_name: string;
  sample_count: number;
  avg_price: number;
  min_price: number;
  max_price: number;
  price_range: number;  // max - min, indicates if pricing is "flat"
  std_dev: number;
  variance_pct: number;
  below_avg_pct: number;
  is_flat_pricing: boolean;  // True if variance <= 8% or range <= $1.50
  is_discounted: boolean;  // True if >= 8% below weekday average
  ticket_types_seen: string[];
}

export interface DiscountDayDiagnostic {
  circuit_name: string;
  theater_count: number;
  total_samples: number;
  overall_avg_price: number;
  day_analysis: DayPriceAnalysis[];
  discount_ticket_types_found: Record<string, Record<string, number>>;
  detected_discount_days: Array<{
    day_of_week?: number;
    day: string;
    price?: number;
    ticket_type?: string;
    method: string;
    variance_pct?: number;
    below_avg_pct?: number;
    sample_count?: number;
  }>;
  detection_thresholds: {
    max_variance_pct: number;
    min_below_avg_pct: number;
    min_samples: number;
    discount_ticket_concentration: number;
  };
}

/**
 * Get diagnostic info for discount day detection
 */
export function useDiscountDayDiagnostic(circuitName: string | null, lookbackDays?: number) {
  return useQuery({
    queryKey: ['discountDayDiagnostic', circuitName, lookbackDays],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (lookbackDays) params.append('lookback_days', String(lookbackDays));

      const response = await api.get<DiscountDayDiagnostic>(
        `/company-profiles/${encodeURIComponent(circuitName ?? '')}/discount-day-diagnostic?${params}`
      );
      return response.data;
    },
    enabled: !!circuitName,
    staleTime: 60 * 1000, // 1 minute
  });
}

// =============================================================================
// DATA COVERAGE TYPES AND HOOKS
// =============================================================================

export interface DayCoverage {
  day_of_week: number;
  day_name: string;
  sample_count: number;
  theater_count: number;
  date_range: string | null;
  has_sufficient_data: boolean;
}

export interface DataCoverageResponse {
  circuit_name: string;
  total_samples: number;
  total_theaters: number;
  day_coverage: DayCoverage[];
  weekdays_with_data: number;
  coverage_assessment: 'excellent' | 'good' | 'limited' | 'insufficient';
  can_detect_discount_days: boolean;
  recommendation: string;
}

/**
 * Get data coverage info for a circuit
 *
 * Use this to check if you have enough data before running profile discovery.
 */
export function useDataCoverage(circuitName: string | null, lookbackDays?: number) {
  return useQuery({
    queryKey: ['dataCoverage', circuitName, lookbackDays],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (lookbackDays) params.append('lookback_days', String(lookbackDays));

      const response = await api.get<DataCoverageResponse>(
        `/company-profiles/${encodeURIComponent(circuitName ?? '')}/data-coverage?${params}`
      );
      return response.data;
    },
    enabled: !!circuitName,
    staleTime: 60 * 1000, // 1 minute
  });
}

// =============================================================================
// HELPERS
// =============================================================================

/**
 * Get day name from day of week number
 */
export function getDayName(dayOfWeek: number): string {
  const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  return days[dayOfWeek] ?? 'Unknown';
}

/**
 * Get color for coverage assessment
 */
export function getCoverageAssessmentColor(assessment: string): string {
  switch (assessment) {
    case 'excellent':
      return 'text-green-600 bg-green-50 dark:bg-green-900/20 dark:text-green-400';
    case 'good':
      return 'text-blue-600 bg-blue-50 dark:bg-blue-900/20 dark:text-blue-400';
    case 'limited':
      return 'text-yellow-600 bg-yellow-50 dark:bg-yellow-900/20 dark:text-yellow-400';
    case 'insufficient':
      return 'text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400';
    default:
      return 'text-gray-600 bg-gray-50 dark:bg-gray-900/20 dark:text-gray-400';
  }
}

/**
 * Format confidence score as percentage
 */
export function formatConfidence(score: number): string {
  return `${Math.round(score * 100)}%`;
}

/**
 * Get confidence level label
 */
export function getConfidenceLevel(score: number): 'low' | 'medium' | 'high' {
  if (score >= 0.7) return 'high';
  if (score >= 0.4) return 'medium';
  return 'low';
}
