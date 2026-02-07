import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  usePresaleWatches,
  useCreatePresaleWatch,
  useUpdatePresaleWatch,
  useDeletePresaleWatch,
  usePresaleWatchNotifications,
  useMarkNotificationRead,
} from './usePresaleWatches';
import { createWrapper } from '@/test/utils';

describe('usePresaleWatches hooks', () => {
  describe('usePresaleWatches', () => {
    it('fetches presale watches list', async () => {
      const { result } = renderHook(() => usePresaleWatches(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns watches with expected structure', async () => {
      const { result } = renderHook(() => usePresaleWatches(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const watch = result.current.data?.[0];
      expect(watch).toMatchObject({
        id: expect.any(Number),
        film_title: expect.any(String),
        alert_type: expect.any(String),
        threshold: expect.any(Number),
        enabled: expect.any(Boolean),
      });
    });
  });

  describe('usePresaleWatchNotifications', () => {
    it('fetches presale watch notifications', async () => {
      const { result } = renderHook(() => usePresaleWatchNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns notifications with expected structure', async () => {
      const { result } = renderHook(() => usePresaleWatchNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const notification = result.current.data?.[0];
      expect(notification).toMatchObject({
        id: expect.any(Number),
        watch_id: expect.any(Number),
        film_title: expect.any(String),
        message: expect.any(String),
        is_read: expect.any(Boolean),
        severity: expect.any(String),
      });
    });

    it('accepts unreadOnly parameter', async () => {
      const { result } = renderHook(() => usePresaleWatchNotifications(true), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('useCreatePresaleWatch', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useCreatePresaleWatch(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useUpdatePresaleWatch', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useUpdatePresaleWatch(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useDeletePresaleWatch', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useDeletePresaleWatch(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useMarkNotificationRead', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useMarkNotificationRead(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });
});
