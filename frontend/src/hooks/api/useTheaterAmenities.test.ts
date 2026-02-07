import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useTheaterAmenities,
  useTheaterAmenity,
  useAmenitiesSummary,
  useCreateTheaterAmenities,
  useUpdateTheaterAmenities,
  useDeleteTheaterAmenities,
  useDiscoverTheaterAmenities,
  useDiscoverAllTheaterAmenities,
  useFormatSummary,
  useScreenCountEstimate,
  theaterAmenitiesKeys,
  getFormatCategoryLabel,
  getPremiumFormatCount,
  getAmenityScoreColor,
  FORMAT_CATEGORY_LABELS,
  type TheaterAmenities,
} from './useTheaterAmenities';
import { createWrapper } from '@/test/utils';

describe('useTheaterAmenities hooks', () => {
  // =========================================================================
  // Query key factory
  // =========================================================================
  describe('theaterAmenitiesKeys', () => {
    it('generates correct key shapes', () => {
      expect(theaterAmenitiesKeys.all).toEqual(['theater-amenities']);
      expect(theaterAmenitiesKeys.lists()).toEqual(['theater-amenities', 'list']);
      expect(theaterAmenitiesKeys.list({ circuit_name: 'AMC' })).toEqual([
        'theater-amenities',
        'list',
        { circuit_name: 'AMC' },
      ]);
      expect(theaterAmenitiesKeys.detail(1)).toEqual(['theater-amenities', 'detail', 1]);
      expect(theaterAmenitiesKeys.summary()).toEqual(['theater-amenities', 'summary']);
      expect(theaterAmenitiesKeys.formatSummary(30)).toEqual([
        'theater-amenities',
        'format-summary',
        30,
      ]);
      expect(theaterAmenitiesKeys.screenCounts('AMC Madison 6', 14)).toEqual([
        'theater-amenities',
        'screen-counts',
        'AMC Madison 6',
        14,
      ]);
    });
  });

  // =========================================================================
  // Utility functions
  // =========================================================================
  describe('getFormatCategoryLabel', () => {
    it('returns known labels', () => {
      expect(getFormatCategoryLabel('imax')).toBe('IMAX');
      expect(getFormatCategoryLabel('dolby')).toBe('Dolby');
      expect(getFormatCategoryLabel('3d')).toBe('3D');
      expect(getFormatCategoryLabel('4dx')).toBe('4DX/MX4D');
      expect(getFormatCategoryLabel('rpx')).toBe('RPX');
    });

    it('returns the raw key for unknown categories', () => {
      expect(getFormatCategoryLabel('laser')).toBe('laser');
    });
  });

  describe('FORMAT_CATEGORY_LABELS', () => {
    it('includes expected entries', () => {
      expect(FORMAT_CATEGORY_LABELS).toHaveProperty('imax');
      expect(FORMAT_CATEGORY_LABELS).toHaveProperty('standard');
      expect(FORMAT_CATEGORY_LABELS).toHaveProperty('other');
    });
  });

  describe('getPremiumFormatCount', () => {
    it('counts all premium flags', () => {
      const amenities = {
        has_imax: true,
        has_dolby_cinema: true,
        has_dolby_atmos: true,
        has_rpx: false,
        has_4dx: false,
        has_screenx: false,
        has_dbox: false,
      } as TheaterAmenities;

      expect(getPremiumFormatCount(amenities)).toBe(3);
    });

    it('returns 0 when no premium formats', () => {
      const amenities = {
        has_imax: false,
        has_dolby_cinema: false,
        has_dolby_atmos: false,
        has_rpx: false,
        has_4dx: false,
        has_screenx: false,
        has_dbox: false,
      } as TheaterAmenities;

      expect(getPremiumFormatCount(amenities)).toBe(0);
    });

    it('returns 7 when all premium formats are present', () => {
      const amenities = {
        has_imax: true,
        has_dolby_cinema: true,
        has_dolby_atmos: true,
        has_rpx: true,
        has_4dx: true,
        has_screenx: true,
        has_dbox: true,
      } as TheaterAmenities;

      expect(getPremiumFormatCount(amenities)).toBe(7);
    });
  });

  describe('getAmenityScoreColor', () => {
    it('returns blue for score >= 8', () => {
      expect(getAmenityScoreColor(8)).toBe('blue');
      expect(getAmenityScoreColor(10)).toBe('blue');
    });

    it('returns green for score >= 5', () => {
      expect(getAmenityScoreColor(5)).toBe('green');
      expect(getAmenityScoreColor(7)).toBe('green');
    });

    it('returns yellow for score >= 2', () => {
      expect(getAmenityScoreColor(2)).toBe('yellow');
      expect(getAmenityScoreColor(4)).toBe('yellow');
    });

    it('returns gray for score < 2', () => {
      expect(getAmenityScoreColor(0)).toBe('gray');
      expect(getAmenityScoreColor(1)).toBe('gray');
    });
  });

  // =========================================================================
  // Query hooks
  // =========================================================================
  describe('useTheaterAmenities', () => {
    it('fetches amenities list', async () => {
      const { result } = renderHook(() => useTheaterAmenities(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
      expect(result.current.data?.[0]).toMatchObject({
        id: expect.any(Number),
        theater_name: expect.any(String),
      });
    });

    it('supports filters', async () => {
      const { result } = renderHook(
        () => useTheaterAmenities({ circuit_name: 'AMC', has_imax: true }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toBeDefined();
    });
  });

  describe('useTheaterAmenity', () => {
    it('fetches a single theater amenity by ID', async () => {
      const { result } = renderHook(() => useTheaterAmenity(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.theater_name).toBe('AMC Madison 6');
      expect(result.current.data?.id).toBe(1);
    });

    it('does not fetch when id is null', () => {
      const { result } = renderHook(() => useTheaterAmenity(null), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useAmenitiesSummary', () => {
    it('fetches amenity summary', async () => {
      const { result } = renderHook(() => useAmenitiesSummary(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.[0]).toMatchObject({
        circuit_name: expect.any(String),
        theater_count: expect.any(Number),
        avg_amenity_score: expect.any(Number),
      });
    });
  });

  describe('useFormatSummary', () => {
    it('fetches format summary', async () => {
      const { result } = renderHook(() => useFormatSummary(30), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.total_theaters_with_plf).toBeGreaterThan(0);
      expect(result.current.data?.by_format).toBeDefined();
    });

    it('respects enabled option', () => {
      const { result } = renderHook(() => useFormatSummary(30, { enabled: false }), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useScreenCountEstimate', () => {
    it('fetches screen count estimate', async () => {
      const { result } = renderHook(() => useScreenCountEstimate('AMC Madison 6'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.estimated_total_screens).toBe(12);
    });

    it('does not fetch when theaterName is null', () => {
      const { result } = renderHook(() => useScreenCountEstimate(null), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // =========================================================================
  // Mutation hooks
  // =========================================================================
  describe('useCreateTheaterAmenities', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useCreateTheaterAmenities(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useUpdateTheaterAmenities', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useUpdateTheaterAmenities(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDeleteTheaterAmenities', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useDeleteTheaterAmenities(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDiscoverTheaterAmenities', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useDiscoverTheaterAmenities(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDiscoverAllTheaterAmenities', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useDiscoverAllTheaterAmenities(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });
});
