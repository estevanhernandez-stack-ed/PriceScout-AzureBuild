/**
 * Settings API Hooks
 *
 * Hooks for managing company-level settings, including tax configuration.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { TaxConfigResponse, TaxConfigUpdateRequest } from '@/types/api.types';

// =============================================================================
// QUERY KEYS
// =============================================================================

export const settingsKeys = {
  all: ['settings'] as const,
  taxConfig: ['settings', 'tax-config'] as const,
  marketScope: ['settings', 'market-scope'] as const,
  nameMapping: ['settings', 'name-mapping'] as const,
  systemDiagnostics: ['settings', 'system-diagnostics'] as const,
};

// =============================================================================
// TAX CONFIG HOOKS
// =============================================================================

/**
 * Fetch current tax configuration
 */
export function useTaxConfig(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: settingsKeys.taxConfig,
    queryFn: async () => {
      const response = await api.get<TaxConfigResponse>('/settings/tax-config');
      return response.data;
    },
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Update tax configuration (partial update supported)
 */
export function useUpdateTaxConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: TaxConfigUpdateRequest) => {
      const response = await api.put<TaxConfigResponse>('/settings/tax-config', data);
      return response.data;
    },
    onSuccess: (data) => {
      // Update cache with new data
      queryClient.setQueryData(settingsKeys.taxConfig, data);
      // Invalidate comparison queries since tax may affect them
      queryClient.invalidateQueries({ queryKey: ['baselines', 'compare-sources'] });
    },
  });
}

// =============================================================================
// MARKET SCOPE TYPES & HOOK
// =============================================================================

export interface DirectorBreakdown {
  director: string;
  market_count: number;
  theater_count: number;
  marcus_count: number;
  competitor_count: number;
}

export interface MatchDiagnostics {
  total_json_theaters: number;
  matched_count: number;
  unmatched_count: number;
  unmatched: string[];
  match_log: Array<{ json_name: string; resolved_name: string; method: string }>;
}

export interface MarketScopeResponse {
  total_in_market_theaters: number;
  total_markets: number;
  total_directors: number;
  marcus_count: number;
  competitor_count: number;
  enttelligence_matched: number;
  enttelligence_unmatched: number;
  directors: DirectorBreakdown[];
  match_diagnostics: MatchDiagnostics;
}

export function useMarketScope(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: settingsKeys.marketScope,
    queryFn: async () => {
      const response = await api.get<MarketScopeResponse>('/settings/market-scope');
      return response.data;
    },
    enabled: options?.enabled ?? true,
    staleTime: 10 * 60 * 1000,
  });
}

// =============================================================================
// NAME MAPPING TYPES & HOOK
// =============================================================================

export interface NameAlias {
  enttelligence_name: string;
  fandango_name: string;
  match_confidence: number | null;
  is_verified: boolean;
}

export interface NameMappingResponse {
  total_market_theaters: number;
  metadata_matched: number;
  enttelligence_matched: number;
  unmatched_theaters: string[];
  non_trivial_matches: Array<{ json_name: string; resolved_name: string; method: string }>;
  aliases: NameAlias[];
}

export function useNameMapping(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: settingsKeys.nameMapping,
    queryFn: async () => {
      const response = await api.get<NameMappingResponse>('/settings/name-mapping');
      return response.data;
    },
    enabled: options?.enabled ?? true,
    staleTime: 10 * 60 * 1000,
  });
}

// =============================================================================
// SYSTEM DIAGNOSTICS TYPES & HOOK
// =============================================================================

export interface DataSourceInfo {
  date_range?: string;
  last_fetch?: string;
  last_scrape?: string;
  theaters?: number;
  circuits?: number;
  total_rows?: number;
  total_showings?: number;
  total_prices?: number;
  status?: string;
}

export interface BaselineSummaryItem {
  active_count: number;
  earliest: string;
  latest_discovery: string;
}

export interface SystemDiagnosticsResponse {
  data_sources: Record<string, DataSourceInfo>;
  table_counts: Record<string, number | null>;
  baseline_summary: Record<string, BaselineSummaryItem>;
  config_summary: {
    tax_enabled: boolean;
    tax_default_rate: number;
    tax_state_overrides: number;
    enttelligence_enabled: boolean;
  };
  error?: string;
}

export function useSystemDiagnostics(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: settingsKeys.systemDiagnostics,
    queryFn: async () => {
      const response = await api.get<SystemDiagnosticsResponse>('/settings/system-diagnostics');
      return response.data;
    },
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60 * 1000,
  });
}
