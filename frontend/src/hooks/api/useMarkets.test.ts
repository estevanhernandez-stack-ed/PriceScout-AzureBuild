import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useMarkets,
  useMarketsHierarchy,
  useMarketTheaters,
  useTheaterCache,
} from './useMarkets';
import { createWrapper } from '@/test/utils';

describe('useMarkets hooks', () => {
  describe('useMarkets', () => {
    it('fetches markets list', async () => {
      const { result } = renderHook(() => useMarkets(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns markets with expected structure', async () => {
      const { result } = renderHook(() => useMarkets(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const market = result.current.data?.[0];
      expect(market).toMatchObject({
        market_name: expect.any(String),
        theater_count: expect.any(Number),
      });
    });
  });

  describe('useMarketsHierarchy', () => {
    it('fetches markets hierarchy', async () => {
      const { result } = renderHook(() => useMarketsHierarchy(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('useMarketTheaters', () => {
    it('fetches theaters in a market', async () => {
      const { result } = renderHook(
        () => useMarketTheaters('Madison'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
    });

    it('returns theaters with expected structure', async () => {
      const { result } = renderHook(
        () => useMarketTheaters('Madison'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const theater = result.current.data?.[0];
      expect(theater).toMatchObject({
        theater_name: expect.any(String),
        market: expect.any(String),
      });
    });

    it('is disabled when market name is empty', async () => {
      const { result } = renderHook(
        () => useMarketTheaters(''),
        { wrapper: createWrapper() }
      );

      expect(result.current.isFetching).toBe(false);
    });
  });

  describe('useTheaterCache', () => {
    it('fetches full theater cache', async () => {
      const { result } = renderHook(() => useTheaterCache(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        metadata: expect.any(Object),
        markets: expect.any(Object),
      });
    });

    it('includes metadata with last updated', async () => {
      const { result } = renderHook(() => useTheaterCache(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.metadata?.last_updated).toBeDefined();
    });
  });
});
