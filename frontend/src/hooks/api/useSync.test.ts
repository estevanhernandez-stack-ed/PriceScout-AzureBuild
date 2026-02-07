import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useEntTelligenceStatus,
  useSyncPrices,
  useSyncMarkets,
  useTaskStatus,
} from './useSync';
import { createWrapper } from '@/test/utils';

describe('useSync hooks', () => {
  describe('useEntTelligenceStatus', () => {
    it('fetches EntTelligence sync status', async () => {
      const { result } = renderHook(() => useEntTelligenceStatus(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        is_fresh: expect.any(Boolean),
        fresh_entries: expect.any(Number),
        total_entries: expect.any(Number),
        hours_until_stale: expect.any(Number),
        quick_scrape_available: expect.any(Boolean),
      });
    });
  });

  describe('useTaskStatus', () => {
    it('fetches task status when given a task ID', async () => {
      const { result } = renderHook(() => useTaskStatus('task-abc-123'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        task_id: 'task-abc-123',
        status: expect.any(String),
        ready: expect.any(Boolean),
      });
    });

    it('is disabled without task ID', () => {
      const { result } = renderHook(() => useTaskStatus(null), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useSyncPrices', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useSyncPrices(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
      expect(result.current.mutateAsync).toBeDefined();
    });
  });

  describe('useSyncMarkets', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useSyncMarkets(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
      expect(result.current.mutateAsync).toBeDefined();
    });
  });
});
