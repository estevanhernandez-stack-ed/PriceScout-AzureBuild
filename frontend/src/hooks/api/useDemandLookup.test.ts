import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useDemandLookup,
  demandKey,
  getFillRateColor,
  getFillRateBadgeVariant,
  computeDemandSummary,
  buildDemandMap,
} from './useDemandLookup';
import type { DemandMetric } from './useDemandLookup';
import { createWrapper } from '@/test/utils';

const mockMetrics: DemandMetric[] = [
  {
    theater_name: 'AMC Madison 6',
    film_title: 'Blockbuster Movie',
    play_date: '2026-01-20',
    showtime: '7:00 PM',
    format: 'Standard',
    circuit_name: 'AMC',
    ticket_type: 'Adult',
    price: 14.99,
    capacity: 200,
    available: 120,
    tickets_sold: 80,
    fill_rate_pct: 40.0,
  },
  {
    theater_name: 'AMC Madison 6',
    film_title: 'Blockbuster Movie',
    play_date: '2026-01-20',
    showtime: '9:30 PM',
    format: 'IMAX',
    circuit_name: 'AMC',
    ticket_type: 'Adult',
    price: 19.99,
    capacity: 300,
    available: 50,
    tickets_sold: 250,
    fill_rate_pct: 83.3,
  },
];

describe('useDemandLookup hooks', () => {
  describe('useDemandLookup', () => {
    it('fetches demand data for theaters and date', async () => {
      const { result } = renderHook(
        () => useDemandLookup(['AMC Madison 6'], '2026-01-20'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns demand metrics with expected structure', async () => {
      const { result } = renderHook(
        () => useDemandLookup(['AMC Madison 6'], '2026-01-20'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const metric = result.current.data?.[0];
      expect(metric).toMatchObject({
        theater_name: expect.any(String),
        film_title: expect.any(String),
        play_date: expect.any(String),
        showtime: expect.any(String),
        price: expect.any(Number),
        capacity: expect.any(Number),
        tickets_sold: expect.any(Number),
        fill_rate_pct: expect.any(Number),
      });
    });

    it('is disabled when theaters array is empty', () => {
      const { result } = renderHook(
        () => useDemandLookup([], '2026-01-20'),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('is disabled when dateFrom is empty', () => {
      const { result } = renderHook(
        () => useDemandLookup(['AMC Madison 6'], ''),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('is disabled when enabled is false', () => {
      const { result } = renderHook(
        () => useDemandLookup(['AMC Madison 6'], '2026-01-20', undefined, undefined, false),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('demandKey', () => {
    it('builds a lookup key from theater, film, and showtime', () => {
      const key = demandKey('AMC Madison 6', 'Blockbuster Movie', '7:00 PM');
      expect(key).toBe('AMC Madison 6|Blockbuster Movie|7:00 PM');
    });
  });

  describe('getFillRateColor', () => {
    it('returns green for low fill rates', () => {
      expect(getFillRateColor(0)).toBe('text-green-400');
      expect(getFillRateColor(49)).toBe('text-green-400');
    });

    it('returns yellow for medium fill rates', () => {
      expect(getFillRateColor(50)).toBe('text-yellow-400');
      expect(getFillRateColor(74)).toBe('text-yellow-400');
    });

    it('returns red for high fill rates', () => {
      expect(getFillRateColor(75)).toBe('text-red-400');
      expect(getFillRateColor(100)).toBe('text-red-400');
    });
  });

  describe('getFillRateBadgeVariant', () => {
    it('returns secondary for low fill rates', () => {
      expect(getFillRateBadgeVariant(30)).toBe('secondary');
    });

    it('returns default for medium fill rates', () => {
      expect(getFillRateBadgeVariant(60)).toBe('default');
    });

    it('returns destructive for high fill rates', () => {
      expect(getFillRateBadgeVariant(80)).toBe('destructive');
    });
  });

  describe('computeDemandSummary', () => {
    it('computes summary from demand metrics', () => {
      const summary = computeDemandSummary(mockMetrics);

      expect(summary.totalShowtimes).toBe(2);
      expect(summary.showtimesWithSales).toBe(2);
      expect(summary.avgFillRate).toBeCloseTo(61.7, 0);
      expect(summary.highDemandCount).toBe(1); // 83.3% >= 70%
    });

    it('handles empty metrics array', () => {
      const summary = computeDemandSummary([]);

      expect(summary.totalShowtimes).toBe(0);
      expect(summary.showtimesWithSales).toBe(0);
      expect(summary.avgFillRate).toBe(0);
      expect(summary.highDemandCount).toBe(0);
    });
  });

  describe('buildDemandMap', () => {
    it('builds a map from demand metrics', () => {
      const map = buildDemandMap(mockMetrics);

      expect(map.size).toBe(2);
      expect(map.get('AMC Madison 6|Blockbuster Movie|7:00 PM')).toBeDefined();
      expect(map.get('AMC Madison 6|Blockbuster Movie|9:30 PM')).toBeDefined();
    });

    it('returns empty map for empty input', () => {
      const map = buildDemandMap([]);
      expect(map.size).toBe(0);
    });
  });
});
