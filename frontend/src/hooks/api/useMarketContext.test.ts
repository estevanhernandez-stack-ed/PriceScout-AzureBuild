import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useTheaterMetadata,
  useMarketEvents,
  useSyncMarketContext,
  useHeatmapData,
} from './useMarketContext';
import { createWrapper } from '@/test/utils';

describe('useMarketContext hooks', () => {
  // =========================================================================
  // QUERY HOOKS
  // =========================================================================

  describe('useTheaterMetadata', () => {
    it('fetches theater metadata list', async () => {
      const { result } = renderHook(() => useTheaterMetadata(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns theaters with expected structure', async () => {
      const { result } = renderHook(() => useTheaterMetadata(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const theater = result.current.data?.[0];
      expect(theater).toMatchObject({
        id: expect.any(Number),
        theater_name: expect.any(String),
        city: expect.any(String),
        state: expect.any(String),
      });
    });

    it('returns theaters with coordinate data', async () => {
      const { result } = renderHook(() => useTheaterMetadata(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const theater = result.current.data?.[0];
      expect(theater?.latitude).toBeDefined();
      expect(theater?.longitude).toBeDefined();
    });
  });

  describe('useMarketEvents', () => {
    it('fetches market events for a date range', async () => {
      const { result } = renderHook(
        () => useMarketEvents('2026-02-01', '2026-02-28'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns events with expected structure', async () => {
      const { result } = renderHook(
        () => useMarketEvents('2026-02-01', '2026-02-28'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const event = result.current.data?.[0];
      expect(event).toMatchObject({
        id: expect.any(Number),
        event_name: expect.any(String),
        event_type: expect.any(String),
        start_date: expect.any(String),
        end_date: expect.any(String),
        impact_score: expect.any(Number),
      });
    });

    it('is disabled when startDate is empty', () => {
      const { result } = renderHook(
        () => useMarketEvents('', '2026-02-28'),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('is disabled when endDate is empty', () => {
      const { result } = renderHook(
        () => useMarketEvents('2026-02-01', ''),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useHeatmapData', () => {
    it('fetches heatmap data', async () => {
      const { result } = renderHook(() => useHeatmapData(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.total_theaters).toBeDefined();
      expect(result.current.data?.theaters_with_coords).toBeDefined();
      expect(result.current.data?.theaters).toBeInstanceOf(Array);
    });

    it('returns theaters with coordinate and price data', async () => {
      const { result } = renderHook(() => useHeatmapData(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const theater = result.current.data?.theaters?.[0];
      expect(theater).toMatchObject({
        theater_name: expect.any(String),
        latitude: expect.any(Number),
        longitude: expect.any(Number),
        formats: expect.any(Array),
      });
    });

    it('can be disabled via options', () => {
      const { result } = renderHook(
        () => useHeatmapData({ enabled: false }),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // =========================================================================
  // MUTATION HOOKS
  // =========================================================================

  describe('useSyncMarketContext', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useSyncMarketContext(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });
});
