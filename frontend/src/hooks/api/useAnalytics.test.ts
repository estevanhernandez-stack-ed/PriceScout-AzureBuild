import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useDashboardStats, useScrapeActivity } from './useAnalytics';
import { createWrapper } from '@/test/utils';

describe('useAnalytics hooks', () => {
  describe('useDashboardStats', () => {
    it('fetches dashboard statistics', async () => {
      const { result } = renderHook(() => useDashboardStats(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        total_price_checks: expect.any(Number),
        active_alerts: expect.any(Number),
        avg_price: expect.any(Number),
        total_theaters: expect.any(Number),
      });
    });

    it('returns price check change percentage', async () => {
      const { result } = renderHook(() => useDashboardStats(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.price_checks_change_pct).toBeDefined();
      expect(typeof result.current.data?.price_checks_change_pct).toBe('number');
    });

    it('accepts custom days parameter', async () => {
      const { result } = renderHook(() => useDashboardStats(7), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('useScrapeActivity', () => {
    it('fetches scrape activity by day', async () => {
      const { result } = renderHook(() => useScrapeActivity(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns activity entries with expected structure', async () => {
      const { result } = renderHook(() => useScrapeActivity(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const entry = result.current.data?.[0];
      expect(entry).toMatchObject({
        day_name: expect.any(String),
        day_index: expect.any(Number),
        scrape_count: expect.any(Number),
        records_scraped: expect.any(Number),
      });
    });

    it('accepts custom days parameter', async () => {
      const { result } = renderHook(() => useScrapeActivity(14), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });
});
