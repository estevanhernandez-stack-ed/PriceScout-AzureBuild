import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import {
  useCircuitBenchmarks,
  useCircuitBenchmarkWeeks,
  useWeekBenchmarks,
  useSyncCircuitBenchmarks,
} from './useCircuitBenchmarks';
import { createWrapper } from '@/test/utils';

describe('useCircuitBenchmarks hooks', () => {
  describe('useCircuitBenchmarks', () => {
    it('fetches circuit benchmarks list', async () => {
      const { result } = renderHook(() => useCircuitBenchmarks(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        benchmarks: expect.any(Array),
        total_count: expect.any(Number),
      });
    });

    it('returns benchmarks with expected structure', async () => {
      const { result } = renderHook(() => useCircuitBenchmarks(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const benchmark = result.current.data?.benchmarks[0];
      expect(benchmark).toMatchObject({
        circuit_name: expect.any(String),
        week_ending_date: expect.any(String),
        total_showtimes: expect.any(Number),
        total_theaters: expect.any(Number),
        plf_total_pct: expect.any(Number),
      });
    });

    it('includes available weeks', async () => {
      const { result } = renderHook(() => useCircuitBenchmarks(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.available_weeks).toBeInstanceOf(Array);
      expect(result.current.data?.available_weeks.length).toBeGreaterThan(0);
    });

    it('supports filtering by circuit name', async () => {
      const { result } = renderHook(
        () => useCircuitBenchmarks({ circuit_name: 'AMC' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.benchmarks).toBeDefined();
    });

    it('supports filtering by week', async () => {
      const { result } = renderHook(
        () => useCircuitBenchmarks({ week_ending_date: '2026-01-12' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.benchmarks).toBeDefined();
    });
  });

  describe('useCircuitBenchmarkWeeks', () => {
    it('fetches available weeks with summary', async () => {
      const { result } = renderHook(() => useCircuitBenchmarkWeeks(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns weeks with expected structure', async () => {
      const { result } = renderHook(() => useCircuitBenchmarkWeeks(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const week = result.current.data?.[0];
      expect(week).toMatchObject({
        week_ending_date: expect.any(String),
        circuit_count: expect.any(Number),
        total_showtimes: expect.any(Number),
        data_freshness: expect.any(String),
      });
    });
  });

  describe('useWeekBenchmarks', () => {
    it('fetches benchmarks for specific week', async () => {
      const { result } = renderHook(
        () => useWeekBenchmarks('2026-01-12'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        week_ending_date: '2026-01-12',
        circuit_count: expect.any(Number),
        benchmarks: expect.any(Array),
      });
    });

    it('is disabled when no week provided', async () => {
      const { result } = renderHook(
        () => useWeekBenchmarks(''),
        { wrapper: createWrapper() }
      );

      // Should not fetch when week is empty
      expect(result.current.isFetching).toBe(false);
    });
  });

  describe('useSyncCircuitBenchmarks', () => {
    it('triggers EntTelligence sync', async () => {
      const { result } = renderHook(() => useSyncCircuitBenchmarks(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate();
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        status: expect.any(String),
        message: expect.any(String),
      });
    });
  });
});
