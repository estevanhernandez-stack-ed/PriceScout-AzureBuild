import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useBasicHealth,
  useSystemHealth,
  useDetailedSystemHealth,
  getStatusColor,
  getStatusVariant,
} from './useSystemHealth';
import { createWrapper } from '@/test/utils';

describe('useSystemHealth hooks', () => {
  describe('useBasicHealth', () => {
    it('fetches basic health data', async () => {
      const { result } = renderHook(() => useBasicHealth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        status: 'healthy',
        version: expect.any(String),
        environment: 'test',
      });
    });

    it('returns loading state initially', () => {
      const { result } = renderHook(() => useBasicHealth(), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(true);
    });
  });

  describe('useSystemHealth', () => {
    it('fetches full system health data', async () => {
      const { result } = renderHook(() => useSystemHealth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        status: 'healthy',
        components: expect.objectContaining({
          database: expect.objectContaining({ status: 'ok' }),
          fandango_scraper: expect.objectContaining({ status: 'ok' }),
        }),
      });
    });

    it('includes circuit breaker data', async () => {
      const { result } = renderHook(() => useSystemHealth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const circuits = result.current.data?.components.circuit_breakers;
      expect(circuits).toBeDefined();
      expect(circuits?.fandango).toMatchObject({
        name: 'fandango',
        state: 'closed',
        is_open: false,
      });
    });
  });

  describe('useDetailedSystemHealth', () => {
    it('fetches detailed system health', async () => {
      const { result } = renderHook(() => useDetailedSystemHealth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        status: expect.stringMatching(/healthy|degraded|unhealthy/),
        version: expect.any(String),
      });
    });
  });
});

describe('getStatusColor', () => {
  it('returns green for healthy states', () => {
    expect(getStatusColor('ok')).toBe('text-green-500');
    expect(getStatusColor('healthy')).toBe('text-green-500');
    expect(getStatusColor('closed')).toBe('text-green-500');
  });

  it('returns yellow for degraded states', () => {
    expect(getStatusColor('degraded')).toBe('text-yellow-500');
    expect(getStatusColor('half_open')).toBe('text-yellow-500');
    expect(getStatusColor('stale')).toBe('text-yellow-500');
  });

  it('returns red for error states', () => {
    expect(getStatusColor('error')).toBe('text-red-500');
    expect(getStatusColor('critical')).toBe('text-red-500');
    expect(getStatusColor('unhealthy')).toBe('text-red-500');
    expect(getStatusColor('open')).toBe('text-red-500');
  });

  it('returns gray for unknown states', () => {
    expect(getStatusColor(undefined)).toBe('text-gray-400');
    expect(getStatusColor('unknown')).toBe('text-gray-400');
  });
});

describe('getStatusVariant', () => {
  it('returns default for healthy states', () => {
    expect(getStatusVariant('ok')).toBe('default');
    expect(getStatusVariant('healthy')).toBe('default');
    expect(getStatusVariant('closed')).toBe('default');
  });

  it('returns secondary for degraded states', () => {
    expect(getStatusVariant('degraded')).toBe('secondary');
    expect(getStatusVariant('half_open')).toBe('secondary');
  });

  it('returns destructive for error states', () => {
    expect(getStatusVariant('error')).toBe('destructive');
    expect(getStatusVariant('critical')).toBe('destructive');
    expect(getStatusVariant('open')).toBe('destructive');
  });

  it('returns outline for unknown states', () => {
    expect(getStatusVariant(undefined)).toBe('outline');
    expect(getStatusVariant('unknown')).toBe('outline');
  });
});
