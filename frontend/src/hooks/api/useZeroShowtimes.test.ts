import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useZeroShowtimeAnalysis, useMarkTheaterStatus } from './useZeroShowtimes';
import { createWrapper } from '@/test/utils';

describe('useZeroShowtimes hooks', () => {
  describe('useZeroShowtimeAnalysis', () => {
    it('fetches zero showtime analysis for given theaters', async () => {
      const { result } = renderHook(
        () => useZeroShowtimeAnalysis(['Closed Theater', 'AMC Madison 6']),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        theaters: expect.any(Array),
        summary: expect.objectContaining({
          likely_off_fandango: expect.any(Number),
          warning: expect.any(Number),
          normal: expect.any(Number),
        }),
      });
      expect(result.current.data?.theaters.length).toBeGreaterThan(0);
    });

    it('is disabled when theater names is null', () => {
      const { result } = renderHook(
        () => useZeroShowtimeAnalysis(null),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('is disabled when theater names array is empty', () => {
      const { result } = renderHook(
        () => useZeroShowtimeAnalysis([]),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('accepts lookbackDays option', async () => {
      const { result } = renderHook(
        () => useZeroShowtimeAnalysis(['AMC Madison 6'], { lookbackDays: 14 }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('useMarkTheaterStatus', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useMarkTheaterStatus(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
      expect(result.current.mutateAsync).toBeDefined();
    });
  });
});
