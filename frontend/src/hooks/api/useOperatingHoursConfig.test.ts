import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useTheaterOperatingHours,
  useUpdateTheaterOperatingHours,
} from './useOperatingHoursConfig';
import { createWrapper } from '@/test/utils';

describe('useOperatingHoursConfig hooks', () => {
  // =========================================================================
  // QUERY HOOKS
  // =========================================================================

  describe('useTheaterOperatingHours', () => {
    it('fetches operating hours for a theater', async () => {
      const { result } = renderHook(
        () => useTheaterOperatingHours('AMC Madison 6'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns hours with expected structure', async () => {
      const { result } = renderHook(
        () => useTheaterOperatingHours('AMC Madison 6'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const hours = result.current.data?.[0];
      expect(hours).toMatchObject({
        day_of_week: expect.any(Number),
        open_time: expect.any(String),
        close_time: expect.any(String),
        first_showtime: expect.any(String),
        last_showtime: expect.any(String),
      });
    });

    it('is disabled when theaterName is null', () => {
      const { result } = renderHook(
        () => useTheaterOperatingHours(null),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // =========================================================================
  // MUTATION HOOKS
  // =========================================================================

  describe('useUpdateTheaterOperatingHours', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useUpdateTheaterOperatingHours(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });
});
