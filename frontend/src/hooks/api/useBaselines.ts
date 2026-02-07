/**
 * Unified Baselines API Hooks
 *
 * Provides hooks for both Fandango and EntTelligence baseline discovery,
 * as well as managing saved baselines.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// =============================================================================
// TYPES
// =============================================================================

export interface SavedBaseline {
  baseline_id: number;
  theater_name: string;
  ticket_type: string;
  format: string | null;
  daypart: string | null;
  day_type: string | null;  // 'weekday', 'weekend', or null (all days)
  day_of_week: number | null;  // 0=Monday, 6=Sunday, or null (all days)
  baseline_price: number;
  effective_from: string;
  effective_to: string | null;
  source: string | null;
  sample_count: number | null;
  last_discovery_at: string | null;
  created_at: string;
  // Optional extended fields (may be populated by some queries)
  variance_percent?: number | null;
  avg_price?: number | null;
  is_premium?: boolean;
}

export interface DiscoveredBaseline {
  theater_name: string;
  ticket_type: string;
  format: string | null;
  day_type: string | null;  // 'weekday', 'weekend', or null (all days)
  day_of_week: number | null;  // 0=Monday, 6=Sunday, or null (all days)
  daypart: string | null;   // 'matinee', 'evening', 'late', or null (all dayparts)
  circuit_name?: string;
  baseline_price: number;
  sample_count: number;
  min_price: number | null;
  max_price: number | null;
  avg_price: number | null;
  volatility_percent: number;
  is_premium: boolean;
  source?: 'fandango' | 'enttelligence';
}

export interface DiscoveryResponse {
  discovered_count: number;
  saved_count: number | null;
  baselines: DiscoveredBaseline[];
}

export interface CircuitAnalysis {
  record_count: number;
  theater_count: number;
  avg_price: number | null;
  min_price: number | null;
  max_price: number | null;
  price_range: number | null;
}

export interface FormatBreakdown {
  count: number;
  avg_price: number | null;
  is_premium: boolean;
}

export interface PriceAnalysis {
  circuits: Record<string, CircuitAnalysis>;
  format_breakdown: Record<string, FormatBreakdown>;
  overall_stats: {
    total_records: number;
    total_theaters: number;
    total_circuits: number;
    date_range: { min: string | null; max: string | null };
    overall_avg_price: number | null;
  };
  data_coverage: Record<string, number>;
  // Fandango-specific fields
  high_volatility_combinations?: Array<{
    theater: string;
    ticket_type: string;
    format: string | null;
    volatility_percent: number;
    price_range: string;
    is_premium: boolean;
  }>;
  format_price_comparison?: Record<string, {
    avg_price: number;
    sample_count: number;
    is_premium: boolean;
  }>;
}

export interface CircuitInfo {
  circuit_name: string;
  record_count: number;
  theater_count: number;
}

export interface CreateBaselineRequest {
  theater_name: string;
  ticket_type: string;
  format?: string | null;
  daypart?: string | null;
  day_type?: string | null;  // 'weekday', 'weekend', or null (all days)
  baseline_price: number;
  effective_from: string;
  effective_to?: string | null;
}

export interface BaselineCoverage {
  total_theaters: number;
  theaters_with_baselines: number;
  theaters_missing_baselines: number;
  coverage_percent: number;
  by_circuit: Record<string, { total: number; covered: number; missing: number }>;
  missing_theaters: Array<{ theater_name: string; circuit: string }>;
}

// =============================================================================
// SAVED BASELINES HOOKS
// =============================================================================

/**
 * Fetch all saved baselines
 */
export function useBaselines(options?: {
  theaterName?: string;
  ticketType?: string;
  dayType?: string;  // 'weekday', 'weekend', or undefined for all
  activeOnly?: boolean;
}) {
  const params = new URLSearchParams();
  if (options?.theaterName) params.append('theater_name', options.theaterName);
  if (options?.ticketType) params.append('ticket_type', options.ticketType);
  if (options?.dayType) params.append('day_type', options.dayType);
  if (options?.activeOnly !== undefined) params.append('active_only', String(options.activeOnly));

  return useQuery({
    queryKey: ['baselines', options],
    queryFn: async () => {
      const response = await api.get<SavedBaseline[]>(`/price-baselines?${params}`);
      return response.data;
    },
  });
}

/**
 * Create a new baseline
 */
export function useCreateBaseline() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CreateBaselineRequest) => {
      const response = await api.post<SavedBaseline>('/price-baselines', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['baselines'] });
    },
  });
}

/**
 * Update a baseline
 */
export function useUpdateBaseline() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: CreateBaselineRequest }) => {
      const response = await api.put<SavedBaseline>(`/price-baselines/${id}`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['baselines'] });
    },
  });
}

/**
 * Delete a baseline
 */
export function useDeleteBaseline() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/price-baselines/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['baselines'] });
    },
  });
}

/**
 * Get baseline coverage analysis
 * Shows which theaters have baselines vs which are missing
 */
export function useBaselineCoverage() {
  return useQuery({
    queryKey: ['baselines', 'coverage'],
    queryFn: async () => {
      const response = await api.get<BaselineCoverage>('/price-baselines/coverage');
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// =============================================================================
// FANDANGO DISCOVERY HOOKS
// =============================================================================

/**
 * Discover baselines from Fandango scrape data
 */
export function useFandangoDiscover(options?: {
  minSamples?: number;
  lookbackDays?: number;
  save?: boolean;
  enabled?: boolean;
}) {
  const params = new URLSearchParams();
  if (options?.minSamples) params.append('min_samples', String(options.minSamples));
  if (options?.lookbackDays) params.append('lookback_days', String(options.lookbackDays));
  if (options?.save) params.append('save', 'true');

  return useQuery({
    queryKey: ['baselines', 'fandango', 'discover', options],
    queryFn: async () => {
      const response = await api.get<DiscoveryResponse>(`/price-baselines/discover?${params}`);
      // Add source marker
      return {
        ...response.data,
        baselines: response.data.baselines.map(b => ({ ...b, source: 'fandango' as const })),
      };
    },
    enabled: options?.enabled ?? false,
  });
}

/**
 * Analyze Fandango price patterns
 */
export function useFandangoAnalyze(options?: {
  lookbackDays?: number;
  enabled?: boolean;
}) {
  const params = new URLSearchParams();
  if (options?.lookbackDays) params.append('lookback_days', String(options.lookbackDays));

  return useQuery({
    queryKey: ['baselines', 'fandango', 'analyze', options],
    queryFn: async () => {
      const response = await api.get<PriceAnalysis>(`/price-baselines/analyze?${params}`);
      return response.data;
    },
    enabled: options?.enabled ?? false,
  });
}

/**
 * Refresh Fandango baselines
 */
export function useFandangoRefresh() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<{ success: boolean; baselines_updated: number; message: string }>(
        '/price-baselines/refresh'
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['baselines'] });
    },
  });
}

interface FandangoDiscoverForTheatersParams {
  theaters: string[];
  minSamples?: number;
  lookbackDays?: number;
  save?: boolean;
}

interface FandangoDiscoverResponse {
  discovered_count: number;
  saved_count: number | null;
  split_by_day_of_week: boolean;
  day_of_week_summary: Record<string, number> | null;
  daypart_summary: Record<string, number>;
  theater_count: number;
  theater_summary: Record<string, number>;
  baselines: DiscoveredBaseline[];
}

/**
 * Discover and optionally save Fandango baselines for specific theaters
 * Used by My Markets tab to create baselines for a market's theaters
 */
export function useDiscoverFandangoBaselinesForTheaters() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: FandangoDiscoverForTheatersParams) => {
      const urlParams = new URLSearchParams();
      urlParams.append('theaters', params.theaters.join(','));
      if (params.minSamples) urlParams.append('min_samples', String(params.minSamples));
      if (params.lookbackDays) urlParams.append('lookback_days', String(params.lookbackDays));
      if (params.save) urlParams.append('save', 'true');
      // Always split by day of week to detect discount days
      urlParams.append('split_by_day_of_week', 'true');

      const response = await api.get<FandangoDiscoverResponse>(
        `/fandango-baselines/discover?${urlParams}`
      );
      return response.data;
    },
    onSuccess: () => {
      // Invalidate baselines queries to refresh the list
      queryClient.invalidateQueries({ queryKey: ['baselines'] });
    },
  });
}

// =============================================================================
// ENTTELLIGENCE DISCOVERY HOOKS
// =============================================================================

/**
 * Discover baselines from EntTelligence cache
 */
export function useEntTelligenceDiscover(options?: {
  minSamples?: number;
  lookbackDays?: number;
  circuits?: string[];
  splitByDayType?: boolean;   // If true, creates separate weekday/weekend baselines
  splitByDaypart?: boolean;   // If true, creates separate matinee/evening/late baselines
  splitByDayOfWeek?: boolean; // If true, creates separate Mon-Sun baselines (more granular than day_type)
  save?: boolean;
  enabled?: boolean;
}) {
  const params = new URLSearchParams();
  if (options?.minSamples) params.append('min_samples', String(options.minSamples));
  if (options?.lookbackDays) params.append('lookback_days', String(options.lookbackDays));
  if (options?.circuits?.length) params.append('circuits', options.circuits.join(','));
  if (options?.splitByDayType) params.append('split_by_day_type', 'true');
  if (options?.splitByDaypart) params.append('split_by_daypart', 'true');
  if (options?.splitByDayOfWeek) params.append('split_by_day_of_week', 'true');
  if (options?.save) params.append('save', 'true');

  return useQuery({
    queryKey: ['baselines', 'enttelligence', 'discover', options],
    queryFn: async () => {
      const response = await api.get<DiscoveryResponse>(`/enttelligence-baselines/discover?${params}`);
      return response.data;
    },
    enabled: options?.enabled ?? false,
  });
}

/**
 * Analyze EntTelligence price patterns
 */
export function useEntTelligenceAnalyze(options?: {
  lookbackDays?: number;
  enabled?: boolean;
}) {
  const params = new URLSearchParams();
  if (options?.lookbackDays) params.append('lookback_days', String(options.lookbackDays));

  return useQuery({
    queryKey: ['baselines', 'enttelligence', 'analyze', options],
    queryFn: async () => {
      const response = await api.get<PriceAnalysis>(`/enttelligence-baselines/analyze?${params}`);
      return response.data;
    },
    enabled: options?.enabled ?? true,
  });
}

/**
 * Refresh EntTelligence baselines
 */
export function useEntTelligenceRefresh() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<{ success: boolean; baselines_updated: number; message: string; source: string }>(
        '/enttelligence-baselines/refresh'
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['baselines'] });
    },
  });
}

/**
 * List all circuits with EntTelligence data
 */
export function useEntTelligenceCircuits() {
  return useQuery({
    queryKey: ['baselines', 'enttelligence', 'circuits'],
    queryFn: async () => {
      const response = await api.get<{ total_circuits: number; circuits: CircuitInfo[] }>(
        '/enttelligence-baselines/circuits'
      );
      return response.data;
    },
  });
}

/**
 * Get baselines for a specific circuit
 */
export function useCircuitBaselines(circuitName: string, options?: {
  minSamples?: number;
  lookbackDays?: number;
  enabled?: boolean;
}) {
  const params = new URLSearchParams();
  if (options?.minSamples) params.append('min_samples', String(options.minSamples));
  if (options?.lookbackDays) params.append('lookback_days', String(options.lookbackDays));

  return useQuery({
    queryKey: ['baselines', 'enttelligence', 'circuit', circuitName, options],
    queryFn: async () => {
      const response = await api.get<{ circuit: string; discovered_count: number; baselines: DiscoveredBaseline[] }>(
        `/enttelligence-baselines/circuit/${encodeURIComponent(circuitName)}?${params}`
      );
      return response.data;
    },
    enabled: (options?.enabled ?? true) && !!circuitName,
  });
}

// =============================================================================
// UTILITY HOOKS
// =============================================================================

/**
 * Get premium formats list
 */
export function usePremiumFormats() {
  return useQuery({
    queryKey: ['baselines', 'premium-formats'],
    queryFn: async () => {
      const response = await api.get<{
        premium_formats: string[];
        event_cinema_keywords: string[];
        description: string;
      }>('/price-baselines/premium-formats');
      return response.data;
    },
    staleTime: 1000 * 60 * 60, // Cache for 1 hour
  });
}

/**
 * Save discovered baselines (triggers discovery with save=true)
 */
export function useSaveDiscoveredBaselines() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (options: {
      source: 'fandango' | 'enttelligence';
      minSamples?: number;
      lookbackDays?: number;
      circuits?: string[];
      splitByDayType?: boolean;   // If true, creates separate weekday/weekend baselines
      splitByDaypart?: boolean;   // If true, creates separate matinee/evening/late baselines
      splitByDayOfWeek?: boolean; // If true, creates separate Mon-Sun baselines (more granular than day_type)
      excludePremium?: boolean;   // If true, exclude PLF/IMAX/Dolby from baselines (default: false = include them)
    }) => {
      const params = new URLSearchParams();
      if (options.minSamples) params.append('min_samples', String(options.minSamples));
      if (options.lookbackDays) params.append('lookback_days', String(options.lookbackDays));
      if (options.circuits?.length) params.append('circuits', options.circuits.join(','));
      if (options.splitByDayType) params.append('split_by_day_type', 'true');
      if (options.splitByDaypart) params.append('split_by_daypart', 'true');
      if (options.splitByDayOfWeek) params.append('split_by_day_of_week', 'true');
      if (options.excludePremium) params.append('exclude_premium', 'true');
      params.append('save', 'true');

      const endpoint = options.source === 'enttelligence'
        ? '/enttelligence-baselines/discover'
        : '/price-baselines/discover';

      const response = await api.get<DiscoveryResponse>(`${endpoint}?${params}`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['baselines'] });
    },
  });
}

// =============================================================================
// EVENT CINEMA HOOKS
// =============================================================================

export interface EventFilmPricing {
  film_title: string;
  record_count: number;
  theater_count: number;
  circuit_count: number;
  circuits: string[];
  ticket_types: string[];
  formats: string[];
  min_price: number;
  max_price: number;
  avg_price: number;
  price_variation: number;
  price_consistent: boolean;  // True if variation < $1
  play_dates: string[];
}

export interface EventCinemaVariation {
  film_title: string;
  min_price: number;
  max_price: number;
  variation: number;
  theaters_involved: number;
  circuits_involved: string[];
}

export interface EventCinemaAnalysis {
  event_films: EventFilmPricing[];
  summary: {
    total_event_cinema_records: number;
    total_regular_records: number;
    unique_films: number;
    circuits_with_event_cinema: string[];
    avg_event_price: number | null;
    avg_regular_price: number | null;
    price_premium_percent: number | null;
  };
  price_variations: EventCinemaVariation[];
  detection_keywords: string[];
}

/**
 * Analyze event cinema pricing from EntTelligence data
 *
 * Event cinema (Fathom Events, Met Opera, concerts, etc.) is excluded from
 * baseline calculations but tracked separately for documentation and analysis.
 */
export function useEventCinemaAnalysis(options?: {
  lookbackDays?: number;
  circuit?: string;
  enabled?: boolean;
}) {
  const params = new URLSearchParams();
  if (options?.lookbackDays) params.append('lookback_days', String(options.lookbackDays));
  if (options?.circuit) params.append('circuit', options.circuit);

  return useQuery({
    queryKey: ['baselines', 'event-cinema', options],
    queryFn: async () => {
      const response = await api.get<EventCinemaAnalysis>(
        `/enttelligence-baselines/event-cinema?${params}`
      );
      return response.data;
    },
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Get the list of keywords used to detect event cinema
 */
export function useEventCinemaKeywords() {
  return useQuery({
    queryKey: ['baselines', 'event-cinema', 'keywords'],
    queryFn: async () => {
      const response = await api.get<{
        keywords: string[];
        description: string;
      }>('/enttelligence-baselines/event-cinema/keywords');
      return response.data;
    },
    staleTime: 1000 * 60 * 60, // Cache for 1 hour
  });
}

// =============================================================================
// BASELINE BROWSER HOOKS - Browse baselines by market and location
// =============================================================================

export interface MarketSummary {
  market: string;
  theater_count: number;
  circuit_count: number;
  baseline_count: number;
}

export interface TheaterSummary {
  theater_name: string;
  circuit_name: string | null;
  baseline_count: number;
  formats: string[];
  ticket_types: string[];
}

export interface CircuitSummary {
  circuit_name: string;
  theater_count: number;
  baseline_count: number;
  theaters: TheaterSummary[];
}

export interface MarketDetail {
  market: string;
  total_theaters: number;
  total_baselines: number;
  circuits: CircuitSummary[];
}

export interface TheaterBaseline {
  baseline_id: number | null;
  ticket_type: string;
  format: string | null;
  baseline_price: number;
  day_type: string | null;
  day_of_week: number | null;  // 0=Monday, 6=Sunday
  daypart: string | null;
  sample_count: number | null;
  min_price: number | null;
  max_price: number | null;
  updated_at: string | null;
}

export interface TheaterBaselinesResponse {
  theater_name: string;
  circuit_name: string | null;
  market: string | null;
  total_baselines: number;
  baselines: TheaterBaseline[];
}

/**
 * List all markets with baseline data
 * Returns markets sorted by baseline count (descending)
 */
export function useBaselineMarkets() {
  return useQuery({
    queryKey: ['baselines', 'markets'],
    queryFn: async () => {
      const response = await api.get<MarketSummary[]>('/baselines/markets');
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Get detailed baseline information for a specific market
 * Returns circuits and theaters with baseline counts
 */
export function useMarketDetail(marketName: string | null, options?: {
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: ['baselines', 'markets', marketName],
    queryFn: async () => {
      // Use query parameter instead of path parameter to handle market names with slashes
      const response = await api.get<MarketDetail>(
        `/baselines/market-detail`,
        { params: { market_name: marketName } }
      );
      return response.data;
    },
    enabled: (options?.enabled ?? true) && !!marketName,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Get all baselines for a specific theater
 * Returns detailed baseline information including ticket types, formats, day types, etc.
 */
export function useTheaterBaselines(theaterName: string | null, options?: {
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: ['baselines', 'theaters', theaterName],
    queryFn: async () => {
      const response = await api.get<TheaterBaselinesResponse>(
        `/baselines/theaters/${encodeURIComponent(theaterName ?? '')}`
      );
      return response.data;
    },
    enabled: (options?.enabled ?? true) && !!theaterName,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// =============================================================================
// BASELINE MAINTENANCE
// =============================================================================

export interface DeduplicateResponse {
  dry_run: boolean;
  success?: boolean;
  total_baselines?: number;
  duplicate_groups?: number;
  to_delete?: number;
  would_remain?: number;
  before?: number;
  after?: number;
  deleted?: number;
  message: string;
  sample_duplicates?: Array<{
    theater_name: string;
    ticket_type: string;
    format: string | null;
    day_of_week: number | null;
    daypart: string | null;
    day_type: string | null;
    duplicate_count: number;
    baseline_ids: string;
    keeping_id: number;
  }>;
}

/**
 * Deduplicate baselines - remove duplicates keeping most recent
 */
export function useDeduplicateBaselines() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (dryRun: boolean = true) => {
      const response = await api.post<DeduplicateResponse>(
        '/baselines/deduplicate',
        null,
        { params: { dry_run: dryRun } }
      );
      return response.data;
    },
    onSuccess: (data) => {
      if (!data.dry_run) {
        // Invalidate all baseline queries after actual deduplication
        queryClient.invalidateQueries({ queryKey: ['baselines'] });
        queryClient.invalidateQueries({ queryKey: ['price-alerts'] });
      }
    },
  });
}


// =============================================================================
// ENTTELLIGENCE VS FANDANGO COMPARISON
// =============================================================================

export interface PriceComparisonItem {
  theater_name: string;
  ticket_type: string;
  format: string | null;
  daypart: string | null;
  day_of_week: number | null;
  enttelligence_price: number;
  fandango_baseline: number;
  difference: number;
  difference_percent: number;
  ent_sample_count: number;
  fandango_sample_count: number | null;
  // Tax-adjusted fields (populated when apply_tax=true)
  ent_price_tax_adjusted: number | null;
  tax_rate_applied: number | null;
  adjusted_difference: number | null;
  adjusted_difference_percent: number | null;
}

export interface PriceComparisonResponse {
  total_comparisons: number;
  avg_difference: number;
  avg_difference_percent: number;
  ent_higher_count: number;
  fandango_higher_count: number;
  exact_match_count: number;
  likely_tax_exclusive_count: number;
  comparisons: PriceComparisonItem[];
  summary: {
    interpretation: string;
    tax_inclusive_likelihood: 'likely_tax_exclusive' | 'likely_tax_inclusive' | 'likely_tax_inclusive_but_different' | 'unknown';
  };
  // Tax adjustment fields
  tax_adjustment_applied: boolean;
  default_tax_rate: number | null;
}

/**
 * Compare EntTelligence prices against Fandango baselines
 *
 * Helps understand:
 * - Are EntTelligence prices tax-inclusive or exclusive?
 * - How accurate is EntTelligence pricing vs actual Fandango prices?
 */
export function useCompareDataSources(options: {
  theaterFilter?: string;
  minSamples?: number;
  limit?: number;
  applyTax?: boolean;
  enabled?: boolean;
} = {}) {
  const { theaterFilter, minSamples = 3, limit = 200, applyTax = false, enabled = true } = options;

  return useQuery({
    queryKey: ['baselines', 'compare-sources', theaterFilter, minSamples, limit, applyTax],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (theaterFilter) params.append('theater_filter', theaterFilter);
      params.append('min_samples', String(minSamples));
      params.append('limit', String(limit));
      if (applyTax) params.append('apply_tax', 'true');

      const response = await api.get<PriceComparisonResponse>(
        `/baselines/compare-sources?${params}`
      );
      return response.data;
    },
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
