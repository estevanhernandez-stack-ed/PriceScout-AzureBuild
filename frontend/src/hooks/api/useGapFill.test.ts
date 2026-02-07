import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useGapFillProposals, useApplyGapFills } from './useGapFill';
import { createWrapper } from '@/test/utils';

describe('useGapFill hooks', () => {
  describe('useGapFillProposals', () => {
    it('fetches gap fill proposals for a theater', async () => {
      const { result } = renderHook(
        () => useGapFillProposals('AMC Madison 6'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.theater_name).toBe('AMC Madison 6');
      expect(result.current.data?.proposals).toBeInstanceOf(Array);
      expect(result.current.data?.proposals?.length).toBeGreaterThan(0);
      expect(result.current.data?.fillable_count).toBeDefined();
    });

    it('does not fetch when theaterName is null', () => {
      const { result } = renderHook(
        () => useGapFillProposals(null),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('supports lookbackDays and minSamples options', async () => {
      const { result } = renderHook(
        () => useGapFillProposals('AMC Madison 6', { lookbackDays: 60, minSamples: 10 }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toBeDefined();
    });
  });

  describe('useApplyGapFills', () => {
    it('exposes mutate function', () => {
      const { result } = renderHook(() => useApplyGapFills(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });
});
