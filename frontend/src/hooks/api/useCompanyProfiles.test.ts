import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useCompanyProfiles,
  useCompanyProfile,
  useDiscoverProfile,
  useDiscoverAllProfiles,
  useDeleteProfile,
  useCleanupDuplicateProfiles,
  useDiscountDayDiagnostic,
  useDataCoverage,
  getDayName,
  getCoverageAssessmentColor,
  formatConfidence,
  getConfidenceLevel,
} from './useCompanyProfiles';
import { createWrapper } from '@/test/utils';

describe('useCompanyProfiles hooks', () => {
  // =========================================================================
  // Utility / helper functions
  // =========================================================================
  describe('getDayName', () => {
    it('returns correct day names', () => {
      expect(getDayName(0)).toBe('Monday');
      expect(getDayName(4)).toBe('Friday');
      expect(getDayName(6)).toBe('Sunday');
    });

    it('returns Unknown for out-of-range', () => {
      expect(getDayName(7)).toBe('Unknown');
      expect(getDayName(-1)).toBe('Unknown');
    });
  });

  describe('getCoverageAssessmentColor', () => {
    it('returns correct color classes for each assessment level', () => {
      expect(getCoverageAssessmentColor('excellent')).toContain('text-green-600');
      expect(getCoverageAssessmentColor('good')).toContain('text-blue-600');
      expect(getCoverageAssessmentColor('limited')).toContain('text-yellow-600');
      expect(getCoverageAssessmentColor('insufficient')).toContain('text-red-600');
    });

    it('returns gray for unknown assessment', () => {
      expect(getCoverageAssessmentColor('other')).toContain('text-gray-600');
    });
  });

  describe('formatConfidence', () => {
    it('formats score as percentage', () => {
      expect(formatConfidence(0.85)).toBe('85%');
      expect(formatConfidence(1.0)).toBe('100%');
      expect(formatConfidence(0)).toBe('0%');
    });

    it('rounds to nearest integer', () => {
      expect(formatConfidence(0.333)).toBe('33%');
      expect(formatConfidence(0.667)).toBe('67%');
    });
  });

  describe('getConfidenceLevel', () => {
    it('returns high for score >= 0.7', () => {
      expect(getConfidenceLevel(0.7)).toBe('high');
      expect(getConfidenceLevel(1.0)).toBe('high');
    });

    it('returns medium for score >= 0.4', () => {
      expect(getConfidenceLevel(0.4)).toBe('medium');
      expect(getConfidenceLevel(0.69)).toBe('medium');
    });

    it('returns low for score < 0.4', () => {
      expect(getConfidenceLevel(0)).toBe('low');
      expect(getConfidenceLevel(0.39)).toBe('low');
    });
  });

  // =========================================================================
  // Query hooks
  // =========================================================================
  describe('useCompanyProfiles', () => {
    it('fetches all company profiles', async () => {
      const { result } = renderHook(() => useCompanyProfiles(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.total).toBeDefined();
      expect(result.current.data?.profiles).toBeInstanceOf(Array);
      expect(result.current.data?.profiles?.length).toBeGreaterThan(0);
      expect(result.current.data?.profiles?.[0]).toMatchObject({
        profile_id: expect.any(Number),
        circuit_name: expect.any(String),
      });
    });
  });

  describe('useCompanyProfile', () => {
    it('fetches a specific company profile by circuit name', async () => {
      const { result } = renderHook(() => useCompanyProfile('AMC'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.circuit_name).toBe('AMC');
      expect(result.current.data?.confidence_score).toBeDefined();
    });

    it('does not fetch when circuitName is null', () => {
      const { result } = renderHook(() => useCompanyProfile(null), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useDiscountDayDiagnostic', () => {
    it('fetches discount day diagnostic data', async () => {
      const { result } = renderHook(() => useDiscountDayDiagnostic('AMC'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.circuit_name).toBe('AMC');
      expect(result.current.data?.day_analysis).toBeInstanceOf(Array);
      expect(result.current.data?.detected_discount_days).toBeInstanceOf(Array);
    });

    it('does not fetch when circuitName is null', () => {
      const { result } = renderHook(() => useDiscountDayDiagnostic(null), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useDataCoverage', () => {
    it('fetches data coverage for a circuit', async () => {
      const { result } = renderHook(() => useDataCoverage('AMC'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.circuit_name).toBe('AMC');
      expect(result.current.data?.coverage_assessment).toBe('excellent');
      expect(result.current.data?.can_detect_discount_days).toBe(true);
    });

    it('does not fetch when circuitName is null', () => {
      const { result } = renderHook(() => useDataCoverage(null), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  // =========================================================================
  // Mutation hooks
  // =========================================================================
  describe('useDiscoverProfile', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useDiscoverProfile(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDiscoverAllProfiles', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useDiscoverAllProfiles(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDeleteProfile', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useDeleteProfile(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useCleanupDuplicateProfiles', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useCleanupDuplicateProfiles(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });
});
