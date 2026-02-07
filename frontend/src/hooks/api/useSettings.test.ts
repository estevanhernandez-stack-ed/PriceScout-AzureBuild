import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useTaxConfig, useUpdateTaxConfig, useMarketScope, useNameMapping, useSystemDiagnostics } from './useSettings';
import { createWrapper } from '@/test/utils';

describe('useSettings hooks', () => {
  describe('useTaxConfig', () => {
    it('fetches tax configuration successfully', async () => {
      const { result } = renderHook(() => useTaxConfig(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        tax_enabled: expect.any(Boolean),
        default_tax_rate: expect.any(Number),
        tax_included_in_price: expect.any(Boolean),
      });
    });

    it('can be disabled via options', () => {
      const { result } = renderHook(() => useTaxConfig({ enabled: false }), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useUpdateTaxConfig', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useUpdateTaxConfig(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
      expect(result.current.mutateAsync).toBeDefined();
    });
  });

  describe('useMarketScope', () => {
    it('fetches market scope data successfully', async () => {
      const { result } = renderHook(() => useMarketScope(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        total_in_market_theaters: expect.any(Number),
        total_markets: expect.any(Number),
        total_directors: expect.any(Number),
        marcus_count: expect.any(Number),
        competitor_count: expect.any(Number),
        enttelligence_matched: expect.any(Number),
        enttelligence_unmatched: expect.any(Number),
        directors: expect.any(Array),
        match_diagnostics: expect.objectContaining({
          total_json_theaters: expect.any(Number),
          matched_count: expect.any(Number),
          unmatched: expect.any(Array),
        }),
      });
    });

    it('can be disabled via options', () => {
      const { result } = renderHook(() => useMarketScope({ enabled: false }), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useNameMapping', () => {
    it('fetches name mapping data successfully', async () => {
      const { result } = renderHook(() => useNameMapping(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        total_market_theaters: expect.any(Number),
        metadata_matched: expect.any(Number),
        enttelligence_matched: expect.any(Number),
        unmatched_theaters: expect.any(Array),
        non_trivial_matches: expect.any(Array),
        aliases: expect.any(Array),
      });
    });

    it('can be disabled via options', () => {
      const { result } = renderHook(() => useNameMapping({ enabled: false }), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useSystemDiagnostics', () => {
    it('fetches system diagnostics successfully', async () => {
      const { result } = renderHook(() => useSystemDiagnostics(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        data_sources: expect.objectContaining({
          enttelligence: expect.any(Object),
          fandango: expect.any(Object),
        }),
        table_counts: expect.any(Object),
        baseline_summary: expect.any(Object),
        config_summary: expect.objectContaining({
          tax_enabled: expect.any(Boolean),
          tax_default_rate: expect.any(Number),
          tax_state_overrides: expect.any(Number),
          enttelligence_enabled: expect.any(Boolean),
        }),
      });
    });

    it('can be disabled via options', () => {
      const { result } = renderHook(() => useSystemDiagnostics({ enabled: false }), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });
});
