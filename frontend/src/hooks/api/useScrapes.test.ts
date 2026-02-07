import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import {
  useScrapeSources,
  useScrapeSource,
  useCreateScrapeSource,
  useUpdateScrapeSource,
  useDeleteScrapeSource,
  useScrapeJobs,
  useScrapeJobStatus,
} from './useScrapes';
import { createWrapper } from '@/test/utils';

describe('useScrapes hooks', () => {
  describe('useScrapeSources', () => {
    it('fetches scrape sources list', async () => {
      const { result } = renderHook(() => useScrapeSources(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('returns sources with expected structure', async () => {
      const { result } = renderHook(() => useScrapeSources(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const source = result.current.data?.[0];
      expect(source).toMatchObject({
        source_id: expect.any(Number),
        name: expect.any(String),
        source_type: expect.any(String),
        is_active: expect.any(Boolean),
      });
    });
  });

  describe('useScrapeSource', () => {
    it('fetches single scrape source by ID', async () => {
      const { result } = renderHook(() => useScrapeSource(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        source_id: expect.any(Number),
        name: expect.any(String),
      });
    });

    it('is disabled when ID is falsy', async () => {
      const { result } = renderHook(() => useScrapeSource(0), {
        wrapper: createWrapper(),
      });

      expect(result.current.isFetching).toBe(false);
    });
  });

  describe('useCreateScrapeSource', () => {
    it('creates a new scrape source', async () => {
      const { result } = renderHook(() => useCreateScrapeSource(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          name: 'New Source',
          source_type: 'web',
          base_url: 'https://example.com',
          is_active: true,
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        source_id: expect.any(Number),
      });
    });
  });

  describe('useUpdateScrapeSource', () => {
    it('updates an existing scrape source', async () => {
      const { result } = renderHook(() => useUpdateScrapeSource(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          sourceId: 1,
          data: { name: 'Updated Source' },
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useDeleteScrapeSource', () => {
    it('deletes a scrape source', async () => {
      const { result } = renderHook(() => useDeleteScrapeSource(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate(1);
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useScrapeJobs', () => {
    it('fetches scrape jobs list', async () => {
      const { result } = renderHook(() => useScrapeJobs(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
    });

    it('returns jobs with expected structure', async () => {
      const { result } = renderHook(() => useScrapeJobs(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const job = result.current.data?.[0];
      expect(job).toMatchObject({
        run_id: expect.any(Number),
        status: expect.any(String),
        mode: expect.any(String),
      });
    });

    it('supports status filter', async () => {
      const { result } = renderHook(
        () => useScrapeJobs({ status: 'completed' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('useScrapeJobStatus', () => {
    it('fetches single job status by ID', async () => {
      const { result } = renderHook(() => useScrapeJobStatus(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        run_id: expect.any(Number),
        status: expect.any(String),
      });
    });

    it('is disabled when ID is falsy', async () => {
      const { result } = renderHook(() => useScrapeJobStatus(0), {
        wrapper: createWrapper(),
      });

      expect(result.current.isFetching).toBe(false);
    });
  });
});
