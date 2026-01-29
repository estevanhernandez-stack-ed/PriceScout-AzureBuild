import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryClient';

// =============================================================================
// TYPES
// =============================================================================

export interface OnboardingStep {
  completed: boolean;
  timestamp: string | null;
  source?: string;
  count?: number;
  profile_id?: number;
  confirmed_by?: number;
}

export interface OnboardingSteps {
  market_added: OnboardingStep;
  initial_scrape: OnboardingStep;
  baseline_discovered: OnboardingStep;
  profile_linked: OnboardingStep;
  baseline_confirmed: OnboardingStep;
}

export interface OnboardingCoverage {
  formats_discovered: string[];
  ticket_types_discovered: string[];
  dayparts_discovered: string[];
  score: number;
}

export interface OnboardingStatus {
  theater_name: string;
  circuit_name: string | null;
  market: string | null;
  onboarding_status: 'not_started' | 'in_progress' | 'complete' | 'needs_review';
  progress_percent: number;
  completed_steps: number;
  total_steps: number;
  steps: OnboardingSteps;
  coverage: OnboardingCoverage;
  notes: string | null;
  last_updated_at: string | null;
}

export interface PendingTheater {
  theater_name: string;
  circuit_name: string | null;
  market: string | null;
  onboarding_status: string;
  progress_percent: number;
  next_step: string;
  last_updated_at: string | null;
}

export interface CoverageIndicators {
  theater_name: string;
  baseline_count: number;
  formats_discovered: string[];
  formats_expected: string[];
  format_coverage: number;
  ticket_types_discovered: string[];
  ticket_types_expected: string[];
  ticket_type_coverage: number;
  dayparts_discovered: string[];
  dayparts_expected: string[];
  daypart_coverage: number;
  overall_score: number;
  gaps: {
    formats: string[];
    ticket_types: string[];
    dayparts: string[];
  };
}

export interface DiscoveryResult {
  success: boolean;
  message?: string;
  baselines_created: number;
  formats_discovered: string[];
  ticket_types_discovered: string[];
  dayparts_discovered: string[];
  coverage_score: number;
  gaps: {
    formats: string[];
    ticket_types: string[];
    dayparts: string[];
  };
}

export interface StartOnboardingRequest {
  theater_name: string;
  circuit_name?: string;
  market?: string;
}

export interface BulkStartRequest {
  theaters: Array<{ name: string; circuit?: string }>;
  market: string;
}

export interface RecordScrapeRequest {
  source: 'fandango' | 'enttelligence';
  count: number;
}

export interface DiscoverBaselinesRequest {
  lookback_days?: number;
  min_samples?: number;
}

export interface LinkProfileRequest {
  circuit_name?: string;
}

export interface ConfirmBaselinesRequest {
  notes?: string;
}

// =============================================================================
// QUERY HOOKS
// =============================================================================

/**
 * Get onboarding status for a specific theater
 */
export function useOnboardingStatus(theaterName: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.theaterOnboarding.status(theaterName),
    queryFn: async () => {
      const response = await api.get<OnboardingStatus>(
        `/theater-onboarding/status/${encodeURIComponent(theaterName)}`
      );
      return response.data;
    },
    enabled: options?.enabled ?? !!theaterName,
  });
}

/**
 * List all theaters with pending onboarding
 */
export function usePendingTheaters() {
  return useQuery({
    queryKey: queryKeys.theaterOnboarding.pending(),
    queryFn: async () => {
      const response = await api.get<PendingTheater[]>('/theater-onboarding/pending');
      return response.data;
    },
  });
}

/**
 * List all theaters in a market with onboarding status
 */
export function useTheatersByMarket(market: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.theaterOnboarding.market(market),
    queryFn: async () => {
      const response = await api.get<OnboardingStatus[]>(
        `/theater-onboarding/market/${encodeURIComponent(market)}`
      );
      return response.data;
    },
    enabled: options?.enabled ?? !!market,
  });
}

/**
 * Get coverage indicators for a theater
 */
export function useCoverageIndicators(theaterName: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.theaterOnboarding.coverage(theaterName),
    queryFn: async () => {
      const response = await api.get<CoverageIndicators>(
        `/theater-onboarding/${encodeURIComponent(theaterName)}/coverage`
      );
      return response.data;
    },
    enabled: options?.enabled ?? !!theaterName,
  });
}

// =============================================================================
// MUTATION HOOKS
// =============================================================================

/**
 * Start onboarding for a new theater
 */
export function useStartOnboarding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: StartOnboardingRequest) => {
      const response = await api.post<OnboardingStatus>(
        '/theater-onboarding/start',
        request
      );
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.theaterOnboarding.all });
      if (data.market) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.theaterOnboarding.market(data.market),
        });
      }
    },
  });
}

/**
 * Bulk start onboarding for multiple theaters
 */
export function useBulkStartOnboarding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: BulkStartRequest) => {
      const response = await api.post<PendingTheater[]>(
        '/theater-onboarding/bulk-start',
        request
      );
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.theaterOnboarding.all });
      queryClient.invalidateQueries({
        queryKey: queryKeys.theaterOnboarding.market(variables.market),
      });
    },
  });
}

/**
 * Record initial scrape completion
 */
export function useRecordScrape() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      theaterName,
      ...request
    }: RecordScrapeRequest & { theaterName: string }) => {
      const response = await api.post<OnboardingStatus>(
        `/theater-onboarding/${encodeURIComponent(theaterName)}/scrape`,
        request
      );
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.theaterOnboarding.all });
      queryClient.invalidateQueries({
        queryKey: queryKeys.theaterOnboarding.status(data.theater_name),
      });
    },
  });
}

/**
 * Discover baselines for a theater
 */
export function useDiscoverBaselines() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      theaterName,
      ...request
    }: DiscoverBaselinesRequest & { theaterName: string }) => {
      const response = await api.post<DiscoveryResult>(
        `/theater-onboarding/${encodeURIComponent(theaterName)}/discover`,
        request
      );
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.theaterOnboarding.all });
      queryClient.invalidateQueries({
        queryKey: queryKeys.theaterOnboarding.status(variables.theaterName),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.theaterOnboarding.coverage(variables.theaterName),
      });
    },
  });
}

/**
 * Link theater to a company profile
 */
export function useLinkProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      theaterName,
      ...request
    }: LinkProfileRequest & { theaterName: string }) => {
      const response = await api.post<OnboardingStatus>(
        `/theater-onboarding/${encodeURIComponent(theaterName)}/link`,
        request
      );
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.theaterOnboarding.all });
      queryClient.invalidateQueries({
        queryKey: queryKeys.theaterOnboarding.status(data.theater_name),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.companyProfiles.all });
    },
  });
}

/**
 * Confirm baselines after user review
 */
export function useConfirmBaselines() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      theaterName,
      ...request
    }: ConfirmBaselinesRequest & { theaterName: string }) => {
      const response = await api.post<OnboardingStatus>(
        `/theater-onboarding/${encodeURIComponent(theaterName)}/confirm`,
        request
      );
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.theaterOnboarding.all });
      queryClient.invalidateQueries({
        queryKey: queryKeys.theaterOnboarding.status(data.theater_name),
      });
    },
  });
}

// =============================================================================
// AMENITY DISCOVERY HOOKS
// =============================================================================

export interface TheaterMissingAmenities {
  theater_name: string;
  circuit_name: string | null;
  market: string | null;
  showing_count: number;
  format_count: number;
  onboarding_status: string;
}

export interface AmenityDiscoveryResult {
  theater_name: string;
  formats_discovered: Record<string, string[]>;
  screen_counts: Record<string, number>;
  amenities_updated: boolean;
  amenity_id: number | null;
}

export interface BackfillAmenitiesRequest {
  circuit_name?: string;
  market?: string;
  lookback_days?: number;
}

export interface BackfillResult {
  theaters_checked: number;
  theaters_needing_amenities: number;
  theaters_updated: number;
  theaters_failed: number;
  details: Array<{
    theater: string;
    success: boolean;
    has_imax?: boolean | null;
    has_dolby?: boolean | null;
    screen_count?: number | null;
    error?: string;
  }>;
}

/**
 * Get list of theaters that have showings but no amenities record
 */
export function useTheatersMissingAmenities(
  circuitName?: string,
  options?: { enabled?: boolean }
) {
  const params = new URLSearchParams();
  if (circuitName) params.append('circuit_name', circuitName);

  return useQuery({
    queryKey: ['theater-onboarding', 'amenities', 'missing', circuitName],
    queryFn: async () => {
      const response = await api.get<TheaterMissingAmenities[]>(
        `/theater-onboarding/amenities/missing?${params}`
      );
      return response.data;
    },
    enabled: options?.enabled ?? true,
  });
}

/**
 * Discover amenities for a specific theater
 */
export function useDiscoverAmenities() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      theaterName,
      lookback_days,
    }: {
      theaterName: string;
      lookback_days?: number;
    }) => {
      const response = await api.post<AmenityDiscoveryResult>(
        `/theater-onboarding/${encodeURIComponent(theaterName)}/amenities`,
        { lookback_days: lookback_days ?? 30 }
      );
      return response.data;
    },
    onSuccess: (data) => {
      // Invalidate both onboarding and amenities queries
      queryClient.invalidateQueries({ queryKey: queryKeys.theaterOnboarding.all });
      queryClient.invalidateQueries({ queryKey: ['theater-amenities'] });
      queryClient.invalidateQueries({
        queryKey: queryKeys.theaterOnboarding.status(data.theater_name),
      });
    },
  });
}

/**
 * Backfill amenities for all existing theaters with showings data
 */
export function useBackfillAmenities() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: BackfillAmenitiesRequest = {}) => {
      const response = await api.post<BackfillResult>(
        '/theater-onboarding/amenities/backfill',
        request
      );
      return response.data;
    },
    onSuccess: () => {
      // Invalidate both onboarding and amenities queries
      queryClient.invalidateQueries({ queryKey: queryKeys.theaterOnboarding.all });
      queryClient.invalidateQueries({ queryKey: ['theater-amenities'] });
    },
  });
}
