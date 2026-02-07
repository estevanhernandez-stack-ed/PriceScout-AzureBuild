import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useOperatingHours,
  useDailyLineup,
  usePlfFormats,
} from './useReports';
import { createWrapper } from '@/test/utils';

describe('useReports hooks', () => {
  describe('useOperatingHours', () => {
    it('fetches operating hours data', async () => {
      const { result } = renderHook(() => useOperatingHours(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        record_count: expect.any(Number),
        date_range: expect.any(Object),
        operating_hours: expect.any(Array),
      });
    });

    it('returns operating hours records with expected structure', async () => {
      const { result } = renderHook(() => useOperatingHours(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const record = result.current.data?.operating_hours[0];
      expect(record).toMatchObject({
        theater_name: expect.any(String),
        date: expect.any(String),
        opening_time: expect.any(String),
        closing_time: expect.any(String),
      });
    });

    it('supports theater filter', async () => {
      const { result } = renderHook(
        () => useOperatingHours({ theater: 'AMC Madison 6' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('useDailyLineup', () => {
    it('fetches daily lineup for theater and date', async () => {
      const { result } = renderHook(
        () => useDailyLineup({ theater: 'AMC Madison 6', date: '2026-01-15' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        theater: expect.any(String),
        date: expect.any(String),
        showtime_count: expect.any(Number),
        showtimes: expect.any(Array),
      });
    });

    it('returns showtimes with expected structure', async () => {
      const { result } = renderHook(
        () => useDailyLineup({ theater: 'AMC Madison 6', date: '2026-01-15' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      // Cast to access showtimes array - type inference lost due to options?: any
      const data = result.current.data as { showtimes?: unknown[] } | undefined;
      const showtime = data?.showtimes?.[0];
      expect(showtime).toMatchObject({
        film_title: expect.any(String),
        showtime: expect.any(String),
      });
    });

    it('is disabled without theater param', async () => {
      const { result } = renderHook(
        () => useDailyLineup({ theater: '', date: '2026-01-15' }),
        { wrapper: createWrapper() }
      );

      // Query should not run when theater is empty
      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('usePlfFormats', () => {
    it('fetches PLF format distribution', async () => {
      const { result } = renderHook(() => usePlfFormats(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        theater_count: expect.any(Number),
        total_plf_showtimes: expect.any(Number),
        theaters: expect.any(Object),
      });
    });

    it('supports date filter', async () => {
      const { result } = renderHook(() => usePlfFormats('2026-01-15'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });
});
