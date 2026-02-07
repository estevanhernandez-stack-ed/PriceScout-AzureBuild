import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ============================================================================
// Types
// ============================================================================

export interface PresaleWatch {
  id: number;
  film_title: string;
  alert_type: 'velocity_drop' | 'velocity_spike' | 'milestone' | 'days_out' | 'market_share';
  threshold: number;
  enabled: boolean;
  created_at: string;
  last_triggered?: string | null;
  trigger_count: number;
}

export interface PresaleWatchCreate {
  film_title: string;
  alert_type: PresaleWatch['alert_type'];
  threshold: number;
}

export interface PresaleWatchUpdate {
  enabled?: boolean;
  threshold?: number;
}

export interface PresaleWatchNotification {
  id: number;
  watch_id: number;
  film_title: string;
  message: string;
  triggered_at: string;
  is_read: boolean;
  severity: 'info' | 'warning' | 'critical';
}

// ============================================================================
// Hooks
// ============================================================================

const WATCHES_KEY = ['presales', 'watches'];
const NOTIFICATIONS_KEY = ['presales', 'watches', 'notifications'];

/**
 * Fetch all presale watches.
 */
export function usePresaleWatches() {
  return useQuery({
    queryKey: WATCHES_KEY,
    queryFn: async () => {
      const response = await api.get<PresaleWatch[]>('/presales/watches');
      return response.data;
    },
  });
}

/**
 * Create a new presale watch.
 */
export function useCreatePresaleWatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: PresaleWatchCreate) => {
      const response = await api.post<PresaleWatch>('/presales/watches', body);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WATCHES_KEY });
    },
  });
}

/**
 * Update a presale watch (toggle enabled, change threshold).
 */
export function useUpdatePresaleWatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: PresaleWatchUpdate & { id: number }) => {
      const response = await api.put<PresaleWatch>(`/presales/watches/${id}`, body);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WATCHES_KEY });
    },
  });
}

/**
 * Delete a presale watch.
 */
export function useDeletePresaleWatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/presales/watches/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WATCHES_KEY });
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
  });
}

/**
 * Fetch presale watch notifications.
 */
export function usePresaleWatchNotifications(unreadOnly = false) {
  return useQuery({
    queryKey: [...NOTIFICATIONS_KEY, { unreadOnly }],
    queryFn: async () => {
      const response = await api.get<PresaleWatchNotification[]>(
        '/presales/watches/notifications',
        { params: { unread_only: unreadOnly } }
      );
      return response.data;
    },
  });
}

/**
 * Mark a notification as read.
 */
export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (notificationId: number) => {
      await api.put(`/presales/watches/notifications/${notificationId}/read`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
  });
}
