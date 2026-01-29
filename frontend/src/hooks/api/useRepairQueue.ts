import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// Types for repair queue
export interface RepairJob {
  theater_name: string;
  market_name: string;
  zip_code?: string;
  attempts: number;
  next_attempt_at?: string;
  first_failure_at?: string;
  last_failure_at?: string;
  error_message?: string;
}

export interface RepairQueueStatus {
  total_queued: number;
  due_now: number;
  max_attempts_reached: number;
  by_attempts: Record<string, number>;
  max_attempts_limit: number;
}

export interface MaintenanceRun {
  timestamp: string;
  duration_seconds: number;
  health_check: {
    status: string;
    checked: number;
    failed: number;
    failure_rate_percent: number;
    failed_theaters?: string[];
    threshold_percent: number;
    alert?: string;
  };
  repairs: {
    status: string;
    total_failed: number;
    attempted: number;
    repaired: number;
    still_failed: number;
    repaired_theaters?: Array<{
      original_name: string;
      new_name: string;
      market: string;
      url: string;
    }>;
    still_failed_theaters?: Array<{
      name: string;
      market: string;
    }>;
  };
  circuit_breaker?: {
    name: string;
    state: string;
    failures: number;
    failure_threshold: number;
  };
  overall_status: string;
  alert_message?: string;
}

// Simplified maintenance history entry from history endpoint
export interface MaintenanceHistoryEntry {
  timestamp: string;
  overall_status: string;
  checked: number;
  failed: number;
  repaired: number;
}

// Query keys
export const repairQueueKeys = {
  all: ['repairQueue'] as const,
  status: () => [...repairQueueKeys.all, 'status'] as const,
  jobs: () => [...repairQueueKeys.all, 'jobs'] as const,
  failed: () => [...repairQueueKeys.all, 'failed'] as const,
  maintenance: () => [...repairQueueKeys.all, 'maintenance'] as const,
};

/**
 * Fetch repair queue status
 */
export function useRepairQueueStatus() {
  return useQuery({
    queryKey: repairQueueKeys.status(),
    queryFn: async () => {
      const response = await api.get<RepairQueueStatus>('/cache/repair-queue/status');
      return response.data;
    },
    refetchInterval: 60000, // Refetch every minute
  });
}

/**
 * Fetch all jobs in repair queue
 */
export function useRepairQueueJobs() {
  return useQuery({
    queryKey: repairQueueKeys.jobs(),
    queryFn: async () => {
      const response = await api.get<RepairJob[]>('/cache/repair-queue/jobs');
      return response.data;
    },
  });
}

/**
 * Fetch permanently failed theaters (max attempts reached)
 */
export function useRepairQueueFailed() {
  return useQuery({
    queryKey: repairQueueKeys.failed(),
    queryFn: async () => {
      const response = await api.get<RepairJob[]>('/cache/repair-queue/failed');
      return response.data;
    },
  });
}

/**
 * Reset a repair job for immediate retry
 */
export function useResetRepairJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      theaterName,
      marketName,
    }: {
      theaterName: string;
      marketName: string;
    }) => {
      const response = await api.post<{ success: boolean }>(
        '/cache/repair-queue/reset',
        { theater_name: theaterName, market_name: marketName }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: repairQueueKeys.all });
    },
  });
}

/**
 * Clear all permanently failed jobs from queue
 */
export function useClearFailedJobs() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.delete<{ cleared: number }>('/cache/repair-queue/failed');
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: repairQueueKeys.all });
    },
  });
}

/**
 * Process repair queue manually
 */
export function useProcessRepairQueue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<{
        processed: number;
        success: number;
        failed: number;
      }>('/cache/repair-queue/process');
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: repairQueueKeys.all });
    },
  });
}

/**
 * Fetch cache maintenance history
 */
export function useMaintenanceHistory(limit = 10) {
  return useQuery({
    queryKey: [...repairQueueKeys.maintenance(), limit],
    queryFn: async () => {
      const response = await api.get<{ entries: MaintenanceHistoryEntry[]; total_count: number }>(
        `/cache/maintenance/history?limit=${limit}`
      );
      // Extract entries array from response
      return response.data.entries || [];
    },
  });
}

/**
 * Run cache maintenance manually
 */
export function useRunMaintenance() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<MaintenanceRun>('/cache/maintenance/run');
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: repairQueueKeys.all });
    },
  });
}

/**
 * Get time until next retry for a job
 */
export function getTimeUntilRetry(nextAttemptAt?: string): string {
  if (!nextAttemptAt) return 'Unknown';

  const nextTime = new Date(nextAttemptAt);
  const now = new Date();
  const diffMs = nextTime.getTime() - now.getTime();

  if (diffMs <= 0) return 'Due now';

  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);

  if (diffHours > 0) {
    return `${diffHours}h ${diffMins % 60}m`;
  }
  return `${diffMins}m`;
}

/**
 * Get backoff display for attempt count
 */
export function getBackoffDisplay(attempts: number): string {
  const hours = Math.min(Math.pow(2, attempts), 24);
  return hours >= 24 ? '24h (max)' : `${hours}h`;
}
