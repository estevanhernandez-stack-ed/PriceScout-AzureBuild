import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

export interface TheaterMetadata {
  id: number;
  theater_name: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  market?: string;
  circuit_name?: string;
  latitude?: number;
  longitude?: number;
  last_geocode_at?: string;
}

export interface MarketEvent {
  id: number;
  event_name: string;
  event_type: string;
  start_date: string;
  end_date: string;
  scope: string;
  scope_value?: string;
  impact_score: number;
  description?: string;
}

export interface SyncResult {
  status: string;
  processed: number;
  updated: number;
  geocoded: number;
  errors: number;
  message?: string;
}

/**
 * Fetch theater metadata for the current company
 */
export function useTheaterMetadata() {
  return useQuery({
    queryKey: ['marketContext', 'theaters'],
    queryFn: async () => {
      const response = await api.get<TheaterMetadata[]>('/market-context/theaters');
      return response.data;
    },
    staleTime: 30 * 60 * 1000, // 30 mins
  });
}

/**
 * Fetch market events for a date range and optional market
 */
export function useMarketEvents(startDate: string, endDate: string, market?: string) {
  return useQuery({
    queryKey: ['marketContext', 'events', startDate, endDate, market],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
      });
      if (market) params.append('market', market);
      
      const response = await api.get<MarketEvent[]>(`/market-context/events?${params.toString()}`);
      return response.data;
    },
    enabled: !!startDate && !!endDate,
    staleTime: 60 * 60 * 1000, // 1 hour
  });
}

/**
 * Trigger synchronization of theater metadata from EntTelligence
 */
export function useSyncMarketContext() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (theaterNames?: string[]) => {
      const response = await api.post<SyncResult>('/market-context/sync/theaters', {
        theater_names: theaterNames
      });
      return response.data;
    },
    onSuccess: () => {
      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: ['marketContext'] });
    },
  });
}

// =============================================================================
// HEATMAP DATA
// =============================================================================

export interface HeatmapTheaterData {
  theater_name: string;
  circuit_name: string | null;
  market: string | null;
  latitude: number;
  longitude: number;
  avg_price: number | null;
  baseline_count: number;
  formats: string[];
}

export interface HeatmapDataResponse {
  total_theaters: number;
  theaters_with_coords: number;
  theaters: HeatmapTheaterData[];
}

/**
 * Fetch theater data for heatmap visualization
 * Returns theaters with coordinates, average baseline prices, and metadata
 */
export function useHeatmapData(options?: {
  market?: string;
  circuit?: string;
  enabled?: boolean;
}) {
  const params = new URLSearchParams();
  if (options?.market) params.append('market', options.market);
  if (options?.circuit) params.append('circuit', options.circuit);

  return useQuery({
    queryKey: ['marketContext', 'heatmap', options],
    queryFn: async () => {
      const response = await api.get<HeatmapDataResponse>(
        `/market-context/theaters/heatmap-data?${params.toString()}`
      );
      return response.data;
    },
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
