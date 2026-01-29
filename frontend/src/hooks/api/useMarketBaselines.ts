/**
 * React Query hooks for Market Baseline Scraping API
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// Types
export interface MarketStats {
  total_markets: number;
  circuits: Record<string, { theaters: number; markets: number }>;
}

export interface MarketScrapePlan {
  total_markets: number;
  by_circuit: Record<string, Array<{ market: string; theater: string }>>;
  plan: Array<{
    market: string;
    theater_name: string;
    theater_url: string;
    circuit: string;
  }>;
}

export interface MarketScrapeRequest {
  circuit?: string;
  max_markets?: number;
  days?: number;
}

export interface MarketScrapeJob {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  total_markets: number;
  completed_markets: number;
  failed_markets: number;
  current_market?: string;
  error?: string;
}

export interface MarketScrapeStartResponse {
  job_id: string;
  status: string;
  total_markets: number;
  dates: string[];
  message: string;
}

// Query keys
export const marketBaselineKeys = {
  all: ['market-baselines'] as const,
  stats: () => [...marketBaselineKeys.all, 'stats'] as const,
  plan: (circuit?: string, maxMarkets?: number) =>
    [...marketBaselineKeys.all, 'plan', { circuit, maxMarkets }] as const,
  job: (jobId: string) => [...marketBaselineKeys.all, 'job', jobId] as const,
};

/**
 * Get market statistics (total markets, circuits breakdown)
 */
export function useMarketStats() {
  return useQuery({
    queryKey: marketBaselineKeys.stats(),
    queryFn: async () => {
      const response = await api.get<MarketStats>('/market-baselines/stats');
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Get market scrape plan preview
 */
export function useMarketScrapePlan(circuit?: string, maxMarkets?: number) {
  return useQuery({
    queryKey: marketBaselineKeys.plan(circuit, maxMarkets),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (circuit) params.append('circuit', circuit);
      if (maxMarkets) params.append('max_markets', maxMarkets.toString());

      const response = await api.get<MarketScrapePlan>(
        `/market-baselines/plan?${params.toString()}`
      );
      return response.data;
    },
    enabled: false, // Only fetch when explicitly requested
  });
}

/**
 * Trigger market baseline scraping
 */
export function useTriggerMarketScrape() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: MarketScrapeRequest) => {
      const response = await api.post<MarketScrapeStartResponse>(
        '/market-baselines/scrape',
        request
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: marketBaselineKeys.all });
    },
  });
}

/**
 * Get market scrape job status
 */
export function useMarketScrapeStatus(jobId: string | null, options?: { refetchInterval?: number }) {
  return useQuery({
    queryKey: marketBaselineKeys.job(jobId || ''),
    queryFn: async () => {
      if (!jobId) return null;
      const response = await api.get<MarketScrapeJob>(
        `/market-baselines/scrape/${jobId}`
      );
      return response.data;
    },
    enabled: !!jobId,
    refetchInterval: options?.refetchInterval,
  });
}

/**
 * Cancel a market scrape job
 */
export function useCancelMarketScrape() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (jobId: string) => {
      const response = await api.post(`/market-baselines/scrape/${jobId}/cancel`);
      return response.data;
    },
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: marketBaselineKeys.job(jobId) });
    },
  });
}
