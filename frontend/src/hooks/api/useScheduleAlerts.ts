import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// Types for schedule alerts
export interface ScheduleAlert {
  alert_id: number;
  company_id: number;
  theater_name: string;
  film_title?: string;
  play_date: string;
  alert_type: 'new_film' | 'new_showtime' | 'removed_showtime' | 'removed_film' | 'format_added' | 'new_schedule' | 'event_added' | 'presale_started';
  old_value?: Record<string, unknown>;
  new_value?: Record<string, unknown>;
  change_details: string;
  source: string;
  baseline_id?: number;
  triggered_at: string;
  detected_at: string;
  is_acknowledged: boolean;
  acknowledged_by?: number;
  acknowledged_at?: string;
  acknowledgment_notes?: string;
}

export interface ScheduleAlertListResponse {
  alerts: ScheduleAlert[];
  total: number;
}

export interface ScheduleAlertSummary {
  total_pending: number;
  total_acknowledged: number;
  by_type: Record<string, number>;
  by_theater: Record<string, number>;
  oldest_pending?: string;
  newest_pending?: string;
}

export interface ScheduleMonitorConfig {
  config_id: number;
  company_id: number;
  is_enabled: boolean;
  check_frequency_hours: number;
  alert_on_new_film: boolean;
  alert_on_new_showtime: boolean;
  alert_on_removed_showtime: boolean;
  alert_on_removed_film: boolean;
  alert_on_format_added: boolean;
  alert_on_time_changed: boolean;
  alert_on_new_schedule: boolean;
  alert_on_event: boolean;
  alert_on_presale: boolean;
  theaters_filter?: string[];
  films_filter?: string[];
  circuits_filter?: string[];
  days_ahead: number;
  notification_enabled: boolean;
  webhook_url?: string;
  notification_email?: string;
  last_check_at?: string;
  last_check_status?: string;
  last_check_alerts_count?: number;
  created_at: string;
  updated_at: string;
}

export interface ScheduleMonitorStatus {
  is_enabled: boolean;
  last_check_at?: string;
  last_check_status?: string;
  total_pending_alerts: number;
  baselines_count: number;
}

interface AlertFilters {
  acknowledged?: boolean;
  alertType?: string;
  theaterName?: string;
  limit?: number;
  offset?: number;
}

// Query keys
export const scheduleAlertKeys = {
  all: ['scheduleAlerts'] as const,
  list: (filters?: AlertFilters) => [...scheduleAlertKeys.all, 'list', filters] as const,
  summary: () => [...scheduleAlertKeys.all, 'summary'] as const,
  detail: (id: number) => [...scheduleAlertKeys.all, 'detail', id] as const,
  config: () => [...scheduleAlertKeys.all, 'config'] as const,
  status: () => [...scheduleAlertKeys.all, 'status'] as const,
};

/**
 * Fetch schedule alerts with filters
 */
export function useScheduleAlerts(filters: AlertFilters = {}) {
  return useQuery({
    queryKey: scheduleAlertKeys.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.acknowledged !== undefined)
        params.append('is_acknowledged', String(filters.acknowledged));
      if (filters.alertType) params.append('alert_type', filters.alertType);
      if (filters.theaterName) params.append('theater_name', filters.theaterName);
      if (filters.limit) params.append('limit', String(filters.limit));
      if (filters.offset) params.append('offset', String(filters.offset));

      const response = await api.get<ScheduleAlertListResponse>(
        `/schedule-alerts?${params.toString()}`
      );
      return response.data.alerts;
    },
  });
}

/**
 * Fetch pending schedule alerts only
 */
export function usePendingScheduleAlerts(limit = 50) {
  return useScheduleAlerts({ acknowledged: false, limit });
}

/**
 * Fetch schedule alert summary statistics
 */
export function useScheduleAlertSummary() {
  return useQuery({
    queryKey: scheduleAlertKeys.summary(),
    queryFn: async () => {
      const response = await api.get<ScheduleAlertSummary>('/schedule-alerts/summary');
      return response.data;
    },
  });
}

/**
 * Acknowledge a schedule alert
 */
export function useAcknowledgeScheduleAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      alertId,
      notes,
    }: {
      alertId: number;
      notes?: string;
    }) => {
      const response = await api.put<{ success: boolean }>(
        `/schedule-alerts/${alertId}/acknowledge`,
        { notes }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: scheduleAlertKeys.all });
    },
  });
}

/**
 * Bulk acknowledge schedule alerts
 */
export function useBulkAcknowledgeScheduleAlerts() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      alertIds,
      notes,
    }: {
      alertIds: number[];
      notes?: string;
    }) => {
      const response = await api.put<{ acknowledged_count: number }>(
        '/schedule-alerts/acknowledge-bulk',
        { alert_ids: alertIds, notes }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: scheduleAlertKeys.all });
    },
  });
}

/**
 * Get schedule monitor configuration
 */
export function useScheduleMonitorConfig() {
  return useQuery({
    queryKey: scheduleAlertKeys.config(),
    queryFn: async () => {
      const response = await api.get<ScheduleMonitorConfig>('/schedule-monitor/config');
      return response.data;
    },
  });
}

/**
 * Update schedule monitor configuration
 */
export function useUpdateScheduleMonitorConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (updates: Partial<ScheduleMonitorConfig>) => {
      const response = await api.put<ScheduleMonitorConfig>('/schedule-monitor/config', updates);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: scheduleAlertKeys.config() });
      queryClient.invalidateQueries({ queryKey: scheduleAlertKeys.status() });
    },
  });
}

/**
 * Get schedule monitor status
 */
export function useScheduleMonitorStatus() {
  return useQuery({
    queryKey: scheduleAlertKeys.status(),
    queryFn: async () => {
      const response = await api.get<ScheduleMonitorStatus>('/schedule-monitor/status');
      return response.data;
    },
    refetchInterval: 60000, // Refetch every minute
  });
}

/**
 * Trigger a manual schedule check
 */
export function useTriggerScheduleCheck() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<{ status: string; alerts_created: number }>(
        '/schedule-monitor/check'
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: scheduleAlertKeys.all });
    },
  });
}

/**
 * Get alert type display info
 */
export function getAlertTypeInfo(alertType: string): { label: string; color: string } {
  switch (alertType) {
    case 'new_film':
      return { label: 'New Film', color: 'text-blue-500' };
    case 'new_showtime':
      return { label: 'New Showtime', color: 'text-green-500' };
    case 'removed_showtime':
      return { label: 'Removed Showtime', color: 'text-orange-500' };
    case 'removed_film':
      return { label: 'Removed Film', color: 'text-red-500' };
    case 'format_added':
      return { label: 'New Format', color: 'text-purple-500' };
    case 'new_schedule':
      return { label: 'New Schedule', color: 'text-cyan-500' };
    case 'event_added':
      return { label: 'Event Added', color: 'text-amber-500' };
    case 'presale_started':
      return { label: 'Presale Started', color: 'text-rose-500' };
    default:
      return { label: alertType, color: 'text-gray-500' };
  }
}
