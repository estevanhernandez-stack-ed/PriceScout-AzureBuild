import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  usePriceChecks,
  useLatestPrices,
  usePriceCheckSummary,
  usePriceComparison,
} from './usePriceChecks';
import { createWrapper } from '@/test/utils';

describe('usePriceChecks hooks', () => {
  describe('usePriceChecks', () => {
    it('fetches price checks list', async () => {
      const { result } = renderHook(() => usePriceChecks(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        total_records: expect.any(Number),
        price_checks: expect.any(Array),
      });
      expect(result.current.data?.price_checks.length).toBeGreaterThan(0);
    });

    it('accepts filter parameters', async () => {
      const { result } = renderHook(
        () => usePriceChecks({ theaterName: 'AMC Madison 6', limit: 10 }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('useLatestPrices', () => {
    it('fetches latest prices for a theater', async () => {
      const { result } = renderHook(() => useLatestPrices('AMC Madison 6'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
    });

    it('is disabled without theater name', () => {
      const { result } = renderHook(() => useLatestPrices(undefined), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('usePriceCheckSummary', () => {
    it('fetches price check summary', async () => {
      const { result } = renderHook(() => usePriceCheckSummary(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        total_checks: expect.any(Number),
        avg_price: expect.any(Number),
      });
    });
  });

  describe('usePriceComparison', () => {
    it('fetches price comparison data', async () => {
      const { result } = renderHook(() => usePriceComparison(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('accepts filter parameters', async () => {
      const { result } = renderHook(
        () => usePriceComparison({ market: 'Madison', ticketType: 'Adult' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });
});
