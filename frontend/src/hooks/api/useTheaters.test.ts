import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import {
  useTheaters,
  useUnmatchedTheaters,
  useTheaterFilms,
  useMatchTheater,
  usePriceHistory,
} from './useTheaters';
import { createWrapper } from '@/test/utils';

describe('useTheaters hooks', () => {
  describe('useTheaters', () => {
    it('fetches theaters list', async () => {
      const { result } = renderHook(() => useTheaters(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns theaters with expected structure', async () => {
      const { result } = renderHook(() => useTheaters(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const theater = result.current.data?.[0];
      expect(theater).toMatchObject({
        theater_name: expect.any(String),
        market: expect.any(String),
      });
    });
  });

  describe('useUnmatchedTheaters', () => {
    it('fetches unmatched theaters list', async () => {
      const { result } = renderHook(() => useUnmatchedTheaters(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        theaters: expect.any(Array),
        total_count: expect.any(Number),
      });
    });
  });

  describe('useTheaterFilms', () => {
    it('fetches films for a theater', async () => {
      const { result } = renderHook(() => useTheaterFilms('AMC Madison 6'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns films with expected structure', async () => {
      const { result } = renderHook(() => useTheaterFilms('AMC Madison 6'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const film = result.current.data?.[0];
      expect(film).toMatchObject({
        film_title: expect.any(String),
      });
    });

    it('is disabled without theater name', async () => {
      const { result } = renderHook(() => useTheaterFilms(''), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useMatchTheater', () => {
    it('matches a theater successfully', async () => {
      const { result } = renderHook(() => useMatchTheater(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          theater_name: 'New Theater',
          market: 'Milwaukee',
          fandango_url: 'https://www.fandango.com/new-theater',
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        success: true,
        theater_name: expect.any(String),
      });
    });
  });

  describe('usePriceHistory', () => {
    it('fetches price history for a theater', async () => {
      const { result } = renderHook(() => usePriceHistory('AMC Madison 6'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns price history with expected structure', async () => {
      const { result } = renderHook(() => usePriceHistory('AMC Madison 6'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const entry = result.current.data?.[0];
      expect(entry).toMatchObject({
        date: expect.any(String),
        ticket_type: expect.any(String),
        avg_price: expect.any(Number),
      });
    });

    it('supports filter options', async () => {
      const { result } = renderHook(
        () => usePriceHistory('AMC Madison 6', { days: 7, ticketType: 'Adult' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });

    it('is disabled without theater name', async () => {
      const { result } = renderHook(() => usePriceHistory(''), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });
});
