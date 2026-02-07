/**
 * Theater Amenities API Hooks
 *
 * Provides hooks for managing theater amenities and discovering
 * formats/screen counts from showings data.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// =============================================================================
// TYPES
// =============================================================================

export interface TheaterAmenities {
  id: number;
  theater_name: string;
  circuit_name: string | null;

  // Seating
  has_recliners: boolean | null;
  has_reserved_seating: boolean | null;
  has_heated_seats: boolean | null;

  // Premium formats
  has_imax: boolean | null;
  has_dolby_cinema: boolean | null;
  has_dolby_atmos: boolean | null;
  has_rpx: boolean | null;
  has_4dx: boolean | null;
  has_screenx: boolean | null;
  has_dbox: boolean | null;

  // Food & beverage
  has_dine_in: boolean | null;
  has_full_bar: boolean | null;
  has_premium_concessions: boolean | null;
  has_reserved_food_delivery: boolean | null;

  // Theater info
  screen_count: number | null;
  premium_screen_count: number | null;
  year_built: number | null;
  year_renovated: number | null;

  // Computed
  premium_formats: string[];
  amenity_score: number;

  // Metadata
  notes: string | null;
  source: string | null;
  last_verified: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface TheaterAmenitiesRequest {
  theater_name: string;
  circuit_name?: string | null;
  has_recliners?: boolean | null;
  has_reserved_seating?: boolean | null;
  has_heated_seats?: boolean | null;
  has_imax?: boolean | null;
  has_dolby_cinema?: boolean | null;
  has_dolby_atmos?: boolean | null;
  has_rpx?: boolean | null;
  has_4dx?: boolean | null;
  has_screenx?: boolean | null;
  has_dbox?: boolean | null;
  has_dine_in?: boolean | null;
  has_full_bar?: boolean | null;
  has_premium_concessions?: boolean | null;
  has_reserved_food_delivery?: boolean | null;
  screen_count?: number | null;
  premium_screen_count?: number | null;
  year_built?: number | null;
  year_renovated?: number | null;
  notes?: string | null;
  source?: string;
}

export interface AmenitySummary {
  circuit_name: string;
  theater_count: number;
  with_recliners: number;
  with_reserved_seating: number;
  with_imax: number;
  with_dolby: number;
  with_dine_in: number;
  with_bar: number;
  avg_amenity_score: number;
}

export interface DiscoveryRequest {
  theater_name?: string | null;
  circuit_name?: string | null;
  lookback_days?: number;
}

export interface DiscoveryResult {
  theater_name: string;
  formats_discovered: Record<string, string[]>;
  screen_counts: Record<string, number>;
  amenities_updated: boolean;
}

export interface DiscoverAllResponse {
  theaters_updated: number;
  circuit_filter: string | null;
  lookback_days: number;
}

export interface FormatSummary {
  by_format: Record<string, number>;
  by_category: Record<string, number>;
  total_theaters_with_plf: number;
}

export interface ScreenCountEstimate {
  theater_name: string;
  formats_available: Record<string, string[]>;
  screen_counts_by_category: Record<string, number>;
  estimated_total_screens: number | null;
  lookback_days: number;
}

export interface AmenitiesFilters {
  theater_name?: string;
  circuit_name?: string;
  has_recliners?: boolean;
  has_imax?: boolean;
  has_dolby?: boolean;
  has_dine_in?: boolean;
  limit?: number;
  offset?: number;
}

// =============================================================================
// QUERY KEYS
// =============================================================================

export const theaterAmenitiesKeys = {
  all: ['theater-amenities'] as const,
  lists: () => [...theaterAmenitiesKeys.all, 'list'] as const,
  list: (filters: AmenitiesFilters) => [...theaterAmenitiesKeys.lists(), filters] as const,
  detail: (id: number) => [...theaterAmenitiesKeys.all, 'detail', id] as const,
  summary: () => [...theaterAmenitiesKeys.all, 'summary'] as const,
  formatSummary: (lookbackDays: number) => [...theaterAmenitiesKeys.all, 'format-summary', lookbackDays] as const,
  screenCounts: (theaterName: string, lookbackDays: number) => [...theaterAmenitiesKeys.all, 'screen-counts', theaterName, lookbackDays] as const,
};

// =============================================================================
// CRUD HOOKS
// =============================================================================

/**
 * List theater amenities with optional filtering
 */
export function useTheaterAmenities(filters: AmenitiesFilters = {}) {
  const params = new URLSearchParams();
  if (filters.theater_name) params.append('theater_name', filters.theater_name);
  if (filters.circuit_name) params.append('circuit_name', filters.circuit_name);
  if (filters.has_recliners !== undefined) params.append('has_recliners', String(filters.has_recliners));
  if (filters.has_imax !== undefined) params.append('has_imax', String(filters.has_imax));
  if (filters.has_dolby !== undefined) params.append('has_dolby', String(filters.has_dolby));
  if (filters.has_dine_in !== undefined) params.append('has_dine_in', String(filters.has_dine_in));
  if (filters.limit) params.append('limit', String(filters.limit));
  if (filters.offset) params.append('offset', String(filters.offset));

  return useQuery({
    queryKey: theaterAmenitiesKeys.list(filters),
    queryFn: async () => {
      const response = await api.get<TheaterAmenities[]>(`/theater-amenities?${params}`);
      return response.data;
    },
  });
}

/**
 * Get a specific theater's amenities by ID
 */
export function useTheaterAmenity(id: number | null, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: theaterAmenitiesKeys.detail(id ?? 0),
    queryFn: async () => {
      const response = await api.get<TheaterAmenities>(`/theater-amenities/${id}`);
      return response.data;
    },
    enabled: (options?.enabled ?? true) && id !== null,
  });
}

/**
 * Get amenity summary by circuit
 */
export function useAmenitiesSummary() {
  return useQuery({
    queryKey: theaterAmenitiesKeys.summary(),
    queryFn: async () => {
      const response = await api.get<AmenitySummary[]>('/theater-amenities/summary');
      return response.data;
    },
  });
}

/**
 * Create theater amenities
 */
export function useCreateTheaterAmenities() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: TheaterAmenitiesRequest) => {
      const response = await api.post<TheaterAmenities>('/theater-amenities', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: theaterAmenitiesKeys.all });
    },
  });
}

/**
 * Update theater amenities
 */
export function useUpdateTheaterAmenities() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: TheaterAmenitiesRequest }) => {
      const response = await api.put<TheaterAmenities>(`/theater-amenities/${id}`, data);
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: theaterAmenitiesKeys.all });
      queryClient.setQueryData(theaterAmenitiesKeys.detail(data.id), data);
    },
  });
}

/**
 * Delete theater amenities
 */
export function useDeleteTheaterAmenities() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/theater-amenities/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: theaterAmenitiesKeys.all });
    },
  });
}

// =============================================================================
// DISCOVERY HOOKS
// =============================================================================

/**
 * Discover and update amenities for a single theater
 */
export function useDiscoverTheaterAmenities() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: DiscoveryRequest) => {
      const response = await api.post<DiscoveryResult>('/theater-amenities/discover', request);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: theaterAmenitiesKeys.all });
    },
  });
}

/**
 * Discover amenities for all theaters (optionally filtered by circuit)
 */
export function useDiscoverAllTheaterAmenities() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: DiscoveryRequest = {}) => {
      const response = await api.post<DiscoverAllResponse>('/theater-amenities/discover-all', request);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: theaterAmenitiesKeys.all });
    },
  });
}

/**
 * Get format summary across all theaters
 */
export function useFormatSummary(lookbackDays: number = 30, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: theaterAmenitiesKeys.formatSummary(lookbackDays),
    queryFn: async () => {
      const response = await api.get<FormatSummary>(`/theater-amenities/format-summary?lookback_days=${lookbackDays}`);
      return response.data;
    },
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Get screen count estimates for a specific theater
 */
export function useScreenCountEstimate(
  theaterName: string | null,
  lookbackDays: number = 14,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: theaterAmenitiesKeys.screenCounts(theaterName ?? '', lookbackDays),
    queryFn: async () => {
      const response = await api.get<ScreenCountEstimate>(
        `/theater-amenities/screen-counts/${encodeURIComponent(theaterName ?? '')}?lookback_days=${lookbackDays}`
      );
      return response.data;
    },
    enabled: (options?.enabled ?? true) && !!theaterName,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Get display names for format categories
 */
export const FORMAT_CATEGORY_LABELS: Record<string, string> = {
  imax: 'IMAX',
  dolby: 'Dolby',
  '3d': '3D',
  '4dx': '4DX/MX4D',
  dbox: 'D-BOX',
  screenx: 'ScreenX',
  rpx: 'RPX',
  plf_other: 'Other PLF',
  standard: 'Standard',
  other: 'Other',
};

/**
 * Get the display label for a format category
 */
export function getFormatCategoryLabel(category: string): string {
  return FORMAT_CATEGORY_LABELS[category] || category;
}

/**
 * Calculate premium format count from amenities
 */
export function getPremiumFormatCount(amenities: TheaterAmenities): number {
  let count = 0;
  if (amenities.has_imax) count++;
  if (amenities.has_dolby_cinema) count++;
  if (amenities.has_dolby_atmos) count++;
  if (amenities.has_rpx) count++;
  if (amenities.has_4dx) count++;
  if (amenities.has_screenx) count++;
  if (amenities.has_dbox) count++;
  return count;
}

/**
 * Get amenity score badge color
 */
export function getAmenityScoreColor(score: number): 'gray' | 'yellow' | 'green' | 'blue' {
  if (score >= 8) return 'blue';
  if (score >= 5) return 'green';
  if (score >= 2) return 'yellow';
  return 'gray';
}
