import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import {
  useBaselines,
  useCreateBaseline,
  useUpdateBaseline,
  useDeleteBaseline,
  useBaselineCoverage,
  useFandangoDiscover,
  useFandangoAnalyze,
  useFandangoRefresh,
  useDiscoverFandangoBaselinesForTheaters,
  useEntTelligenceDiscover,
  useEntTelligenceAnalyze,
  useEntTelligenceRefresh,
  useEntTelligenceCircuits,
  useCircuitBaselines,
  usePremiumFormats,
  useSaveDiscoveredBaselines,
  useEventCinemaAnalysis,
  useEventCinemaKeywords,
  useBaselineMarkets,
  useMarketDetail,
  useTheaterBaselines,
  useDeduplicateBaselines,
  useCompareDataSources,
} from './useBaselines';
import { createWrapper } from '@/test/utils';

describe('useBaselines hooks', () => {
  // ===========================================================================
  // SAVED BASELINES
  // ===========================================================================
  describe('useBaselines', () => {
    it('fetches baselines list', async () => {
      const { result } = renderHook(() => useBaselines(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns baselines with expected structure', async () => {
      const { result } = renderHook(() => useBaselines(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const baseline = result.current.data?.[0];
      expect(baseline).toMatchObject({
        baseline_id: expect.any(Number),
        theater_name: expect.any(String),
        ticket_type: expect.any(String),
        baseline_price: expect.any(Number),
      });
    });

    it('supports theater filter', async () => {
      const { result } = renderHook(
        () => useBaselines({ theaterName: 'AMC Madison 6' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });

    it('supports ticket type filter', async () => {
      const { result } = renderHook(
        () => useBaselines({ ticketType: 'Adult' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });

    it('supports dayType filter', async () => {
      const { result } = renderHook(
        () => useBaselines({ dayType: 'weekday' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });

    it('supports activeOnly filter', async () => {
      const { result } = renderHook(
        () => useBaselines({ activeOnly: true }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('useCreateBaseline', () => {
    it('creates a new baseline', async () => {
      const { result } = renderHook(() => useCreateBaseline(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          theater_name: 'Test Theater',
          ticket_type: 'Adult',
          baseline_price: 12.99,
          effective_from: '2026-01-01',
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        baseline_id: expect.any(Number),
      });
    });
  });

  describe('useUpdateBaseline', () => {
    it('exposes a mutate function', () => {
      const { result } = renderHook(() => useUpdateBaseline(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDeleteBaseline', () => {
    it('deletes a baseline', async () => {
      const { result } = renderHook(() => useDeleteBaseline(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate(1);
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  // ===========================================================================
  // BASELINE COVERAGE
  // ===========================================================================
  describe('useBaselineCoverage', () => {
    it('fetches coverage data', async () => {
      const { result } = renderHook(() => useBaselineCoverage(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        total_theaters: expect.any(Number),
        theaters_with_baselines: expect.any(Number),
        theaters_missing_baselines: expect.any(Number),
        coverage_percent: expect.any(Number),
      });
    });

    it('includes by_circuit and missing_theaters', async () => {
      const { result } = renderHook(() => useBaselineCoverage(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.by_circuit).toBeDefined();
      expect(result.current.data?.missing_theaters).toBeInstanceOf(Array);
    });
  });

  // ===========================================================================
  // FANDANGO DISCOVERY
  // ===========================================================================
  describe('useFandangoDiscover', () => {
    it('is disabled by default', () => {
      const { result } = renderHook(() => useFandangoDiscover(), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('fetches when enabled', async () => {
      const { result } = renderHook(
        () => useFandangoDiscover({ enabled: true }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.discovered_count).toBe(5);
      expect(result.current.data?.baselines?.[0]?.source).toBe('fandango');
    });
  });

  describe('useFandangoAnalyze', () => {
    it('is disabled by default', () => {
      const { result } = renderHook(() => useFandangoAnalyze(), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('fetches analysis when enabled', async () => {
      const { result } = renderHook(
        () => useFandangoAnalyze({ enabled: true }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.circuits).toBeDefined();
      expect(result.current.data?.format_breakdown).toBeDefined();
      expect(result.current.data?.overall_stats).toBeDefined();
    });
  });

  describe('useFandangoRefresh', () => {
    it('exposes a mutate function', () => {
      const { result } = renderHook(() => useFandangoRefresh(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDiscoverFandangoBaselinesForTheaters', () => {
    it('exposes a mutate function', () => {
      const { result } = renderHook(() => useDiscoverFandangoBaselinesForTheaters(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  // ===========================================================================
  // ENTTELLIGENCE DISCOVERY
  // ===========================================================================
  describe('useEntTelligenceDiscover', () => {
    it('is disabled by default', () => {
      const { result } = renderHook(() => useEntTelligenceDiscover(), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('fetches when enabled', async () => {
      const { result } = renderHook(
        () => useEntTelligenceDiscover({ enabled: true }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.discovered_count).toBe(8);
      expect(result.current.data?.baselines).toBeInstanceOf(Array);
    });
  });

  describe('useEntTelligenceAnalyze', () => {
    it('fetches analysis (enabled by default)', async () => {
      const { result } = renderHook(
        () => useEntTelligenceAnalyze(),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.circuits).toBeDefined();
      expect(result.current.data?.overall_stats?.total_records).toBe(200);
    });

    it('respects enabled=false', () => {
      const { result } = renderHook(
        () => useEntTelligenceAnalyze({ enabled: false }),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useEntTelligenceRefresh', () => {
    it('exposes a mutate function', () => {
      const { result } = renderHook(() => useEntTelligenceRefresh(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useEntTelligenceCircuits', () => {
    it('fetches circuits list', async () => {
      const { result } = renderHook(() => useEntTelligenceCircuits(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.total_circuits).toBe(3);
      expect(result.current.data?.circuits).toHaveLength(3);
      expect(result.current.data?.circuits?.[0]?.circuit_name).toBe('AMC');
    });
  });

  describe('useCircuitBaselines', () => {
    it('fetches baselines for a circuit', async () => {
      const { result } = renderHook(
        () => useCircuitBaselines('AMC'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.circuit).toBe('AMC');
      expect(result.current.data?.discovered_count).toBe(4);
      expect(result.current.data?.baselines).toBeInstanceOf(Array);
    });

    it('is disabled when circuitName is empty', () => {
      const { result } = renderHook(
        () => useCircuitBaselines(''),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // ===========================================================================
  // UTILITY HOOKS
  // ===========================================================================
  describe('usePremiumFormats', () => {
    it('fetches premium formats', async () => {
      const { result } = renderHook(() => usePremiumFormats(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.premium_formats).toBeInstanceOf(Array);
      expect(result.current.data?.premium_formats).toContain('IMAX');
      expect(result.current.data?.event_cinema_keywords).toBeInstanceOf(Array);
    });
  });

  describe('useSaveDiscoveredBaselines', () => {
    it('exposes a mutate function', () => {
      const { result } = renderHook(() => useSaveDiscoveredBaselines(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  // ===========================================================================
  // EVENT CINEMA
  // ===========================================================================
  describe('useEventCinemaAnalysis', () => {
    it('fetches event cinema analysis', async () => {
      const { result } = renderHook(
        () => useEventCinemaAnalysis(),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.event_films).toBeInstanceOf(Array);
      expect(result.current.data?.summary?.unique_films).toBe(1);
      expect(result.current.data?.price_variations).toBeInstanceOf(Array);
    });

    it('respects enabled=false', () => {
      const { result } = renderHook(
        () => useEventCinemaAnalysis({ enabled: false }),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useEventCinemaKeywords', () => {
    it('fetches event cinema keywords', async () => {
      const { result } = renderHook(() => useEventCinemaKeywords(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.keywords).toBeInstanceOf(Array);
      expect(result.current.data?.keywords).toContain('Fathom');
      expect(result.current.data?.description).toBeDefined();
    });
  });

  // ===========================================================================
  // BASELINE BROWSER
  // ===========================================================================
  describe('useBaselineMarkets', () => {
    it('fetches baseline markets', async () => {
      const { result } = renderHook(() => useBaselineMarkets(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
      expect(result.current.data?.[0]).toMatchObject({
        market: expect.any(String),
        theater_count: expect.any(Number),
        baseline_count: expect.any(Number),
      });
    });
  });

  describe('useMarketDetail', () => {
    it('fetches market detail', async () => {
      const { result } = renderHook(
        () => useMarketDetail('Madison'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.market).toBe('Madison');
      expect(result.current.data?.circuits).toBeInstanceOf(Array);
    });

    it('is disabled when marketName is null', () => {
      const { result } = renderHook(
        () => useMarketDetail(null),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useTheaterBaselines', () => {
    it('fetches theater baselines', async () => {
      const { result } = renderHook(
        () => useTheaterBaselines('AMC Madison 6'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.theater_name).toBe('AMC Madison 6');
      expect(result.current.data?.baselines).toBeInstanceOf(Array);
    });

    it('is disabled when theaterName is null', () => {
      const { result } = renderHook(
        () => useTheaterBaselines(null),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // ===========================================================================
  // MAINTENANCE
  // ===========================================================================
  describe('useDeduplicateBaselines', () => {
    it('exposes a mutate function', () => {
      const { result } = renderHook(() => useDeduplicateBaselines(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  // ===========================================================================
  // DATA SOURCE COMPARISON
  // ===========================================================================
  describe('useCompareDataSources', () => {
    it('fetches comparison data', async () => {
      const { result } = renderHook(
        () => useCompareDataSources(),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.total_comparisons).toBe(10);
      expect(result.current.data?.comparisons).toBeInstanceOf(Array);
      expect(result.current.data?.summary).toBeDefined();
    });

    it('respects enabled=false', () => {
      const { result } = renderHook(
        () => useCompareDataSources({ enabled: false }),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });
});
