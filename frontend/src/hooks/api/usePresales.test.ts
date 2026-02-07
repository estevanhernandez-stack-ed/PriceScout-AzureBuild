import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  usePresales,
  usePresaleFilms,
  usePresaleCircuits,
} from './usePresales';
import { createWrapper } from '@/test/utils';

describe('usePresales hooks', () => {
  describe('usePresales', () => {
    it('fetches presale snapshots', async () => {
      const { result } = renderHook(() => usePresales(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
    });

    it('returns snapshots with expected structure', async () => {
      const { result } = renderHook(() => usePresales(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const snapshot = result.current.data?.[0];
      expect(snapshot).toMatchObject({
        circuit_name: expect.any(String),
        film_title: expect.any(String),
        total_tickets_sold: expect.any(Number),
        total_revenue: expect.any(Number),
      });
    });

    it('supports filtering by circuit', async () => {
      const { result } = renderHook(
        () => usePresales({ circuit_name: 'AMC' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });

    it('supports market scope filter', async () => {
      const { result } = renderHook(
        () => usePresales({ market_scope: 'our_markets' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('usePresaleFilms', () => {
    it('fetches presale films list', async () => {
      const { result } = renderHook(() => usePresaleFilms(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
    });

    it('returns films with expected structure', async () => {
      const { result } = renderHook(() => usePresaleFilms(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const film = result.current.data?.[0];
      expect(film).toMatchObject({
        film_title: expect.any(String),
        release_date: expect.any(String),
        current_tickets: expect.any(Number),
        days_until_release: expect.any(Number),
      });
    });
  });

  describe('usePresaleCircuits', () => {
    it('fetches presale circuits list', async () => {
      const { result } = renderHook(() => usePresaleCircuits(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
    });

    it('returns circuits with expected structure', async () => {
      const { result } = renderHook(() => usePresaleCircuits(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const circuit = result.current.data?.[0];
      expect(circuit).toMatchObject({
        circuit_name: expect.any(String),
        total_films: expect.any(Number),
        total_tickets: expect.any(Number),
        total_revenue: expect.any(Number),
      });
    });
  });
});
