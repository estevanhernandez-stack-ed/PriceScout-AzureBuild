import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useTheaterCoverage,
  useAllTheaterCoverage,
  useCoverageHierarchy,
  useMarketCoverage,
  getDayName,
  getCoverageLevel,
  getSeverityColor,
  getCoverageColor,
  formatDaysMissing,
} from './useCoverageGaps';
import { createWrapper } from '@/test/utils';

describe('useCoverageGaps hooks', () => {
  // =========================================================================
  // Utility / helper functions
  // =========================================================================
  describe('getDayName', () => {
    it('returns correct day names for valid indices', () => {
      expect(getDayName(0)).toBe('Monday');
      expect(getDayName(1)).toBe('Tuesday');
      expect(getDayName(2)).toBe('Wednesday');
      expect(getDayName(3)).toBe('Thursday');
      expect(getDayName(4)).toBe('Friday');
      expect(getDayName(5)).toBe('Saturday');
      expect(getDayName(6)).toBe('Sunday');
    });

    it('returns Unknown for out-of-range index', () => {
      expect(getDayName(7)).toBe('Unknown');
      expect(getDayName(-1)).toBe('Unknown');
    });
  });

  describe('getCoverageLevel', () => {
    it('returns excellent for score >= 90', () => {
      expect(getCoverageLevel(90)).toBe('excellent');
      expect(getCoverageLevel(100)).toBe('excellent');
    });

    it('returns good for score >= 70', () => {
      expect(getCoverageLevel(70)).toBe('good');
      expect(getCoverageLevel(89)).toBe('good');
    });

    it('returns fair for score >= 50', () => {
      expect(getCoverageLevel(50)).toBe('fair');
      expect(getCoverageLevel(69)).toBe('fair');
    });

    it('returns poor for score < 50', () => {
      expect(getCoverageLevel(0)).toBe('poor');
      expect(getCoverageLevel(49)).toBe('poor');
    });
  });

  describe('getSeverityColor', () => {
    it('returns red for error severity', () => {
      expect(getSeverityColor('error')).toBe('text-red-500');
    });

    it('returns yellow for warning severity', () => {
      expect(getSeverityColor('warning')).toBe('text-yellow-500');
    });
  });

  describe('getCoverageColor', () => {
    it('returns green for score >= 90', () => {
      expect(getCoverageColor(90)).toBe('text-green-600');
      expect(getCoverageColor(100)).toBe('text-green-600');
    });

    it('returns blue for score >= 70', () => {
      expect(getCoverageColor(70)).toBe('text-blue-600');
      expect(getCoverageColor(89)).toBe('text-blue-600');
    });

    it('returns yellow for score >= 50', () => {
      expect(getCoverageColor(50)).toBe('text-yellow-600');
      expect(getCoverageColor(69)).toBe('text-yellow-600');
    });

    it('returns red for score < 50', () => {
      expect(getCoverageColor(0)).toBe('text-red-600');
      expect(getCoverageColor(49)).toBe('text-red-600');
    });
  });

  describe('formatDaysMissing', () => {
    it('returns "None" when all days have data', () => {
      expect(formatDaysMissing([0, 1, 2, 3, 4, 5, 6])).toBe('None');
    });

    it('lists missing day names', () => {
      expect(formatDaysMissing([0, 1, 2, 3, 4])).toBe('Saturday, Sunday');
    });

    it('returns all days when no data', () => {
      const result = formatDaysMissing([]);
      expect(result).toContain('Monday');
      expect(result).toContain('Sunday');
    });

    it('handles a single missing day', () => {
      expect(formatDaysMissing([0, 1, 2, 3, 4, 5])).toBe('Sunday');
    });
  });

  // =========================================================================
  // Query hooks
  // =========================================================================
  describe('useTheaterCoverage', () => {
    it('fetches coverage for a specific theater', async () => {
      const { result } = renderHook(
        () => useTheaterCoverage('AMC Madison 6'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.theater_name).toBe('AMC Madison 6');
      expect(result.current.data?.overall_coverage_score).toBeDefined();
      expect(result.current.data?.gaps).toBeInstanceOf(Array);
    });

    it('does not fetch when theaterName is null', () => {
      const { result } = renderHook(() => useTheaterCoverage(null), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('passes lookbackDays option', async () => {
      const { result } = renderHook(
        () => useTheaterCoverage('AMC Madison 6', { lookbackDays: 60 }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toBeDefined();
    });
  });

  describe('useAllTheaterCoverage', () => {
    it('fetches coverage for all theaters', async () => {
      const { result } = renderHook(() => useAllTheaterCoverage(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.total).toBeDefined();
      expect(result.current.data?.theaters).toBeInstanceOf(Array);
    });

    it('supports filter options', async () => {
      const { result } = renderHook(
        () => useAllTheaterCoverage({ lookbackDays: 30, circuit: 'AMC' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toBeDefined();
    });
  });

  describe('useCoverageHierarchy', () => {
    it('fetches coverage hierarchy', async () => {
      const { result } = renderHook(() => useCoverageHierarchy(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
      const companies = Object.keys(result.current.data ?? {});
      expect(companies.length).toBeGreaterThan(0);
    });
  });

  describe('useMarketCoverage', () => {
    it('fetches market coverage detail', async () => {
      const { result } = renderHook(
        () => useMarketCoverage('Director A', 'Madison'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.market_name).toBe('Madison');
      expect(result.current.data?.theaters).toBeInstanceOf(Array);
    });

    it('does not fetch when director is null', () => {
      const { result } = renderHook(
        () => useMarketCoverage(null, 'Madison'),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('does not fetch when market is null', () => {
      const { result } = renderHook(
        () => useMarketCoverage('Director A', null),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });
});
