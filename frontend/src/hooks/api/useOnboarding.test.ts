import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useOnboardingStatus,
  usePendingTheaters,
  useTheatersByMarket,
  useCoverageIndicators,
  useStartOnboarding,
  useBulkStartOnboarding,
  useRecordScrape,
  useDiscoverBaselines,
  useLinkProfile,
  useConfirmBaselines,
  useTheatersMissingAmenities,
  useDiscoverAmenities,
  useBackfillAmenities,
} from './useOnboarding';
import { createWrapper } from '@/test/utils';

describe('useOnboarding hooks', () => {
  // =========================================================================
  // QUERY HOOKS
  // =========================================================================

  describe('useOnboardingStatus', () => {
    it('fetches onboarding status for a theater', async () => {
      const { result } = renderHook(
        () => useOnboardingStatus('AMC Madison 6'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.theater_name).toBe('AMC Madison 6');
      expect(result.current.data?.onboarding_status).toBe('in_progress');
      expect(result.current.data?.progress_percent).toBe(60);
      expect(result.current.data?.steps).toBeDefined();
    });

    it('returns data with expected coverage structure', async () => {
      const { result } = renderHook(
        () => useOnboardingStatus('AMC Madison 6'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.coverage).toMatchObject({
        formats_discovered: expect.any(Array),
        ticket_types_discovered: expect.any(Array),
        dayparts_discovered: expect.any(Array),
        score: expect.any(Number),
      });
    });

    it('is disabled when theaterName is empty', () => {
      const { result } = renderHook(
        () => useOnboardingStatus(''),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('usePendingTheaters', () => {
    it('fetches pending theaters list', async () => {
      const { result } = renderHook(() => usePendingTheaters(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns pending theaters with expected structure', async () => {
      const { result } = renderHook(() => usePendingTheaters(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const theater = result.current.data?.[0];
      expect(theater).toMatchObject({
        theater_name: expect.any(String),
        onboarding_status: expect.any(String),
        progress_percent: expect.any(Number),
        next_step: expect.any(String),
      });
    });
  });

  describe('useTheatersByMarket', () => {
    it('fetches theaters for a given market', async () => {
      const { result } = renderHook(
        () => useTheatersByMarket('Madison'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
      expect(result.current.data?.[0]?.theater_name).toBeDefined();
    });

    it('is disabled when market is empty', () => {
      const { result } = renderHook(
        () => useTheatersByMarket(''),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useCoverageIndicators', () => {
    it('fetches coverage indicators for a theater', async () => {
      const { result } = renderHook(
        () => useCoverageIndicators('AMC Madison 6'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.theater_name).toBe('AMC Madison 6');
      expect(result.current.data?.overall_score).toBeDefined();
      expect(result.current.data?.gaps).toBeDefined();
    });

    it('returns coverage with gap details', async () => {
      const { result } = renderHook(
        () => useCoverageIndicators('AMC Madison 6'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.gaps).toMatchObject({
        formats: expect.any(Array),
        ticket_types: expect.any(Array),
        dayparts: expect.any(Array),
      });
    });

    it('is disabled when theaterName is empty', () => {
      const { result } = renderHook(
        () => useCoverageIndicators(''),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // =========================================================================
  // AMENITY DISCOVERY HOOKS
  // =========================================================================

  describe('useTheatersMissingAmenities', () => {
    it('fetches theaters missing amenities', async () => {
      const { result } = renderHook(
        () => useTheatersMissingAmenities(),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns theaters with expected structure', async () => {
      const { result } = renderHook(
        () => useTheatersMissingAmenities(),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const theater = result.current.data?.[0];
      expect(theater).toMatchObject({
        theater_name: expect.any(String),
        showing_count: expect.any(Number),
        format_count: expect.any(Number),
        onboarding_status: expect.any(String),
      });
    });
  });

  // =========================================================================
  // MUTATION HOOKS
  // =========================================================================

  describe('useStartOnboarding', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useStartOnboarding(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useBulkStartOnboarding', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useBulkStartOnboarding(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useRecordScrape', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useRecordScrape(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDiscoverBaselines', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useDiscoverBaselines(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useLinkProfile', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useLinkProfile(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useConfirmBaselines', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useConfirmBaselines(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDiscoverAmenities', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useDiscoverAmenities(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useBackfillAmenities', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useBackfillAmenities(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });
});
