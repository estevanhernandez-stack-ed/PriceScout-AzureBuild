import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import {
  useRepairQueueStatus,
  useRepairQueueJobs,
  useRepairQueueFailed,
  useResetRepairJob,
  useClearFailedJobs,
  useProcessRepairQueue,
  useMaintenanceHistory,
  useRunMaintenance,
  getTimeUntilRetry,
  getBackoffDisplay,
} from './useRepairQueue';
import { createWrapper } from '@/test/utils';

describe('useRepairQueue hooks', () => {
  describe('useRepairQueueStatus', () => {
    it('fetches repair queue status', async () => {
      const { result } = renderHook(() => useRepairQueueStatus(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        total_queued: expect.any(Number),
        due_now: expect.any(Number),
        max_attempts_reached: expect.any(Number),
      });
    });

    it('includes attempt distribution', async () => {
      const { result } = renderHook(() => useRepairQueueStatus(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.by_attempts).toBeDefined();
      expect(result.current.data?.max_attempts_limit).toBeGreaterThan(0);
    });
  });

  describe('useRepairQueueJobs', () => {
    it('fetches queued jobs list', async () => {
      const { result } = renderHook(() => useRepairQueueJobs(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns jobs with expected structure', async () => {
      const { result } = renderHook(() => useRepairQueueJobs(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const job = result.current.data?.[0];
      expect(job).toMatchObject({
        theater_name: expect.any(String),
        market_name: expect.any(String),
        attempts: expect.any(Number),
      });
    });
  });

  describe('useRepairQueueFailed', () => {
    it('fetches permanently failed theaters', async () => {
      const { result } = renderHook(() => useRepairQueueFailed(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
    });
  });

  describe('useResetRepairJob', () => {
    it('resets a repair job for retry', async () => {
      const { result } = renderHook(() => useResetRepairJob(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          theaterName: 'Test Theater',
          marketName: 'Madison',
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        success: true,
      });
    });
  });

  describe('useClearFailedJobs', () => {
    it('clears permanently failed jobs', async () => {
      const { result } = renderHook(() => useClearFailedJobs(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate();
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        cleared: expect.any(Number),
      });
    });
  });

  describe('useProcessRepairQueue', () => {
    it('processes repair queue manually', async () => {
      const { result } = renderHook(() => useProcessRepairQueue(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate();
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        processed: expect.any(Number),
        success: expect.any(Number),
        failed: expect.any(Number),
      });
    });
  });

  describe('useMaintenanceHistory', () => {
    it('fetches maintenance history', async () => {
      const { result } = renderHook(() => useMaintenanceHistory(10), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
    });
  });

  describe('useRunMaintenance', () => {
    it('runs maintenance manually', async () => {
      const { result } = renderHook(() => useRunMaintenance(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate();
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        overall_status: expect.any(String),
        health_check: expect.any(Object),
        repairs: expect.any(Object),
      });
    });
  });
});

describe('Repair queue utility functions', () => {
  describe('getTimeUntilRetry', () => {
    it('returns "Unknown" for undefined input', () => {
      expect(getTimeUntilRetry(undefined)).toBe('Unknown');
    });

    it('returns "Due now" for past times', () => {
      const pastTime = new Date(Date.now() - 60000).toISOString();
      expect(getTimeUntilRetry(pastTime)).toBe('Due now');
    });

    it('returns minutes for near future', () => {
      const futureTime = new Date(Date.now() + 30 * 60000).toISOString();
      const result = getTimeUntilRetry(futureTime);
      expect(result).toMatch(/\d+m/);
    });

    it('returns hours and minutes for far future', () => {
      const futureTime = new Date(Date.now() + 90 * 60000).toISOString();
      const result = getTimeUntilRetry(futureTime);
      expect(result).toMatch(/\d+h \d+m/);
    });
  });

  describe('getBackoffDisplay', () => {
    it('returns exponential backoff times', () => {
      expect(getBackoffDisplay(0)).toBe('1h');
      expect(getBackoffDisplay(1)).toBe('2h');
      expect(getBackoffDisplay(2)).toBe('4h');
      expect(getBackoffDisplay(3)).toBe('8h');
      expect(getBackoffDisplay(4)).toBe('16h');
    });

    it('caps at 24 hours', () => {
      expect(getBackoffDisplay(5)).toBe('24h (max)');
      expect(getBackoffDisplay(10)).toBe('24h (max)');
    });
  });
});
