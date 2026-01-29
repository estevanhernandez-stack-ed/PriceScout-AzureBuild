import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryClient';

// ============================================================================
// Types
// ============================================================================

export interface CacheStatus {
  cache_file_exists: boolean;
  last_updated?: string;
  market_count: number;
  theater_count: number;
  file_size_kb: number;
  metadata?: {
    last_updated?: string;
    last_refresh_type?: string;
  };
}

export interface CacheMarket {
  market_name: string;
  total_theaters: number;
  active_theaters: number;
  not_on_fandango: number;
}

export interface CacheMarketList {
  markets: CacheMarket[];
  total_count: number;
}

export interface UnmatchedTheater {
  theater_name: string;
  market: string;
  company?: string;
  url?: string;
  status: 'no_match' | 'not_on_fandango' | 'closed';
}

export interface UnmatchedTheaterList {
  theaters: UnmatchedTheater[];
  total_count: number;
}

export interface TheaterMatchRequest {
  theater_name: string;
  market: string;
  fandango_url?: string;
  new_name?: string;
  mark_as_closed?: boolean;
  not_on_fandango?: boolean;
  external_url?: string;
}

export interface TheaterMatchResponse {
  success: boolean;
  message: string;
  theater_name: string;
  matched_name?: string;
  url?: string;
}

export interface CacheBackup {
  filename: string;
  path: string;
  size_kb: number;
  modified_at: string;
}

// ============================================================================
// Cache Status Hooks
// ============================================================================

/**
 * Fetch cache status and statistics
 */
export function useCacheStatus() {
  return useQuery({
    queryKey: queryKeys.cache.status(),
    queryFn: async () => {
      const response = await api.get<CacheStatus>('/cache/status');
      return response.data;
    },
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Fetch list of markets in the cache
 */
export function useCacheMarkets() {
  return useQuery({
    queryKey: ['cache', 'markets'],
    queryFn: async () => {
      const response = await api.get<CacheMarketList>('/cache/markets');
      return response.data;
    },
  });
}

/**
 * Fetch backup file status
 */
export function useCacheBackups() {
  return useQuery({
    queryKey: ['cache', 'backups'],
    queryFn: async () => {
      const response = await api.get<{
        backups: CacheBackup[];
        backup_count: number;
      }>('/cache/backup');
      return response.data;
    },
  });
}

/**
 * Trigger cache refresh
 */
export function useRefreshCache() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (options: {
      rebuild_broken_urls?: boolean;
      force_full_refresh?: boolean;
    } = {}) => {
      const response = await api.post<{
        status: string;
        message: string;
        started_at: string;
      }>('/cache/refresh', options);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.cache.status() });
      queryClient.invalidateQueries({ queryKey: ['cache'] });
      queryClient.invalidateQueries({ queryKey: ['theaterCache'] });
    },
  });
}

// ============================================================================
// Unmatched Theaters Hooks
// ============================================================================

/**
 * Fetch list of unmatched theaters
 */
export function useUnmatchedTheaters() {
  return useQuery({
    queryKey: queryKeys.theaters.unmatched(),
    queryFn: async () => {
      const response = await api.get<UnmatchedTheaterList>('/theaters/unmatched');
      return response.data;
    },
  });
}

export interface TheaterDiscoveryResult {
  name: string;
  url: string;
  code?: string;
}

export interface TheaterDiscoveryResponse {
  found: boolean;
  theater_name?: string;
  url?: string;
  theater_code?: string;
  all_results: TheaterDiscoveryResult[];
  error?: string;
  cache_updated: boolean;
}

/**
 * Match a theater to Fandango or update its status
 */
export function useMatchTheater() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: TheaterMatchRequest) => {
      const response = await api.post<TheaterMatchResponse>(
        '/theaters/match',
        request
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.theaters.unmatched() });
      queryClient.invalidateQueries({ queryKey: ['theaterCache'] });
      queryClient.invalidateQueries({ queryKey: queryKeys.cache.status() });
      queryClient.invalidateQueries({ queryKey: ['marketsHierarchy'] });
    },
  });
}

/**
 * Discover a theater's Fandango URL by searching
 */
export function useDiscoverTheater() {
  return useMutation({
    mutationFn: async ({
      theater_name,
      update_cache = false,
      market,
    }: {
      theater_name: string;
      update_cache?: boolean;
      market?: string;
    }) => {
      const response = await api.post<TheaterDiscoveryResponse>(
        '/theaters/discover',
        { theater_name, update_cache, market }
      );
      return response.data;
    },
  });
}

/**
 * Fetch the full theater cache
 */
export function useTheaterCache() {
  return useQuery({
    queryKey: ['theaterCache'],
    queryFn: async () => {
      const response = await api.get('/cache/theaters');
      return response.data;
    },
  });
}
