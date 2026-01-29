import { http, HttpResponse } from 'msw';

const API_BASE = '/api/v1';

// Mock data
export const mockHealthResponse = {
  status: 'healthy',
  timestamp: '2026-01-16T12:00:00Z',
  version: '1.0.0',
  environment: 'test',
  database: 'connected',
};

export const mockSystemHealthResponse = {
  status: 'healthy',
  timestamp: '2026-01-16T12:00:00Z',
  version: '1.0.0',
  environment: 'test',
  components: {
    database: { status: 'ok', message: 'Connected' },
    fandango_scraper: {
      status: 'ok',
      last_check: '2026-01-16T11:55:00Z',
      failure_rate_percent: 0.5,
      theaters_checked: 100,
      theaters_failed: 1,
    },
    enttelligence: {
      status: 'ok',
      last_sync: '2026-01-16T10:00:00Z',
      records_synced: 5000,
    },
    alerts: {
      status: 'ok',
      price_pending: 5,
      schedule_pending: 2,
      total_pending: 7,
    },
    scheduler: {
      status: 'ok',
      last_activity: '2026-01-16T11:58:00Z',
      age_minutes: 2,
    },
    circuit_breakers: {
      fandango: {
        name: 'fandango',
        state: 'closed',
        failures: 0,
        failure_threshold: 5,
        reset_timeout: 300,
        last_state_change: Date.now(),
        is_open: false,
      },
      enttelligence: {
        name: 'enttelligence',
        state: 'closed',
        failures: 0,
        failure_threshold: 3,
        reset_timeout: 600,
        last_state_change: Date.now(),
        is_open: false,
      },
    },
  },
};

export const mockCacheStatus = {
  cache_file_exists: true,
  last_updated: '2026-01-16T10:00:00Z',
  market_count: 15,
  theater_count: 250,
  file_size_kb: 1024,
  metadata: {
    last_updated: '2026-01-16T10:00:00Z',
    last_refresh_type: 'full',
  },
};

export const mockCacheMarkets = {
  markets: [
    { market_name: 'Madison', total_theaters: 12, active_theaters: 10, not_on_fandango: 2 },
    { market_name: 'Milwaukee', total_theaters: 18, active_theaters: 16, not_on_fandango: 2 },
    { market_name: 'Minneapolis', total_theaters: 25, active_theaters: 23, not_on_fandango: 2 },
  ],
  total_count: 3,
};

export const mockUnmatchedTheaters = {
  theaters: [
    { theater_name: 'Test Cinema', market: 'Madison', status: 'no_match' },
    { theater_name: 'Closed Theater', market: 'Milwaukee', status: 'closed' },
  ],
  total_count: 2,
};

export const mockRepairQueueStatus = {
  queue_length: 5,
  in_progress: 1,
  failed_count: 2,
  last_processed: '2026-01-16T11:30:00Z',
};

export const mockRepairQueueJobs = {
  jobs: [
    {
      theater_name: 'Test Theater 1',
      market_name: 'Madison',
      attempts: 2,
      next_attempt_at: '2026-01-16T12:00:00Z',
      last_error: 'Connection timeout',
    },
    {
      theater_name: 'Test Theater 2',
      market_name: 'Milwaukee',
      attempts: 1,
      next_attempt_at: '2026-01-16T12:30:00Z',
    },
  ],
  total_count: 2,
};

export const mockUser = {
  id: 1,
  username: 'test_user',
  email: 'test@example.com',
  role: 'admin',
  company_id: 1,
  is_active: true,
  allowed_modes: ['all'],
  created_at: '2026-01-01T00:00:00Z',
};

export const mockAuthResponse = {
  access_token: 'mock-jwt-token',
  token_type: 'bearer',
  expires_in: 3600,
  user: mockUser,
};

// MSW Handlers
export const handlers = [
  // Health endpoints
  http.get(`${API_BASE}/health`, () => {
    return HttpResponse.json(mockHealthResponse);
  }),

  http.get(`${API_BASE}/health/full`, () => {
    return HttpResponse.json(mockSystemHealthResponse);
  }),

  http.get(`${API_BASE}/system/health`, () => {
    return HttpResponse.json(mockSystemHealthResponse);
  }),

  // Cache endpoints
  http.get(`${API_BASE}/cache/status`, () => {
    return HttpResponse.json(mockCacheStatus);
  }),

  http.get(`${API_BASE}/cache/markets`, () => {
    return HttpResponse.json(mockCacheMarkets);
  }),

  http.post(`${API_BASE}/cache/refresh`, () => {
    return HttpResponse.json({
      status: 'started',
      message: 'Cache refresh initiated',
      started_at: new Date().toISOString(),
    });
  }),

  // Theaters endpoints
  http.get(`${API_BASE}/theaters/unmatched`, () => {
    return HttpResponse.json(mockUnmatchedTheaters);
  }),

  http.post(`${API_BASE}/theaters/match`, async ({ request }) => {
    const body = await request.json() as { theater_name: string };
    return HttpResponse.json({
      success: true,
      message: 'Theater matched successfully',
      theater_name: body.theater_name,
      matched_name: body.theater_name,
    });
  }),

  // Repair queue endpoints
  http.get(`${API_BASE}/cache/repair-queue/status`, () => {
    return HttpResponse.json(mockRepairQueueStatus);
  }),

  http.get(`${API_BASE}/cache/repair-queue/jobs`, () => {
    return HttpResponse.json(mockRepairQueueJobs);
  }),

  // Circuit breaker endpoints
  http.post(`${API_BASE}/system/circuits/reset`, () => {
    return HttpResponse.json({ success: true, message: 'All circuits reset' });
  }),

  http.post(`${API_BASE}/system/circuits/:name/reset`, ({ params }) => {
    return HttpResponse.json({
      success: true,
      message: `Circuit ${params.name} reset`,
    });
  }),

  http.post(`${API_BASE}/system/circuits/:name/open`, ({ params }) => {
    return HttpResponse.json({
      success: true,
      message: `Circuit ${params.name} tripped`,
    });
  }),

  // Auth endpoints
  http.post(`${API_BASE}/auth/login`, () => {
    return HttpResponse.json(mockAuthResponse);
  }),

  http.get(`${API_BASE}/auth/me`, () => {
    return HttpResponse.json(mockUser);
  }),

  http.post(`${API_BASE}/auth/refresh`, () => {
    return HttpResponse.json(mockAuthResponse);
  }),

  // Fallback for API info
  http.get(`${API_BASE}/info`, () => {
    return HttpResponse.json({
      name: 'PriceScout API',
      version: '1.0.0',
      authentication: 'JWT',
      rate_limits: { requests_per_minute: 60 },
      endpoints: [],
      documentation: '/api/v1/docs',
    });
  }),

  http.get('/', () => {
    return HttpResponse.json({
      name: 'PriceScout API',
      version: '1.0.0',
      status: 'operational',
      docs: '/api/v1/docs',
      health: '/api/v1/health',
    });
  }),
];
