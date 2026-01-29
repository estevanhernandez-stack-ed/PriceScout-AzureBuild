/**
 * PriceScout API Endpoint Definitions
 *
 * This file maps all API endpoints to their request/response types.
 * Use this as a reference when building API service functions.
 *
 * Base URL: /api/v1
 * Generated from actual router definitions: 2026-01-07
 */

import type {
  Token,
  LoginRequest,
  PasswordChange,
  PasswordReset,
  PasswordResetRequest,
  PasswordResetWithCode,
  UserResponse,
  UserCreate,
  UserUpdate,
  UserList,
  PriceCheckLatest,
  PriceCheckSummary,
  PriceHistory,
  PriceComparison,
  PriceAlert,
  AlertListResponse,
  AlertSummary,
  AcknowledgeRequest,
  AcknowledgeResponse,
  ScrapeSourceCreate,
  ScrapeSourceResponse,
  ScrapeSourceUpdate,
  ScrapeJobStatus,
  TriggerResponse,
  UnmatchedTheaterList,
  TheaterMatchRequest,
  TheaterMatchResponse,
  CircuitBenchmark,
  CircuitBenchmarkList,
  WeekSummary,
  PresaleSnapshot,
  PresaleTrajectory,
  VelocityMetrics,
  CacheStatus,
  CacheRefreshRequest,
  CacheRefreshResponse,
  SyncStatus,
  SelectionAnalysisRequest,
  ShowtimeViewRequest,
  AuditLogList,
  ApiInfo,
  HealthCheck,
} from './api.types';

// ============================================================================
// API Endpoint Type Definitions
// ============================================================================

/**
 * Authentication Endpoints
 * Router: auth.py
 * Prefix: /auth
 */
export interface AuthEndpoints {
  /** POST /api/v1/auth/token - OAuth2 password grant */
  'POST /auth/token': {
    request: LoginRequest; // Form data
    response: Token;
  };

  /** POST /api/v1/auth/logout - Logout current user */
  'POST /auth/logout': {
    request: void;
    response: { message: string };
  };

  /** GET /api/v1/auth/me - Get current user info */
  'GET /auth/me': {
    request: void;
    response: UserResponse;
  };

  /** POST /api/v1/auth/refresh - Refresh access token */
  'POST /auth/refresh': {
    request: void;
    response: Token;
  };

  /** GET /api/v1/auth/health - Auth service health */
  'GET /auth/health': {
    request: void;
    response: {
      status: string;
      db_auth_enabled: boolean;
      entra_enabled: boolean;
      api_key_enabled: boolean;
    };
  };
}

/**
 * User Self-Service Endpoints
 * Router: users.py
 * Prefix: /users
 */
export interface UserEndpoints {
  /** POST /api/v1/users/change-password - Change own password */
  'POST /users/change-password': {
    request: PasswordChange;
    response: { message: string };
  };

  /** POST /api/v1/users/reset-password-request - Request reset code */
  'POST /users/reset-password-request': {
    request: PasswordResetRequest;
    response: { message: string };
  };

  /** POST /api/v1/users/reset-password-with-code - Reset with code */
  'POST /users/reset-password-with-code': {
    request: PasswordResetWithCode;
    response: { message: string };
  };
}

/**
 * Admin Endpoints
 * Router: admin.py
 * Prefix: (none - routes include /admin)
 */
export interface AdminEndpoints {
  /** GET /api/v1/admin/users - List all users */
  'GET /admin/users': {
    request: { skip?: number; limit?: number };
    response: UserList;
  };

  /** GET /api/v1/admin/users/:user_id - Get user by ID */
  'GET /admin/users/:user_id': {
    request: void;
    response: UserResponse;
  };

  /** POST /api/v1/admin/users - Create new user */
  'POST /admin/users': {
    request: UserCreate;
    response: UserResponse;
  };

  /** PUT /api/v1/admin/users/:user_id - Update user */
  'PUT /admin/users/:user_id': {
    request: UserUpdate;
    response: UserResponse;
  };

  /** DELETE /api/v1/admin/users/:user_id - Delete user */
  'DELETE /admin/users/:user_id': {
    request: void;
    response: void; // 204 No Content
  };

  /** POST /api/v1/admin/users/:user_id/reset-password - Reset user password */
  'POST /admin/users/:user_id/reset-password': {
    request: PasswordReset;
    response: { message: string };
  };

  /** GET /api/v1/admin/audit-log - Audit logs */
  'GET /admin/audit-log': {
    request: {
      username?: string;
      event_type?: string;
      event_category?: string;
      severity?: string;
      date_from?: string;
      date_to?: string;
      limit?: number;
      offset?: number;
    };
    response: AuditLogList;
  };

  /** GET /api/v1/admin/audit-log/event-types - List event types */
  'GET /admin/audit-log/event-types': {
    request: void;
    response: { event_types: string[] };
  };

  /** GET /api/v1/admin/audit-log/categories - List categories */
  'GET /admin/audit-log/categories': {
    request: void;
    response: { categories: string[] };
  };
}

/**
 * Price Check Endpoints
 * Router: price_checks.py
 * Prefix: (none)
 */
export interface PriceCheckEndpoints {
  /** GET /api/v1/price-checks - Query price checks */
  'GET /price-checks': {
    request: {
      theater_name?: string;
      film_title?: string;
      date_from?: string;
      date_to?: string;
      ticket_type?: string;
      format?: string;
      limit?: number;
      offset?: number;
    };
    response: PriceCheckSummary;
  };

  /** GET /api/v1/price-checks/latest/:theater_name - Latest prices for theater */
  'GET /price-checks/latest/:theater_name': {
    request: void;
    response: PriceCheckLatest[];
  };

  /** GET /api/v1/price-history/:theater_name - Price history */
  'GET /price-history/:theater_name': {
    request: {
      days?: number;
      ticket_type?: string;
      format?: string;
    };
    response: PriceHistory[];
  };

  /** GET /api/v1/price-comparison - Compare prices across theaters */
  'GET /price-comparison': {
    request: {
      market?: string;
      theater_names?: string[];
      ticket_type?: string;
    };
    response: PriceComparison[];
  };
}

/**
 * Price Alert Endpoints
 * Router: price_alerts.py
 * Prefix: /price-alerts
 */
export interface PriceAlertEndpoints {
  /** GET /api/v1/price-alerts - List alerts */
  'GET /price-alerts': {
    request: {
      acknowledged?: boolean;
      alert_type?: string;
      theater_name?: string;
      limit?: number;
      offset?: number;
    };
    response: AlertListResponse;
  };

  /** GET /api/v1/price-alerts/summary - Alert statistics */
  'GET /price-alerts/summary': {
    request: void;
    response: AlertSummary;
  };

  /** GET /api/v1/price-alerts/:alert_id - Get single alert */
  'GET /price-alerts/:alert_id': {
    request: void;
    response: PriceAlert;
  };

  /** PUT /api/v1/price-alerts/:alert_id/acknowledge - Acknowledge alert */
  'PUT /price-alerts/:alert_id/acknowledge': {
    request: AcknowledgeRequest;
    response: AcknowledgeResponse;
  };

  /** PUT /api/v1/price-alerts/acknowledge-bulk - Bulk acknowledge */
  'PUT /price-alerts/acknowledge-bulk': {
    request: { alert_ids: number[]; notes?: string };
    response: { acknowledged_count: number };
  };
}

/**
 * Scrape Source Endpoints
 * Router: scrape_sources.py
 * Prefix: (none)
 */
export interface ScrapeSourceEndpoints {
  /** GET /api/v1/scrape-sources - List scrape sources */
  'GET /scrape-sources': {
    request: { active_only?: boolean };
    response: ScrapeSourceResponse[];
  };

  /** POST /api/v1/scrape-sources - Create scrape source */
  'POST /scrape-sources': {
    request: ScrapeSourceCreate;
    response: ScrapeSourceResponse;
  };

  /** GET /api/v1/scrape-sources/:source_id - Get scrape source */
  'GET /scrape-sources/:source_id': {
    request: void;
    response: ScrapeSourceResponse;
  };

  /** PUT /api/v1/scrape-sources/:source_id - Update scrape source */
  'PUT /scrape-sources/:source_id': {
    request: ScrapeSourceUpdate;
    response: ScrapeSourceResponse;
  };

  /** DELETE /api/v1/scrape-sources/:source_id - Delete scrape source */
  'DELETE /scrape-sources/:source_id': {
    request: void;
    response: void; // 204 No Content
  };
}

/**
 * Scrape Job Endpoints
 * Router: scrape_sources.py
 * Prefix: /scrape-jobs
 */
export interface ScrapeJobEndpoints {
  /** POST /api/v1/scrape-jobs/trigger/:source_id - Trigger scrape job */
  'POST /scrape-jobs/trigger/:source_id': {
    request: void;
    response: TriggerResponse;
  };

  /** GET /api/v1/scrape-jobs/:run_id/status - Get scrape job status */
  'GET /scrape-jobs/:run_id/status': {
    request: void;
    response: ScrapeJobStatus;
  };

  /** GET /api/v1/scrape-jobs - List scrape jobs */
  'GET /scrape-jobs': {
    request: {
      source_id?: number;
      status?: string;
      limit?: number;
      offset?: number;
    };
    response: ScrapeJobStatus[];
  };
}

/**
 * Scrape Data Endpoints
 * Router: scrapes.py
 * Prefix: (none)
 */
export interface ScrapeDataEndpoints {
  /** POST /api/v1/scrapes/save - Save scrape data */
  'POST /scrapes/save': {
    request: {
      run_id: number;
      data: Record<string, unknown>[];
    };
    response: { message: string; records_saved: number };
  };

  /** POST /api/v1/scrape_runs - Create scrape run */
  'POST /scrape_runs': {
    request: {
      source_id: number;
      status?: string;
    };
    response: { run_id: number; status: string };
  };
}

/**
 * Market Endpoints
 * Router: markets.py
 * Prefix: /markets
 */
export interface MarketEndpoints {
  /** GET /api/v1/markets - List markets */
  'GET /markets': {
    request: void;
    response: { markets: string[] };
  };
}

/**
 * Cache & Theater Matching Endpoints
 * Router: cache.py
 * Prefix: (none)
 */
export interface CacheEndpoints {
  /** GET /api/v1/cache/status - Cache status */
  'GET /cache/status': {
    request: void;
    response: CacheStatus;
  };

  /** GET /api/v1/cache/markets - Get cached markets data */
  'GET /cache/markets': {
    request: void;
    response: {
      markets: Array<{
        name: string;
        theater_count: number;
      }>;
    };
  };

  /** POST /api/v1/cache/refresh - Refresh cache */
  'POST /cache/refresh': {
    request: CacheRefreshRequest;
    response: CacheRefreshResponse;
  };

  /** GET /api/v1/cache/backup - Download cache backup */
  'GET /cache/backup': {
    request: void;
    response: Blob; // JSON file download
  };

  /** GET /api/v1/theaters/unmatched - List unmatched theaters */
  'GET /theaters/unmatched': {
    request: { market?: string };
    response: UnmatchedTheaterList;
  };

  /** POST /api/v1/theaters/match - Match/update theater */
  'POST /theaters/match': {
    request: TheaterMatchRequest;
    response: TheaterMatchResponse;
  };
}

/**
 * Circuit Benchmark Endpoints
 * Router: circuit_benchmarks.py
 * Prefix: /circuit-benchmarks
 */
export interface CircuitBenchmarkEndpoints {
  /** GET /api/v1/circuit-benchmarks - List benchmarks */
  'GET /circuit-benchmarks': {
    request: {
      circuit_name?: string;
      week_ending?: string;
      limit?: number;
    };
    response: CircuitBenchmarkList;
  };

  /** GET /api/v1/circuit-benchmarks/weeks - Available weeks */
  'GET /circuit-benchmarks/weeks': {
    request: void;
    response: WeekSummary[];
  };

  /** GET /api/v1/circuit-benchmarks/:week_ending_date - Benchmarks for week */
  'GET /circuit-benchmarks/:week_ending_date': {
    request: void;
    response: CircuitBenchmark[];
  };

  /** POST /api/v1/circuit-benchmarks/sync - Sync from EntTelligence */
  'POST /circuit-benchmarks/sync': {
    request: void;
    response: SyncStatus;
  };

  /** GET /api/v1/circuit-benchmarks/compare - Compare circuits */
  'GET /circuit-benchmarks/compare': {
    request: {
      circuits: string[];
      week_ending: string;
    };
    response: CircuitBenchmark[];
  };
}

/**
 * Presale Tracking Endpoints
 * Router: presales.py
 * Prefix: /presales
 */
export interface PresaleEndpoints {
  /** GET /api/v1/presales - List presale snapshots */
  'GET /presales': {
    request: {
      film_title?: string;
      circuit_name?: string;
      release_date?: string;
      limit?: number;
    };
    response: PresaleSnapshot[];
  };

  /** GET /api/v1/presales/films - Films with presale data */
  'GET /presales/films': {
    request: void;
    response: Array<{
      film_title: string;
      release_date: string;
      has_snapshots: boolean;
    }>;
  };

  /** GET /api/v1/presales/:film_title - Presale trajectory for film */
  'GET /presales/:film_title': {
    request: { circuit_name?: string };
    response: PresaleTrajectory;
  };

  /** GET /api/v1/presales/velocity/:film_title - Velocity metrics */
  'GET /presales/velocity/:film_title': {
    request: void;
    response: VelocityMetrics[];
  };

  /** GET /api/v1/presales/compare - Compare presales across films */
  'GET /presales/compare': {
    request: {
      film_titles: string[];
      circuit_name?: string;
    };
    response: Array<{
      film_title: string;
      trajectory: PresaleTrajectory;
    }>;
  };

  /** POST /api/v1/presales/sync - Sync from EntTelligence */
  'POST /presales/sync': {
    request: void;
    response: SyncStatus;
  };
}

/**
 * Report Endpoints
 * Router: reports.py
 * Prefix: /reports (via main.py include)
 */
export interface ReportEndpoints {
  /** POST /api/v1/reports/selection-analysis - Selection analysis */
  'POST /reports/selection-analysis': {
    request: SelectionAnalysisRequest;
    response: Blob; // CSV or JSON based on format param
  };

  /** POST /api/v1/reports/showtime-view/html - HTML showtime view */
  'POST /reports/showtime-view/html': {
    request: ShowtimeViewRequest;
    response: string; // HTML content
  };

  /** POST /api/v1/reports/showtime-view/pdf - PDF showtime view */
  'POST /reports/showtime-view/pdf': {
    request: ShowtimeViewRequest;
    response: Blob; // PDF file
  };

  /** GET /api/v1/reports/daily-lineup - Daily lineup report */
  'GET /reports/daily-lineup': {
    request: {
      date?: string;
      market?: string;
      format?: 'json' | 'csv' | 'pdf';
    };
    response: Blob | Record<string, unknown>;
  };

  /** GET /api/v1/reports/operating-hours - Operating hours report */
  'GET /reports/operating-hours': {
    request: {
      market?: string;
      date_from?: string;
      date_to?: string;
      format?: 'json' | 'csv';
    };
    response: Blob | Record<string, unknown>;
  };

  /** GET /api/v1/reports/plf-formats - PLF formats report */
  'GET /reports/plf-formats': {
    request: {
      market?: string;
      date?: string;
      format?: 'json' | 'csv';
    };
    response: Blob | Record<string, unknown>;
  };
}

/**
 * Resource Endpoints (Theaters, Films, Showtimes, Pricing)
 * Router: resources.py
 * Prefix: (none)
 */
export interface ResourceEndpoints {
  /** GET /api/v1/theaters - List theaters */
  'GET /theaters': {
    request: {
      market?: string;
      company?: string;
      search?: string;
      limit?: number;
      offset?: number;
    };
    response: {
      theaters: Array<{
        name: string;
        market: string;
        company?: string;
        url?: string;
        is_matched: boolean;
      }>;
      total_count: number;
    };
  };

  /** GET /api/v1/films - List films */
  'GET /films': {
    request: {
      search?: string;
      date_from?: string;
      date_to?: string;
      limit?: number;
      offset?: number;
    };
    response: {
      films: Array<{
        title: string;
        release_date?: string;
        showtime_count: number;
      }>;
      total_count: number;
    };
  };

  /** GET /api/v1/scrape-runs - List scrape runs */
  'GET /scrape-runs': {
    request: {
      source_id?: number;
      status?: string;
      date_from?: string;
      date_to?: string;
      limit?: number;
      offset?: number;
    };
    response: {
      runs: Array<{
        run_id: number;
        source_name: string;
        status: string;
        started_at: string;
        completed_at?: string;
        records_scraped: number;
      }>;
      total_count: number;
    };
  };

  /** GET /api/v1/showtimes/search - Search showtimes */
  'GET /showtimes/search': {
    request: {
      theater_name?: string;
      film_title?: string;
      date?: string;
      date_from?: string;
      date_to?: string;
      format?: string;
      limit?: number;
      offset?: number;
    };
    response: {
      showtimes: Array<{
        theater_name: string;
        film_title: string;
        showtime: string;
        play_date: string;
        format?: string;
        price?: number;
      }>;
      total_count: number;
    };
  };

  /** GET /api/v1/pricing - Get pricing data */
  'GET /pricing': {
    request: {
      theater_name?: string;
      film_title?: string;
      ticket_type?: string;
      format?: string;
      date_from?: string;
      date_to?: string;
      limit?: number;
      offset?: number;
    };
    response: {
      pricing: Array<{
        theater_name: string;
        film_title: string;
        ticket_type: string;
        format?: string;
        price: number;
        scraped_at: string;
      }>;
      total_count: number;
    };
  };
}

/**
 * Task Endpoints (Background Jobs)
 * Router: tasks.py
 * Prefix: /tasks
 */
export interface TaskEndpoints {
  /** GET /api/v1/tasks - List background tasks */
  'GET /tasks': {
    request: void;
    response: {
      tasks: Array<{
        task_id: string;
        task_type: string;
        status: string;
        started_at: string;
        completed_at?: string;
        result?: Record<string, unknown>;
        error?: string;
      }>;
    };
  };
}

/**
 * System Endpoints
 * Defined in main.py
 */
export interface SystemEndpoints {
  /** GET / - API root info */
  'GET /': {
    request: void;
    response: {
      name: string;
      version: string;
      status: string;
      docs: string;
      health: string;
    };
  };

  /** GET /api/v1/info - Full API info */
  'GET /info': {
    request: void;
    response: ApiInfo;
  };

  /** GET /api/v1/health - Health check */
  'GET /health': {
    request: void;
    response: HealthCheck;
  };

  /** GET /api/v1/openapi.json - OpenAPI spec */
  'GET /openapi.json': {
    request: void;
    response: Record<string, unknown>;
  };
}

// ============================================================================
// Combined API Type
// ============================================================================

/** All API endpoints combined */
export type AllEndpoints = AuthEndpoints &
  UserEndpoints &
  AdminEndpoints &
  PriceCheckEndpoints &
  PriceAlertEndpoints &
  ScrapeSourceEndpoints &
  ScrapeJobEndpoints &
  ScrapeDataEndpoints &
  MarketEndpoints &
  CacheEndpoints &
  CircuitBenchmarkEndpoints &
  PresaleEndpoints &
  ReportEndpoints &
  ResourceEndpoints &
  TaskEndpoints &
  SystemEndpoints;

/** Extract request type for an endpoint */
export type RequestType<T extends keyof AllEndpoints> =
  AllEndpoints[T]['request'];

/** Extract response type for an endpoint */
export type ResponseType<T extends keyof AllEndpoints> =
  AllEndpoints[T]['response'];

// ============================================================================
// Endpoint URL Helpers
// ============================================================================

/** API base URL */
export const API_BASE = '/api/v1';

/** Build URL with path parameters */
export function buildUrl(
  path: string,
  params: Record<string, string | number>
): string {
  let url = path;
  for (const [key, value] of Object.entries(params)) {
    url = url.replace(`:${key}`, encodeURIComponent(String(value)));
  }
  return `${API_BASE}${url}`;
}

/** Build URL with query parameters */
export function buildUrlWithQuery(
  path: string,
  query: Record<string, string | number | boolean | undefined>
): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) {
      params.append(key, String(value));
    }
  }
  const queryString = params.toString();
  return queryString ? `${API_BASE}${path}?${queryString}` : `${API_BASE}${path}`;
}
