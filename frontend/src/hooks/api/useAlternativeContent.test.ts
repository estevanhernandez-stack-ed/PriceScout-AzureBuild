import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useACFilms,
  useACFilm,
  useCreateACFilm,
  useUpdateACFilm,
  useDeleteACFilm,
  useRunACDetection,
  useACDetectionPreview,
  useCheckFilm,
  useCircuitACPricing,
  useCircuitACPricingByName,
  useUpdateCircuitACPricing,
  getContentTypeLabel,
  getContentTypeColor,
  isAlternativeContent,
  CONTENT_TYPE_LABELS,
  CONTENT_TYPE_COLORS,
} from './useAlternativeContent';
import { createWrapper } from '@/test/utils';

describe('useAlternativeContent hooks', () => {
  // =========================================================================
  // Utility / helper functions
  // =========================================================================
  describe('CONTENT_TYPE_LABELS', () => {
    it('has expected content type entries', () => {
      expect(CONTENT_TYPE_LABELS).toHaveProperty('fathom_event', 'Fathom Event');
      expect(CONTENT_TYPE_LABELS).toHaveProperty('opera_broadcast', 'Opera Broadcast');
      expect(CONTENT_TYPE_LABELS).toHaveProperty('anime_event', 'Anime Event');
      expect(CONTENT_TYPE_LABELS).toHaveProperty('unknown', 'Unknown');
    });
  });

  describe('CONTENT_TYPE_COLORS', () => {
    it('has color classes for known types', () => {
      expect(CONTENT_TYPE_COLORS.fathom_event).toContain('bg-purple');
      expect(CONTENT_TYPE_COLORS.opera_broadcast).toContain('bg-red');
      expect(CONTENT_TYPE_COLORS.unknown).toContain('bg-gray');
    });
  });

  describe('getContentTypeLabel', () => {
    it('returns labels for known types', () => {
      expect(getContentTypeLabel('fathom_event')).toBe('Fathom Event');
      expect(getContentTypeLabel('opera_broadcast')).toBe('Opera Broadcast');
      expect(getContentTypeLabel('concert_film')).toBe('Concert Film');
    });

    it('returns raw key for unknown types', () => {
      expect(getContentTypeLabel('custom_type')).toBe('custom_type');
    });
  });

  describe('getContentTypeColor', () => {
    it('returns correct color for known types', () => {
      expect(getContentTypeColor('fathom_event')).toContain('bg-purple');
      expect(getContentTypeColor('anime_event')).toContain('bg-green');
    });

    it('returns gray for unknown types', () => {
      expect(getContentTypeColor('custom_type')).toContain('bg-gray');
    });
  });

  describe('isAlternativeContent', () => {
    it('returns true when normalized title is in the set', () => {
      const acSet = new Set(['met opera la boheme', 'nt live hamlet']);
      expect(isAlternativeContent('Met Opera La Boheme', acSet)).toBe(true);
    });

    it('returns false when title is not in the set', () => {
      const acSet = new Set(['met opera la boheme']);
      expect(isAlternativeContent('Avengers Endgame', acSet)).toBe(false);
    });

    it('strips parenthetical content during normalization', () => {
      const acSet = new Set(['met opera la boheme']);
      expect(isAlternativeContent('Met Opera La Boheme (2026 Encore)', acSet)).toBe(true);
    });

    it('handles extra whitespace', () => {
      const acSet = new Set(['nt live hamlet']);
      expect(isAlternativeContent('  NT  Live  Hamlet  ', acSet)).toBe(true);
    });
  });

  // =========================================================================
  // Query hooks
  // =========================================================================
  describe('useACFilms', () => {
    it('fetches AC films list', async () => {
      const { result } = renderHook(() => useACFilms(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.total).toBeDefined();
      expect(result.current.data?.films).toBeInstanceOf(Array);
      expect(result.current.data?.films?.length).toBeGreaterThan(0);
      expect(result.current.data?.content_types).toBeInstanceOf(Array);
    });

    it('supports filter options', async () => {
      const { result } = renderHook(
        () => useACFilms({ contentType: 'opera_broadcast', isVerified: true }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toBeDefined();
    });
  });

  describe('useACFilm', () => {
    it('fetches a single AC film by ID', async () => {
      const { result } = renderHook(() => useACFilm(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.id).toBe(1);
      expect(result.current.data?.film_title).toBeDefined();
    });

    it('does not fetch when filmId is null', () => {
      const { result } = renderHook(() => useACFilm(null), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useACDetectionPreview', () => {
    it('does not fetch when enabled is false (default)', () => {
      const { result } = renderHook(() => useACDetectionPreview(90, false), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('fetches preview when enabled', async () => {
      const { result } = renderHook(() => useACDetectionPreview(90, true), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.title_detected).toBeInstanceOf(Array);
      expect(result.current.data?.total_title).toBeDefined();
    });
  });

  describe('useCheckFilm', () => {
    it('checks if a film is alternative content', async () => {
      const { result } = renderHook(() => useCheckFilm('Met Opera: La Boheme'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.is_alternative_content).toBe(true);
      expect(result.current.data?.content_type).toBe('opera_broadcast');
    });

    it('does not fetch when filmTitle is null', () => {
      const { result } = renderHook(() => useCheckFilm(null), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useCircuitACPricing', () => {
    it('fetches all circuit AC pricing', async () => {
      const { result } = renderHook(() => useCircuitACPricing(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
      expect(result.current.data?.[0]).toMatchObject({
        circuit_name: expect.any(String),
        content_type: expect.any(String),
      });
    });
  });

  describe('useCircuitACPricingByName', () => {
    it('fetches AC pricing for a specific circuit', async () => {
      const { result } = renderHook(() => useCircuitACPricingByName('AMC'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.circuit_name).toBe('AMC');
    });

    it('does not fetch when circuitName is null', () => {
      const { result } = renderHook(() => useCircuitACPricingByName(null), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // =========================================================================
  // Mutation hooks
  // =========================================================================
  describe('useCreateACFilm', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useCreateACFilm(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useUpdateACFilm', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useUpdateACFilm(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDeleteACFilm', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useDeleteACFilm(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useRunACDetection', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useRunACDetection(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useUpdateCircuitACPricing', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useUpdateCircuitACPricing(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });
});
