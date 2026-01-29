import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

export interface AuditLogEntry {
  log_id: number;
  timestamp: string;
  username: string | null;
  event_type: string;
  event_category: string;
  severity: string;
  details: string | null;
  ip_address: string | null;
}

export interface AuditLogListResponse {
  entries: AuditLogEntry[];
  total_count: number;
}

export interface AuditLogFilters {
  limit?: number;
  offset?: number;
  eventType?: string;
  eventCategory?: string;
  severity?: string;
  username?: string;
  dateFrom?: string;
  dateTo?: string;
}

export const auditLogKeys = {
  all: ['auditLogs'] as const,
  list: (filters: AuditLogFilters) => [...auditLogKeys.all, 'list', filters] as const,
  eventTypes: () => [...auditLogKeys.all, 'eventTypes'] as const,
  categories: () => [...auditLogKeys.all, 'categories'] as const,
};

export function useAuditLogs(filters: AuditLogFilters = {}) {
  return useQuery({
    queryKey: auditLogKeys.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.limit) params.append('limit', String(filters.limit));
      if (filters.offset) params.append('offset', String(filters.offset));
      if (filters.eventType && filters.eventType !== 'all') params.append('event_type', filters.eventType);
      if (filters.eventCategory && filters.eventCategory !== 'all') params.append('event_category', filters.eventCategory);
      if (filters.severity && filters.severity !== 'all') params.append('severity', filters.severity);
      if (filters.username) params.append('username', filters.username);
      if (filters.dateFrom) params.append('date_from', filters.dateFrom);
      if (filters.dateTo) params.append('date_to', filters.dateTo);

      const response = await api.get<AuditLogListResponse>(`/admin/audit-log?${params.toString()}`);
      return response.data;
    },
  });
}

export function useAuditLogEventTypes() {
  return useQuery({
    queryKey: auditLogKeys.eventTypes(),
    queryFn: async () => {
      const response = await api.get<{ event_types: string[] }>('/admin/audit-log/event-types');
      return response.data.event_types;
    },
  });
}

export function useAuditLogCategories() {
  return useQuery({
    queryKey: auditLogKeys.categories(),
    queryFn: async () => {
      const response = await api.get<{ categories: string[] }>('/admin/audit-log/categories');
      return response.data.categories;
    },
  });
}

export function getSeverityStyle(severity: string) {
  switch (severity.toLowerCase()) {
    case 'critical':
    case 'error':
      return 'bg-red-500/10 text-red-500 border-red-500/20';
    case 'warning':
      return 'bg-amber-500/10 text-amber-500 border-amber-500/20';
    case 'info':
      return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
    case 'success':
      return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20';
    default:
      return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
  }
}
