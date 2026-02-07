import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useDiscountPrograms,
  useCreateDiscountProgram,
  useDeleteDiscountProgram,
  useProfileGaps,
  useResolveGap,
  useProfileVersions,
  useCompanyProfiles,
  useCompanyProfile,
} from './useDiscountPrograms';
import { createWrapper } from '@/test/utils';

describe('useDiscountPrograms hooks', () => {
  // =========================================================================
  // DISCOUNT PROGRAMS QUERY HOOKS
  // =========================================================================

  describe('useDiscountPrograms', () => {
    it('fetches discount programs for a circuit', async () => {
      const { result } = renderHook(
        () => useDiscountPrograms('AMC'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns programs with expected structure', async () => {
      const { result } = renderHook(
        () => useDiscountPrograms('AMC'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const program = result.current.data?.[0];
      expect(program).toMatchObject({
        program_id: expect.any(Number),
        circuit_name: expect.any(String),
        program_name: expect.any(String),
        day_of_week: expect.any(Number),
        discount_type: expect.any(String),
        discount_value: expect.any(Number),
        is_active: expect.any(Boolean),
      });
    });

    it('is disabled when circuitName is empty', () => {
      const { result } = renderHook(
        () => useDiscountPrograms(''),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // =========================================================================
  // PROFILE GAPS QUERY HOOKS
  // =========================================================================

  describe('useProfileGaps', () => {
    it('fetches profile gaps for a circuit', async () => {
      const { result } = renderHook(
        () => useProfileGaps('AMC'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns gaps with expected structure', async () => {
      const { result } = renderHook(
        () => useProfileGaps('AMC'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const gap = result.current.data?.[0];
      expect(gap).toMatchObject({
        gap_id: expect.any(Number),
        gap_type: expect.any(String),
        expected_value: expect.any(String),
        is_resolved: expect.any(Boolean),
      });
    });

    it('is disabled when circuitName is empty', () => {
      const { result } = renderHook(
        () => useProfileGaps(''),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // =========================================================================
  // PROFILE VERSIONS QUERY HOOKS
  // =========================================================================

  describe('useProfileVersions', () => {
    it('fetches profile versions for a circuit', async () => {
      const { result } = renderHook(
        () => useProfileVersions('AMC'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns versions with expected structure', async () => {
      const { result } = renderHook(
        () => useProfileVersions('AMC'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const version = result.current.data?.[0];
      expect(version).toMatchObject({
        profile_id: expect.any(Number),
        circuit_name: expect.any(String),
        version: expect.any(Number),
        is_current: expect.any(Boolean),
        confidence_score: expect.any(Number),
      });
    });

    it('is disabled when circuitName is empty', () => {
      const { result } = renderHook(
        () => useProfileVersions(''),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // =========================================================================
  // COMPANY PROFILES QUERY HOOKS
  // =========================================================================

  describe('useCompanyProfiles', () => {
    it('fetches company profiles list', async () => {
      const { result } = renderHook(() => useCompanyProfiles(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.total).toBeDefined();
      expect(result.current.data?.profiles).toBeInstanceOf(Array);
    });
  });

  describe('useCompanyProfile', () => {
    it('fetches a single company profile', async () => {
      const { result } = renderHook(
        () => useCompanyProfile('AMC'),
        { wrapper: createWrapper() },
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.profile_id).toBeDefined();
      expect(result.current.data?.circuit_name).toBeDefined();
    });

    it('is disabled when circuitName is empty', () => {
      const { result } = renderHook(
        () => useCompanyProfile(''),
        { wrapper: createWrapper() },
      );

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // =========================================================================
  // MUTATION HOOKS
  // =========================================================================

  describe('useCreateDiscountProgram', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useCreateDiscountProgram(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDeleteDiscountProgram', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useDeleteDiscountProgram(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useResolveGap', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useResolveGap(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });
});
