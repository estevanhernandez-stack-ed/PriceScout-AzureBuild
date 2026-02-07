/**
 * PriceScout API TypeScript Interfaces
 *
 * Auto-generated from OpenAPI schema v2.0.0
 * Generated: 2026-01-07
 *
 * These interfaces match the FastAPI backend response schemas exactly.
 * Use these for type-safe API interactions in the React frontend.
 */

// ============================================================================
// Authentication Types
// ============================================================================

/** OAuth2 login request (form data) */
export interface LoginRequest {
  username: string;
  password: string;
  grant_type?: 'password';
  scope?: string;
  client_id?: string | null;
  client_secret?: string | null;
}

/** JWT token response */
export interface Token {
  access_token: string;
  token_type: string;
}

/** Password change request (authenticated user) */
export interface PasswordChange {
  old_password: string;
  new_password: string;
}

/** Admin password reset */
export interface PasswordReset {
  new_password: string;
  force_change?: boolean;
}

/** Request password reset code */
export interface PasswordResetRequest {
  username: string;
}

/** Complete password reset with code */
export interface PasswordResetWithCode {
  username: string;
  code: string;
  new_password: string;
}

// ============================================================================
// User Types
// ============================================================================

/** User roles */
export type UserRole = 'admin' | 'manager' | 'user';

/** Home location types */
export type HomeLocationType = 'director' | 'market' | 'theater';

/** Create new user request */
export interface UserCreate {
  username: string;
  password: string;
  role?: UserRole;
  company?: string | null;
  default_company?: string | null;
  home_location_type?: HomeLocationType | null;
  home_location_value?: string | null;
}

/** User response from API */
export interface UserResponse {
  user_id: number;
  username: string;
  role: string;
  company?: string | null;
  default_company?: string | null;
  home_location_type?: string | null;
  home_location_value?: string | null;
  is_admin: boolean;
  is_active: boolean;
  created_at?: string | null;
  last_login?: string | null;
}

/** Update user request */
export interface UserUpdate {
  username?: string | null;
  role?: UserRole | null;
  company?: string | null;
  default_company?: string | null;
  home_location_type?: HomeLocationType | null;
  home_location_value?: string | null;
  is_active?: boolean | null;
}

/** List of users response */
export interface UserList {
  users: UserResponse[];
  total_count: number;
}

// ============================================================================
// Price Check Types
// ============================================================================

/** Single price check record */
export interface PriceCheck {
  price_id: number;
  theater_name: string;
  film_title: string;
  showtime: string;
  /** ISO date string (YYYY-MM-DD) */
  play_date: string;
  ticket_type: string;
  format?: string | null;
  price: number;
  /** ISO datetime string */
  scraped_at: string;
}

/** Latest price by theater/format */
export interface PriceCheckLatest {
  theater_name: string;
  ticket_type: string;
  format?: string | null;
  price: number;
  /** ISO datetime string */
  last_checked: string;
  sample_film?: string | null;
}

/** Summary response for price checks query */
export interface PriceCheckSummary {
  total_records: number;
  date_range: Record<string, unknown>;
  price_checks: PriceCheck[];
}

/** Price comparison between theaters */
export interface PriceComparison {
  theater_name: string;
  ticket_type: string;
  avg_price: number;
  price_count: number;
  vs_market_avg?: number | null;
}

/** Price history entry */
export interface PriceHistory {
  /** ISO date string (YYYY-MM-DD) */
  date: string;
  ticket_type: string;
  format?: string | null;
  avg_price: number;
  min_price: number;
  max_price: number;
  price_count: number;
}

// ============================================================================
// Price Alert Types
// ============================================================================

/** Alert types (snake_case values stored in database) */
export type AlertType = 'price_increase' | 'price_decrease' | 'surge_detected' | 'new_offering' | 'discontinued' | 'discount_day_overcharge' | string;

/** Price alert model */
export interface PriceAlert {
  alert_id: number;
  theater_name: string;
  film_title?: string | null;
  ticket_type?: string | null;
  format?: string | null;
  /** Daypart: matinee, evening, late_night */
  daypart?: string | null;
  /** Actual showtime e.g., "7:30 PM" */
  showtime?: string | null;
  alert_type: AlertType;
  old_price?: number | null;
  new_price?: number | null;
  /** ISO datetime string - when the old/baseline price was captured */
  old_price_captured_at?: string | null;
  price_change_percent?: number | null;
  /** ISO datetime string */
  triggered_at: string;
  /** ISO date string (YYYY-MM-DD) */
  play_date?: string | null;
  is_acknowledged?: boolean;
  acknowledged_by?: string | null;
  /** ISO datetime string */
  acknowledged_at?: string | null;
  acknowledgment_notes?: string | null;
}

/** Alert list response */
export interface AlertListResponse {
  total: number;
  pending: number;
  alerts: PriceAlert[];
}

/** Summary statistics for alerts */
export interface AlertSummary {
  total_pending: number;
  total_acknowledged: number;
  by_type: Record<string, number>;
  by_theater: Record<string, number>;
  /** ISO datetime string */
  oldest_pending?: string | null;
  /** ISO datetime string */
  newest_pending?: string | null;
}

/** Acknowledge alert request */
export interface AcknowledgeRequest {
  notes?: string | null;
}

/** Acknowledge alert response */
export interface AcknowledgeResponse {
  alert_id: number;
  acknowledged?: boolean;
  /** ISO datetime string */
  acknowledged_at: string;
  acknowledged_by: string;
}

// ============================================================================
// Scrape Source & Job Types
// ============================================================================

/** Source types */
export type SourceType = 'web' | 'api' | 'file';

/** Create scrape source request */
export interface ScrapeSourceCreate {
  name: string;
  source_type?: SourceType;
  base_url?: string | null;
  /** Frequency in minutes (5-10080) */
  scrape_frequency_minutes?: number;
  is_active?: boolean;
  configuration?: Record<string, unknown> | null;
}

/** Scrape source response */
export interface ScrapeSourceResponse {
  source_id: number;
  company_id: number;
  name: string;
  source_type?: SourceType;
  base_url?: string | null;
  scrape_frequency_minutes?: number;
  is_active?: boolean;
  configuration?: Record<string, unknown> | null;
  /** ISO datetime string */
  last_scrape_at?: string | null;
  last_scrape_status?: string | null;
  last_scrape_records?: number;
  /** ISO datetime string */
  created_at: string;
  /** ISO datetime string */
  updated_at: string;
}

/** Update scrape source request */
export interface ScrapeSourceUpdate {
  name?: string | null;
  source_type?: string | null;
  base_url?: string | null;
  scrape_frequency_minutes?: number | null;
  is_active?: boolean | null;
  configuration?: Record<string, unknown> | null;
}

/** Scrape job status */
export type ScrapeStatus = 'Pending' | 'Running' | 'Completed' | 'Failed' | string;

/** Scrape job status response */
export interface ScrapeJobStatus {
  run_id: number;
  source_id?: number | null;
  status: ScrapeStatus;
  /** ISO datetime string */
  started_at: string;
  /** ISO datetime string */
  completed_at?: string | null;
  records_scraped?: number;
  error_message?: string | null;
}

/** Trigger scrape response */
export interface TriggerResponse {
  message: string;
  run_id: number;
  source_id: number;
  source_name: string;
}

/** Scrape data result */
export interface ScrapeData {
  run_id: number;
  data: Record<string, unknown>[];
}

// ============================================================================
// Theater Types
// ============================================================================

/** Unmatched theater record */
export interface UnmatchedTheater {
  theater_name: string;
  market: string;
  company?: string | null;
  url?: string | null;
  status: string;
}

/** List of unmatched theaters */
export interface UnmatchedTheaterList {
  theaters: UnmatchedTheater[];
  total_count: number;
}

/** Theater match request */
export interface TheaterMatchRequest {
  theater_name: string;
  market: string;
  fandango_url?: string | null;
  new_name?: string | null;
  mark_as_closed?: boolean;
  not_on_fandango?: boolean;
  external_url?: string | null;
}

/** Theater match response */
export interface TheaterMatchResponse {
  success: boolean;
  message: string;
  theater_name: string;
  matched_name?: string | null;
  url?: string | null;
}

// ============================================================================
// Circuit Benchmark Types (EntTelligence)
// ============================================================================

/** Circuit benchmark data */
export interface CircuitBenchmark {
  benchmark_id: number;
  circuit_name: string;
  week_ending_date: string;
  period_start_date?: string | null;
  total_showtimes?: number;
  total_capacity?: number;
  total_theaters?: number;
  total_films?: number;
  avg_screens_per_film?: number;
  avg_showtimes_per_theater?: number;
  /** Format distribution percentages */
  format_standard_pct?: number;
  format_imax_pct?: number;
  format_dolby_pct?: number;
  format_3d_pct?: number;
  format_other_premium_pct?: number;
  plf_total_pct?: number;
  /** Daypart distribution percentages */
  daypart_matinee_pct?: number;
  daypart_evening_pct?: number;
  daypart_late_pct?: number;
  /** Average pricing */
  avg_price_general?: number | null;
  avg_price_child?: number | null;
  avg_price_senior?: number | null;
  data_source?: string;
  created_at?: string | null;
}

/** List of circuit benchmarks */
export interface CircuitBenchmarkList {
  benchmarks: CircuitBenchmark[];
  total_count: number;
  available_weeks: string[];
}

/** Week summary for benchmarks */
export interface WeekSummary {
  week_ending_date: string;
  period_start_date: string;
  circuit_count: number;
  total_showtimes: number;
  data_freshness: string;
}

// ============================================================================
// Presale Tracking Types (EntTelligence)
// ============================================================================

/** Presale snapshot data */
export interface PresaleSnapshot {
  id: number;
  circuit_name: string;
  film_title: string;
  release_date: string;
  snapshot_date: string;
  days_before_release: number;
  total_tickets_sold?: number;
  total_revenue?: number;
  total_showtimes?: number;
  total_theaters?: number;
  avg_tickets_per_show?: number;
  avg_tickets_per_theater?: number;
  avg_ticket_price?: number;
  /** Format breakdown */
  tickets_imax?: number;
  tickets_dolby?: number;
  tickets_3d?: number;
  tickets_premium?: number;
  tickets_standard?: number;
  data_source?: string;
}

/** Presale trajectory (film over time) */
export interface PresaleTrajectory {
  film_title: string;
  release_date: string;
  circuit_name: string;
  snapshots: PresaleSnapshot[];
  current_tickets: number;
  current_revenue: number;
  velocity_trend: string;
  days_until_release: number;
}

/** Velocity metrics for presales */
export interface VelocityMetrics {
  film_title: string;
  circuit_name: string;
  snapshot_date: string;
  daily_tickets: number;
  daily_revenue: number;
  velocity_change: number;
  trend: string;
}

// ============================================================================
// Cache & Sync Types
// ============================================================================

/** Cache status response */
export interface CacheStatus {
  cache_file_exists: boolean;
  last_updated?: string | null;
  market_count?: number;
  theater_count?: number;
  file_size_kb?: number;
  metadata?: Record<string, unknown> | null;
}

/** Cache refresh request */
export interface CacheRefreshRequest {
  rebuild_broken_urls?: boolean;
  force_full_refresh?: boolean;
}

/** Cache refresh response */
export interface CacheRefreshResponse {
  status: string;
  message: string;
  started_at: string;
}

/** Sync status response */
export interface SyncStatus {
  status: string;
  message: string;
  last_sync?: string | null;
  records_synced?: number;
}

// ============================================================================
// Report Types
// ============================================================================

/** Report format options */
export type ReportFormat = 'csv' | 'json' | 'pdf' | 'html';

/** Selection analysis request */
export interface SelectionAnalysisRequest {
  /** Nested dict: date -> theater -> film -> time -> [showing dicts] */
  selected_showtimes: Record<string, unknown>;
}

/** Showtime view request for reports */
export interface ShowtimeViewRequest {
  all_showings: Record<string, unknown>;
  selected_films: string[];
  theaters: Record<string, unknown>[];
  date_start: string;
  date_end: string;
  context_title?: string | null;
}

// ============================================================================
// Admin Types
// ============================================================================

/** Audit log entry */
export interface AuditLogEntry {
  log_id: number;
  timestamp: string;
  username?: string | null;
  event_type: string;
  event_category: string;
  severity: string;
  details?: string | null;
  ip_address?: string | null;
}

/** Audit log list response */
export interface AuditLogList {
  entries: AuditLogEntry[];
  total_count: number;
}

// ============================================================================
// Error Types (RFC 7807)
// ============================================================================

/** Validation error detail */
export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/** HTTP validation error response */
export interface HTTPValidationError {
  detail?: ValidationError[];
}

/** RFC 7807 Problem Details error response */
export interface ProblemDetails {
  type?: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  timestamp?: string;
  trace_id?: string;
  errors?: Record<string, string[]>;
}

// ============================================================================
// API Response Wrappers
// ============================================================================

/** Generic paginated response */
export interface PaginatedResponse<T> {
  items: T[];
  total_count: number;
  page?: number;
  page_size?: number;
  has_more?: boolean;
}

/** Generic API response wrapper */
export interface ApiResponse<T> {
  data: T;
  status: 'success' | 'error';
  message?: string;
}

/** API info response */
export interface ApiInfo {
  name: string;
  version: string;
  status: string;
  docs?: string;
  health?: string;
  authentication?: Record<string, unknown>;
  rate_limits?: Record<string, unknown>;
  endpoints?: Record<string, unknown>;
  documentation?: string;
}

/** Health check response */
export interface HealthCheck {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  version: string;
  environment: string;
  database?: {
    status: string;
    latency_ms?: number;
  };
  cache?: {
    status: string;
  };
}

// ============================================================================
// Utility Types
// ============================================================================

/** ISO date string (YYYY-MM-DD) */
export type ISODateString = string;

/** ISO datetime string (YYYY-MM-DDTHH:mm:ss.sssZ) */
export type ISODateTimeString = string;

/** Currency amount (stored as number, displayed with formatting) */
export type Currency = number;

/** Percentage (0-100 or 0-1 depending on context) */
export type Percentage = number;

/** ID type for database primary keys */
export type ID = number;

// ============================================================================
// API Endpoint Types
// ============================================================================

/** Query parameters for price checks */
export interface PriceCheckQueryParams {
  theater_id?: number;
  theater_name?: string;
  film_title?: string;
  date_from?: ISODateString;
  date_to?: ISODateString;
  ticket_type?: string;
  format?: string;
  limit?: number;
  offset?: number;
}

/** Query parameters for alerts */
export interface AlertQueryParams {
  acknowledged?: boolean;
  alert_type?: AlertType;
  theater_name?: string;
  date_from?: ISODateString;
  date_to?: ISODateString;
  limit?: number;
  offset?: number;
}

/** Query parameters for scrape jobs */
export interface ScrapeJobQueryParams {
  source_id?: number;
  status?: ScrapeStatus;
  date_from?: ISODateTimeString;
  date_to?: ISODateTimeString;
  limit?: number;
  offset?: number;
}

// ============================================================================
// Tax Configuration Types
// ============================================================================

/** Tax configuration for estimated tax adjustment on EntTelligence prices */
export interface TaxConfig {
  enabled: boolean;
  /** Default tax rate as decimal (e.g., 0.075 = 7.5%) */
  default_rate: number;
  /** Per-state tax rate overrides, keyed by 2-letter state code */
  per_state: Record<string, number>;
}

/** Tax config API response */
export interface TaxConfigResponse {
  enabled: boolean;
  default_rate: number;
  per_state: Record<string, number>;
}

/** Tax config update request (partial update supported) */
export interface TaxConfigUpdateRequest {
  enabled?: boolean;
  default_rate?: number;
  per_state?: Record<string, number>;
}

/** Query parameters for circuit benchmarks */
export interface CircuitBenchmarkQueryParams {
  circuit_name?: string;
  week_ending?: ISODateString;
  limit?: number;
}

/** Query parameters for presales */
export interface PresaleQueryParams {
  film_title?: string;
  circuit_name?: string;
  release_date?: ISODateString;
}
