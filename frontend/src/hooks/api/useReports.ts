import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ============================================================================
// Types
// ============================================================================

export interface OperatingHoursRecord {
  theater_name: string;
  date: string;
  opening_time: string;
  closing_time: string;
  first_showtime?: string;
  last_showtime?: string;
  total_showtimes: number;
}

export interface OperatingHoursResponse {
  record_count: number;
  date_range: {
    earliest?: string;
    latest?: string;
  };
  operating_hours: OperatingHoursRecord[];
}

export interface DailyLineupShowtime {
  film_title: string;
  showtime: string;
  format?: string;
  daypart?: string;
  runtime?: number;
}

export interface DailyLineupResponse {
  theater: string;
  date: string;
  showtime_count: number;
  showtimes: DailyLineupShowtime[];
}

export interface PlfFormatData {
  format: string;
  showtime_count: number;
}

export interface PlfFormatsResponse {
  theater_count: number;
  total_plf_showtimes: number;
  theaters: Record<string, PlfFormatData[]>;
}

// ============================================================================
// Operating Hours Hooks
// ============================================================================

interface OperatingHoursFilters {
  theater?: string;
  date?: string;
  limit?: number;
}

/**
 * Fetch operating hours data (existing data from database)
 */
export function useOperatingHours(filters: OperatingHoursFilters = {}) {
  return useQuery({
    queryKey: ['reports', 'operating-hours', filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.theater) params.append('theater', filters.theater);
      if (filters.date) params.append('date', filters.date);
      if (filters.limit) params.append('limit', String(filters.limit));

      const response = await api.get<OperatingHoursResponse>(
        `/reports/operating-hours?${params.toString()}`
      );
      return response.data;
    },
  });
}

// ============================================================================
// Operating Hours Scraping
// ============================================================================

export interface OperatingHoursScrapeRecord {
  theater_name: string;
  date: string;
  open_time: string;
  close_time: string;
  first_showtime?: string;
  last_showtime?: string;
  duration_hours: number;
  showtime_count: number;
}

export interface WeekComparisonRecord {
  theater_name: string;
  day_of_week: string;
  prev_date?: string;
  prev_open?: string;
  prev_close?: string;
  prev_first?: string;
  prev_last?: string;
  prev_duration?: number;
  curr_date: string;
  curr_open: string;
  curr_close: string;
  curr_first?: string;
  curr_last?: string;
  curr_duration: number;
  status: 'changed' | 'no_change' | 'new';
}

export interface OperatingHoursScrapeResponse {
  operating_hours: OperatingHoursScrapeRecord[];
  comparison?: WeekComparisonRecord[];
  summary: { changed: number; no_change: number; new: number };
  duration_seconds: number;
}

interface FetchOperatingHoursRequest {
  theaters: { name: string; url: string }[];
  start_date: string;
  end_date: string;
}

/**
 * Scrape and calculate operating hours for theaters and date range
 */
export function useFetchOperatingHours() {
  return useMutation({
    mutationFn: async (request: FetchOperatingHoursRequest) => {
      const response = await api.post<OperatingHoursScrapeResponse>(
        '/scrapes/operating-hours',
        request
      );
      return response.data;
    },
  });
}

// ============================================================================
// Daily Lineup Hooks
// ============================================================================

interface DailyLineupParams {
  theater: string;
  date: string;
}

/**
 * Fetch daily lineup for a specific theater and date
 */
export function useDailyLineup(params: DailyLineupParams, options?: Record<string, unknown>) {
  return useQuery({
    queryKey: ['reports', 'daily-lineup', params.theater, params.date],
    queryFn: async () => {
      const searchParams = new URLSearchParams();
      searchParams.append('theater', params.theater);
      searchParams.append('date', params.date);

      const response = await api.get<DailyLineupResponse>(
        `/reports/daily-lineup?${searchParams.toString()}`
      );
      return response.data;
    },
    enabled: !!params.theater && !!params.date,
    ...options,
  });
}

// ============================================================================
// PLF Formats Hooks
// ============================================================================

/**
 * Fetch PLF (Premium Large Format) distribution data
 */
export function usePlfFormats(date?: string) {
  return useQuery({
    queryKey: ['reports', 'plf-formats', date],
    queryFn: async () => {
      const params = date ? `?date=${date}` : '';
      const response = await api.get<PlfFormatsResponse>(
        `/reports/plf-formats${params}`
      );
      return response.data;
    },
  });
}

// ============================================================================
// Report Generation Hooks
// ============================================================================

interface ShowtimeViewRequest {
  all_showings: Record<string, unknown>[];
  selected_films: string[];
  theaters: string[];
  date_start: string;
  date_end: string;
  context_title?: string;
}

/**
 * Generate showtime view HTML report
 */
export function useGenerateShowtimeHtml() {
  return useMutation({
    mutationFn: async (request: ShowtimeViewRequest) => {
      const response = await api.post('/reports/showtime-view/html', request, {
        responseType: 'blob',
      });
      return response.data as Blob;
    },
  });
}

/**
 * Generate showtime view PDF report
 */
export function useGenerateShowtimePdf() {
  return useMutation({
    mutationFn: async (request: ShowtimeViewRequest) => {
      const response = await api.post('/reports/showtime-view/pdf', request, {
        responseType: 'blob',
      });
      return response.data as Blob;
    },
  });
}

interface SelectionAnalysisRequest {
  selectedShowtimes: Record<string, unknown>;
  format?: 'csv' | 'json';
}

/**
 * Generate selection analysis report
 */
export function useGenerateSelectionAnalysis() {
  return useMutation({
    mutationFn: async (request: SelectionAnalysisRequest) => {
      const format = request.format || 'csv';
      const response = await api.post(
        `/reports/selection-analysis?format=${format}`,
        { selected_showtimes: request.selectedShowtimes },
        {
          responseType: format === 'csv' ? 'blob' : 'json',
        }
      );
      return response.data;
    },
  });
}
