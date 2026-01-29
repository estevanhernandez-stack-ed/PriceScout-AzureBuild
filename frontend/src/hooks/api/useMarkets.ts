import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryClient';

interface Market {
  market_name: string;
  theater_count: number;
  company?: string;
}

interface MarketTheater {
  theater_name: string;
  market: string;
  url?: string;
  status?: string;
  company?: string;
}

interface Theater {
  name: string;
  url: string;
  company: string;
  zip?: string;
  status?: string;
  not_on_fandango?: boolean;
}

interface MarketData {
  theaters: Theater[];
}

interface TheaterCache {
  metadata: {
    last_updated: string;
    last_refresh_type: string;
  };
  markets: Record<string, MarketData>;
}

// Director → Market → Theaters hierarchy
interface MarketTheaterEntry {
  name: string;
  url: string;
  zip?: string;
  status?: string;
}

interface MarketEntry {
  theaters: MarketTheaterEntry[];
}

// Full hierarchy: Company → Director → Market → Theaters
export type MarketsHierarchy = Record<string, Record<string, Record<string, MarketEntry>>>;

/**
 * Fetch all markets with full Director hierarchy
 * Returns: { "Company": { "Director": { "Market": { theaters: [...] } } } }
 */
export function useMarketsHierarchy() {
  return useQuery({
    queryKey: ['marketsHierarchy'],
    queryFn: async () => {
      const response = await api.get<MarketsHierarchy>('/markets');
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch all markets (flat list - deprecated, use useMarketsHierarchy)
 */
export function useMarkets() {
  return useQuery({
    queryKey: queryKeys.markets.list(),
    queryFn: async () => {
      const response = await api.get<Market[]>('/markets');
      return response.data;
    },
  });
}

/**
 * Fetch theaters in a specific market
 */
export function useMarketTheaters(marketName: string) {
  return useQuery({
    queryKey: queryKeys.markets.theaters(marketName),
    queryFn: async () => {
      const response = await api.get<MarketTheater[]>(
        `/markets/${encodeURIComponent(marketName)}/theaters`
      );
      return response.data;
    },
    enabled: !!marketName,
  });
}

/**
 * Fetch the full theater cache with all markets and theaters
 */
export function useTheaterCache() {
  return useQuery({
    queryKey: ['theaterCache'],
    queryFn: async () => {
      const response = await api.get<TheaterCache>('/cache/theaters');
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
