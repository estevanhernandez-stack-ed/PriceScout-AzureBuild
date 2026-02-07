import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryClient';
import type {
  PriceAlert,
  AlertListResponse,
  AlertSummary,
  AcknowledgeResponse,
} from '@/types';

interface AlertFilters {
  acknowledged?: boolean;
  alertType?: string;
  theaterName?: string;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
  offset?: number;
}

/**
 * Fetch price alerts with filters
 */
export function usePriceAlerts(filters: AlertFilters = {}) {
  return useQuery({
    queryKey: queryKeys.priceAlerts.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.acknowledged !== undefined)
        params.append('acknowledged', String(filters.acknowledged));
      if (filters.alertType) params.append('alert_type', filters.alertType);
      if (filters.theaterName) params.append('theater_name', filters.theaterName);
      if (filters.dateFrom) params.append('date_from', filters.dateFrom);
      if (filters.dateTo) params.append('date_to', filters.dateTo);
      if (filters.limit) params.append('limit', String(filters.limit));
      if (filters.offset) params.append('offset', String(filters.offset));

      const response = await api.get<AlertListResponse>(
        `/price-alerts?${params.toString()}`
      );
      return response.data;
    },
  });
}

/**
 * Fetch pending alerts only (convenience hook)
 */
export function usePendingAlerts(limit = 50) {
  return usePriceAlerts({ acknowledged: false, limit });
}

/**
 * Fetch alert summary statistics
 */
export function useAlertSummary() {
  return useQuery({
    queryKey: queryKeys.priceAlerts.summary(),
    queryFn: async () => {
      const response = await api.get<AlertSummary>('/price-alerts/summary');
      return response.data;
    },
  });
}

/**
 * Fetch a single alert by ID
 */
export function usePriceAlert(alertId: number) {
  return useQuery({
    queryKey: queryKeys.priceAlerts.detail(alertId),
    queryFn: async () => {
      const response = await api.get<PriceAlert>(`/price-alerts/${alertId}`);
      return response.data;
    },
    enabled: !!alertId,
  });
}

/**
 * Acknowledge a single alert
 */
export function useAcknowledgeAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      alertId,
      notes,
    }: {
      alertId: number;
      notes?: string;
    }) => {
      const response = await api.put<AcknowledgeResponse>(
        `/price-alerts/${alertId}/acknowledge`,
        { notes }
      );
      return response.data;
    },
    onSuccess: () => {
      // Invalidate alerts list and summary
      queryClient.invalidateQueries({ queryKey: queryKeys.priceAlerts.all });
    },
  });
}

/**
 * Acknowledge multiple alerts in bulk
 */
export function useBulkAcknowledge() {
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
        '/price-alerts/acknowledge-bulk',
        { alert_ids: alertIds, notes }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.priceAlerts.all });
    },
  });
}

/**
 * Acknowledge ALL pending alerts for the company
 */
export function useAcknowledgeAll() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ notes }: { notes?: string } = {}) => {
      const response = await api.put<{ acknowledged_count: number }>(
        '/price-alerts/acknowledge-all',
        { notes }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.priceAlerts.all });
    },
  });
}

// =============================================================================
// ADVANCE SURGE SCANNER
// =============================================================================

export interface SurgeDetection {
  theater_name: string;
  circuit_name: string | null;
  film_title: string;
  play_date: string;
  ticket_type: string;
  format: string | null;
  current_price: number;
  baseline_price: number;
  surge_percent: number;
  surge_multiplier: number;
  day_type: string | null;
  day_of_week: number | null;  // 0=Monday, 6=Sunday
  daypart: string | null;  // matinee, evening, or late
  is_discount_day: boolean;  // True if this is a known discount day for the circuit
  discount_day_price: number | null;  // Expected discount price if is_discount_day
}

export interface DiscountDayComplianceItem {
  theater_name: string;
  circuit_name: string | null;
  film_title: string;
  play_date: string;
  ticket_type: string;
  format: string | null;
  current_price: number;
  expected_discount_price: number;
  discount_program_name: string | null;
  is_compliant: boolean;
  is_special_event: boolean;
  is_loyalty_ac: boolean;
  is_plf: boolean;
  deviation_percent: number | null;
}

export interface AdvanceSurgeScanResponse {
  scan_date_from: string;
  scan_date_to: string;
  total_prices_scanned: number;
  total_surges_found: number;
  surge_threshold_percent: number;
  min_surge_amount: number | null;
  surges: SurgeDetection[];
  circuits_scanned: string[];
  films_with_surges: string[];
  discount_day_prices_filtered: number;  // Count of prices skipped due to discount day matching
  discount_day_compliance: DiscountDayComplianceItem[];  // Detailed per-film compliance info
  discount_day_violations: number;  // Count of non-compliant (excluding special events)
  circuits_with_profiles: string[];  // Circuits that have discovered profiles
}

interface SurgeScanFilters {
  dateFrom: string;
  dateTo: string;
  circuit?: string;
  theater?: string;
  film?: string;
  surgeThreshold?: number;
  minSurgeAmount?: number;
}

/**
 * Scan advance dates for surge pricing
 * Compares EntTelligence cache prices against baselines to detect surges
 *
 * Detection logic: A surge is flagged if price exceeds baseline by:
 * - >= surgeThreshold percent (e.g., 20% above baseline), OR
 * - >= minSurgeAmount dollars (e.g., $1.00 above baseline)
 */
export function useAdvanceSurgeScan(filters: SurgeScanFilters, options?: { enabled?: boolean }) {
  const params = new URLSearchParams();
  params.append('date_from', filters.dateFrom);
  params.append('date_to', filters.dateTo);
  if (filters.circuit) params.append('circuit', filters.circuit);
  if (filters.theater) params.append('theater', filters.theater);
  if (filters.film) params.append('film', filters.film);
  if (filters.surgeThreshold !== undefined) params.append('surge_threshold', String(filters.surgeThreshold));
  if (filters.minSurgeAmount !== undefined) params.append('min_surge_amount', String(filters.minSurgeAmount));

  return useQuery({
    queryKey: ['surge-scanner', 'advance', filters],
    queryFn: async () => {
      const response = await api.get<AdvanceSurgeScanResponse>(
        `/surge-scanner/advance?${params.toString()}`
      );
      return response.data;
    },
    enabled: options?.enabled ?? false,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}


// =============================================================================
// NEW FILM MONITORING
// =============================================================================

export interface NewFilmSurge {
  film_title: string;
  theater_name: string;
  circuit_name: string | null;
  play_date: string;
  ticket_type: string;
  format: string | null;
  current_price: number;
  baseline_price: number;
  surge_percent: number;
  first_seen: string | null;
  is_presale: boolean;
}

export interface NewFilmSurgeResponse {
  check_time: string;
  lookback_hours: number;
  total_new_prices: number;
  surges_found: number;
  films_checked: string[];
  surges: NewFilmSurge[];
}

interface NewFilmMonitorFilters {
  lookbackHours?: number;
  surgeThreshold?: number;
  minSurgeAmount?: number;
  circuit?: string;
}

/**
 * Monitor recently posted films for surge pricing
 *
 * Checks for prices added in the last N hours that exceed baselines.
 * Useful for detecting surges on new film announcements or presale openings.
 */
export function useNewFilmMonitor(filters: NewFilmMonitorFilters = {}, options?: { enabled?: boolean }) {
  const params = new URLSearchParams();
  if (filters.lookbackHours) params.append('lookback_hours', String(filters.lookbackHours));
  if (filters.surgeThreshold !== undefined) params.append('surge_threshold', String(filters.surgeThreshold));
  if (filters.minSurgeAmount !== undefined) params.append('min_surge_amount', String(filters.minSurgeAmount));
  if (filters.circuit) params.append('circuit', filters.circuit);

  return useQuery({
    queryKey: ['surge-scanner', 'new-films', filters],
    queryFn: async () => {
      const response = await api.get<NewFilmSurgeResponse>(
        `/surge-scanner/new-films?${params.toString()}`
      );
      return response.data;
    },
    enabled: options?.enabled ?? false,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchInterval: 10 * 60 * 1000, // Refetch every 10 minutes when enabled
  });
}
