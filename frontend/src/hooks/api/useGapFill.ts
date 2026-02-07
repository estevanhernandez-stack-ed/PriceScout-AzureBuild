/**
 * Gap Fill API Hooks
 *
 * Provides hooks for proposing and applying baseline gap fills from available
 * data sources (EntTelligence cache, circuit averages).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// =============================================================================
// TYPES
// =============================================================================

export interface ProposedGapFill {
  theater_name: string;
  ticket_type: string;
  format: string;
  daypart: string | null;
  day_type: string | null;
  proposed_price: number;
  source: 'enttelligence' | 'circuit_average';
  sample_count: number;
  confidence: number;
  gap_type: string;
  gap_description: string;
}

export interface GapFillProposals {
  theater_name: string;
  total_gaps: number;
  proposals: ProposedGapFill[];
  fillable_count: number;
  unfillable_gaps: number;
}

export interface GapFillApplyResult {
  baselines_created: number;
  baselines_skipped: number;
  theater_name: string;
}

// =============================================================================
// HOOKS
// =============================================================================

/**
 * Fetch gap fill proposals for a specific theater.
 * Returns proposed baselines from EntTelligence cache and circuit averages.
 */
export function useGapFillProposals(
  theaterName: string | null,
  options?: { lookbackDays?: number; minSamples?: number }
) {
  return useQuery<GapFillProposals>({
    queryKey: ['gapFill', 'proposals', theaterName, options],
    queryFn: async () => {
      const params: Record<string, string | number> = {};
      if (options?.lookbackDays) params.lookback_days = options.lookbackDays;
      if (options?.minSamples) params.min_samples = options.minSamples;

      const response = await api.get<GapFillProposals>(
        `/baselines/gap-fill/${encodeURIComponent(theaterName ?? '')}`,
        { params }
      );
      return response.data;
    },
    enabled: !!theaterName,
  });
}

/**
 * Apply gap fill proposals as new baselines for a theater.
 * Re-analyzes gaps and applies proposals meeting the confidence threshold.
 */
export function useApplyGapFills() {
  const queryClient = useQueryClient();

  return useMutation<GapFillApplyResult, Error, { theaterName: string; minConfidence?: number }>({
    mutationFn: async ({ theaterName, minConfidence = 0.7 }) => {
      const response = await api.post<GapFillApplyResult>(
        `/baselines/gap-fill/${encodeURIComponent(theaterName)}/apply`,
        { min_confidence: minConfidence }
      );
      return response.data;
    },
    onSuccess: () => {
      // Invalidate gap fill proposals and coverage gaps for the theater
      queryClient.invalidateQueries({ queryKey: ['gapFill'] });
      queryClient.invalidateQueries({ queryKey: ['coverageGaps'] });
      queryClient.invalidateQueries({ queryKey: ['baselines'] });
    },
  });
}
