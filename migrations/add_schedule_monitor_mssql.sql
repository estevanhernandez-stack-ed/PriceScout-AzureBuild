-- ============================================================================
-- Schedule Monitor Tables Migration (Azure SQL / MSSQL)
-- Created: January 2026
-- Purpose: Track when theaters post their schedules to EntTelligence
-- ============================================================================

-- Schedule Baselines: Snapshots of theater schedules for change detection
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'schedule_baselines')
BEGIN
    CREATE TABLE schedule_baselines (
        baseline_id INT IDENTITY(1,1) PRIMARY KEY,
        company_id INT NOT NULL,
        theater_name NVARCHAR(255) NOT NULL,
        film_title NVARCHAR(500) NOT NULL,
        play_date DATE NOT NULL,
        showtimes NVARCHAR(MAX) NOT NULL,  -- JSON array of showtime strings
        snapshot_at DATETIME2 DEFAULT GETUTCDATE() NOT NULL,
        source NVARCHAR(50) DEFAULT 'enttelligence',
        effective_from DATETIME2 DEFAULT GETUTCDATE() NOT NULL,
        effective_to DATETIME2 NULL,  -- NULL = current baseline

        CONSTRAINT FK_schedule_baselines_company
            FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
    );

    -- Indexes
    CREATE INDEX idx_schedule_baselines_company ON schedule_baselines(company_id);
    CREATE INDEX idx_schedule_baselines_theater ON schedule_baselines(theater_name);
    CREATE INDEX idx_schedule_baselines_date ON schedule_baselines(play_date);
    CREATE INDEX idx_schedule_baselines_lookup ON schedule_baselines(company_id, theater_name, film_title, play_date);
    CREATE INDEX idx_schedule_baselines_current ON schedule_baselines(effective_to) WHERE effective_to IS NULL;
END
GO


-- Schedule Alerts: Detected schedule changes
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'schedule_alerts')
BEGIN
    CREATE TABLE schedule_alerts (
        alert_id INT IDENTITY(1,1) PRIMARY KEY,
        company_id INT NOT NULL,
        theater_name NVARCHAR(255) NOT NULL,
        film_title NVARCHAR(500) NULL,
        play_date DATE NULL,
        alert_type NVARCHAR(50) NOT NULL,  -- new_film, new_showtime, removed_showtime, removed_film, format_added
        old_value NVARCHAR(MAX) NULL,  -- JSON
        new_value NVARCHAR(MAX) NULL,  -- JSON
        change_details NVARCHAR(MAX) NULL,
        triggered_at DATETIME2 DEFAULT GETUTCDATE() NOT NULL,
        is_acknowledged BIT DEFAULT 0,
        acknowledged_by INT NULL,
        acknowledged_at DATETIME2 NULL,
        acknowledgment_notes NVARCHAR(MAX) NULL,

        CONSTRAINT FK_schedule_alerts_company
            FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
        CONSTRAINT FK_schedule_alerts_acknowledged_by
            FOREIGN KEY (acknowledged_by) REFERENCES users(user_id) ON DELETE SET NULL
    );

    -- Indexes
    CREATE INDEX idx_schedule_alerts_company ON schedule_alerts(company_id);
    CREATE INDEX idx_schedule_alerts_theater ON schedule_alerts(theater_name);
    CREATE INDEX idx_schedule_alerts_type ON schedule_alerts(alert_type);
    CREATE INDEX idx_schedule_alerts_triggered ON schedule_alerts(triggered_at);
    CREATE INDEX idx_schedule_alerts_unack ON schedule_alerts(is_acknowledged) WHERE is_acknowledged = 0;
END
GO


-- Schedule Monitor Config: Per-company monitoring settings
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'schedule_monitor_config')
BEGIN
    CREATE TABLE schedule_monitor_config (
        config_id INT IDENTITY(1,1) PRIMARY KEY,
        company_id INT NOT NULL UNIQUE,
        is_enabled BIT DEFAULT 1,
        check_frequency_hours INT DEFAULT 6,
        alert_on_new_film BIT DEFAULT 1,
        alert_on_new_showtime BIT DEFAULT 1,
        alert_on_removed_showtime BIT DEFAULT 1,
        alert_on_removed_film BIT DEFAULT 1,
        alert_on_format_added BIT DEFAULT 1,
        days_ahead INT DEFAULT 14,
        last_check_at DATETIME2 NULL,
        last_check_alerts_count INT DEFAULT 0,
        created_at DATETIME2 DEFAULT GETUTCDATE(),
        updated_at DATETIME2 DEFAULT GETUTCDATE(),

        CONSTRAINT FK_schedule_monitor_config_company
            FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
    );

    -- Index
    CREATE INDEX idx_schedule_monitor_config_company ON schedule_monitor_config(company_id);
END
GO


-- ============================================================================
-- Add to competitive schema views (optional)
-- ============================================================================

-- View for schedule monitoring alerts (PascalCase for platform compatibility)
IF NOT EXISTS (SELECT * FROM sys.views WHERE name = 'ScheduleAlerts' AND schema_id = SCHEMA_ID('competitive'))
BEGIN
    EXEC('
    CREATE VIEW competitive.ScheduleAlerts AS
    SELECT
        alert_id AS Id,
        company_id AS CompanyId,
        theater_name AS TheaterName,
        film_title AS FilmTitle,
        play_date AS PlayDate,
        alert_type AS AlertType,
        old_value AS OldValue,
        new_value AS NewValue,
        change_details AS ChangeDetails,
        triggered_at AS TriggeredAt,
        is_acknowledged AS IsAcknowledged,
        acknowledged_by AS AcknowledgedBy,
        acknowledged_at AS AcknowledgedAt
    FROM dbo.schedule_alerts
    ')
END
GO
