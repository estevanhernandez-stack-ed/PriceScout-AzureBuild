import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useMarketStats,
  useMarketScrapePlan,
  useTriggerMarketScrape,
  useMarketScrapeStatus,
  useCancelMarketScrape,
  marketBaselineKeys,
} from './useMarketBaselines';
import { createWrapper } from '@/test/utils';

describe('useMarketBaselines hooks', () => {
  // =========================================================================
  // QUERY KEY FACTORY
  // =========================================================================

  describe('marketBaselineKeys', () => {
    it('generates correct base key', () => {
      expect(marketBaselineKeys.all).toEqual(['market-baselines']);
    });

    it('generates correct stats key', () => {
      expect(marketBaselineKeys.stats()).toEqual(['market-baselines', 'stats']);
    });

    it('generates correct plan key with parameters', () => {
      const key = marketBaselineKeys.plan('AMC', 5);
      expect(key).toEqual(['market-baselines', 'plan', { circuit: 'AMC', maxMarkets: 5 }]);
    });

    it('generates correct plan key without parameters', () => {
      const key = marketBaselineKeys.plan();
      expect(key).toEqual(['market-baselines', 'plan', { circuit: undefined, maxMarkets: undefined }]);
    });

    it('generates correct job key', () => {
      expect(marketBaselineKeys.job('job-123')).toEqual(['market-baselines', 'job', 'job-123']);
    });
  });

  // =========================================================================
  // QUERY HOOKS
  // =========================================================================

  describe('useMarketStats', () => {
    it('fetches market statistics', async () => {
      const { result } = renderHook(() => useMarketStats(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.total_markets).toBe(15);
      expect(result.current.data?.circuits).toBeDefined();
    });

    it('returns circuits breakdown', async () => {
      const { result } = renderHook(() => useMarketStats(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.circuits?.AMC).toMatchObject({
        theaters: expect.any(Number),
        markets: expect.any(Number),
      });
    });
  });

  describe('useMarketScrapePlan', () => {
    it('does not fetch automatically (enabled: false)', () => {
      const { result } = renderHook(
        () => useMarketScrapePlan('AMC', 5),
        { wrapper: createWrapper() },
      );

      // The hook has enabled: false by default, so it should not fetch
      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useMarketScrapeStatus', () => {
    it('fetches job status for a valid jobId', async () => {
      const { result } = renderHook(
        () => useMarketScrapeStatus('job-123'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.job_id).toBe('job-123');
      expect(result.current.data?.status).toBe('running');
      expect(result.current.data?.total_markets).toBeDefined();
    });

    it('is disabled when jobId is null', () => {
      const { result } = renderHook(
        () => useMarketScrapeStatus(null),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // =========================================================================
  // MUTATION HOOKS
  // =========================================================================

  describe('useTriggerMarketScrape', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useTriggerMarketScrape(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useCancelMarketScrape', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useCancelMarketScrape(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });
});
