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
  total_queued: 5,
  due_now: 2,
  max_attempts_reached: 1,
  by_attempts: { '1': 2, '2': 2, '3': 1 },
  max_attempts_limit: 5,
};

export const mockRepairQueueJobs = [
  {
    theater_name: 'Test Theater 1',
    market_name: 'Madison',
    attempts: 2,
    next_attempt_at: '2026-01-16T12:00:00Z',
    error_message: 'Connection timeout',
  },
  {
    theater_name: 'Test Theater 2',
    market_name: 'Milwaukee',
    attempts: 1,
    next_attempt_at: '2026-01-16T12:30:00Z',
  },
];

export const mockCircuitBenchmarks = {
  benchmarks: [
    {
      benchmark_id: 1,
      circuit_name: 'AMC',
      week_ending_date: '2026-01-12',
      total_showtimes: 5000,
      total_capacity: 250000,
      total_theaters: 50,
      total_films: 25,
      avg_screens_per_film: 4.5,
      avg_showtimes_per_theater: 100,
      format_standard_pct: 70.0,
      format_imax_pct: 10.0,
      format_dolby_pct: 8.0,
      format_3d_pct: 7.0,
      format_other_premium_pct: 5.0,
      plf_total_pct: 30.0,
      daypart_matinee_pct: 25.0,
      daypart_evening_pct: 55.0,
      daypart_late_pct: 20.0,
      data_source: 'enttelligence',
    },
    {
      benchmark_id: 2,
      circuit_name: 'Regal',
      week_ending_date: '2026-01-12',
      total_showtimes: 4500,
      total_capacity: 225000,
      total_theaters: 45,
      total_films: 23,
      avg_screens_per_film: 4.2,
      avg_showtimes_per_theater: 100,
      format_standard_pct: 72.0,
      format_imax_pct: 8.0,
      format_dolby_pct: 6.0,
      format_3d_pct: 9.0,
      format_other_premium_pct: 5.0,
      plf_total_pct: 28.0,
      daypart_matinee_pct: 28.0,
      daypart_evening_pct: 52.0,
      daypart_late_pct: 20.0,
      data_source: 'enttelligence',
    },
  ],
  total_count: 2,
  available_weeks: ['2026-01-12', '2026-01-05', '2025-12-29'],
};

export const mockPriceAlerts = {
  alerts: [
    {
      alert_id: 1,
      theater_name: 'AMC Madison 6',
      film_title: 'Test Movie',
      showtime: '7:00 PM',
      play_date: '2026-01-20',
      alert_type: 'price_increase',
      old_price: 12.99,
      new_price: 14.99,
      price_diff: 2.0,
      created_at: '2026-01-16T10:00:00Z',
      acknowledged: false,
    },
    {
      alert_id: 2,
      theater_name: 'Regal Cinema',
      film_title: 'Another Film',
      showtime: '8:30 PM',
      play_date: '2026-01-21',
      alert_type: 'price_decrease',
      old_price: 15.99,
      new_price: 11.99,
      price_diff: -4.0,
      created_at: '2026-01-16T09:00:00Z',
      acknowledged: true,
    },
  ],
  total_count: 2,
  unacknowledged_count: 1,
};

export const mockAlertSummary = {
  total_alerts: 10,
  pending_alerts: 5,
  acknowledged_today: 3,
  by_type: {
    price_increase: 6,
    price_decrease: 4,
  },
};

// Mock presales - returns arrays to match hook return types
export const mockPresales = [
  {
    id: 1,
    circuit_name: 'AMC',
    film_title: 'Blockbuster Movie',
    release_date: '2026-02-15',
    snapshot_date: '2026-02-01',
    days_before_release: 14,
    total_tickets_sold: 5000,
    total_revenue: 75000,
    total_showtimes: 200,
    total_theaters: 50,
    avg_tickets_per_show: 25,
    avg_tickets_per_theater: 100,
    avg_ticket_price: 15.00,
    data_source: 'enttelligence',
  },
];

export const mockPresaleFilms = [
  {
    film_title: 'Blockbuster Movie',
    release_date: '2026-02-15',
    total_circuits: 3,
    circuit_name: null,
    current_tickets: 15000,
    current_revenue: 225000,
    days_until_release: 10,
    latest_snapshot: '2026-02-05',
  },
];

export const mockPresaleCircuits = [
  {
    circuit_name: 'AMC',
    total_films: 5,
    total_tickets: 25000,
    total_revenue: 375000,
    snapshot_count: 50,
  },
];

export const mockScrapeSources = [
  {
    source_id: 1,
    company_id: 1,
    name: 'Fandango Primary',
    source_type: 'web',
    base_url: 'https://www.fandango.com',
    scrape_frequency_minutes: 60,
    is_active: true,
    configuration: null,
    last_scrape_at: '2026-01-16T10:00:00Z',
    last_scrape_status: 'completed',
    last_scrape_records: 500,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-16T10:00:00Z',
  },
];

export const mockScrapeJobs = [
  {
    run_id: 1,
    status: 'completed',
    mode: 'prices',
    started_at: '2026-01-16T10:00:00Z',
    completed_at: '2026-01-16T10:30:00Z',
    records_scraped: 500,
    theaters_processed: 10,
  },
  {
    run_id: 2,
    status: 'running',
    mode: 'showings',
    started_at: '2026-01-16T11:00:00Z',
    records_scraped: 200,
    theaters_processed: 5,
  },
];

export const mockMarkets = [
  { market_name: 'Madison', theater_count: 12 },
  { market_name: 'Milwaukee', theater_count: 18 },
  { market_name: 'Minneapolis', theater_count: 25 },
];

export const mockMarketTheaters = [
  { theater_name: 'AMC Madison 6', market: 'Madison', url: 'https://fandango.com/amc-madison-6' },
  { theater_name: 'Marcus Point Cinema', market: 'Madison', url: 'https://fandango.com/marcus-point' },
];

export const mockFilms = [
  {
    film_title: 'Blockbuster Movie',
    imdb_id: 'tt1234567',
    genre: 'Action',
    mpaa_rating: 'PG-13',
    director: 'John Director',
    release_date: '2026-02-15',
    imdb_rating: 8.5,
  },
  {
    film_title: 'Drama Film',
    imdb_id: 'tt7654321',
    genre: 'Drama',
    mpaa_rating: 'R',
    director: 'Jane Director',
    release_date: '2026-03-01',
    imdb_rating: 7.8,
  },
];

// Mock baselines - matches SavedBaseline type from useBaselines.ts
export const mockBaselines = [
  {
    baseline_id: 1,
    theater_name: 'AMC Madison 6',
    ticket_type: 'Adult',
    format: 'Standard',
    daypart: 'evening',
    day_type: 'weekday',
    day_of_week: null,
    baseline_price: 12.99,
    effective_from: '2026-01-01',
    effective_to: null,
    source: 'fandango',
    sample_count: 50,
    last_discovery_at: '2026-01-15T00:00:00Z',
    created_at: '2026-01-15T00:00:00Z',
  },
];

export const mockUser = {
  user_id: 1,
  username: 'test_user',
  role: 'admin',
  company: 'Test Company',
  default_company: 'Test Company',
  home_location_type: null,
  home_location_value: null,
  is_admin: true,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  last_login: '2026-01-16T10:00:00Z',
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

  http.get(`${API_BASE}/cache/repair-queue/failed`, () => {
    return HttpResponse.json([mockRepairQueueJobs[0]]);
  }),

  http.post(`${API_BASE}/cache/repair-queue/reset`, () => {
    return HttpResponse.json({ success: true });
  }),

  http.delete(`${API_BASE}/cache/repair-queue/failed`, () => {
    return HttpResponse.json({ cleared: 1 });
  }),

  http.post(`${API_BASE}/cache/repair-queue/process`, () => {
    return HttpResponse.json({ processed: 2, success: 1, failed: 1 });
  }),

  http.get(`${API_BASE}/cache/maintenance/history`, () => {
    return HttpResponse.json({
      entries: [
        { timestamp: '2026-01-16T10:00:00Z', overall_status: 'ok', checked: 100, failed: 2, repaired: 1 },
      ],
      total_count: 1,
    });
  }),

  http.post(`${API_BASE}/cache/maintenance/run`, () => {
    return HttpResponse.json({
      timestamp: new Date().toISOString(),
      duration_seconds: 45,
      health_check: { status: 'ok', checked: 100, failed: 2, failure_rate_percent: 2, threshold_percent: 10 },
      repairs: { status: 'ok', total_failed: 2, attempted: 2, repaired: 1, still_failed: 1 },
      overall_status: 'ok',
    });
  }),

  // Circuit benchmarks endpoints
  http.get(`${API_BASE}/circuit-benchmarks`, () => {
    return HttpResponse.json(mockCircuitBenchmarks);
  }),

  http.get(`${API_BASE}/circuit-benchmarks/weeks`, () => {
    return HttpResponse.json([
      { week_ending_date: '2026-01-12', period_start_date: '2026-01-06', circuit_count: 5, total_showtimes: 25000, data_freshness: 'fresh' },
      { week_ending_date: '2026-01-05', period_start_date: '2025-12-30', circuit_count: 5, total_showtimes: 24000, data_freshness: 'recent' },
    ]);
  }),

  http.get(`${API_BASE}/circuit-benchmarks/:weekDate`, ({ params }) => {
    return HttpResponse.json({
      week_ending_date: params['weekDate'],
      circuit_count: 2,
      total_showtimes: 9500,
      total_theaters: 95,
      benchmarks: mockCircuitBenchmarks.benchmarks,
    });
  }),

  http.post(`${API_BASE}/circuit-benchmarks/sync`, () => {
    return HttpResponse.json({ status: 'started', message: 'Sync initiated', records_synced: 0 });
  }),

  // Price alerts endpoints
  http.get(`${API_BASE}/price-alerts`, () => {
    return HttpResponse.json(mockPriceAlerts);
  }),

  http.get(`${API_BASE}/price-alerts/summary`, () => {
    return HttpResponse.json(mockAlertSummary);
  }),

  http.get(`${API_BASE}/price-alerts/:id`, () => {
    return HttpResponse.json(mockPriceAlerts.alerts[0]);
  }),

  http.put(`${API_BASE}/price-alerts/:id/acknowledge`, () => {
    return HttpResponse.json({ success: true, acknowledged_at: new Date().toISOString() });
  }),

  http.put(`${API_BASE}/price-alerts/acknowledge-bulk`, () => {
    return HttpResponse.json({ acknowledged_count: 2 });
  }),

  http.put(`${API_BASE}/price-alerts/acknowledge-all`, () => {
    return HttpResponse.json({ acknowledged_count: 5 });
  }),

  // Presales endpoints
  http.get(`${API_BASE}/presales`, () => {
    return HttpResponse.json(mockPresales);
  }),

  http.get(`${API_BASE}/presales/films`, () => {
    return HttpResponse.json(mockPresaleFilms);
  }),

  http.get(`${API_BASE}/presales/circuits`, () => {
    return HttpResponse.json(mockPresaleCircuits);
  }),

  // Scrape sources endpoints
  http.get(`${API_BASE}/scrape-sources`, () => {
    return HttpResponse.json(mockScrapeSources);
  }),

  http.get(`${API_BASE}/scrape-sources/:id`, () => {
    return HttpResponse.json(mockScrapeSources[0]);
  }),

  http.post(`${API_BASE}/scrape-sources`, () => {
    return HttpResponse.json({ ...mockScrapeSources[0], source_id: 2 });
  }),

  http.put(`${API_BASE}/scrape-sources/:id`, () => {
    return HttpResponse.json(mockScrapeSources[0]);
  }),

  http.delete(`${API_BASE}/scrape-sources/:id`, () => {
    return HttpResponse.json({ success: true });
  }),

  // Scrape jobs endpoints
  http.get(`${API_BASE}/scrapes/jobs`, () => {
    return HttpResponse.json(mockScrapeJobs);
  }),

  http.get(`${API_BASE}/scrape-runs`, () => {
    return HttpResponse.json(mockScrapeJobs);
  }),

  http.get(`${API_BASE}/scrape-runs/:id`, () => {
    return HttpResponse.json(mockScrapeJobs[0]);
  }),

  http.post(`${API_BASE}/scrapes/trigger`, () => {
    return HttpResponse.json({ status: 'started', run_id: 3, message: 'Scrape triggered' });
  }),

  // Markets endpoints
  http.get(`${API_BASE}/markets`, () => {
    return HttpResponse.json(mockMarkets);
  }),

  http.get(`${API_BASE}/markets/:marketName/theaters`, () => {
    return HttpResponse.json(mockMarketTheaters);
  }),

  http.get(`${API_BASE}/cache/theaters`, () => {
    return HttpResponse.json({
      metadata: { last_updated: '2026-01-16T10:00:00Z', last_refresh_type: 'full' },
      markets: { Madison: { theaters: mockMarketTheaters } },
    });
  }),

  // Films endpoints
  http.get(`${API_BASE}/films`, () => {
    return HttpResponse.json(mockFilms);
  }),

  http.post(`${API_BASE}/films/:filmTitle/enrich`, () => {
    return HttpResponse.json({ success: true, film_title: 'Blockbuster Movie', enriched: true });
  }),

  http.post(`${API_BASE}/films/discover/fandango`, () => {
    return HttpResponse.json({ discovered: 5, films: ['New Film 1', 'New Film 2'] });
  }),

  // Price Baselines endpoints (used by useBaselines hooks)
  http.get(`${API_BASE}/price-baselines`, () => {
    return HttpResponse.json(mockBaselines);
  }),

  http.post(`${API_BASE}/price-baselines`, () => {
    return HttpResponse.json({ ...mockBaselines[0], baseline_id: 2 });
  }),

  http.put(`${API_BASE}/price-baselines/:id`, () => {
    return HttpResponse.json(mockBaselines[0]);
  }),

  http.delete(`${API_BASE}/price-baselines/:id`, () => {
    return new HttpResponse(null, { status: 204 });
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

  // Theaters endpoints
  http.get(`${API_BASE}/theaters`, () => {
    return HttpResponse.json([
      {
        theater_name: 'AMC Madison 6',
        market: 'Madison',
        url: 'https://www.fandango.com/amc-madison-6',
        status: 'active',
        company: 'AMC',
      },
      {
        theater_name: 'Marcus Point Cinema',
        market: 'Madison',
        url: 'https://www.fandango.com/marcus-point',
        status: 'active',
        company: 'Marcus',
      },
    ]);
  }),

  http.get(`${API_BASE}/theaters/unmatched`, () => {
    return HttpResponse.json({
      theaters: [
        { theater_name: 'New Theater', market: 'Milwaukee', status: 'no_match' },
      ],
      total_count: 1,
    });
  }),

  http.get(`${API_BASE}/theaters/:name/films`, () => {
    return HttpResponse.json([
      { film_title: 'Blockbuster Movie', format: 'Standard', first_showtime: '10:00', last_showtime: '22:00' },
      { film_title: 'Indie Film', format: 'Standard', first_showtime: '14:00', last_showtime: '20:00' },
    ]);
  }),

  http.post(`${API_BASE}/theaters/match`, () => {
    return HttpResponse.json({
      success: true,
      theater_name: 'New Theater',
      fandango_url: 'https://www.fandango.com/new-theater',
    });
  }),

  http.get(`${API_BASE}/price-history/:theaterName`, () => {
    return HttpResponse.json([
      { date: '2026-01-15', ticket_type: 'Adult', format: 'Standard', avg_price: 12.99, min_price: 10.99, max_price: 14.99, price_count: 5 },
      { date: '2026-01-14', ticket_type: 'Adult', format: 'Standard', avg_price: 12.49, min_price: 10.99, max_price: 13.99, price_count: 5 },
    ]);
  }),

  // Audit log endpoints
  http.get(`${API_BASE}/admin/audit-log`, () => {
    return HttpResponse.json({
      entries: [
        {
          log_id: 1,
          timestamp: '2026-01-15T12:00:00Z',
          username: 'admin',
          event_type: 'USER_LOGIN',
          event_category: 'auth',
          severity: 'info',
          details: 'User logged in successfully',
          ip_address: '192.168.1.1',
        },
        {
          log_id: 2,
          timestamp: '2026-01-15T11:00:00Z',
          username: 'test_user',
          event_type: 'SCRAPE_COMPLETE',
          event_category: 'scraping',
          severity: 'success',
          details: 'Scrape completed: 150 records',
          ip_address: null,
        },
      ],
      total_count: 2,
    });
  }),

  http.get(`${API_BASE}/admin/audit-log/event-types`, () => {
    return HttpResponse.json({
      event_types: ['USER_LOGIN', 'USER_LOGOUT', 'SCRAPE_START', 'SCRAPE_COMPLETE', 'ALERT_TRIGGERED'],
    });
  }),

  http.get(`${API_BASE}/admin/audit-log/categories`, () => {
    return HttpResponse.json({
      categories: ['auth', 'scraping', 'alerts', 'system', 'admin'],
    });
  }),

  // Analytics endpoints
  http.get(`${API_BASE}/analytics/dashboard-stats`, () => {
    return HttpResponse.json({
      total_price_checks: 1250,
      price_checks_change_pct: 12.5,
      active_alerts: 8,
      alerts_change: 2,
      avg_price: 14.99,
      price_change_pct: 3.2,
      total_theaters: 45,
      total_films: 120,
    });
  }),

  http.get(`${API_BASE}/analytics/scrape-activity`, () => {
    return HttpResponse.json([
      { day_name: 'Monday', day_index: 0, scrape_count: 15, records_scraped: 450 },
      { day_name: 'Tuesday', day_index: 1, scrape_count: 12, records_scraped: 380 },
      { day_name: 'Wednesday', day_index: 2, scrape_count: 18, records_scraped: 520 },
    ]);
  }),

  // Reports endpoints
  http.get(`${API_BASE}/reports/operating-hours`, () => {
    return HttpResponse.json({
      record_count: 10,
      date_range: { earliest: '2026-01-01', latest: '2026-01-31' },
      operating_hours: [
        {
          theater_name: 'AMC Madison 6',
          date: '2026-01-15',
          opening_time: '10:00',
          closing_time: '23:00',
          first_showtime: '10:30',
          last_showtime: '22:15',
          total_showtimes: 24,
        },
      ],
    });
  }),

  http.get(`${API_BASE}/reports/daily-lineup`, () => {
    return HttpResponse.json({
      theater: 'AMC Madison 6',
      date: '2026-01-15',
      showtime_count: 18,
      showtimes: [
        { film_title: 'Blockbuster Movie', showtime: '14:00', format: 'Standard', daypart: 'matinee' },
        { film_title: 'Indie Film', showtime: '19:00', format: 'Standard', daypart: 'evening' },
      ],
    });
  }),

  http.get(`${API_BASE}/reports/plf-formats`, () => {
    return HttpResponse.json({
      theater_count: 5,
      total_plf_showtimes: 45,
      theaters: {
        'AMC Madison 6': [
          { format: 'IMAX', showtime_count: 8 },
          { format: 'Dolby Cinema', showtime_count: 6 },
        ],
      },
    });
  }),

  // Users endpoints
  http.get(`${API_BASE}/users`, () => {
    return HttpResponse.json({
      users: [mockUser],
      total_count: 1,
    });
  }),

  http.get(`${API_BASE}/users/:id`, () => {
    return HttpResponse.json(mockUser);
  }),

  http.post(`${API_BASE}/users`, () => {
    return HttpResponse.json({ ...mockUser, user_id: 2 });
  }),

  http.put(`${API_BASE}/users/:id`, () => {
    return HttpResponse.json(mockUser);
  }),

  http.delete(`${API_BASE}/users/:id`, () => {
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API_BASE}/auth/change-password`, () => {
    return HttpResponse.json({ message: 'Password changed successfully' });
  }),

  http.post(`${API_BASE}/users/:id/reset-password`, () => {
    return HttpResponse.json({ message: 'Password reset successfully' });
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

  // =========================================================================
  // Settings endpoints (useSettings hooks)
  // =========================================================================
  http.get(`${API_BASE}/settings/tax-config`, () => {
    return HttpResponse.json({
      tax_enabled: true,
      default_tax_rate: 8.5,
      tax_included_in_price: false,
      state_rates: { WI: 5.0, MN: 6.875 },
      updated_at: '2026-01-15T00:00:00Z',
    });
  }),

  http.put(`${API_BASE}/settings/tax-config`, async ({ request }) => {
    const body = await request.json() as Record<string, unknown>;
    return HttpResponse.json({
      tax_enabled: true,
      default_tax_rate: 8.5,
      tax_included_in_price: false,
      state_rates: { WI: 5.0, MN: 6.875 },
      updated_at: new Date().toISOString(),
      ...body,
    });
  }),

  http.get(`${API_BASE}/settings/market-scope`, () => {
    return HttpResponse.json({
      total_in_market_theaters: 204,
      total_markets: 57,
      total_directors: 6,
      marcus_count: 78,
      competitor_count: 126,
      enttelligence_matched: 189,
      enttelligence_unmatched: 15,
      directors: [
        { director: 'John Smith', market_count: 12, theater_count: 45, marcus_count: 15, competitor_count: 30 },
      ],
      match_diagnostics: {
        total_json_theaters: 204,
        matched_count: 189,
        unmatched_count: 15,
        unmatched: ['Theater A', 'Theater B'],
        match_log: [
          { json_name: 'Marcus Cinema', resolved_name: 'Marcus Cinemas', method: 'normalized' },
        ],
      },
    });
  }),

  http.get(`${API_BASE}/settings/name-mapping`, () => {
    return HttpResponse.json({
      total_market_theaters: 204,
      metadata_matched: 189,
      enttelligence_matched: 189,
      unmatched_theaters: ['Theater A', 'Theater B'],
      non_trivial_matches: [
        { json_name: 'Marcus Cinema', resolved_name: 'Marcus Cinemas', method: 'normalized' },
      ],
      aliases: [
        { enttelligence_name: 'Movie Tavern Northlake', fandango_name: 'Movie Tavern Tucker', match_confidence: 0.95, is_verified: true },
      ],
    });
  }),

  http.get(`${API_BASE}/settings/system-diagnostics`, () => {
    return HttpResponse.json({
      data_sources: {
        enttelligence: { date_range: '2026-01-01 to 2026-02-06', last_fetch: '2026-02-06T02:00:00Z', theaters: 189, circuits: 27, total_rows: 45000 },
        fandango: { date_range: '2026-01-01 to 2026-02-06', last_scrape: '2026-02-05T18:30:00Z', theaters: 189, total_showings: 12000, total_prices: 48000 },
      },
      table_counts: { enttelligence_price_cache: 45000, showings: 12000, prices: 48000, price_baselines: 3200 },
      baseline_summary: { fandango: { active_count: 1800, earliest: '2026-01-01', latest_discovery: '2026-02-05' } },
      config_summary: { tax_enabled: true, tax_default_rate: 0.075, tax_state_overrides: 20, enttelligence_enabled: true },
    });
  }),

  // =========================================================================
  // Price Checks endpoints (usePriceChecks hooks)
  // =========================================================================
  http.get(`${API_BASE}/price-checks`, () => {
    return HttpResponse.json({
      total_records: 2,
      price_checks: [
        {
          check_id: 1,
          theater_name: 'AMC Madison 6',
          film_title: 'Blockbuster Movie',
          showtime: '7:00 PM',
          ticket_type: 'Adult',
          price: 14.99,
          format: 'Standard',
          date: '2026-01-15',
        },
        {
          check_id: 2,
          theater_name: 'Marcus Point Cinema',
          film_title: 'Indie Film',
          showtime: '8:00 PM',
          ticket_type: 'Adult',
          price: 12.49,
          format: 'Standard',
          date: '2026-01-15',
        },
      ],
    });
  }),

  http.get(`${API_BASE}/price-checks/latest`, () => {
    return HttpResponse.json([
      { theater_name: 'AMC Madison 6', ticket_type: 'Adult', price: 14.99, last_checked: '2026-01-15' },
    ]);
  }),

  http.get(`${API_BASE}/price-checks/latest/:theaterName`, () => {
    return HttpResponse.json([
      { theater_name: 'AMC Madison 6', ticket_type: 'Adult', price: 14.99, last_checked: '2026-01-15' },
    ]);
  }),

  http.get(`${API_BASE}/price-checks/summary`, () => {
    return HttpResponse.json({
      total_checks: 500,
      avg_price: 13.75,
      min_price: 8.99,
      max_price: 22.99,
      theater_count: 12,
      date_range: { from: '2026-01-01', to: '2026-01-15' },
    });
  }),

  http.get(`${API_BASE}/price-comparison`, () => {
    return HttpResponse.json([
      { theater_name: 'AMC Madison 6', avg_price: 14.99, min_price: 12.99, max_price: 16.99 },
      { theater_name: 'Marcus Point Cinema', avg_price: 12.49, min_price: 10.99, max_price: 14.99 },
    ]);
  }),

  // =========================================================================
  // Schedule Alerts endpoints (useScheduleAlerts hooks)
  // =========================================================================
  http.get(`${API_BASE}/schedule-alerts`, () => {
    return HttpResponse.json({
      alerts: [
        {
          alert_id: 1,
          company_id: 1,
          theater_name: 'AMC Madison 6',
          film_title: 'New Release',
          play_date: '2026-01-20',
          alert_type: 'new_film',
          change_details: 'New film added to schedule',
          source: 'fandango',
          triggered_at: '2026-01-16T10:00:00Z',
          detected_at: '2026-01-16T10:00:00Z',
          is_acknowledged: false,
        },
      ],
      total: 1,
    });
  }),

  http.get(`${API_BASE}/schedule-alerts/summary`, () => {
    return HttpResponse.json({
      total_pending: 5,
      total_acknowledged: 12,
      by_type: { new_film: 3, new_showtime: 2 },
      by_theater: { 'AMC Madison 6': 3, 'Marcus Point Cinema': 2 },
      oldest_pending: '2026-01-14T08:00:00Z',
      newest_pending: '2026-01-16T10:00:00Z',
    });
  }),

  http.put(`${API_BASE}/schedule-alerts/:id/acknowledge`, () => {
    return HttpResponse.json({ success: true });
  }),

  http.put(`${API_BASE}/schedule-alerts/acknowledge-bulk`, () => {
    return HttpResponse.json({ acknowledged_count: 3 });
  }),

  http.get(`${API_BASE}/schedule-monitor/config`, () => {
    return HttpResponse.json({
      config_id: 1,
      company_id: 1,
      is_enabled: true,
      check_frequency_hours: 6,
      alert_on_new_film: true,
      alert_on_new_showtime: true,
      alert_on_removed_showtime: true,
      alert_on_removed_film: true,
      alert_on_format_added: false,
      alert_on_time_changed: false,
      alert_on_new_schedule: true,
      alert_on_event: false,
      alert_on_presale: false,
      days_ahead: 14,
      notification_enabled: false,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-15T00:00:00Z',
    });
  }),

  http.put(`${API_BASE}/schedule-monitor/config`, () => {
    return HttpResponse.json({
      config_id: 1,
      company_id: 1,
      is_enabled: true,
      check_frequency_hours: 6,
      alert_on_new_film: true,
      alert_on_new_showtime: true,
      alert_on_removed_showtime: true,
      alert_on_removed_film: true,
      alert_on_format_added: false,
      alert_on_time_changed: false,
      alert_on_new_schedule: true,
      alert_on_event: false,
      alert_on_presale: false,
      days_ahead: 14,
      notification_enabled: false,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: new Date().toISOString(),
    });
  }),

  http.get(`${API_BASE}/schedule-monitor/status`, () => {
    return HttpResponse.json({
      is_enabled: true,
      last_check_at: '2026-01-16T10:00:00Z',
      last_check_status: 'ok',
      total_pending_alerts: 5,
      baselines_count: 42,
    });
  }),

  http.post(`${API_BASE}/schedule-monitor/check`, () => {
    return HttpResponse.json({ status: 'completed', alerts_created: 2 });
  }),

  // =========================================================================
  // Sync endpoints (useSync hooks)
  // =========================================================================
  http.get(`${API_BASE}/enttelligence/status`, () => {
    return HttpResponse.json({
      is_fresh: true,
      fresh_entries: 4500,
      total_entries: 5000,
      last_sync: '2026-01-16T10:00:00Z',
      hours_until_stale: 20,
      quick_scrape_available: true,
    });
  }),

  http.post(`${API_BASE}/enttelligence/sync`, () => {
    return HttpResponse.json({
      status: 'started',
      message: 'Sync initiated successfully',
      records_fetched: 0,
      task_id: 'task-abc-123',
      ready: false,
    });
  }),

  http.post(`${API_BASE}/market-context/sync/theaters`, () => {
    return HttpResponse.json({
      status: 'started',
      message: 'Theater sync task initiated.',
      task_id: 'task-def-456',
    });
  }),

  http.get(`${API_BASE}/system/tasks/:taskId`, ({ params }) => {
    return HttpResponse.json({
      task_id: params['taskId'],
      status: 'completed',
      ready: true,
      result: { message: 'Task completed', records_cached: 500 },
    });
  }),

  // =========================================================================
  // Zero Showtime endpoints (useZeroShowtimes hooks)
  // =========================================================================
  http.post(`${API_BASE}/scrapes/zero-showtime-analysis`, () => {
    return HttpResponse.json({
      theaters: [
        {
          theater_name: 'Closed Theater',
          total_scrapes: 30,
          zero_count: 28,
          last_nonzero_date: '2025-12-01',
          consecutive_zeros: 28,
          last_scrape_date: '2026-01-15',
          classification: 'likely_off_fandango',
        },
        {
          theater_name: 'AMC Madison 6',
          total_scrapes: 30,
          zero_count: 1,
          last_nonzero_date: '2026-01-15',
          consecutive_zeros: 0,
          last_scrape_date: '2026-01-15',
          classification: 'normal',
        },
      ],
      summary: {
        likely_off_fandango: 1,
        warning: 0,
        normal: 1,
      },
    });
  }),

  http.post(`${API_BASE}/scrapes/mark-theater-status`, () => {
    return HttpResponse.json({
      success: true,
      theater_name: 'Closed Theater',
      new_status: 'not_on_fandango',
    });
  }),

  // =========================================================================
  // Presale Watches endpoints (usePresaleWatches hooks)
  // =========================================================================
  http.get(`${API_BASE}/presales/watches`, () => {
    return HttpResponse.json([
      {
        id: 1,
        film_title: 'Blockbuster Movie',
        alert_type: 'velocity_drop',
        threshold: 20,
        enabled: true,
        created_at: '2026-01-10T00:00:00Z',
        last_triggered: null,
        trigger_count: 0,
      },
      {
        id: 2,
        film_title: 'Sequel Film',
        alert_type: 'milestone',
        threshold: 10000,
        enabled: true,
        created_at: '2026-01-12T00:00:00Z',
        last_triggered: '2026-01-15T08:00:00Z',
        trigger_count: 1,
      },
    ]);
  }),

  http.post(`${API_BASE}/presales/watches`, () => {
    return HttpResponse.json({
      id: 3,
      film_title: 'New Movie',
      alert_type: 'velocity_spike',
      threshold: 50,
      enabled: true,
      created_at: new Date().toISOString(),
      last_triggered: null,
      trigger_count: 0,
    });
  }),

  http.put(`${API_BASE}/presales/watches/:id`, () => {
    return HttpResponse.json({
      id: 1,
      film_title: 'Blockbuster Movie',
      alert_type: 'velocity_drop',
      threshold: 30,
      enabled: true,
      created_at: '2026-01-10T00:00:00Z',
      last_triggered: null,
      trigger_count: 0,
    });
  }),

  http.delete(`${API_BASE}/presales/watches/:id`, () => {
    return new HttpResponse(null, { status: 204 });
  }),

  http.get(`${API_BASE}/presales/watches/notifications`, () => {
    return HttpResponse.json([
      {
        id: 1,
        watch_id: 2,
        film_title: 'Sequel Film',
        message: 'Milestone reached: 10,000 tickets sold',
        triggered_at: '2026-01-15T08:00:00Z',
        is_read: false,
        severity: 'info',
      },
    ]);
  }),

  http.put(`${API_BASE}/presales/watches/notifications/:id/read`, () => {
    return HttpResponse.json({ success: true });
  }),

  // =========================================================================
  // Box Office Board endpoints (useBoxOfficeBoard hooks)
  // =========================================================================
  http.get(`${API_BASE}/reports/box-office-board`, () => {
    return HttpResponse.text('<html><body><h1>Box Office Board</h1></body></html>');
  }),

  // =========================================================================
  // Demand Lookup endpoints (useDemandLookup hooks)
  // =========================================================================
  http.get(`${API_BASE}/presales/demand-lookup`, () => {
    return HttpResponse.json([
      {
        theater_name: 'AMC Madison 6',
        film_title: 'Blockbuster Movie',
        play_date: '2026-01-20',
        showtime: '7:00 PM',
        format: 'Standard',
        circuit_name: 'AMC',
        ticket_type: 'Adult',
        price: 14.99,
        capacity: 200,
        available: 120,
        tickets_sold: 80,
        fill_rate_pct: 40.0,
      },
      {
        theater_name: 'AMC Madison 6',
        film_title: 'Blockbuster Movie',
        play_date: '2026-01-20',
        showtime: '9:30 PM',
        format: 'IMAX',
        circuit_name: 'AMC',
        ticket_type: 'Adult',
        price: 19.99,
        capacity: 300,
        available: 50,
        tickets_sold: 250,
        fill_rate_pct: 83.3,
      },
    ]);
  }),

  // =========================================================================
  // Theater Amenities endpoints (useTheaterAmenities hooks)
  // =========================================================================
  http.get(`${API_BASE}/theater-amenities`, () => {
    return HttpResponse.json([
      {
        id: 1,
        theater_name: 'AMC Madison 6',
        circuit_name: 'AMC',
        has_recliners: true,
        has_reserved_seating: true,
        has_heated_seats: false,
        has_imax: true,
        has_dolby_cinema: true,
        has_dolby_atmos: true,
        has_rpx: false,
        has_4dx: false,
        has_screenx: false,
        has_dbox: false,
        has_dine_in: false,
        has_full_bar: false,
        has_premium_concessions: true,
        has_reserved_food_delivery: false,
        screen_count: 12,
        premium_screen_count: 3,
        year_built: 2005,
        year_renovated: 2020,
        premium_formats: ['IMAX', 'Dolby Cinema'],
        amenity_score: 7,
        notes: null,
        source: 'manual',
        last_verified: '2026-01-10T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-10T00:00:00Z',
      },
    ]);
  }),

  http.get(`${API_BASE}/theater-amenities/summary`, () => {
    return HttpResponse.json([
      {
        circuit_name: 'AMC',
        theater_count: 10,
        with_recliners: 8,
        with_reserved_seating: 10,
        with_imax: 5,
        with_dolby: 4,
        with_dine_in: 2,
        with_bar: 1,
        avg_amenity_score: 6.5,
      },
    ]);
  }),

  http.get(`${API_BASE}/theater-amenities/format-summary`, () => {
    return HttpResponse.json({
      by_format: { IMAX: 15, 'Dolby Cinema': 12, '3D': 8 },
      by_category: { imax: 15, dolby: 12, '3d': 8 },
      total_theaters_with_plf: 25,
    });
  }),

  http.get(`${API_BASE}/theater-amenities/screen-counts/:theaterName`, () => {
    return HttpResponse.json({
      theater_name: 'AMC Madison 6',
      formats_available: { imax: ['IMAX'], dolby: ['Dolby Cinema'] },
      screen_counts_by_category: { imax: 1, dolby: 1, standard: 10 },
      estimated_total_screens: 12,
      lookback_days: 14,
    });
  }),

  http.get(`${API_BASE}/theater-amenities/:id`, () => {
    return HttpResponse.json({
      id: 1,
      theater_name: 'AMC Madison 6',
      circuit_name: 'AMC',
      has_recliners: true,
      has_reserved_seating: true,
      has_heated_seats: false,
      has_imax: true,
      has_dolby_cinema: true,
      has_dolby_atmos: true,
      has_rpx: false,
      has_4dx: false,
      has_screenx: false,
      has_dbox: false,
      has_dine_in: false,
      has_full_bar: false,
      has_premium_concessions: true,
      has_reserved_food_delivery: false,
      screen_count: 12,
      premium_screen_count: 3,
      year_built: 2005,
      year_renovated: 2020,
      premium_formats: ['IMAX', 'Dolby Cinema'],
      amenity_score: 7,
      notes: null,
      source: 'manual',
      last_verified: '2026-01-10T00:00:00Z',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-10T00:00:00Z',
    });
  }),

  http.post(`${API_BASE}/theater-amenities`, () => {
    return HttpResponse.json({
      id: 2,
      theater_name: 'New Theater',
      circuit_name: 'Regal',
      has_recliners: false,
      has_reserved_seating: false,
      has_heated_seats: false,
      has_imax: false,
      has_dolby_cinema: false,
      has_dolby_atmos: false,
      has_rpx: false,
      has_4dx: false,
      has_screenx: false,
      has_dbox: false,
      has_dine_in: false,
      has_full_bar: false,
      has_premium_concessions: false,
      has_reserved_food_delivery: false,
      screen_count: null,
      premium_screen_count: null,
      year_built: null,
      year_renovated: null,
      premium_formats: [],
      amenity_score: 0,
      notes: null,
      source: 'manual',
      last_verified: null,
      created_at: '2026-01-16T00:00:00Z',
      updated_at: null,
    });
  }),

  http.put(`${API_BASE}/theater-amenities/:id`, () => {
    return HttpResponse.json({
      id: 1,
      theater_name: 'AMC Madison 6',
      circuit_name: 'AMC',
      has_recliners: true,
      has_reserved_seating: true,
      has_heated_seats: false,
      has_imax: true,
      has_dolby_cinema: true,
      has_dolby_atmos: true,
      has_rpx: false,
      has_4dx: false,
      has_screenx: false,
      has_dbox: false,
      has_dine_in: false,
      has_full_bar: false,
      has_premium_concessions: true,
      has_reserved_food_delivery: false,
      screen_count: 12,
      premium_screen_count: 3,
      year_built: 2005,
      year_renovated: 2020,
      premium_formats: ['IMAX', 'Dolby Cinema'],
      amenity_score: 7,
      notes: null,
      source: 'manual',
      last_verified: '2026-01-10T00:00:00Z',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-16T00:00:00Z',
    });
  }),

  http.delete(`${API_BASE}/theater-amenities/:id`, () => {
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API_BASE}/theater-amenities/discover`, () => {
    return HttpResponse.json({
      theater_name: 'AMC Madison 6',
      formats_discovered: { imax: ['IMAX'], dolby: ['Dolby Cinema'] },
      screen_counts: { imax: 1, dolby: 1 },
      amenities_updated: true,
    });
  }),

  http.post(`${API_BASE}/theater-amenities/discover-all`, () => {
    return HttpResponse.json({
      theaters_updated: 5,
      circuit_filter: null,
      lookback_days: 30,
    });
  }),

  // =========================================================================
  // Coverage Gaps endpoints (useCoverageGaps hooks)
  // =========================================================================
  http.get(`${API_BASE}/baselines/coverage-gaps`, () => {
    return HttpResponse.json({
      total: 2,
      theaters: [
        {
          theater_name: 'AMC Madison 6',
          circuit_name: 'AMC',
          total_samples: 150,
          gap_count: 2,
          healthy_count: 12,
          coverage_score: 85,
          day_coverage_pct: 85.7,
          days_missing: ['Sunday'],
          formats: ['Standard', 'IMAX'],
          ticket_types: ['Adult', 'Child'],
        },
      ],
    });
  }),

  http.get(`${API_BASE}/baselines/coverage-gaps/:theaterName`, () => {
    return HttpResponse.json({
      theater_name: 'AMC Madison 6',
      circuit_name: 'AMC',
      total_samples: 150,
      unique_ticket_types: ['Adult', 'Child'],
      unique_formats: ['Standard', 'IMAX'],
      days_with_data: [0, 1, 2, 3, 4, 5],
      date_range_start: '2026-01-01',
      date_range_end: '2026-01-15',
      gaps: [
        {
          gap_type: 'missing_day',
          severity: 'warning',
          description: 'No data for Sunday',
          details: { day: 6 },
        },
      ],
      gap_count: 1,
      day_coverage_pct: 85.7,
      format_coverage_pct: 100,
      overall_coverage_score: 90,
      healthy_baselines: [
        {
          format: 'Standard',
          ticket_type: 'Adult',
          day_of_week: 0,
          day_name: 'Monday',
          sample_count: 20,
          avg_price: 12.99,
          variance_pct: 3.5,
        },
      ],
      healthy_count: 12,
    });
  }),

  http.get(`${API_BASE}/baselines/coverage-hierarchy`, () => {
    return HttpResponse.json({
      'Test Company': {
        total_theaters: 10,
        total_gaps: 5,
        avg_coverage_score: 82,
        directors: {
          'Director A': {
            total_theaters: 5,
            total_gaps: 3,
            avg_coverage_score: 80,
            markets: {
              Madison: {
                total_theaters: 3,
                total_gaps: 2,
                total_samples: 200,
                avg_coverage_score: 78,
                theaters_with_gaps: 2,
                theaters: [],
              },
            },
          },
        },
      },
    });
  }),

  http.get(`${API_BASE}/baselines/coverage-market/:directorName/:marketName`, () => {
    return HttpResponse.json({
      market_name: 'Madison',
      director_name: 'Director A',
      company_name: 'Test Company',
      total_theaters: 3,
      total_gaps: 2,
      total_samples: 200,
      avg_coverage_score: 78,
      theaters_with_gaps: 2,
      theaters: [
        {
          theater_name: 'AMC Madison 6',
          total_samples: 100,
          gap_count: 1,
          healthy_count: 8,
          coverage_score: 85,
          day_coverage_pct: 85.7,
          days_missing: ['Sunday'],
          formats: ['Standard'],
        },
      ],
    });
  }),

  // =========================================================================
  // Gap Fill endpoints (useGapFill hooks)
  // =========================================================================
  http.get(`${API_BASE}/baselines/gap-fill/:theaterName`, () => {
    return HttpResponse.json({
      theater_name: 'AMC Madison 6',
      total_gaps: 3,
      proposals: [
        {
          theater_name: 'AMC Madison 6',
          ticket_type: 'Adult',
          format: 'Standard',
          daypart: 'evening',
          day_type: 'weekend',
          proposed_price: 14.99,
          source: 'enttelligence',
          sample_count: 25,
          confidence: 0.85,
          gap_type: 'missing_day',
          gap_description: 'No Sunday data',
        },
      ],
      fillable_count: 1,
      unfillable_gaps: 2,
    });
  }),

  http.post(`${API_BASE}/baselines/gap-fill/:theaterName/apply`, () => {
    return HttpResponse.json({
      baselines_created: 1,
      baselines_skipped: 2,
      theater_name: 'AMC Madison 6',
    });
  }),

  // =========================================================================
  // Company Profiles endpoints (useCompanyProfiles hooks)
  // =========================================================================
  http.get(`${API_BASE}/company-profiles`, () => {
    return HttpResponse.json({
      total: 1,
      profiles: [
        {
          profile_id: 1,
          circuit_name: 'AMC',
          discovered_at: '2026-01-01T00:00:00Z',
          last_updated_at: '2026-01-15T00:00:00Z',
          ticket_types: ['Adult', 'Child', 'Senior'],
          daypart_scheme: 'time-based',
          daypart_boundaries: { matinee: '16:00', evening: '20:00' },
          has_flat_matinee: false,
          has_discount_days: true,
          discount_days: [
            {
              day_of_week: 1,
              day: 'Tuesday',
              price: 8.99,
              program: 'Discount Tuesdays',
              sample_count: 50,
              variance_pct: 2.5,
              below_avg_pct: 25,
            },
          ],
          premium_formats: ['IMAX', 'Dolby Cinema'],
          premium_surcharges: { IMAX: 5.0, 'Dolby Cinema': 6.0 },
          theater_count: 10,
          sample_count: 500,
          date_range_start: '2025-12-01',
          date_range_end: '2026-01-15',
          confidence_score: 0.85,
        },
      ],
    });
  }),

  http.get(`${API_BASE}/company-profiles/:circuitName/discount-day-diagnostic`, () => {
    return HttpResponse.json({
      circuit_name: 'AMC',
      theater_count: 10,
      total_samples: 500,
      overall_avg_price: 13.50,
      day_analysis: [
        {
          day_of_week: 1,
          day_name: 'Tuesday',
          sample_count: 70,
          avg_price: 8.99,
          min_price: 7.99,
          max_price: 9.99,
          price_range: 2.0,
          std_dev: 0.5,
          variance_pct: 5.6,
          below_avg_pct: 33.4,
          is_flat_pricing: true,
          is_discounted: true,
          ticket_types_seen: ['Discount'],
        },
      ],
      discount_ticket_types_found: { Tuesday: { Discount: 70 } },
      detected_discount_days: [
        {
          day: 'Tuesday',
          day_of_week: 1,
          price: 8.99,
          method: 'ticket_type',
          variance_pct: 5.6,
          below_avg_pct: 33.4,
          sample_count: 70,
        },
      ],
      detection_thresholds: {
        max_variance_pct: 15,
        min_below_avg_pct: 8,
        min_samples: 5,
        discount_ticket_concentration: 0.5,
      },
    });
  }),

  http.get(`${API_BASE}/company-profiles/:circuitName/data-coverage`, () => {
    return HttpResponse.json({
      circuit_name: 'AMC',
      total_samples: 500,
      total_theaters: 10,
      day_coverage: [
        {
          day_of_week: 0,
          day_name: 'Monday',
          sample_count: 70,
          theater_count: 10,
          date_range: '2025-12-01 to 2026-01-15',
          has_sufficient_data: true,
        },
      ],
      weekdays_with_data: 7,
      coverage_assessment: 'excellent',
      can_detect_discount_days: true,
      recommendation: 'Data coverage is excellent.',
    });
  }),

  http.get(`${API_BASE}/company-profiles/:circuitName`, () => {
    return HttpResponse.json({
      profile_id: 1,
      circuit_name: 'AMC',
      discovered_at: '2026-01-01T00:00:00Z',
      last_updated_at: '2026-01-15T00:00:00Z',
      ticket_types: ['Adult', 'Child', 'Senior'],
      daypart_scheme: 'time-based',
      daypart_boundaries: { matinee: '16:00', evening: '20:00' },
      has_flat_matinee: false,
      has_discount_days: true,
      discount_days: [],
      premium_formats: ['IMAX', 'Dolby Cinema'],
      premium_surcharges: { IMAX: 5.0, 'Dolby Cinema': 6.0 },
      theater_count: 10,
      sample_count: 500,
      date_range_start: '2025-12-01',
      date_range_end: '2026-01-15',
      confidence_score: 0.85,
    });
  }),

  http.post(`${API_BASE}/company-profiles/discover`, () => {
    return HttpResponse.json({
      profile: {
        profile_id: 2,
        circuit_name: 'Regal',
        discovered_at: new Date().toISOString(),
        last_updated_at: null,
        ticket_types: ['Adult'],
        daypart_scheme: 'unknown',
        daypart_boundaries: {},
        has_flat_matinee: false,
        has_discount_days: false,
        discount_days: [],
        premium_formats: [],
        premium_surcharges: {},
        theater_count: 5,
        sample_count: 100,
        date_range_start: '2025-12-15',
        date_range_end: '2026-01-15',
        confidence_score: 0.6,
      },
      message: 'Profile discovered for Regal',
    });
  }),

  http.post(`${API_BASE}/company-profiles/discover-all`, () => {
    return HttpResponse.json({
      total: 2,
      profiles: [],
    });
  }),

  http.delete(`${API_BASE}/company-profiles/:circuitName`, () => {
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${API_BASE}/company-profiles/cleanup-duplicates`, () => {
    return HttpResponse.json({
      message: 'Cleanup complete',
      deleted: ['AMC (old)'],
      kept: ['AMC'],
      existing_before: [{ name: 'AMC', theaters: 10 }, { name: 'AMC (old)', theaters: 3 }],
      remaining_after: [{ name: 'AMC', theaters: 10 }],
      note: 'Removed 1 duplicate',
    });
  }),

  // =========================================================================
  // Alternative Content endpoints (useAlternativeContent hooks)
  // =========================================================================
  http.get(`${API_BASE}/alternative-content`, () => {
    return HttpResponse.json({
      total: 2,
      films: [
        {
          id: 1,
          film_title: 'Met Opera: La Boheme',
          normalized_title: 'met opera la boheme',
          content_type: 'opera_broadcast',
          content_source: 'Met Opera',
          detected_by: 'title_pattern',
          detection_confidence: 0.95,
          detection_reason: 'Title matches opera pattern',
          first_seen_at: '2026-01-01T00:00:00Z',
          last_seen_at: '2026-01-15T00:00:00Z',
          occurrence_count: 12,
          is_verified: true,
          is_active: true,
        },
        {
          id: 2,
          film_title: 'Dragon Ball Super: Broly',
          normalized_title: 'dragon ball super broly',
          content_type: 'anime_event',
          content_source: 'Fathom Events',
          detected_by: 'ticket_type',
          detection_confidence: 0.8,
          detection_reason: 'Special event ticket type',
          first_seen_at: '2026-01-05T00:00:00Z',
          last_seen_at: '2026-01-10T00:00:00Z',
          occurrence_count: 5,
          is_verified: false,
          is_active: true,
        },
      ],
      content_types: ['opera_broadcast', 'anime_event'],
    });
  }),

  http.get(`${API_BASE}/alternative-content/detect/preview`, () => {
    return HttpResponse.json({
      title_detected: [
        {
          film_title: 'NT Live: Hamlet',
          normalized_title: 'nt live hamlet',
          content_type: 'theater_broadcast',
          content_source: null,
          detected_by: 'title_pattern',
          detection_confidence: 0.9,
          detection_reason: 'NT Live prefix',
        },
      ],
      ticket_type_detected: [],
      total_title: 1,
      total_ticket_type: 0,
    });
  }),

  http.get(`${API_BASE}/alternative-content/check/:filmTitle`, () => {
    return HttpResponse.json({
      film_title: 'Met Opera: La Boheme',
      normalized_title: 'met opera la boheme',
      is_alternative_content: true,
      content_type: 'opera_broadcast',
      pattern_detection: {
        detected_type: 'opera_broadcast',
        confidence: 0.95,
        reason: 'Title matches opera pattern',
      },
    });
  }),

  http.get(`${API_BASE}/alternative-content/circuit-pricing`, () => {
    return HttpResponse.json([
      {
        id: 1,
        circuit_name: 'AMC',
        content_type: 'fathom_event',
        standard_ticket_type: 'Special Event',
        discount_ticket_type: null,
        typical_price_min: 15.0,
        typical_price_max: 22.0,
        discount_day_applies: false,
        discount_day_ticket_type: null,
        discount_day_price: null,
        notes: null,
        source: 'manual',
      },
    ]);
  }),

  http.get(`${API_BASE}/alternative-content/circuit-pricing/:circuitName`, () => {
    return HttpResponse.json({
      id: 1,
      circuit_name: 'AMC',
      content_type: 'fathom_event',
      standard_ticket_type: 'Special Event',
      discount_ticket_type: null,
      typical_price_min: 15.0,
      typical_price_max: 22.0,
      discount_day_applies: false,
      discount_day_ticket_type: null,
      discount_day_price: null,
      notes: null,
      source: 'manual',
    });
  }),

  http.get(`${API_BASE}/alternative-content/:filmId`, () => {
    return HttpResponse.json({
      id: 1,
      film_title: 'Met Opera: La Boheme',
      normalized_title: 'met opera la boheme',
      content_type: 'opera_broadcast',
      content_source: 'Met Opera',
      detected_by: 'title_pattern',
      detection_confidence: 0.95,
      detection_reason: 'Title matches opera pattern',
      first_seen_at: '2026-01-01T00:00:00Z',
      last_seen_at: '2026-01-15T00:00:00Z',
      occurrence_count: 12,
      is_verified: true,
      is_active: true,
    });
  }),

  http.post(`${API_BASE}/alternative-content/detect`, () => {
    return HttpResponse.json({
      title_detected: 3,
      ticket_type_detected: 1,
      total_unique: 4,
      new_saved: 2,
      message: 'Detection complete: 4 AC films found, 2 new saved',
    });
  }),

  http.post(`${API_BASE}/alternative-content`, () => {
    return HttpResponse.json({
      id: 3,
      film_title: 'New Special Event',
      normalized_title: 'new special event',
      content_type: 'special_presentation',
      content_source: null,
      detected_by: 'manual',
      detection_confidence: 1.0,
      detection_reason: 'Manually added',
      first_seen_at: new Date().toISOString(),
      last_seen_at: new Date().toISOString(),
      occurrence_count: 0,
      is_verified: true,
      is_active: true,
    });
  }),

  http.put(`${API_BASE}/alternative-content/circuit-pricing/:circuitName`, () => {
    return HttpResponse.json({
      id: 1,
      circuit_name: 'AMC',
      content_type: 'fathom_event',
      standard_ticket_type: 'Special Event',
      discount_ticket_type: null,
      typical_price_min: 16.0,
      typical_price_max: 23.0,
      discount_day_applies: false,
      discount_day_ticket_type: null,
      discount_day_price: null,
      notes: 'Updated pricing',
      source: 'manual',
    });
  }),

  http.put(`${API_BASE}/alternative-content/:filmId`, () => {
    return HttpResponse.json({
      id: 1,
      film_title: 'Met Opera: La Boheme',
      normalized_title: 'met opera la boheme',
      content_type: 'opera_broadcast',
      content_source: 'Met Opera',
      detected_by: 'title_pattern',
      detection_confidence: 0.95,
      detection_reason: 'Title matches opera pattern',
      first_seen_at: '2026-01-01T00:00:00Z',
      last_seen_at: '2026-01-15T00:00:00Z',
      occurrence_count: 12,
      is_verified: true,
      is_active: true,
    });
  }),

  http.delete(`${API_BASE}/alternative-content/:filmId`, () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // =========================================================================
  // Theater Onboarding endpoints (useOnboarding hooks)
  // =========================================================================
  http.get(`${API_BASE}/theater-onboarding/status/:theaterName`, ({ params }) => {
    return HttpResponse.json({
      theater_name: decodeURIComponent(params['theaterName'] as string),
      circuit_name: 'AMC',
      market: 'Madison',
      onboarding_status: 'in_progress',
      progress_percent: 60,
      completed_steps: 3,
      total_steps: 5,
      steps: {
        market_added: { completed: true, timestamp: '2026-01-10T00:00:00Z' },
        initial_scrape: { completed: true, timestamp: '2026-01-11T00:00:00Z', source: 'fandango', count: 50 },
        baseline_discovered: { completed: true, timestamp: '2026-01-12T00:00:00Z' },
        profile_linked: { completed: false, timestamp: null },
        baseline_confirmed: { completed: false, timestamp: null },
      },
      coverage: {
        formats_discovered: ['Standard', 'IMAX'],
        ticket_types_discovered: ['Adult', 'Child'],
        dayparts_discovered: ['matinee', 'evening'],
        score: 65,
      },
      notes: null,
      last_updated_at: '2026-01-12T00:00:00Z',
    });
  }),

  http.get(`${API_BASE}/theater-onboarding/pending`, () => {
    return HttpResponse.json([
      {
        theater_name: 'AMC Madison 6',
        circuit_name: 'AMC',
        market: 'Madison',
        onboarding_status: 'in_progress',
        progress_percent: 60,
        next_step: 'link_profile',
        last_updated_at: '2026-01-12T00:00:00Z',
      },
    ]);
  }),

  http.get(`${API_BASE}/theater-onboarding/market/:market`, () => {
    return HttpResponse.json([
      {
        theater_name: 'AMC Madison 6',
        circuit_name: 'AMC',
        market: 'Madison',
        onboarding_status: 'in_progress',
        progress_percent: 60,
        completed_steps: 3,
        total_steps: 5,
        steps: {
          market_added: { completed: true, timestamp: '2026-01-10T00:00:00Z' },
          initial_scrape: { completed: true, timestamp: '2026-01-11T00:00:00Z', source: 'fandango', count: 50 },
          baseline_discovered: { completed: true, timestamp: '2026-01-12T00:00:00Z' },
          profile_linked: { completed: false, timestamp: null },
          baseline_confirmed: { completed: false, timestamp: null },
        },
        coverage: { formats_discovered: ['Standard'], ticket_types_discovered: ['Adult'], dayparts_discovered: ['evening'], score: 40 },
        notes: null,
        last_updated_at: '2026-01-12T00:00:00Z',
      },
    ]);
  }),

  http.get(`${API_BASE}/theater-onboarding/:theaterName/coverage`, ({ params }) => {
    return HttpResponse.json({
      theater_name: decodeURIComponent(params['theaterName'] as string),
      baseline_count: 12,
      formats_discovered: ['Standard', 'IMAX'],
      formats_expected: ['Standard', 'IMAX', 'Dolby Cinema'],
      format_coverage: 66.7,
      ticket_types_discovered: ['Adult', 'Child'],
      ticket_types_expected: ['Adult', 'Child', 'Senior'],
      ticket_type_coverage: 66.7,
      dayparts_discovered: ['matinee', 'evening'],
      dayparts_expected: ['matinee', 'evening', 'late'],
      daypart_coverage: 66.7,
      overall_score: 66.7,
      gaps: { formats: ['Dolby Cinema'], ticket_types: ['Senior'], dayparts: ['late'] },
    });
  }),

  http.post(`${API_BASE}/theater-onboarding/start`, () => {
    return HttpResponse.json({
      theater_name: 'New Theater',
      circuit_name: null,
      market: 'Madison',
      onboarding_status: 'not_started',
      progress_percent: 0,
      completed_steps: 0,
      total_steps: 5,
      steps: {
        market_added: { completed: false, timestamp: null },
        initial_scrape: { completed: false, timestamp: null },
        baseline_discovered: { completed: false, timestamp: null },
        profile_linked: { completed: false, timestamp: null },
        baseline_confirmed: { completed: false, timestamp: null },
      },
      coverage: { formats_discovered: [], ticket_types_discovered: [], dayparts_discovered: [], score: 0 },
      notes: null,
      last_updated_at: null,
    });
  }),

  http.post(`${API_BASE}/theater-onboarding/bulk-start`, () => {
    return HttpResponse.json([
      { theater_name: 'Theater A', circuit_name: 'AMC', market: 'Madison', onboarding_status: 'not_started', progress_percent: 0, next_step: 'add_market', last_updated_at: null },
    ]);
  }),

  http.post(`${API_BASE}/theater-onboarding/:theaterName/scrape`, ({ params }) => {
    return HttpResponse.json({
      theater_name: decodeURIComponent(params['theaterName'] as string),
      circuit_name: 'AMC',
      market: 'Madison',
      onboarding_status: 'in_progress',
      progress_percent: 40,
      completed_steps: 2,
      total_steps: 5,
      steps: {
        market_added: { completed: true, timestamp: '2026-01-10T00:00:00Z' },
        initial_scrape: { completed: true, timestamp: new Date().toISOString(), source: 'fandango', count: 30 },
        baseline_discovered: { completed: false, timestamp: null },
        profile_linked: { completed: false, timestamp: null },
        baseline_confirmed: { completed: false, timestamp: null },
      },
      coverage: { formats_discovered: [], ticket_types_discovered: [], dayparts_discovered: [], score: 0 },
      notes: null,
      last_updated_at: new Date().toISOString(),
    });
  }),

  http.post(`${API_BASE}/theater-onboarding/:theaterName/discover`, () => {
    return HttpResponse.json({
      success: true,
      message: 'Baselines discovered',
      baselines_created: 8,
      formats_discovered: ['Standard', 'IMAX'],
      ticket_types_discovered: ['Adult', 'Child'],
      dayparts_discovered: ['matinee', 'evening'],
      coverage_score: 65,
      gaps: { formats: ['Dolby Cinema'], ticket_types: ['Senior'], dayparts: ['late'] },
    });
  }),

  http.post(`${API_BASE}/theater-onboarding/:theaterName/link`, ({ params }) => {
    return HttpResponse.json({
      theater_name: decodeURIComponent(params['theaterName'] as string),
      circuit_name: 'AMC',
      market: 'Madison',
      onboarding_status: 'in_progress',
      progress_percent: 80,
      completed_steps: 4,
      total_steps: 5,
      steps: {
        market_added: { completed: true, timestamp: '2026-01-10T00:00:00Z' },
        initial_scrape: { completed: true, timestamp: '2026-01-11T00:00:00Z', source: 'fandango', count: 50 },
        baseline_discovered: { completed: true, timestamp: '2026-01-12T00:00:00Z' },
        profile_linked: { completed: true, timestamp: new Date().toISOString(), profile_id: 1 },
        baseline_confirmed: { completed: false, timestamp: null },
      },
      coverage: { formats_discovered: ['Standard', 'IMAX'], ticket_types_discovered: ['Adult', 'Child'], dayparts_discovered: ['matinee', 'evening'], score: 65 },
      notes: null,
      last_updated_at: new Date().toISOString(),
    });
  }),

  http.post(`${API_BASE}/theater-onboarding/:theaterName/confirm`, ({ params }) => {
    return HttpResponse.json({
      theater_name: decodeURIComponent(params['theaterName'] as string),
      circuit_name: 'AMC',
      market: 'Madison',
      onboarding_status: 'complete',
      progress_percent: 100,
      completed_steps: 5,
      total_steps: 5,
      steps: {
        market_added: { completed: true, timestamp: '2026-01-10T00:00:00Z' },
        initial_scrape: { completed: true, timestamp: '2026-01-11T00:00:00Z', source: 'fandango', count: 50 },
        baseline_discovered: { completed: true, timestamp: '2026-01-12T00:00:00Z' },
        profile_linked: { completed: true, timestamp: '2026-01-13T00:00:00Z', profile_id: 1 },
        baseline_confirmed: { completed: true, timestamp: new Date().toISOString(), confirmed_by: 1 },
      },
      coverage: { formats_discovered: ['Standard', 'IMAX'], ticket_types_discovered: ['Adult', 'Child'], dayparts_discovered: ['matinee', 'evening'], score: 65 },
      notes: 'Confirmed by admin',
      last_updated_at: new Date().toISOString(),
    });
  }),

  http.get(`${API_BASE}/theater-onboarding/amenities/missing`, () => {
    return HttpResponse.json([
      { theater_name: 'Orphan Theater', circuit_name: 'Regal', market: 'Milwaukee', showing_count: 100, format_count: 3, onboarding_status: 'in_progress' },
    ]);
  }),

  http.post(`${API_BASE}/theater-onboarding/:theaterName/amenities`, ({ params }) => {
    return HttpResponse.json({
      theater_name: decodeURIComponent(params['theaterName'] as string),
      formats_discovered: { Standard: ['Screen 1', 'Screen 2'], IMAX: ['Screen 3'] },
      screen_counts: { Standard: 2, IMAX: 1 },
      amenities_updated: true,
      amenity_id: 42,
    });
  }),

  http.post(`${API_BASE}/theater-onboarding/amenities/backfill`, () => {
    return HttpResponse.json({
      theaters_checked: 10,
      theaters_needing_amenities: 5,
      theaters_updated: 4,
      theaters_failed: 1,
      details: [
        { theater: 'Theater A', success: true, has_imax: true, has_dolby: false, screen_count: 8 },
        { theater: 'Theater B', success: false, error: 'No showings data' },
      ],
    });
  }),

  // =========================================================================
  // Market Context endpoints (useMarketContext hooks)
  // =========================================================================
  http.get(`${API_BASE}/market-context/theaters`, () => {
    return HttpResponse.json([
      { id: 1, theater_name: 'AMC Madison 6', address: '123 Main St', city: 'Madison', state: 'WI', zip_code: '53703', market: 'Madison', circuit_name: 'AMC', latitude: 43.073, longitude: -89.401 },
      { id: 2, theater_name: 'Marcus Point Cinema', address: '456 Oak Ave', city: 'Madison', state: 'WI', zip_code: '53711', market: 'Madison', circuit_name: 'Marcus', latitude: 43.060, longitude: -89.500 },
    ]);
  }),

  http.get(`${API_BASE}/market-context/events`, () => {
    return HttpResponse.json([
      { id: 1, event_name: 'Holiday Weekend', event_type: 'holiday', start_date: '2026-02-14', end_date: '2026-02-16', scope: 'national', impact_score: 8, description: 'Valentines Day weekend' },
    ]);
  }),

  http.get(`${API_BASE}/market-context/theaters/heatmap-data`, () => {
    return HttpResponse.json({
      total_theaters: 2,
      theaters_with_coords: 2,
      theaters: [
        { theater_name: 'AMC Madison 6', circuit_name: 'AMC', market: 'Madison', latitude: 43.073, longitude: -89.401, avg_price: 14.99, baseline_count: 12, formats: ['Standard', 'IMAX'] },
        { theater_name: 'Marcus Point Cinema', circuit_name: 'Marcus', market: 'Madison', latitude: 43.060, longitude: -89.500, avg_price: 12.49, baseline_count: 8, formats: ['Standard'] },
      ],
    });
  }),

  // =========================================================================
  // Market Baselines endpoints (useMarketBaselines hooks)
  // =========================================================================
  http.get(`${API_BASE}/market-baselines/stats`, () => {
    return HttpResponse.json({
      total_markets: 15,
      circuits: {
        AMC: { theaters: 50, markets: 8 },
        Regal: { theaters: 45, markets: 7 },
      },
    });
  }),

  http.get(`${API_BASE}/market-baselines/plan`, () => {
    return HttpResponse.json({
      total_markets: 3,
      by_circuit: {
        AMC: [{ market: 'Madison', theater: 'AMC Madison 6' }],
      },
      plan: [
        { market: 'Madison', theater_name: 'AMC Madison 6', theater_url: 'https://fandango.com/amc-madison-6', circuit: 'AMC' },
      ],
    });
  }),

  http.post(`${API_BASE}/market-baselines/scrape`, () => {
    return HttpResponse.json({
      job_id: 'job-123',
      status: 'pending',
      total_markets: 3,
      dates: ['2026-01-20', '2026-01-21'],
      message: 'Market scrape started',
    });
  }),

  http.get(`${API_BASE}/market-baselines/scrape/:jobId`, ({ params }) => {
    return HttpResponse.json({
      job_id: params['jobId'],
      status: 'running',
      total_markets: 3,
      completed_markets: 1,
      failed_markets: 0,
      current_market: 'Madison',
    });
  }),

  http.post(`${API_BASE}/market-baselines/scrape/:jobId/cancel`, ({ params }) => {
    return HttpResponse.json({
      job_id: params['jobId'],
      status: 'cancelled',
      message: 'Job cancelled',
    });
  }),

  // =========================================================================
  // Discount Programs endpoints (useDiscountPrograms hooks)
  // =========================================================================
  http.get(`${API_BASE}/company-profiles/:circuitName/discount-programs`, () => {
    return HttpResponse.json([
      {
        program_id: 1,
        circuit_name: 'AMC',
        program_name: 'Discount Tuesdays',
        day_of_week: 2,
        day_name: 'Tuesday',
        discount_type: 'flat_price',
        discount_value: 8.99,
        applicable_ticket_types: ['Adult'],
        applicable_formats: ['Standard'],
        applicable_dayparts: null,
        is_active: true,
        confidence_score: 0.95,
        sample_count: 120,
        source: 'auto_detected',
        discovered_at: '2026-01-05T00:00:00Z',
        last_verified_at: '2026-01-15T00:00:00Z',
      },
    ]);
  }),

  http.post(`${API_BASE}/company-profiles/:circuitName/discount-programs`, () => {
    return HttpResponse.json({
      program_id: 2,
      circuit_name: 'AMC',
      program_name: 'Matinee Special',
      day_of_week: 0,
      day_name: 'Sunday',
      discount_type: 'percentage_off',
      discount_value: 20,
      applicable_ticket_types: null,
      applicable_formats: null,
      applicable_dayparts: ['matinee'],
      is_active: true,
      confidence_score: 0.80,
      sample_count: 0,
      source: 'manual',
      discovered_at: new Date().toISOString(),
      last_verified_at: null,
    });
  }),

  http.delete(`${API_BASE}/company-profiles/:circuitName/discount-programs/:programId`, () => {
    return HttpResponse.json({ message: 'Discount program deactivated' });
  }),

  http.get(`${API_BASE}/company-profiles/:circuitName/gaps`, () => {
    return HttpResponse.json([
      {
        gap_id: 1,
        gap_type: 'format',
        expected_value: 'Dolby Cinema',
        reason: 'No baselines found for this format',
        first_detected_at: '2026-01-10T00:00:00Z',
        resolved_at: null,
        resolution_notes: null,
        is_resolved: false,
      },
    ]);
  }),

  http.post(`${API_BASE}/company-profiles/:circuitName/gaps/:gapId/resolve`, () => {
    return HttpResponse.json({
      gap_id: 1,
      gap_type: 'format',
      expected_value: 'Dolby Cinema',
      reason: 'No baselines found for this format',
      first_detected_at: '2026-01-10T00:00:00Z',
      resolved_at: new Date().toISOString(),
      resolution_notes: 'Manually resolved',
      is_resolved: true,
    });
  }),

  http.get(`${API_BASE}/company-profiles/:circuitName/versions`, () => {
    return HttpResponse.json([
      {
        profile_id: 1,
        circuit_name: 'AMC',
        version: 1,
        is_current: true,
        discovered_at: '2026-01-01T00:00:00Z',
        last_updated_at: '2026-01-15T00:00:00Z',
        ticket_types: ['Adult', 'Child', 'Senior'],
        daypart_scheme: 'standard',
        daypart_labels: { matinee: 'Matinee', evening: 'Evening' },
        format_upcharges: { IMAX: 5.0 },
        theater_count: 50,
        sample_count: 500,
        confidence_score: 0.92,
      },
    ]);
  }),

  // =========================================================================
  // Operating Hours Config endpoints (useOperatingHoursConfig hooks)
  // =========================================================================
  http.get(`${API_BASE}/market-context/operating-hours`, () => {
    return HttpResponse.json([
      { day_of_week: 0, open_time: '10:00', close_time: '23:00', first_showtime: '10:30', last_showtime: '22:15' },
      { day_of_week: 1, open_time: '11:00', close_time: '23:00', first_showtime: '11:30', last_showtime: '22:00' },
    ]);
  }),

  http.post(`${API_BASE}/market-context/operating-hours`, () => {
    return HttpResponse.json({ success: true, message: 'Operating hours updated' });
  }),

  // =========================================================================
  // Baseline Coverage (useBaselineCoverage)
  // =========================================================================
  http.get(`${API_BASE}/price-baselines/coverage`, () => {
    return HttpResponse.json({
      total_theaters: 50,
      theaters_with_baselines: 35,
      theaters_missing_baselines: 15,
      coverage_percent: 70.0,
      by_circuit: {
        AMC: { total: 20, covered: 15, missing: 5 },
        Regal: { total: 15, covered: 10, missing: 5 },
      },
      missing_theaters: [
        { theater_name: 'Missing Theater 1', circuit: 'AMC' },
        { theater_name: 'Missing Theater 2', circuit: 'Regal' },
      ],
    });
  }),

  // =========================================================================
  // Fandango Baseline Discovery (useFandangoDiscover, useFandangoAnalyze, etc.)
  // =========================================================================
  http.get(`${API_BASE}/price-baselines/discover`, () => {
    return HttpResponse.json({
      discovered_count: 5,
      saved_count: null,
      baselines: [
        {
          theater_name: 'AMC Madison 6',
          ticket_type: 'Adult',
          format: 'Standard',
          day_type: 'weekday',
          day_of_week: null,
          daypart: 'evening',
          baseline_price: 12.99,
          sample_count: 30,
          min_price: 11.99,
          max_price: 13.99,
          avg_price: 12.99,
          volatility_percent: 3.5,
          is_premium: false,
        },
      ],
    });
  }),

  http.get(`${API_BASE}/price-baselines/analyze`, () => {
    return HttpResponse.json({
      circuits: {
        AMC: { record_count: 100, theater_count: 5, avg_price: 13.50, min_price: 10.99, max_price: 18.99, price_range: 8.0 },
      },
      format_breakdown: {
        Standard: { count: 80, avg_price: 12.99, is_premium: false },
        IMAX: { count: 20, avg_price: 18.99, is_premium: true },
      },
      overall_stats: {
        total_records: 100,
        total_theaters: 5,
        total_circuits: 1,
        date_range: { min: '2026-01-01', max: '2026-01-15' },
        overall_avg_price: 13.50,
      },
      data_coverage: { AMC: 100 },
    });
  }),

  http.post(`${API_BASE}/price-baselines/refresh`, () => {
    return HttpResponse.json({
      success: true,
      baselines_updated: 10,
      message: 'Baselines refreshed successfully',
    });
  }),

  http.get(`${API_BASE}/price-baselines/premium-formats`, () => {
    return HttpResponse.json({
      premium_formats: ['IMAX', 'Dolby Cinema', 'IMAX 3D', 'RPX', 'ScreenX'],
      event_cinema_keywords: ['Fathom', 'Met Opera', 'NT Live'],
      description: 'Premium large format (PLF) screen types',
    });
  }),

  // =========================================================================
  // Fandango Baselines for Theaters (useDiscoverFandangoBaselinesForTheaters)
  // =========================================================================
  http.get(`${API_BASE}/fandango-baselines/discover`, () => {
    return HttpResponse.json({
      discovered_count: 3,
      saved_count: null,
      split_by_day_of_week: true,
      day_of_week_summary: { Monday: 1, Tuesday: 1, Wednesday: 1 },
      daypart_summary: { evening: 2, matinee: 1 },
      theater_count: 1,
      theater_summary: { 'AMC Madison 6': 3 },
      baselines: [
        {
          theater_name: 'AMC Madison 6',
          ticket_type: 'Adult',
          format: 'Standard',
          day_type: 'weekday',
          day_of_week: 0,
          daypart: 'evening',
          baseline_price: 12.99,
          sample_count: 10,
          min_price: 12.49,
          max_price: 13.49,
          avg_price: 12.99,
          volatility_percent: 2.0,
          is_premium: false,
        },
      ],
    });
  }),

  // =========================================================================
  // EntTelligence Baseline endpoints
  // =========================================================================
  http.get(`${API_BASE}/enttelligence-baselines/discover`, () => {
    return HttpResponse.json({
      discovered_count: 8,
      saved_count: null,
      baselines: [
        {
          theater_name: 'AMC Madison 6',
          ticket_type: 'Adult',
          format: 'Standard',
          day_type: null,
          day_of_week: null,
          daypart: null,
          circuit_name: 'AMC',
          baseline_price: 13.50,
          sample_count: 45,
          min_price: 12.99,
          max_price: 14.99,
          avg_price: 13.50,
          volatility_percent: 5.0,
          is_premium: false,
        },
      ],
    });
  }),

  http.get(`${API_BASE}/enttelligence-baselines/analyze`, () => {
    return HttpResponse.json({
      circuits: {
        AMC: { record_count: 200, theater_count: 10, avg_price: 14.00, min_price: 10.99, max_price: 22.99, price_range: 12.0 },
      },
      format_breakdown: {
        Standard: { count: 150, avg_price: 13.00, is_premium: false },
        IMAX: { count: 50, avg_price: 19.99, is_premium: true },
      },
      overall_stats: {
        total_records: 200,
        total_theaters: 10,
        total_circuits: 1,
        date_range: { min: '2026-01-01', max: '2026-01-15' },
        overall_avg_price: 14.00,
      },
      data_coverage: { AMC: 200 },
    });
  }),

  http.post(`${API_BASE}/enttelligence-baselines/refresh`, () => {
    return HttpResponse.json({
      success: true,
      baselines_updated: 15,
      message: 'EntTelligence baselines refreshed',
      source: 'enttelligence',
    });
  }),

  http.get(`${API_BASE}/enttelligence-baselines/circuits`, () => {
    return HttpResponse.json({
      total_circuits: 3,
      circuits: [
        { circuit_name: 'AMC', record_count: 200, theater_count: 10 },
        { circuit_name: 'Regal', record_count: 150, theater_count: 8 },
        { circuit_name: 'Cinemark', record_count: 100, theater_count: 5 },
      ],
    });
  }),

  http.get(`${API_BASE}/enttelligence-baselines/circuit/:circuitName`, () => {
    return HttpResponse.json({
      circuit: 'AMC',
      discovered_count: 4,
      baselines: [
        {
          theater_name: 'AMC Madison 6',
          ticket_type: 'Adult',
          format: 'Standard',
          day_type: null,
          day_of_week: null,
          daypart: null,
          circuit_name: 'AMC',
          baseline_price: 13.50,
          sample_count: 45,
          min_price: 12.99,
          max_price: 14.99,
          avg_price: 13.50,
          volatility_percent: 5.0,
          is_premium: false,
        },
      ],
    });
  }),

  // =========================================================================
  // Event Cinema endpoints (useEventCinemaAnalysis, useEventCinemaKeywords)
  // =========================================================================
  http.get(`${API_BASE}/enttelligence-baselines/event-cinema/keywords`, () => {
    return HttpResponse.json({
      keywords: ['Fathom', 'Met Opera', 'NT Live', 'Bolshoi Ballet'],
      description: 'Keywords used to detect event cinema titles',
    });
  }),

  http.get(`${API_BASE}/enttelligence-baselines/event-cinema`, () => {
    return HttpResponse.json({
      event_films: [
        {
          film_title: 'Met Opera: Carmen',
          record_count: 20,
          theater_count: 5,
          circuit_count: 2,
          circuits: ['AMC', 'Regal'],
          ticket_types: ['Adult'],
          formats: ['Standard'],
          min_price: 22.00,
          max_price: 28.00,
          avg_price: 25.00,
          price_variation: 6.00,
          price_consistent: false,
          play_dates: ['2026-01-20'],
        },
      ],
      summary: {
        total_event_cinema_records: 20,
        total_regular_records: 500,
        unique_films: 1,
        circuits_with_event_cinema: ['AMC', 'Regal'],
        avg_event_price: 25.00,
        avg_regular_price: 13.50,
        price_premium_percent: 85.2,
      },
      price_variations: [
        {
          film_title: 'Met Opera: Carmen',
          min_price: 22.00,
          max_price: 28.00,
          variation: 6.00,
          theaters_involved: 5,
          circuits_involved: ['AMC', 'Regal'],
        },
      ],
      detection_keywords: ['Fathom', 'Met Opera'],
    });
  }),

  // =========================================================================
  // Baseline Browser endpoints (useBaselineMarkets, useMarketDetail, useTheaterBaselines)
  // =========================================================================
  http.get(`${API_BASE}/baselines/markets`, () => {
    return HttpResponse.json([
      { market: 'Madison', theater_count: 5, circuit_count: 2, baseline_count: 20 },
      { market: 'Milwaukee', theater_count: 8, circuit_count: 3, baseline_count: 35 },
    ]);
  }),

  http.get(`${API_BASE}/baselines/market-detail`, () => {
    return HttpResponse.json({
      market: 'Madison',
      total_theaters: 5,
      total_baselines: 20,
      circuits: [
        {
          circuit_name: 'AMC',
          theater_count: 2,
          baseline_count: 10,
          theaters: [
            { theater_name: 'AMC Madison 6', circuit_name: 'AMC', baseline_count: 5, formats: ['Standard', 'IMAX'], ticket_types: ['Adult', 'Child'] },
          ],
        },
      ],
    });
  }),

  http.get(`${API_BASE}/baselines/theaters/:theaterName`, () => {
    return HttpResponse.json({
      theater_name: 'AMC Madison 6',
      circuit_name: 'AMC',
      market: 'Madison',
      total_baselines: 3,
      baselines: [
        {
          baseline_id: 1,
          ticket_type: 'Adult',
          format: 'Standard',
          baseline_price: 12.99,
          day_type: 'weekday',
          day_of_week: null,
          daypart: 'evening',
          sample_count: 50,
          min_price: 11.99,
          max_price: 13.99,
          updated_at: '2026-01-15T00:00:00Z',
        },
      ],
    });
  }),

  // =========================================================================
  // Baseline Maintenance (useDeduplicateBaselines)
  // =========================================================================
  http.post(`${API_BASE}/baselines/deduplicate`, () => {
    return HttpResponse.json({
      dry_run: true,
      total_baselines: 100,
      duplicate_groups: 5,
      to_delete: 8,
      would_remain: 92,
      message: 'Dry run complete. Found 5 duplicate groups with 8 duplicates.',
    });
  }),

  // =========================================================================
  // Data Source Comparison (useCompareDataSources)
  // =========================================================================
  http.get(`${API_BASE}/baselines/compare-sources`, () => {
    return HttpResponse.json({
      total_comparisons: 10,
      avg_difference: 1.25,
      avg_difference_percent: 8.5,
      ent_higher_count: 7,
      fandango_higher_count: 2,
      exact_match_count: 1,
      likely_tax_exclusive_count: 6,
      comparisons: [
        {
          theater_name: 'AMC Madison 6',
          ticket_type: 'Adult',
          format: 'Standard',
          daypart: 'evening',
          day_of_week: null,
          enttelligence_price: 14.24,
          fandango_baseline: 12.99,
          difference: 1.25,
          difference_percent: 9.6,
          ent_sample_count: 30,
          fandango_sample_count: 50,
          ent_price_tax_adjusted: null,
          tax_rate_applied: null,
          adjusted_difference: null,
          adjusted_difference_percent: null,
        },
      ],
      summary: {
        interpretation: 'EntTelligence prices are generally higher.',
        tax_inclusive_likelihood: 'likely_tax_exclusive',
      },
      tax_adjustment_applied: false,
      default_tax_rate: null,
    });
  }),

  // =========================================================================
  // Auth token + logout endpoints (for authStore.login / authStore.logout)
  // =========================================================================
  http.post(`${API_BASE}/auth/token`, () => {
    return HttpResponse.json({
      access_token: 'mock-jwt-token',
      token_type: 'bearer',
    });
  }),

  http.post(`${API_BASE}/auth/logout`, () => {
    return HttpResponse.json({ success: true });
  }),
];
