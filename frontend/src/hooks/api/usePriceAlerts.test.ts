import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import {
  usePriceAlerts,
  usePendingAlerts,
  useAlertSummary,
  usePriceAlert,
  useAcknowledgeAlert,
  useBulkAcknowledge,
  useAcknowledgeAll,
} from './usePriceAlerts';
import { createWrapper } from '@/test/utils';

describe('usePriceAlerts hooks', () => {
  describe('usePriceAlerts', () => {
    it('fetches price alerts list', async () => {
      const { result } = renderHook(() => usePriceAlerts(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        alerts: expect.any(Array),
        total_count: expect.any(Number),
      });
    });

    it('returns alerts with expected structure', async () => {
      const { result } = renderHook(() => usePriceAlerts(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const alert = result.current.data?.alerts[0];
      expect(alert).toMatchObject({
        alert_id: expect.any(Number),
        theater_name: expect.any(String),
        film_title: expect.any(String),
        alert_type: expect.any(String),
      });
    });

    it('supports filtering by acknowledged status', async () => {
      const { result } = renderHook(
        () => usePriceAlerts({ acknowledged: false }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.alerts).toBeDefined();
    });

    it('supports filtering by alert type', async () => {
      const { result } = renderHook(
        () => usePriceAlerts({ alertType: 'price_increase' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.alerts).toBeDefined();
    });

    it('supports date range filtering', async () => {
      const { result } = renderHook(
        () => usePriceAlerts({ dateFrom: '2026-01-01', dateTo: '2026-01-31' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.alerts).toBeDefined();
    });
  });

  describe('usePendingAlerts', () => {
    it('fetches only unacknowledged alerts', async () => {
      const { result } = renderHook(() => usePendingAlerts(50), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.alerts).toBeDefined();
    });
  });

  describe('useAlertSummary', () => {
    it('fetches alert summary statistics', async () => {
      const { result } = renderHook(() => useAlertSummary(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        total_alerts: expect.any(Number),
        pending_alerts: expect.any(Number),
      });
    });

    it('includes breakdown by type', async () => {
      const { result } = renderHook(() => useAlertSummary(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.by_type).toBeDefined();
    });
  });

  describe('usePriceAlert', () => {
    it('fetches single alert by ID', async () => {
      const { result } = renderHook(() => usePriceAlert(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        alert_id: expect.any(Number),
        theater_name: expect.any(String),
      });
    });

    it('is disabled when ID is falsy', async () => {
      const { result } = renderHook(() => usePriceAlert(0), {
        wrapper: createWrapper(),
      });

      expect(result.current.isFetching).toBe(false);
    });
  });

  describe('useAcknowledgeAlert', () => {
    it('acknowledges a single alert', async () => {
      const { result } = renderHook(() => useAcknowledgeAlert(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({ alertId: 1 });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        success: true,
      });
    });

    it('supports adding notes', async () => {
      const { result } = renderHook(() => useAcknowledgeAlert(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({ alertId: 1, notes: 'Reviewed and approved' });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useBulkAcknowledge', () => {
    it('acknowledges multiple alerts', async () => {
      const { result } = renderHook(() => useBulkAcknowledge(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({ alertIds: [1, 2, 3] });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        acknowledged_count: expect.any(Number),
      });
    });
  });

  describe('useAcknowledgeAll', () => {
    it('acknowledges all pending alerts', async () => {
      const { result } = renderHook(() => useAcknowledgeAll(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({});
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        acknowledged_count: expect.any(Number),
      });
    });
  });
});
