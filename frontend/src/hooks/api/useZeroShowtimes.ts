/**
 * Zero Showtime Analysis Hooks
 *
 * Detects theaters consistently returning 0 showtimes from Fandango,
 * indicating they may have moved to their own ticketing sites.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// =============================================================================
// TYPES
// =============================================================================

export interface ZeroShowtimeTheater {
  theater_name: string;
  total_scrapes: number;
  zero_count: number;
  last_nonzero_date: string | null;
  consecutive_zeros: number;
  last_scrape_date: string | null;
  classification: 'likely_off_fandango' | 'warning' | 'normal';
}

export interface ZeroShowtimeAnalysis {
  theaters: ZeroShowtimeTheater[];
  summary: {
    likely_off_fandango: number;
    warning: number;
    normal: number;
  };
}

export interface MarkTheaterStatusRequest {
  theater_name: string;
  market: string;
  status: 'not_on_fandango' | 'closed' | 'active';
  external_url?: string;
  reason?: string;
}

export interface MarkTheaterStatusResponse {
  success: boolean;
  theater_name: string;
  new_status: string;
}

// =============================================================================
// HOOKS
// =============================================================================

/**
 * Analyze operating hours history to find theaters with zero showtimes.
 * Pass theater names to analyze; returns classification for each.
 */
export function useZeroShowtimeAnalysis(
  theaterNames: string[] | null,
  options?: { lookbackDays?: number }
) {
  return useQuery<ZeroShowtimeAnalysis>({
    queryKey: ['zeroShowtimes', theaterNames, options?.lookbackDays],
    queryFn: async () => {
      const response = await api.post<ZeroShowtimeAnalysis>(
        '/scrapes/zero-showtime-analysis',
        {
          theater_names: theaterNames,
          lookback_days: options?.lookbackDays ?? 30,
        }
      );
      return response.data;
    },
    enabled: !!theaterNames && theaterNames.length > 0,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Mark a theater's Fandango availability status.
 * Use "not_on_fandango" when theater moved to own ticketing,
 * or "active" to re-enable a previously flagged theater.
 */
export function useMarkTheaterStatus() {
  const queryClient = useQueryClient();

  return useMutation<MarkTheaterStatusResponse, Error, MarkTheaterStatusRequest>({
    mutationFn: async (request) => {
      const response = await api.post<MarkTheaterStatusResponse>(
        '/scrapes/mark-theater-status',
        request
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['theaterCache'] });
      queryClient.invalidateQueries({ queryKey: ['zeroShowtimes'] });
      queryClient.invalidateQueries({ queryKey: ['markets'] });
    },
  });
}
