import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryClient';
import type {
  UnmatchedTheaterList,
  TheaterMatchRequest,
  TheaterMatchResponse,
} from '@/types';

interface Theater {
  theater_name: string;
  market: string;
  url?: string;
  status?: string;
  company?: string;
}

interface TheaterFilm {
  film_title: string;
  format?: string;
  first_showtime?: string;
  last_showtime?: string;
}

/**
 * Fetch all theaters
 */
export function useTheaters() {
  return useQuery({
    queryKey: queryKeys.theaters.list(),
    queryFn: async () => {
      const response = await api.get<Theater[]>('/theaters');
      return response.data;
    },
  });
}

/**
 * Fetch unmatched theaters (need Fandango URL mapping)
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

/**
 * Fetch films currently showing at a theater
 */
export function useTheaterFilms(theaterName: string) {
  return useQuery({
    queryKey: queryKeys.theaters.films(theaterName),
    queryFn: async () => {
      const response = await api.get<TheaterFilm[]>(
        `/theaters/${encodeURIComponent(theaterName)}/films`
      );
      return response.data;
    },
    enabled: !!theaterName,
  });
}

/**
 * Match an unmatched theater to Fandango
 */
export function useMatchTheater() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: TheaterMatchRequest) => {
      const response = await api.post<TheaterMatchResponse>(
        '/theaters/match',
        data
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.theaters.unmatched() });
      queryClient.invalidateQueries({ queryKey: queryKeys.theaters.list() });
    },
  });
}

// ============================================================================
// Price History
// ============================================================================

export interface PriceHistoryEntry {
  date: string;
  ticket_type: string;
  format: string;
  avg_price: number;
  min_price: number;
  max_price: number;
  price_count: number;
}

/**
 * Fetch price history for a theater
 */
export function usePriceHistory(
  theaterName: string,
  filters: { days?: number; ticketType?: string; format?: string } = {}
) {
  return useQuery({
    queryKey: queryKeys.priceHistory.byTheater(theaterName, filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.days) params.append('days', String(filters.days));
      if (filters.ticketType) params.append('ticket_type', filters.ticketType);
      if (filters.format) params.append('format', filters.format);

      const response = await api.get<PriceHistoryEntry[]>(
        `/price-history/${encodeURIComponent(theaterName)}?${params.toString()}`
      );
      return response.data;
    },
    enabled: !!theaterName,
  });
}
