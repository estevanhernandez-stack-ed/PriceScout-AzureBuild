import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryClient';
import type {
  ScrapeSourceResponse,
  ScrapeSourceCreate,
  ScrapeSourceUpdate,
  ScrapeJobStatus,
  TriggerResponse,
  ScrapeData,
} from '@/types';

// ============================================================================
// Scrape Sources
// ============================================================================

/**
 * Fetch all scrape sources
 */
export function useScrapeSources() {
  return useQuery({
    queryKey: queryKeys.scrapeSources.list(),
    queryFn: async () => {
      const response = await api.get<ScrapeSourceResponse[]>('/scrape-sources');
      return response.data;
    },
  });
}

/**
 * Fetch a single scrape source
 */
export function useScrapeSource(sourceId: number) {
  return useQuery({
    queryKey: queryKeys.scrapeSources.detail(sourceId),
    queryFn: async () => {
      const response = await api.get<ScrapeSourceResponse>(
        `/scrape-sources/${sourceId}`
      );
      return response.data;
    },
    enabled: !!sourceId,
  });
}

/**
 * Create a new scrape source
 */
export function useCreateScrapeSource() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ScrapeSourceCreate) => {
      const response = await api.post<ScrapeSourceResponse>(
        '/scrape-sources',
        data
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scrapeSources.all });
    },
  });
}

/**
 * Update a scrape source
 */
export function useUpdateScrapeSource() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      sourceId,
      data,
    }: {
      sourceId: number;
      data: ScrapeSourceUpdate;
    }) => {
      const response = await api.put<ScrapeSourceResponse>(
        `/scrape-sources/${sourceId}`,
        data
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scrapeSources.all });
    },
  });
}

/**
 * Delete a scrape source
 */
export function useDeleteScrapeSource() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (sourceId: number) => {
      await api.delete(`/scrape-sources/${sourceId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scrapeSources.all });
    },
  });
}

// ============================================================================
// Scrape Jobs
// ============================================================================

interface ScrapeJobFilters {
  sourceId?: number;
  status?: string;
  limit?: number;
  offset?: number;
}

/**
 * Fetch scrape jobs with filters
 */
export function useScrapeJobs(filters: ScrapeJobFilters = {}) {
  return useQuery({
    queryKey: queryKeys.scrapeJobs.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.sourceId) params.append('source_id', String(filters.sourceId));
      if (filters.status) params.append('status', filters.status);
      if (filters.limit) params.append('limit', String(filters.limit));
      if (filters.offset) params.append('offset', String(filters.offset));

      const response = await api.get<ScrapeJobStatus[]>(
        `/scrape-runs?${params.toString()}`
      );
      return response.data;
    },
  });
}

/**
 * Fetch status of a specific scrape job
 */
export function useScrapeJobStatus(runId: number) {
  return useQuery({
    queryKey: queryKeys.scrapeJobs.status(runId),
    queryFn: async () => {
      const response = await api.get<ScrapeJobStatus>(`/scrape-runs/${runId}`);
      return response.data;
    },
    enabled: !!runId,
    // Poll while job is running
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && (data.status === 'Running' || data.status === 'Pending')) {
        return 5000; // Poll every 5 seconds
      }
      return false;
    },
  });
}

/**
 * Fetch data from a completed scrape job
 */
export function useScrapeJobData(runId: number) {
  return useQuery({
    queryKey: queryKeys.scrapeJobs.data(runId),
    queryFn: async () => {
      const response = await api.get<ScrapeData>(`/scrape-runs/${runId}/data`);
      return response.data;
    },
    enabled: !!runId,
  });
}

/**
 * Trigger a new scrape job for a scrape source
 */
export function useTriggerScrapeSource() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (sourceId: number) => {
      const response = await api.post<TriggerResponse>(
        `/scrape-sources/${sourceId}/trigger`
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scrapeJobs.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.scrapeSources.all });
    },
  });
}

// ============================================================================
// Market Mode Scraping
// ============================================================================

interface TriggerMarketScrapeRequest {
  mode: 'market' | 'compsnipe' | 'poster' | 'lineup';
  market?: string;
  theaters: { name: string; url: string }[];
  dates: string[]; // YYYY-MM-DD format
  film_titles?: string[]; // For poster mode
  selected_showtimes?: string[]; // List of "date|theater|film|time" keys
  // Cache options for hybrid scrape
  use_cache?: boolean;
  cache_max_age_hours?: number;
}

interface TriggerMarketScrapeResponse {
  job_id: number;
  status: string;
  message: string;
}

interface ScrapeStatusResponse {
  job_id: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  theaters_completed: number;
  theaters_total: number;
  showings_completed?: number;
  showings_total?: number;
  current_theater?: string;
  current_showing?: string;
  duration_seconds?: number;
  results?: Record<string, unknown>[];
  error?: string;
  // Cache statistics
  use_cache?: boolean;
  cache_hits?: number;
  cache_misses?: number;
  // Verification results (populated for mode=verification)
  verification_results?: VerificationResponse;
}

/**
 * Trigger a market mode scrape
 */
export function useTriggerScrape() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: TriggerMarketScrapeRequest) => {
      const response = await api.post<TriggerMarketScrapeResponse>(
        '/scrapes/trigger',
        request
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scrapeJobs.all });
    },
  });
}

/**
 * Check status of a market mode scrape job
 */
export function useScrapeStatus(
  jobId: number,
  options: { enabled?: boolean; refetchInterval?: number | false } = {}
) {
  return useQuery({
    queryKey: ['scrapeStatus', jobId],
    queryFn: async () => {
      const response = await api.get<ScrapeStatusResponse>(
        `/scrapes/${jobId}/status`
      );
      return response.data;
    },
    enabled: options.enabled ?? !!jobId,
    refetchInterval: options.refetchInterval,
    // Always refetch fresh data for scrape status - don't use stale cached data
    staleTime: 0,
    gcTime: 0,
  });
}

/**
 * Cancel a running scrape job
 */
export function useCancelScrape() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (runId: number) => {
      const response = await api.post<{ message: string }>(
        `/scrape-runs/${runId}/cancel`
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scrapeJobs.all });
    },
  });
}

// ============================================================================
// Showtime Fetching
// ============================================================================

export interface Showing {
  film_title: string;
  format: string;
  showtime: string;
  daypart: string;
  ticket_url?: string;
  is_plf: boolean;
}

interface FetchShowtimesRequest {
  theaters: { name: string; url: string }[];
  dates: string[]; // YYYY-MM-DD format
}

interface FetchShowtimesResponse {
  showtimes: Record<string, Record<string, Showing[]>>; // {date: {theater: [showings]}}
  duration_seconds: number;
}

/**
 * Fetch showtimes for theaters and dates (for film/showtime selection)
 */
export function useFetchShowtimes() {
  return useMutation({
    mutationFn: async (request: FetchShowtimesRequest) => {
      const response = await api.post<FetchShowtimesResponse>(
        '/scrapes/fetch-showtimes',
        request
      );
      return response.data;
    },
  });
}

// ============================================================================
// Time Estimation
// ============================================================================

interface TimeEstimateRequest {
  num_showings: number;
  mode?: string;
}

interface TimeEstimateResponse {
  estimated_seconds: number;
  formatted_time: string;
  has_historical_data: boolean;
}

/**
 * Estimate scrape time based on historical data
 */
export function useEstimateScrapeTime() {
  return useMutation({
    mutationFn: async (request: TimeEstimateRequest) => {
      const response = await api.post<TimeEstimateResponse>(
        '/scrapes/estimate-time',
        request
      );
      return response.data;
    },
  });
}

// ============================================================================
// Theater Search
// ============================================================================

export interface TheaterSearchResult {
  name: string;
  url: string;
  market?: string;
}

/**
 * Search for theaters on Fandango
 */
export function useSearchTheatersFandango() {
  return useMutation({
    mutationFn: async ({
      query,
      searchType = 'name',
      date,
    }: {
      query: string;
      searchType?: 'name' | 'zip';
      date?: string;
    }) => {
      const params = new URLSearchParams({ query, search_type: searchType });
      if (date) params.append('date', date);

      const response = await api.get<TheaterSearchResult[]>(
        `/scrapes/search-theaters/fandango?${params.toString()}`
      );
      return response.data;
    },
  });
}

/**
 * Search for theaters in the local cache
 */
export function useSearchTheatersCache() {
  return useMutation({
    mutationFn: async (query?: string) => {
      const params = new URLSearchParams();
      if (query) params.append('query', query);

      const response = await api.get<TheaterSearchResult[]>(
        `/scrapes/search-theaters/cache?${params.toString()}`
      );
      return response.data;
    },
  });
}

/**
 * Fetch all active/recent live scrape jobs
 */
export function useLiveScrapeJobs() {
  return useQuery({
    queryKey: ['liveScrapeJobs'],
    queryFn: async () => {
      const response = await api.get<ScrapeStatusResponse[]>('/scrapes/jobs');
      return response.data;
    },
    refetchInterval: 5000,
  });
}

// ============================================================================
// Theater Collision Detection
// ============================================================================

interface ActiveTheatersResponse {
  active_theater_count: number;
  theaters: { url: string; job_id: number }[];
}

interface CollisionCheckResponse {
  has_collision: boolean;
  conflicting_theaters?: { name: string; url: string; job_id: number }[];
  conflicting_job_ids?: number[];
}

/**
 * Get all theaters currently being scraped
 */
export function useActiveTheaters() {
  return useQuery({
    queryKey: ['activeTheaters'],
    queryFn: async () => {
      const response = await api.get<ActiveTheatersResponse>('/scrapes/active-theaters');
      return response.data;
    },
    // Refresh frequently to catch new scrapes
    refetchInterval: 10000,
  });
}

/**
 * Check if theaters would conflict with active scrapes
 */
export function useCheckTheaterCollision() {
  return useMutation({
    mutationFn: async (theaters: { name: string; url: string }[]) => {
      const response = await api.post<CollisionCheckResponse>(
        '/scrapes/check-collision',
        theaters
      );
      return response.data;
    },
  });
}

/**
 * Type for 409 Conflict error response from trigger endpoint
 */
export interface ScrapeConflictError {
  message: string;
  conflicting_theaters: string[];
  conflicting_job_ids: number[];
  suggestion: string;
}

/**
 * Cancel a live scrape job
 */
export function useCancelLiveScrapeJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (jobId: number) => {
      const response = await api.post(`/scrapes/jobs/${jobId}/cancel`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['liveScrapeJobs'] });
    },
  });
}

// ============================================================================
// Showtime Count Comparison (Weather/Closure Monitoring)
// ============================================================================

export interface TheaterCountComparison {
  theater_name: string;
  play_date: string;
  current_count: number;
  previous_count: number;
  delta: number;
  delta_percent: number;
  status: 'normal' | 'reduced' | 'closed' | 'increased' | 'no_previous';
  current_scrape_time?: string;
  previous_scrape_time?: string;
}

export interface ShowtimeComparisonResponse {
  comparisons: TheaterCountComparison[];
  current_time: string;
  filter_applied: string;
}

/**
 * Compare showtime counts between current and previous scrape runs.
 *
 * Use for weather/closure monitoring - identifies theaters with significant
 * drops in showtime counts. Intelligently filters by time-of-day.
 *
 * @param currentCounts - Map of theater name -> current showtime count from fresh scrape.
 *                        When provided, uses this as source of truth for "current" data
 *                        (handles cases where theaters with 0 showtimes aren't in DB).
 */
export function useCompareShowtimeCounts() {
  return useMutation({
    mutationFn: async ({
      theaters,
      playDates,
      currentCounts,
    }: {
      theaters: string[];
      playDates: string[];
      // Nested: theater_name -> play_date -> count
      currentCounts?: Record<string, Record<string, number>>;
    }) => {
      const response = await api.post<ShowtimeComparisonResponse>(
        '/scrapes/compare-counts',
        {
          theaters,
          play_dates: playDates,
          current_counts: currentCounts,
        }
      );
      return response.data;
    },
  });
}

// ============================================================================
// Showtime Verification (Fandango Live vs EntTelligence Cache)
// ============================================================================

export interface ShowtimeMatchItem {
  date: string;
  theater_name: string;
  film_title: string;
  showtime: string;
  format: string;
  status: 'cached' | 'new' | 'missing_from_fandango';
  cached_price?: number;
  cache_age_minutes?: number;
}

export interface TheaterVerificationSummary {
  theater_name: string;
  cached_count: number;
  new_count: number;
  missing_count: number;
  total_fandango: number;
  total_cached: number;
  closure_warning: boolean;
  closure_reason?: string;
}

export interface CompareShowtimesResponse {
  summary: {
    cached: number;
    new: number;
    missing: number;
    closure_warnings: number;
  };
  by_theater: TheaterVerificationSummary[];
  matches: ShowtimeMatchItem[];
  cache_freshness?: string;
}

interface CompareShowtimesRequest {
  theaters: string[];
  play_dates: string[];
  fandango_showtimes: Record<string, Record<string, Showing[]>>;
  company_id?: number;
}

export function useCompareShowtimes() {
  return useMutation({
    mutationFn: async (request: CompareShowtimesRequest) => {
      const response = await api.post<CompareShowtimesResponse>(
        '/scrapes/compare-showtimes',
        request
      );
      return response.data;
    },
  });
}

// ============================================================================
// Fandango Verification (Spot-Check EntTelligence + Tax vs Fandango)
// ============================================================================

export interface PriceVerificationItem {
  theater_name: string;
  film_title: string;
  showtime: string;
  format?: string;
  ticket_type: string;
  fandango_price: number;
  enttelligence_price: number;
  tax_rate: number;
  enttelligence_with_tax: number;
  difference: number;
  difference_percent: number;
  match_status: 'exact' | 'close' | 'divergent';
}

export interface VerificationSummary {
  total_verified: number;
  exact_matches: number;
  close_matches: number;
  divergent: number;
  avg_difference_percent: number;
}

export interface VerificationResponse {
  job_id: number;
  status: string;
  summary?: VerificationSummary;
  comparisons?: PriceVerificationItem[];
  fandango_only?: number;
  error?: string;
}

interface TriggerVerificationRequest {
  theaters: { name: string; url: string }[];
  dates: string[];
  selected_showtimes?: string[];
  market?: string;
}

/**
 * Trigger a Fandango verification scrape.
 * Scrapes Fandango live and compares against EntTelligence + tax.
 */
export function useTriggerVerification() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: TriggerVerificationRequest) => {
      const response = await api.post<{ job_id: number; status: string; message: string }>(
        '/scrapes/verify-prices',
        request
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scrapeJobs.all });
    },
  });
}

/**
 * Fetch verification results for a completed verification job
 */
export function useVerificationResults(
  jobId: number,
  options: { enabled?: boolean } = {}
) {
  return useQuery({
    queryKey: ['verificationResults', jobId],
    queryFn: async () => {
      const response = await api.get<VerificationResponse>(
        `/scrapes/${jobId}/verification`
      );
      return response.data;
    },
    enabled: options.enabled ?? !!jobId,
    staleTime: 0,
  });
}
