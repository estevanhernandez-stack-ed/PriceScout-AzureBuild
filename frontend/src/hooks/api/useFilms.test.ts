import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useFilms, useEnrichFilm, useDiscoverFandango } from './useFilms';
import { createWrapper } from '@/test/utils';

describe('useFilms hooks', () => {
  describe('useFilms', () => {
    it('fetches films list', async () => {
      const { result } = renderHook(() => useFilms(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns films with expected structure', async () => {
      const { result } = renderHook(() => useFilms(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const film = result.current.data?.[0];
      expect(film).toMatchObject({
        film_title: expect.any(String),
      });
    });

    it('includes metadata fields when available', async () => {
      const { result } = renderHook(() => useFilms(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const film = result.current.data?.[0];
      expect(film?.imdb_id).toBeDefined();
      expect(film?.genre).toBeDefined();
    });
  });

  describe('useEnrichFilm', () => {
    it('enriches a film with metadata', async () => {
      const { result } = renderHook(() => useEnrichFilm(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate('Blockbuster Movie');
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        success: true,
      });
    });
  });

  describe('useDiscoverFandango', () => {
    it('discovers new films from Fandango', async () => {
      const { result } = renderHook(() => useDiscoverFandango(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate();
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        discovered: expect.any(Number),
      });
    });
  });
});
