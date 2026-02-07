import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useScheduleAlerts,
  usePendingScheduleAlerts,
  useScheduleAlertSummary,
  useAcknowledgeScheduleAlert,
  useBulkAcknowledgeScheduleAlerts,
  useScheduleMonitorConfig,
  useScheduleMonitorStatus,
  useTriggerScheduleCheck,
  useUpdateScheduleMonitorConfig,
  getAlertTypeInfo,
} from './useScheduleAlerts';
import { createWrapper } from '@/test/utils';

describe('useScheduleAlerts hooks', () => {
  describe('useScheduleAlerts', () => {
    it('fetches schedule alerts list', async () => {
      const { result } = renderHook(() => useScheduleAlerts(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });

    it('accepts filter parameters', async () => {
      const { result } = renderHook(
        () => useScheduleAlerts({ acknowledged: false, limit: 10 }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('usePendingScheduleAlerts', () => {
    it('fetches pending alerts only', async () => {
      const { result } = renderHook(() => usePendingScheduleAlerts(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
    });
  });

  describe('useScheduleAlertSummary', () => {
    it('fetches alert summary statistics', async () => {
      const { result } = renderHook(() => useScheduleAlertSummary(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        total_pending: expect.any(Number),
        total_acknowledged: expect.any(Number),
        by_type: expect.any(Object),
        by_theater: expect.any(Object),
      });
    });
  });

  describe('useScheduleMonitorConfig', () => {
    it('fetches monitor configuration', async () => {
      const { result } = renderHook(() => useScheduleMonitorConfig(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        config_id: expect.any(Number),
        is_enabled: expect.any(Boolean),
        check_frequency_hours: expect.any(Number),
        days_ahead: expect.any(Number),
      });
    });
  });

  describe('useScheduleMonitorStatus', () => {
    it('fetches monitor status', async () => {
      const { result } = renderHook(() => useScheduleMonitorStatus(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        is_enabled: expect.any(Boolean),
        total_pending_alerts: expect.any(Number),
        baselines_count: expect.any(Number),
      });
    });
  });

  describe('useAcknowledgeScheduleAlert', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useAcknowledgeScheduleAlert(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useBulkAcknowledgeScheduleAlerts', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useBulkAcknowledgeScheduleAlerts(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useUpdateScheduleMonitorConfig', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useUpdateScheduleMonitorConfig(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('useTriggerScheduleCheck', () => {
    it('provides mutate function', () => {
      const { result } = renderHook(() => useTriggerScheduleCheck(), {
        wrapper: createWrapper(),
      });

      expect(result.current.mutate).toBeDefined();
    });
  });

  describe('getAlertTypeInfo', () => {
    it('returns correct info for known alert types', () => {
      expect(getAlertTypeInfo('new_film')).toEqual({ label: 'New Film', color: 'text-blue-500' });
      expect(getAlertTypeInfo('new_showtime')).toEqual({ label: 'New Showtime', color: 'text-green-500' });
      expect(getAlertTypeInfo('removed_showtime')).toEqual({ label: 'Removed Showtime', color: 'text-orange-500' });
      expect(getAlertTypeInfo('removed_film')).toEqual({ label: 'Removed Film', color: 'text-red-500' });
      expect(getAlertTypeInfo('format_added')).toEqual({ label: 'New Format', color: 'text-purple-500' });
      expect(getAlertTypeInfo('new_schedule')).toEqual({ label: 'New Schedule', color: 'text-cyan-500' });
      expect(getAlertTypeInfo('event_added')).toEqual({ label: 'Event Added', color: 'text-amber-500' });
      expect(getAlertTypeInfo('presale_started')).toEqual({ label: 'Presale Started', color: 'text-rose-500' });
    });

    it('returns default info for unknown alert types', () => {
      const info = getAlertTypeInfo('unknown_type');
      expect(info).toEqual({ label: 'unknown_type', color: 'text-gray-500' });
    });
  });
});
