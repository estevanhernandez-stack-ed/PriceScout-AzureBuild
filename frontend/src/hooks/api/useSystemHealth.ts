import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';

// Types for system health response
export interface ComponentHealth {
  status: 'ok' | 'degraded' | 'error' | 'critical' | 'unknown' | 'not_configured' | 'not_implemented' | 'stale';
  message?: string;
  [key: string]: unknown;
}

export interface DatabaseHealth extends ComponentHealth {
  status: 'ok' | 'error';
}

export interface FandangoScraperHealth extends ComponentHealth {
  last_check?: string;
  failure_rate_percent?: number;
  theaters_checked?: number;
  theaters_failed?: number;
}

export interface EntTelligenceHealth extends ComponentHealth {
  last_sync?: string;
  last_status?: string;
  records_synced?: number;
}

export interface AlertsHealth extends ComponentHealth {
  price_pending?: number;
  schedule_pending?: number;
  total_pending?: number;
}

export interface SchedulerHealth extends ComponentHealth {
  last_activity?: string;
  age_minutes?: number;
}

export interface CircuitBreakerStatus {
  name: string;
  state: 'closed' | 'open' | 'half_open';
  failures: number;
  failure_threshold: number;
  reset_timeout: number;
  last_failure_time?: number;
  last_state_change: number;
  is_open: boolean;
}

export interface SystemHealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string; // From the API, though our new one might not have it yet
  version: string;
  environment: string;
  components: {
    database?: DatabaseHealth;
    fandango_scraper?: FandangoScraperHealth;
    enttelligence?: EntTelligenceHealth;
    alerts?: AlertsHealth;
    scheduler?: SchedulerHealth;
    circuit_breakers?: Record<string, CircuitBreakerStatus>;
  };
  circuits?: Record<string, CircuitBreakerStatus>; // From new system API
  features?: Record<string, boolean>;
}

export interface BasicHealthResponse {
  status: string;
  timestamp: string;
  version: string;
  environment: string;
  database?: string;
  entra_id?: string;
  telemetry?: string;
}

// Query keys
export const systemHealthKeys = {
  all: ['systemHealth'] as const,
  basic: () => [...systemHealthKeys.all, 'basic'] as const,
  full: () => [...systemHealthKeys.all, 'full'] as const,
  detailed: () => [...systemHealthKeys.all, 'detailed'] as const,
};

/**
 * Fetch basic health check
 */
export function useBasicHealth() {
  return useQuery({
    queryKey: systemHealthKeys.basic(),
    queryFn: async () => {
      const response = await api.get<BasicHealthResponse>('/health');
      return response.data;
    },
    refetchInterval: 30000,
  });
}

/**
 * Fetch comprehensive system health (Original /health/full)
 */
export function useSystemHealth() {
  return useQuery({
    queryKey: systemHealthKeys.full(),
    queryFn: async () => {
      const response = await api.get<SystemHealthResponse>('/health/full');
      return response.data;
    },
    refetchInterval: 30000,
  });
}

/**
 * Fetch detailed system health (New /api/v1/system/health)
 */
export function useDetailedSystemHealth() {
  return useQuery({
    queryKey: systemHealthKeys.detailed(),
    queryFn: async () => {
      const response = await api.get<SystemHealthResponse>('/system/health');
      return response.data;
    },
    refetchInterval: 10000, // Faster refresh for management
  });
}

/**
 * Reset circuit breakers mutation
 */
export function useResetCircuits() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (name?: string) => {
      const url = name 
        ? `/system/circuits/${name}/reset` 
        : '/system/circuits/reset';
      const response = await api.post(url);
      return response.data;
    },
    onSuccess: (_, name) => {
      useToast.getState().toast({
        title: name ? `Circuit breaker '${name}' reset` : 'All circuit breakers reset',
        variant: 'default',
      });
      queryClient.invalidateQueries({ queryKey: systemHealthKeys.all });
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      useToast.getState().toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to reset circuits',
        variant: 'destructive',
      });
    },
  });
}

/**
 * Trip circuit breaker mutation (Force Open)
 */
export function useTripCircuit() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (name: string) => {
      const response = await api.post(`/system/circuits/${name}/open`);
      return response.data;
    },
    onSuccess: (_, name) => {
      useToast.getState().toast({
        title: `Circuit breaker '${name}' forced OPEN`,
        variant: 'destructive',
      });
      queryClient.invalidateQueries({ queryKey: systemHealthKeys.all });
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      useToast.getState().toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to trip circuit',
        variant: 'destructive',
      });
    },
  });
}

/**
 * Fetch maintenance status
 */
export function useMaintenanceStatus() {
  return useQuery({
    queryKey: [...systemHealthKeys.all, 'maintenance'],
    queryFn: async () => {
      const response = await api.get('/system/maintenance/status');
      return response.data;
    },
  });
}

/**
 * Trigger data retention cleanup
 */
export function useRunRetention() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post('/system/maintenance/retention');
      return response.data;
    },
    onSuccess: (data) => {
      useToast.getState().toast({
        title: data.status === 'triggered' ? 'Cleanup Task Triggered' : 'Cleanup Task Completed',
        description: data.status === 'triggered' ? `Task ID: ${data.task_id}` : 'All old records purged.',
      });
      queryClient.invalidateQueries({ queryKey: [...systemHealthKeys.all, 'maintenance'] });
    },
  });
}

/**
 * Get status color based on component status
 */
export function getStatusColor(status?: string): string {
  switch (status) {
    case 'ok':
    case 'healthy':
    case 'closed':
      return 'text-green-500';
    case 'degraded':
    case 'half_open':
    case 'stale':
      return 'text-yellow-500';
    case 'error':
    case 'critical':
    case 'unhealthy':
    case 'open':
      return 'text-red-500';
    default:
      return 'text-gray-400';
  }
}

/**
 * Get status badge variant based on status
 */
export function getStatusVariant(status?: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'ok':
    case 'healthy':
    case 'closed':
      return 'default';
    case 'degraded':
    case 'half_open':
    case 'stale':
      return 'secondary';
    case 'error':
    case 'critical':
    case 'unhealthy':
    case 'open':
      return 'destructive';
    default:
      return 'outline';
  }
}
