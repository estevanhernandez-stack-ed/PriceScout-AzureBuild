-- Migration: Add company_profiles table
-- Date: 2026-01-25
-- Description: Store discovered pricing profiles for theater circuits/companies

-- SQLite version (used for local development)
CREATE TABLE IF NOT EXISTS company_profiles (
    profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    circuit_name TEXT NOT NULL,

    -- Discovery metadata
    discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Ticket type patterns discovered (JSON array)
    ticket_types TEXT DEFAULT '[]',

    -- Daypart scheme
    daypart_scheme TEXT DEFAULT 'unknown',
    daypart_boundaries TEXT DEFAULT '{}',

    -- Pricing structure flags
    has_flat_matinee BOOLEAN DEFAULT 0,
    has_discount_days BOOLEAN DEFAULT 0,

    -- Detected discount days (JSON array)
    discount_days TEXT DEFAULT '[]',

    -- Premium formats (JSON array and object)
    premium_formats TEXT DEFAULT '[]',
    premium_surcharges TEXT DEFAULT '{}',

    -- Data quality metrics
    theater_count INTEGER DEFAULT 0,
    sample_count INTEGER DEFAULT 0,
    date_range_start DATE,
    date_range_end DATE,
    confidence_score REAL DEFAULT 0.0,

    -- Foreign key
    FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
    UNIQUE (company_id, circuit_name)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_company_profiles_company ON company_profiles(company_id);
CREATE INDEX IF NOT EXISTS idx_company_profiles_circuit ON company_profiles(circuit_name);

-- PostgreSQL version (for production)
-- Uncomment and use for PostgreSQL deployment:
/*
CREATE TABLE IF NOT EXISTS pricescout.company_profiles (
    profile_id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES pricescout.companies(company_id) ON DELETE CASCADE,
    circuit_name VARCHAR(100) NOT NULL,

    -- Discovery metadata
    discovered_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    -- Ticket type patterns discovered
    ticket_types JSONB DEFAULT '[]',

    -- Daypart scheme
    daypart_scheme VARCHAR(50) DEFAULT 'unknown',
    daypart_boundaries JSONB DEFAULT '{}',

    -- Pricing structure flags
    has_flat_matinee BOOLEAN DEFAULT FALSE,
    has_discount_days BOOLEAN DEFAULT FALSE,

    -- Detected discount days
    discount_days JSONB DEFAULT '[]',

    -- Premium formats
    premium_formats JSONB DEFAULT '[]',
    premium_surcharges JSONB DEFAULT '{}',

    -- Data quality metrics
    theater_count INTEGER DEFAULT 0,
    sample_count INTEGER DEFAULT 0,
    date_range_start DATE,
    date_range_end DATE,
    confidence_score NUMERIC(3,2) DEFAULT 0.0,

    UNIQUE (company_id, circuit_name)
);

CREATE INDEX IF NOT EXISTS idx_company_profiles_company ON pricescout.company_profiles(company_id);
CREATE INDEX IF NOT EXISTS idx_company_profiles_circuit ON pricescout.company_profiles(circuit_name);
*/
