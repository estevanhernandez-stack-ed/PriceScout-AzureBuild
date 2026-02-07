import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useAuditLogs,
  useAuditLogEventTypes,
  useAuditLogCategories,
  getSeverityStyle,
} from './useAuditLog';
import { createWrapper } from '@/test/utils';

describe('useAuditLog hooks', () => {
  describe('useAuditLogs', () => {
    it('fetches audit log entries', async () => {
      const { result } = renderHook(() => useAuditLogs(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        entries: expect.any(Array),
        total_count: expect.any(Number),
      });
    });

    it('returns entries with expected structure', async () => {
      const { result } = renderHook(() => useAuditLogs(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const entry = result.current.data?.entries[0];
      expect(entry).toMatchObject({
        log_id: expect.any(Number),
        timestamp: expect.any(String),
        event_type: expect.any(String),
        event_category: expect.any(String),
        severity: expect.any(String),
      });
    });

    it('supports filter options', async () => {
      const { result } = renderHook(
        () => useAuditLogs({ limit: 10, eventType: 'USER_LOGIN' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('useAuditLogEventTypes', () => {
    it('fetches event types', async () => {
      const { result } = renderHook(() => useAuditLogEventTypes(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });
  });

  describe('useAuditLogCategories', () => {
    it('fetches categories', async () => {
      const { result } = renderHook(() => useAuditLogCategories(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeInstanceOf(Array);
      expect(result.current.data?.length).toBeGreaterThan(0);
    });
  });
});

describe('getSeverityStyle utility', () => {
  it('returns red style for critical severity', () => {
    const style = getSeverityStyle('critical');
    expect(style).toContain('red');
  });

  it('returns red style for error severity', () => {
    const style = getSeverityStyle('error');
    expect(style).toContain('red');
  });

  it('returns amber style for warning severity', () => {
    const style = getSeverityStyle('warning');
    expect(style).toContain('amber');
  });

  it('returns blue style for info severity', () => {
    const style = getSeverityStyle('info');
    expect(style).toContain('blue');
  });

  it('returns emerald style for success severity', () => {
    const style = getSeverityStyle('success');
    expect(style).toContain('emerald');
  });

  it('returns gray style for unknown severity', () => {
    const style = getSeverityStyle('unknown');
    expect(style).toContain('gray');
  });

  it('is case-insensitive', () => {
    const style = getSeverityStyle('WARNING');
    expect(style).toContain('amber');
  });
});
