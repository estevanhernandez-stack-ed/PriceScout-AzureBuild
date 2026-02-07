/**
 * Alternative Content API Hooks
 *
 * Provides hooks for managing Alternative Content (special events) films
 * and circuit AC pricing strategies.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// =============================================================================
// TYPES
// =============================================================================

export interface ACFilm {
  id: number;
  film_title: string;
  normalized_title: string;
  content_type: string;
  content_source: string | null;
  detected_by: string;
  detection_confidence: number;
  detection_reason: string | null;
  first_seen_at: string;
  last_seen_at: string;
  occurrence_count: number;
  is_verified: boolean;
  is_active: boolean;
}

export interface ACFilmListResponse {
  total: number;
  films: ACFilm[];
  content_types: string[];
}

export interface CreateACFilmRequest {
  film_title: string;
  content_type: string;
  content_source?: string;
}

export interface UpdateACFilmRequest {
  content_type?: string;
  content_source?: string;
  is_verified?: boolean;
  is_active?: boolean;
}

export interface DetectionResult {
  title_detected: number;
  ticket_type_detected: number;
  total_unique: number;
  new_saved: number;
  message: string;
}

export interface DetectionPreview {
  title_detected: Array<{
    film_title: string;
    normalized_title: string;
    content_type: string;
    content_source: string | null;
    detected_by: string;
    detection_confidence: number;
    detection_reason: string;
  }>;
  ticket_type_detected: Array<{
    film_title: string;
    normalized_title: string;
    content_type: string;
    detected_by: string;
    detection_confidence: number;
    detection_reason: string;
    ac_ticket_types: string[];
  }>;
  total_title: number;
  total_ticket_type: number;
}

export interface FilmCheckResult {
  film_title: string;
  normalized_title: string;
  is_alternative_content: boolean;
  content_type: string | null;
  pattern_detection: {
    detected_type: string;
    confidence: number;
    reason: string;
  } | null;
}

export interface CircuitACPricing {
  id: number;
  circuit_name: string;
  content_type: string;
  standard_ticket_type: string | null;
  discount_ticket_type: string | null;
  typical_price_min: number | null;
  typical_price_max: number | null;
  discount_day_applies: boolean;
  discount_day_ticket_type: string | null;
  discount_day_price: number | null;
  notes: string | null;
  source: string | null;
}

export interface UpdateCircuitACPricingRequest {
  standard_ticket_type?: string;
  discount_ticket_type?: string;
  typical_price_min?: number;
  typical_price_max?: number;
  discount_day_applies?: boolean;
  discount_day_ticket_type?: string;
  discount_day_price?: number;
  notes?: string;
}

// =============================================================================
// CONTENT TYPE HELPERS
// =============================================================================

export const CONTENT_TYPE_LABELS: Record<string, string> = {
  fathom_event: 'Fathom Event',
  opera_broadcast: 'Opera Broadcast',
  theater_broadcast: 'Theater Broadcast',
  concert_film: 'Concert Film',
  anime_event: 'Anime Event',
  sports_event: 'Sports Event',
  classic_rerelease: 'Classic Re-release',
  marathon: 'Marathon',
  special_presentation: 'Special Presentation',
  indian_cinema: 'Indian Cinema',
  unknown: 'Unknown',
};

export const CONTENT_TYPE_COLORS: Record<string, string> = {
  fathom_event: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  opera_broadcast: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  theater_broadcast: 'bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-300',
  concert_film: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  anime_event: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  sports_event: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  classic_rerelease: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  marathon: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300',
  special_presentation: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300',
  indian_cinema: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  unknown: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300',
};

export function getContentTypeLabel(contentType: string): string {
  return CONTENT_TYPE_LABELS[contentType] || contentType;
}

export function getContentTypeColor(contentType: string): string {
  return CONTENT_TYPE_COLORS[contentType] || CONTENT_TYPE_COLORS.unknown;
}

// =============================================================================
// AC FILMS HOOKS
// =============================================================================

export interface UseACFilmsOptions {
  contentType?: string;
  isVerified?: boolean;
  isActive?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
}

/**
 * Fetch Alternative Content films with optional filters
 */
export function useACFilms(options: UseACFilmsOptions = {}) {
  const { contentType, isVerified, isActive = true, search, limit = 100, offset = 0 } = options;

  return useQuery({
    queryKey: ['alternativeContent', 'films', options],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (contentType) params.append('content_type', contentType);
      if (isVerified !== undefined) params.append('is_verified', String(isVerified));
      if (isActive !== undefined) params.append('is_active', String(isActive));
      if (search) params.append('search', search);
      params.append('limit', String(limit));
      params.append('offset', String(offset));

      const response = await api.get<ACFilmListResponse>(
        `/alternative-content?${params}`
      );
      return response.data;
    },
    staleTime: 2 * 60 * 1000, // 2 minutes
  });
}

/**
 * Fetch a specific AC film by ID
 */
export function useACFilm(filmId: number | null) {
  return useQuery({
    queryKey: ['alternativeContent', 'film', filmId],
    queryFn: async () => {
      const response = await api.get<ACFilm>(`/alternative-content/${filmId}`);
      return response.data;
    },
    enabled: filmId !== null,
  });
}

/**
 * Create a new AC film entry
 */
export function useCreateACFilm() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: CreateACFilmRequest) => {
      const response = await api.post<ACFilm>('/alternative-content', request);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alternativeContent'] });
    },
  });
}

/**
 * Update an AC film
 */
export function useUpdateACFilm() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ filmId, ...request }: UpdateACFilmRequest & { filmId: number }) => {
      const response = await api.put<ACFilm>(`/alternative-content/${filmId}`, request);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alternativeContent'] });
    },
  });
}

/**
 * Delete (deactivate) an AC film
 */
export function useDeleteACFilm() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (filmId: number) => {
      await api.delete(`/alternative-content/${filmId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alternativeContent'] });
    },
  });
}

// =============================================================================
// DETECTION HOOKS
// =============================================================================

/**
 * Run AC detection on recent showings
 */
export function useRunACDetection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (lookbackDays: number = 90) => {
      const response = await api.post<DetectionResult>(
        `/alternative-content/detect?lookback_days=${lookbackDays}`
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alternativeContent'] });
    },
  });
}

/**
 * Preview what would be detected without saving
 */
export function useACDetectionPreview(lookbackDays: number = 90, enabled: boolean = false) {
  return useQuery({
    queryKey: ['alternativeContent', 'detectionPreview', lookbackDays],
    queryFn: async () => {
      const response = await api.get<DetectionPreview>(
        `/alternative-content/detect/preview?lookback_days=${lookbackDays}`
      );
      return response.data;
    },
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Check if a specific film is Alternative Content
 */
export function useCheckFilm(filmTitle: string | null) {
  return useQuery({
    queryKey: ['alternativeContent', 'check', filmTitle],
    queryFn: async () => {
      const response = await api.get<FilmCheckResult>(
        `/alternative-content/check/${encodeURIComponent(filmTitle ?? '')}`
      );
      return response.data;
    },
    enabled: !!filmTitle,
  });
}

// =============================================================================
// CIRCUIT AC PRICING HOOKS
// =============================================================================

/**
 * Fetch all circuit AC pricing strategies
 */
export function useCircuitACPricing() {
  return useQuery({
    queryKey: ['alternativeContent', 'circuitPricing'],
    queryFn: async () => {
      const response = await api.get<CircuitACPricing[]>('/alternative-content/circuit-pricing');
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch AC pricing for a specific circuit
 */
export function useCircuitACPricingByName(circuitName: string | null) {
  return useQuery({
    queryKey: ['alternativeContent', 'circuitPricing', circuitName],
    queryFn: async () => {
      const response = await api.get<CircuitACPricing>(
        `/alternative-content/circuit-pricing/${encodeURIComponent(circuitName ?? '')}`
      );
      return response.data;
    },
    enabled: !!circuitName,
  });
}

/**
 * Update circuit AC pricing
 */
export function useUpdateCircuitACPricing() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      circuitName,
      ...request
    }: UpdateCircuitACPricingRequest & { circuitName: string }) => {
      const response = await api.put<CircuitACPricing>(
        `/alternative-content/circuit-pricing/${encodeURIComponent(circuitName)}`,
        request
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alternativeContent', 'circuitPricing'] });
    },
  });
}

// =============================================================================
// UTILITY HOOKS
// =============================================================================

/**
 * Get a Set of normalized AC film titles for quick lookup
 */
export function useACFilmTitlesSet() {
  const { data } = useACFilms({ isActive: true, limit: 500 });

  return new Set(data?.films.map((f) => f.normalized_title.toLowerCase()) ?? []);
}

/**
 * Check if a film title is in the AC list
 */
export function isAlternativeContent(
  filmTitle: string,
  acTitlesSet: Set<string>
): boolean {
  // Normalize the title for comparison
  const normalized = filmTitle
    .toLowerCase()
    .replace(/\([^)]*\)/g, '') // Remove parenthetical content
    .replace(/\s+/g, ' ')
    .trim();

  return acTitlesSet.has(normalized);
}
