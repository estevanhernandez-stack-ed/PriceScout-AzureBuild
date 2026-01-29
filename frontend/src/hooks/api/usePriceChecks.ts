import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryClient';
import type {
  PriceCheck,
  PriceCheckLatest,
  PriceCheckSummary,
  PriceComparison,
} from '@/types';

interface PriceCheckListResponse {
  total_records: number;
  price_checks: PriceCheck[];
}

interface PriceCheckFilters {
  theaterName?: string;
  filmTitle?: string;
  dateFrom?: string;
  dateTo?: string;
  ticketType?: string;
  format?: string;
  limit?: number;
  offset?: number;
}

/**
 * Fetch paginated price checks with filters
 */
export function usePriceChecks(filters: PriceCheckFilters = {}) {
  return useQuery({
    queryKey: queryKeys.priceChecks.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.theaterName) params.append('theater_name', filters.theaterName);
      if (filters.filmTitle) params.append('film_title', filters.filmTitle);
      if (filters.dateFrom) params.append('date_from', filters.dateFrom);
      if (filters.dateTo) params.append('date_to', filters.dateTo);
      if (filters.ticketType) params.append('ticket_type', filters.ticketType);
      if (filters.format) params.append('format', filters.format);
      if (filters.limit) params.append('limit', String(filters.limit));
      if (filters.offset) params.append('offset', String(filters.offset));

      const response = await api.get<PriceCheckListResponse>(
        `/price-checks?${params.toString()}`
      );
      return response.data;
    },
  });
}

/**
 * Fetch latest prices for a specific theater
 */
export function useLatestPrices(theaterName?: string) {
  return useQuery({
    queryKey: queryKeys.priceChecks.latest(theaterName),
    queryFn: async () => {
      const url = theaterName
        ? `/price-checks/latest/${encodeURIComponent(theaterName)}`
        : '/price-checks/latest';
      const response = await api.get<PriceCheckLatest[]>(url);
      return response.data;
    },
    enabled: !!theaterName,
  });
}

/**
 * Fetch price check summary with aggregated data
 */
export function usePriceCheckSummary(filters: PriceCheckFilters = {}) {
  return useQuery({
    queryKey: queryKeys.priceChecks.summary(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.theaterName) params.append('theater_name', filters.theaterName);
      if (filters.dateFrom) params.append('date_from', filters.dateFrom);
      if (filters.dateTo) params.append('date_to', filters.dateTo);

      const response = await api.get<PriceCheckSummary>(
        `/price-checks/summary?${params.toString()}`
      );
      return response.data;
    },
  });
}

/**
 * Fetch price comparison across theaters
 */
export function usePriceComparison(params: { market?: string; ticketType?: string; format?: string; days?: number } = {}) {
  return useQuery({
    queryKey: queryKeys.priceChecks.comparison(params),
    queryFn: async () => {
      const searchParams = new URLSearchParams();
      if (params.market) searchParams.append('market', params.market);
      if (params.ticketType) searchParams.append('ticket_type', params.ticketType);
      if (params.format) searchParams.append('format', params.format);
      if (params.days) searchParams.append('days', String(params.days));

      const response = await api.get<PriceComparison[]>(
        `/price-comparison?${searchParams.toString()}`
      );
      return response.data;
    },
  });
}

