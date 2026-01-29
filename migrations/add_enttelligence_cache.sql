-- Migration: Add EntTelligence Price Cache
-- Date: January 12, 2026
-- Purpose: Cache EntTelligence pricing data for hybrid scrape optimization
-- Supports: SQLite (local dev)

-- ============================================================================
-- EntTelligence Price Cache Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS enttelligence_price_cache (
    cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,

    -- Showtime identifiers (composite key for lookup)
    play_date DATE NOT NULL,
    theater_name VARCHAR(255) NOT NULL,
    film_title VARCHAR(500) NOT NULL,
    showtime VARCHAR(20) NOT NULL,
    format VARCHAR(100),

    -- Pricing data
    ticket_type VARCHAR(100) NOT NULL,
    price NUMERIC(6, 2) NOT NULL,

    -- Source and freshness tracking
    source VARCHAR(50) DEFAULT 'enttelligence',
    fetched_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,

    -- EntTelligence metadata
    circuit_name VARCHAR(100),
    enttelligence_theater_id VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
);

-- Unique constraint for upsert operations
CREATE UNIQUE INDEX IF NOT EXISTS idx_ent_cache_unique ON enttelligence_price_cache (
    company_id, play_date, theater_name, film_title, showtime, format, ticket_type
);

-- Fast lookup by showtime key
CREATE INDEX IF NOT EXISTS idx_ent_cache_lookup ON enttelligence_price_cache (
    play_date, theater_name, film_title, showtime
);

-- Filter by company
CREATE INDEX IF NOT EXISTS idx_ent_cache_company ON enttelligence_price_cache (company_id);

-- Find expired entries for cleanup
CREATE INDEX IF NOT EXISTS idx_ent_cache_expires ON enttelligence_price_cache (expires_at);

-- Filter by circuit for analytics
CREATE INDEX IF NOT EXISTS idx_ent_cache_circuit ON enttelligence_price_cache (circuit_name);


-- ============================================================================
-- Theater Name Mapping Table
-- ============================================================================
-- Maps EntTelligence theater names to Fandango theater names
-- Handles cases where naming differs between systems

CREATE TABLE IF NOT EXISTS theater_name_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,

    -- EntTelligence naming
    enttelligence_name VARCHAR(255) NOT NULL,
    enttelligence_theater_id VARCHAR(50),
    circuit_name VARCHAR(100),

    -- Fandango naming
    fandango_name VARCHAR(255) NOT NULL,
    fandango_url VARCHAR(500),

    -- Mapping metadata
    match_confidence NUMERIC(3, 2) DEFAULT 1.0,  -- 1.0 = exact, 0.8 = fuzzy
    is_verified BOOLEAN DEFAULT FALSE,
    verified_by INTEGER,
    verified_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
    FOREIGN KEY (verified_by) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_theater_mapping_unique ON theater_name_mapping (
    company_id, enttelligence_name
);

CREATE INDEX IF NOT EXISTS idx_theater_mapping_fandango ON theater_name_mapping (fandango_name);
CREATE INDEX IF NOT EXISTS idx_theater_mapping_circuit ON theater_name_mapping (circuit_name);


-- ============================================================================
-- Sync Status Table
-- ============================================================================
-- Track EntTelligence sync jobs for monitoring

CREATE TABLE IF NOT EXISTS enttelligence_sync_runs (
    sync_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,

    -- Sync metadata
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(50) DEFAULT 'running',  -- 'running', 'completed', 'failed'

    -- Statistics
    circuits_synced INTEGER DEFAULT 0,
    theaters_synced INTEGER DEFAULT 0,
    prices_cached INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,

    -- Error tracking
    error_message TEXT,

    -- Trigger info
    triggered_by VARCHAR(50),  -- 'startup', 'scheduled', 'manual'
    user_id INTEGER,

    FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_company ON enttelligence_sync_runs (company_id);
CREATE INDEX IF NOT EXISTS idx_sync_runs_status ON enttelligence_sync_runs (status);
CREATE INDEX IF NOT EXISTS idx_sync_runs_started ON enttelligence_sync_runs (started_at DESC);
