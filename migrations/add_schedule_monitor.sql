-- ============================================================================
-- Schedule Monitor Tables Migration
-- Created: January 2026
-- Purpose: Track when theaters post their schedules to EntTelligence
-- ============================================================================

-- Schedule Baselines: Snapshots of theater schedules for change detection
CREATE TABLE IF NOT EXISTS schedule_baselines (
    baseline_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    theater_name VARCHAR(255) NOT NULL,
    film_title VARCHAR(500) NOT NULL,
    play_date DATE NOT NULL,
    showtimes TEXT NOT NULL,  -- JSON array of showtime strings
    snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    source VARCHAR(50) DEFAULT 'enttelligence',
    effective_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    effective_to TIMESTAMP,  -- NULL = current baseline

    FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
);

-- Indexes for schedule_baselines
CREATE INDEX IF NOT EXISTS idx_schedule_baselines_company ON schedule_baselines(company_id);
CREATE INDEX IF NOT EXISTS idx_schedule_baselines_theater ON schedule_baselines(theater_name);
CREATE INDEX IF NOT EXISTS idx_schedule_baselines_date ON schedule_baselines(play_date);
CREATE INDEX IF NOT EXISTS idx_schedule_baselines_lookup ON schedule_baselines(company_id, theater_name, film_title, play_date);
CREATE INDEX IF NOT EXISTS idx_schedule_baselines_current ON schedule_baselines(effective_to) WHERE effective_to IS NULL;


-- Schedule Alerts: Detected schedule changes
CREATE TABLE IF NOT EXISTS schedule_alerts (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    theater_name VARCHAR(255) NOT NULL,
    film_title VARCHAR(500),
    play_date DATE,
    alert_type VARCHAR(50) NOT NULL,  -- new_film, new_showtime, removed_showtime, removed_film, format_added
    old_value TEXT,  -- JSON
    new_value TEXT,  -- JSON
    change_details TEXT,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    is_acknowledged BOOLEAN DEFAULT 0,
    acknowledged_by INTEGER,
    acknowledged_at TIMESTAMP,
    acknowledgment_notes TEXT,

    FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
    FOREIGN KEY (acknowledged_by) REFERENCES users(user_id) ON DELETE SET NULL
);

-- Indexes for schedule_alerts
CREATE INDEX IF NOT EXISTS idx_schedule_alerts_company ON schedule_alerts(company_id);
CREATE INDEX IF NOT EXISTS idx_schedule_alerts_theater ON schedule_alerts(theater_name);
CREATE INDEX IF NOT EXISTS idx_schedule_alerts_type ON schedule_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_schedule_alerts_triggered ON schedule_alerts(triggered_at);
CREATE INDEX IF NOT EXISTS idx_schedule_alerts_unack ON schedule_alerts(is_acknowledged) WHERE is_acknowledged = 0;


-- Schedule Monitor Config: Per-company monitoring settings
CREATE TABLE IF NOT EXISTS schedule_monitor_config (
    config_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL UNIQUE,
    is_enabled BOOLEAN DEFAULT 1,
    check_frequency_hours INTEGER DEFAULT 6,
    alert_on_new_film BOOLEAN DEFAULT 1,
    alert_on_new_showtime BOOLEAN DEFAULT 1,
    alert_on_removed_showtime BOOLEAN DEFAULT 1,
    alert_on_removed_film BOOLEAN DEFAULT 1,
    alert_on_format_added BOOLEAN DEFAULT 1,
    days_ahead INTEGER DEFAULT 14,
    last_check_at TIMESTAMP,
    last_check_alerts_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
);

-- Index for schedule_monitor_config
CREATE INDEX IF NOT EXISTS idx_schedule_monitor_config_company ON schedule_monitor_config(company_id);


-- ============================================================================
-- Usage Notes:
--
-- 1. Create baselines from current EntTelligence data:
--    INSERT INTO schedule_baselines (company_id, theater_name, film_title, play_date, showtimes)
--    SELECT company_id, theater_name, film_title, play_date, showtimes
--    FROM enttelligence_price_cache WHERE play_date >= date('now');
--
-- 2. Detect new films (films in cache but not in baselines):
--    SELECT c.* FROM enttelligence_price_cache c
--    LEFT JOIN schedule_baselines b ON c.theater_name = b.theater_name
--        AND c.film_title = b.film_title AND c.play_date = b.play_date
--    WHERE b.baseline_id IS NULL;
--
-- 3. View pending alerts:
--    SELECT * FROM schedule_alerts WHERE is_acknowledged = 0 ORDER BY triggered_at DESC;
-- ============================================================================
