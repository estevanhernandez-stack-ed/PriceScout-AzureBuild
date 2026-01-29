import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import {
  useCacheStatus,
  useCacheMarkets,
  useUnmatchedTheaters,
  useRefreshCache,
  useMatchTheater,
} from './useCache';
import { createWrapper } from '@/test/utils';

describe('useCache hooks', () => {
  describe('useCacheStatus', () => {
    it('fetches cache status', async () => {
      const { result } = renderHook(() => useCacheStatus(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        cache_file_exists: true,
        market_count: expect.any(Number),
        theater_count: expect.any(Number),
        file_size_kb: expect.any(Number),
      });
    });

    it('includes metadata when available', async () => {
      const { result } = renderHook(() => useCacheStatus(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.metadata).toBeDefined();
      expect(result.current.data?.metadata?.last_updated).toBeDefined();
    });
  });

  describe('useCacheMarkets', () => {
    it('fetches list of markets', async () => {
      const { result } = renderHook(() => useCacheMarkets(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.markets).toBeInstanceOf(Array);
      expect(result.current.data?.total_count).toBeGreaterThan(0);
    });

    it('returns market with expected structure', async () => {
      const { result } = renderHook(() => useCacheMarkets(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const market = result.current.data?.markets[0];
      expect(market).toMatchObject({
        market_name: expect.any(String),
        total_theaters: expect.any(Number),
        active_theaters: expect.any(Number),
        not_on_fandango: expect.any(Number),
      });
    });
  });

  describe('useUnmatchedTheaters', () => {
    it('fetches unmatched theaters list', async () => {
      const { result } = renderHook(() => useUnmatchedTheaters(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.theaters).toBeInstanceOf(Array);
      expect(result.current.data?.total_count).toBeDefined();
    });

    it('returns theater with expected structure', async () => {
      const { result } = renderHook(() => useUnmatchedTheaters(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      if (result.current.data && result.current.data.theaters.length > 0) {
        const theater = result.current.data.theaters[0];
        expect(theater).toMatchObject({
          theater_name: expect.any(String),
          market: expect.any(String),
          status: expect.stringMatching(/no_match|not_on_fandango|closed/),
        });
      }
    });
  });

  describe('useRefreshCache', () => {
    it('triggers cache refresh mutation', async () => {
      const { result } = renderHook(() => useRefreshCache(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        status: 'started',
        message: expect.any(String),
      });
    });

    it('supports force full refresh option', async () => {
      const { result } = renderHook(() => useRefreshCache(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({ force_full_refresh: true });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useMatchTheater', () => {
    it('matches theater successfully', async () => {
      const { result } = renderHook(() => useMatchTheater(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          theater_name: 'Test Theater',
          market: 'Madison',
          fandango_url: 'https://www.fandango.com/test-theater',
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        success: true,
        theater_name: 'Test Theater',
      });
    });

    it('can mark theater as closed', async () => {
      const { result } = renderHook(() => useMatchTheater(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          theater_name: 'Closed Cinema',
          market: 'Milwaukee',
          mark_as_closed: true,
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });
});
