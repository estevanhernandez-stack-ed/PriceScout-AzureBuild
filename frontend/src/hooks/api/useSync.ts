import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';

export interface SyncStatus {
  is_fresh: boolean;
  fresh_entries: number;
  total_entries: number;
  last_sync: string | null;
  hours_until_stale: number;
  quick_scrape_available: boolean;
}

export interface SyncResponse {
  status: string;
  message: string;
  records_fetched?: number;
  records_cached?: number;
  task_id?: string;
  ready?: boolean;
}

export interface TaskStatusResponse {
  task_id: string;
  status: string;
  ready: boolean;
  result?: any;
  error?: string;
  progress?: any;
}

/**
 * Fetch EntTelligence sync status
 */
export function useEntTelligenceStatus() {
  return useQuery({
    queryKey: ['sync', 'enttelligence', 'status'],
    queryFn: async () => {
      const response = await api.get<SyncStatus>('/enttelligence/status');
      return response.data;
    },
    refetchInterval: 60000,
  });
}

/**
 * Trigger EntTelligence price sync
 */
export function useSyncPrices() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: async (params: { start_date: string; end_date?: string; circuits?: string[] }) => {
      const response = await api.post<SyncResponse>('/enttelligence/sync', params);
      return response.data;
    },
    onSuccess: (data) => {
      toast({
        title: 'Sync Started',
        description: data.message,
      });
      queryClient.invalidateQueries({ queryKey: ['sync', 'enttelligence', 'status'] });
    },
  });
}

/**
 * Trigger Theater/Market sync from EntTelligence
 */
export function useSyncMarkets() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<SyncResponse>('/market-context/sync/theaters');
      return response.data;
    },
    onSuccess: (data) => {
      toast({
        title: 'Market Sync',
        description: data.message || 'Theater sync task initiated.',
      });
      queryClient.invalidateQueries({ queryKey: ['cache', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['cache', 'markets'] });
    },
  });
}

/**
 * Hook to poll for Celery task status
 */
export function useTaskStatus(taskId: string | null) {
  return useQuery({
    queryKey: ['system', 'task', taskId],
    queryFn: async () => {
      if (!taskId) return null;
      const response = await api.get<TaskStatusResponse>(`/system/tasks/${taskId}`);
      return response.data;
    },
    enabled: !!taskId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && data.ready) return false;
      return 2000; // Poll every 2 seconds
    },
  });
}
