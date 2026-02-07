"""
SQLAlchemy ORM Models for PriceScout
Version: 1.0.0
Date: November 13, 2025

This module defines database models using SQLAlchemy ORM.
Supports both SQLite (local development) and PostgreSQL (production).

Usage:
    from app.db_models import Company, User, Showing, Price
    from app.db_session import get_session
    
    with get_session() as session:
        users = session.query(User).filter_by(role='admin').all()
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, 
    DateTime, Date, Text, ForeignKey, CheckConstraint, UniqueConstraint,
    Index, Numeric, BigInteger, MetaData
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB, INET
from datetime import datetime, UTC
from decimal import Decimal
import json
import os

# Schema prefix for unified database (default 'pricescout' per Accords convention)
# SQLite doesn't support schemas, so we set it to None for SQLite
def _detect_db_type_for_schema():
    """Detect database type to determine if schema should be used."""
    from urllib.parse import urlparse

    explicit = os.getenv('DB_TYPE')
    if explicit == 'sqlite':
        return 'sqlite'
    if explicit in {'postgresql', 'postgres', 'mssql'}:
        return explicit

    db_url = os.getenv('DATABASE_URL', '')
    if db_url:
        try:
            scheme = urlparse(db_url).scheme.lower()
            if scheme.startswith('postgres'):
                return 'postgresql'
            if scheme.startswith('mssql'):
                return 'mssql'
        except Exception:
            pass

    # Default to SQLite for local development
    return 'sqlite'

_db_type = _detect_db_type_for_schema()
DB_SCHEMA = None if _db_type == 'sqlite' else os.getenv('DB_SCHEMA', 'pricescout')

# Create metadata with schema (None for SQLite, schema name for PostgreSQL/MSSQL)
metadata = MetaData(schema=DB_SCHEMA)
Base = declarative_base(metadata=metadata)


# ============================================================================
# CORE SCHEMA REFERENCES (Read-Only)
# These map to shared core.* tables in TheatreOperationsDB.
# On SQLite (dev), these are not available — all core FKs will be NULL.
# See: libs/core/Database/Scripts/003_CreatePriceScoutViews.sql
# ============================================================================

CORE_SCHEMA = None if _db_type == 'sqlite' else 'core'

if CORE_SCHEMA:
    core_metadata = MetaData(schema=CORE_SCHEMA)
    CoreBase = declarative_base(metadata=core_metadata)

    class CoreDivision(CoreBase):
        """Read-only reference to core.Divisions (brand/division master data)."""
        __tablename__ = 'Divisions'
        Id = Column(Integer, primary_key=True)
        Code = Column(String(20))
        Name = Column(String(100))
        IsActive = Column(Boolean)

    class CoreLocation(CoreBase):
        """Read-only reference to core.Locations (Marcus theater locations)."""
        __tablename__ = 'Locations'
        Id = Column(Integer, primary_key=True)
        Code = Column(String(20))
        Name = Column(String(200))
        DivisionId = Column(Integer)
        City = Column(String(100))
        State = Column(String(50))
        Market = Column(String(100))
        ScreenCount = Column(Integer)
        IsActive = Column(Boolean)

    class CorePersonnel(CoreBase):
        """Read-only reference to core.Personnel (Entra ID linked employees)."""
        __tablename__ = 'Personnel'
        Id = Column(Integer, primary_key=True)
        EntraObjectId = Column(String(36))
        Email = Column(String(256))
        DisplayName = Column(String(200))
        FirstName = Column(String(100))
        LastName = Column(String(100))
        JobTitle = Column(String(100))
        LocationId = Column(Integer)
        DivisionId = Column(Integer)
        IsActive = Column(Boolean)

    class CoreCompetitorLocation(CoreBase):
        """Read-only reference to core.CompetitorLocations."""
        __tablename__ = 'CompetitorLocations'
        Id = Column(Integer, primary_key=True)
        Name = Column(String(200))
        Chain = Column(String(100))
        City = Column(String(100))
        State = Column(String(50))
        ScreenCount = Column(Integer)
        HasImax = Column(Boolean)
        NearestLocationId = Column(Integer)
        DistanceMiles = Column(Numeric(6, 2))
        IsActive = Column(Boolean)
else:
    CoreBase = None
    CoreDivision = None
    CoreLocation = None
    CorePersonnel = None
    CoreCompetitorLocation = None


# ============================================================================
# PRICESCOUT TABLES: Multi-tenancy and User Management
# ============================================================================

class Company(Base):
    """Multi-tenant companies with isolated data access"""
    __tablename__ = 'companies'
    
    company_id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    is_active = Column(Boolean, default=True)
    settings = Column(Text, default='{}')  # JSON string for SQLite, JSONB for PostgreSQL
    core_division_id = Column(Integer, nullable=True)  # FK to core.Divisions.Id (enforced at SQL level)

    # Relationships
    users = relationship("User", back_populates="company", foreign_keys="User.company_id")
    scrape_runs = relationship("ScrapeRun", back_populates="company", cascade="all, delete-orphan")
    showings = relationship("Showing", back_populates="company", cascade="all, delete-orphan")
    prices = relationship("Price", back_populates="company", cascade="all, delete-orphan")
    films = relationship("Film", back_populates="company", cascade="all, delete-orphan")
    operating_hours = relationship("OperatingHours", back_populates="company", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Company(id={self.company_id}, name='{self.company_name}')>"
    
    @property
    def settings_dict(self):
        """Parse settings JSON string to dict"""
        try:
            return json.loads(self.settings) if isinstance(self.settings, str) else self.settings
        except Exception:
            return {}
    
    @settings_dict.setter
    def settings_dict(self, value):
        """Set settings from dict"""
        self.settings = json.dumps(value)


class User(Base):
    """Application users with RBAC (admin/manager/user roles)"""
    __tablename__ = 'users'
    
    user_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default='user')
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='NO ACTION'))
    default_company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='SET NULL'))
    home_location_type = Column(String(50))  # 'director', 'market', or 'theater'
    home_location_value = Column(String(255))
    allowed_modes = Column(Text, default='[]')  # JSON array of sidebar modes
    is_admin = Column(Boolean, default=False)
    must_change_password = Column(Boolean, default=False)
    reset_code = Column(String(10))
    reset_code_expiry = Column(BigInteger)
    reset_attempts = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_login = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    core_personnel_id = Column(Integer, nullable=True)  # FK to core.Personnel.Id (enforced at SQL level)

    # Relationships
    company = relationship("Company", back_populates="users", foreign_keys=[company_id])
    default_company = relationship("Company", foreign_keys=[default_company_id])
    scrape_runs = relationship("ScrapeRun", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'manager', 'user')", name='valid_role'),
        CheckConstraint(
            "home_location_type IS NULL OR home_location_type IN ('director', 'market', 'theater')",
            name='valid_home_location'
        ),
        Index('idx_users_username', 'username'),
        Index('idx_users_company', 'company_id'),
        Index('idx_users_role', 'role'),
        Index('idx_users_active', 'is_active'),
    )
    
    def __repr__(self):
        return f"<User(id={self.user_id}, username='{self.username}', role='{self.role}')>"
    
    @property
    def allowed_modes_list(self):
        """Parse allowed_modes JSON to list"""
        try:
            return json.loads(self.allowed_modes) if isinstance(self.allowed_modes, str) else self.allowed_modes
        except Exception:
            return []
    
    @allowed_modes_list.setter
    def allowed_modes_list(self, value):
        """Set allowed_modes from list"""
        self.allowed_modes = json.dumps(value)


class AuditLog(Base):
    """Security audit trail for compliance and debugging"""
    __tablename__ = 'audit_log'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )
    
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    username = Column(String(100))
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='SET NULL'))
    event_type = Column(String(100), nullable=False)  # 'login', 'logout', 'data_access', etc.
    event_category = Column(String(50), nullable=False)  # 'authentication', 'authorization', 'data', 'system'
    severity = Column(String(20), default='info')  # 'info', 'warning', 'error', 'critical'
    details = Column(Text)  # JSON string
    ip_address = Column(String(45))  # IPv6-compatible
    user_agent = Column(Text)
    session_id = Column(String(255))
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")
    
    __table_args__ = (
        Index('idx_audit_timestamp', 'timestamp'),
        Index('idx_audit_user', 'user_id'),
        Index('idx_audit_company', 'company_id'),
        Index('idx_audit_event_type', 'event_type'),
        Index('idx_audit_severity', 'severity'),
    )
    
    def __repr__(self):
        return f"<AuditLog(id={self.log_id}, type='{self.event_type}', user='{self.username}')>"


# ============================================================================
# PRICING DATA TABLES: Scraped theater and film information
# ============================================================================

class ScrapeRun(Base):
    """Data collection sessions tracking"""
    __tablename__ = 'scrape_runs'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )
    
    run_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    run_timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    mode = Column(String(100), nullable=False)  # 'market', 'operating_hours', 'compsnipe', etc.
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    status = Column(String(50), default='completed')  # 'running', 'completed', 'failed'
    records_scraped = Column(Integer, default=0)
    error_message = Column(Text)
    
    # Relationships
    company = relationship("Company", back_populates="scrape_runs")
    user = relationship("User", back_populates="scrape_runs")
    prices = relationship("Price", back_populates="scrape_run")
    operating_hours = relationship("OperatingHours", back_populates="scrape_run")
    
    __table_args__ = (
        Index('idx_scrape_runs_company', 'company_id'),
        Index('idx_scrape_runs_timestamp', 'run_timestamp'),
        Index('idx_scrape_runs_mode', 'mode'),
    )
    
    def __repr__(self):
        return f"<ScrapeRun(id={self.run_id}, mode='{self.mode}', status='{self.status}')>"


class ScrapeCheckpoint(Base):
    """Checkpoint tracking for long-running scrapes - enables resume on crash"""
    __tablename__ = 'scrape_checkpoints'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )

    checkpoint_id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey('scrape_runs.run_id', ondelete='CASCADE'), nullable=False)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    job_id = Column(String(100), nullable=False, index=True)  # Unique job identifier
    theater_name = Column(String(255), nullable=False)
    market = Column(String(255))
    play_date = Column(Date, nullable=False)
    phase = Column(String(50), nullable=False)  # 'showings', 'prices'
    status = Column(String(50), default='completed')  # 'completed', 'in_progress', 'failed'
    showings_count = Column(Integer, default=0)
    prices_count = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)

    __table_args__ = (
        Index('idx_checkpoints_job', 'job_id'),
        Index('idx_checkpoints_run', 'run_id'),
        Index('idx_checkpoints_theater', 'theater_name', 'play_date'),
        UniqueConstraint('job_id', 'theater_name', 'play_date', 'phase', name='unique_checkpoint'),
    )

    def __repr__(self):
        return f"<ScrapeCheckpoint(job={self.job_id}, theater='{self.theater_name}', phase='{self.phase}', status='{self.status}')>"


class Showing(Base):
    """Theater screening schedules with pricing"""
    __tablename__ = 'showings'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )
    
    showing_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    play_date = Column(Date, nullable=False, index=True)
    theater_name = Column(String(255), nullable=False)
    film_title = Column(String(500), nullable=False)
    showtime = Column(String(20), nullable=False)
    format = Column(String(100))  # '2D', '3D', 'IMAX', 'Dolby', etc.
    daypart = Column(String(50))  # 'matinee', 'evening', 'late_night'
    is_plf = Column(Boolean, default=False)  # Premium Large Format
    ticket_url = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    
    # Relationships
    company = relationship("Company", back_populates="showings")
    prices = relationship("Price", back_populates="showing", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('company_id', 'play_date', 'theater_name', 'film_title', 'showtime', 'format',
                        name='unique_showing'),
        Index('idx_showings_company', 'company_id'),
        Index('idx_showings_theater_date', 'company_id', 'theater_name', 'play_date'),
        Index('idx_showings_film', 'company_id', 'film_title'),
        Index('idx_showings_date', 'play_date'),
    )
    
    def __repr__(self):
        return f"<Showing(id={self.showing_id}, theater='{self.theater_name}', film='{self.film_title}')>"


class Price(Base):
    """Ticket pricing data by type (Adult/Senior/Child/etc)"""
    __tablename__ = 'prices'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )
    
    price_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    run_id = Column(Integer, ForeignKey('scrape_runs.run_id', ondelete='NO ACTION'))
    showing_id = Column(Integer, ForeignKey('showings.showing_id', ondelete='NO ACTION'))
    ticket_type = Column(String(100), nullable=False)  # 'Adult', 'Senior', 'Child', etc.
    price = Column(Numeric(6, 2), nullable=False)
    capacity = Column(String(50))  # Optional theater capacity info
    play_date = Column(Date)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    
    # Relationships
    company = relationship("Company", back_populates="prices")
    scrape_run = relationship("ScrapeRun", back_populates="prices")
    showing = relationship("Showing", back_populates="prices")
    
    __table_args__ = (
        CheckConstraint('price >= 0', name='price_positive'),
        Index('idx_prices_company', 'company_id'),
        Index('idx_prices_run', 'run_id'),
        Index('idx_prices_showing', 'showing_id'),
        Index('idx_prices_date', 'play_date'),
    )
    
    def __repr__(self):
        return f"<Price(id={self.price_id}, type='{self.ticket_type}', price={self.price})>"


class Film(Base):
    """Movie metadata from OMDB/IMDB enrichment"""
    __tablename__ = 'films'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )
    
    film_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    film_title = Column(String(500), nullable=False)
    imdb_id = Column(String(20), index=True)
    genre = Column(String(255))
    mpaa_rating = Column(String(20))
    director = Column(String(500))
    actors = Column(Text)
    plot = Column(Text)
    poster_url = Column(Text)
    metascore = Column(Integer)
    imdb_rating = Column(Numeric(3, 1))
    release_date = Column(String(50), index=True)
    domestic_gross = Column(BigInteger)
    runtime = Column(String(50))
    opening_weekend_domestic = Column(BigInteger)
    last_omdb_update = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    
    # Relationships
    company = relationship("Company", back_populates="films")
    
    __table_args__ = (
        UniqueConstraint('company_id', 'film_title', name='unique_film_per_company'),
        Index('idx_films_company', 'company_id'),
        Index('idx_films_title', 'company_id', 'film_title'),
        Index('idx_films_imdb', 'imdb_id'),
        Index('idx_films_release_date', 'release_date'),
    )
    
    def __repr__(self):
        return f"<Film(id={self.film_id}, title='{self.film_title}', imdb='{self.imdb_id}')>"


class OperatingHours(Base):
    """Theater daily operating schedules"""
    __tablename__ = 'operating_hours'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )
    
    operating_hours_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    run_id = Column(Integer, ForeignKey('scrape_runs.run_id', ondelete='NO ACTION'))
    market = Column(String(255))
    theater_name = Column(String(255), nullable=False)
    scrape_date = Column(Date, nullable=False)
    open_time = Column(String(50))
    close_time = Column(String(50))
    first_showtime = Column(String(50))
    last_showtime = Column(String(50))
    showtime_count = Column(Integer, default=0)
    duration_hours = Column(Numeric(5, 2))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    
    # Relationships
    company = relationship("Company", back_populates="operating_hours")
    scrape_run = relationship("ScrapeRun", back_populates="operating_hours")
    
    __table_args__ = (
        Index('idx_operating_hours_company', 'company_id'),
        Index('idx_operating_hours_theater_date', 'company_id', 'theater_name', 'scrape_date'),
        Index('idx_operating_hours_market', 'company_id', 'market'),
    )
    
    def __repr__(self):
        return f"<OperatingHours(id={self.operating_hours_id}, theater='{self.theater_name}')>"


# ============================================================================
# REFERENCE AND ERROR TRACKING TABLES
# ============================================================================

class UnmatchedFilm(Base):
    """Films that failed OMDB matching (needs review)"""
    __tablename__ = 'unmatched_films'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )
    
    unmatched_film_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    film_title = Column(String(500), nullable=False, index=True)
    first_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    last_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    occurrence_count = Column(Integer, default=1)
    
    __table_args__ = (
        UniqueConstraint('company_id', 'film_title', name='unique_unmatched_film'),
        Index('idx_unmatched_films_company', 'company_id'),
        Index('idx_unmatched_films_title', 'film_title'),
    )
    
    def __repr__(self):
        return f"<UnmatchedFilm(id={self.unmatched_film_id}, title='{self.film_title}', count={self.occurrence_count})>"


class IgnoredFilm(Base):
    """Films intentionally excluded from processing"""
    __tablename__ = 'ignored_films'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )
    
    ignored_film_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    film_title = Column(String(500), nullable=False)
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    created_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    
    __table_args__ = (
        UniqueConstraint('company_id', 'film_title', name='unique_ignored_film'),
        Index('idx_ignored_films_company', 'company_id'),
    )
    
    def __repr__(self):
        return f"<IgnoredFilm(id={self.ignored_film_id}, title='{self.film_title}')>"


class UnmatchedTicketType(Base):
    """Unparseable ticket descriptions (needs review)"""
    __tablename__ = 'unmatched_ticket_types'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )
    
    unmatched_ticket_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    original_description = Column(Text)
    unmatched_part = Column(String(255))
    first_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    last_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    theater_name = Column(String(255))
    film_title = Column(String(500))
    showtime = Column(String(20))
    format = Column(String(100))
    play_date = Column(Date)
    occurrence_count = Column(Integer, default=1)
    
    __table_args__ = (
        UniqueConstraint('company_id', 'unmatched_part', 'theater_name', 'film_title', 'play_date',
                        name='unique_unmatched_ticket'),
        Index('idx_unmatched_tickets_company', 'company_id'),
        Index('idx_unmatched_tickets_theater', 'company_id', 'theater_name'),
    )
    
    def __repr__(self):
        return f"<UnmatchedTicketType(id={self.unmatched_ticket_id}, part='{self.unmatched_part}')>"


# ============================================================================
# PRICE ALERTS AND SURGE DETECTION
# ============================================================================

class PriceAlert(Base):
    """Price change and surge pricing alerts"""
    __tablename__ = 'price_alerts'

    alert_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    price_id = Column(Integer, ForeignKey('prices.price_id', ondelete='SET NULL'))
    showing_id = Column(Integer, ForeignKey('showings.showing_id', ondelete='SET NULL'))

    # Alert context
    theater_name = Column(String(255), nullable=False)
    film_title = Column(String(500))
    ticket_type = Column(String(100))
    format = Column(String(100))
    daypart = Column(String(50))  # matinee, evening, late_night - for context

    # Price change data
    alert_type = Column(String(50), nullable=False)  # price_increase, price_decrease, surge_detected, new_offering, discontinued
    old_price = Column(Numeric(6, 2))
    new_price = Column(Numeric(6, 2))
    price_change_percent = Column(Numeric(5, 2))

    # Surge pricing specific
    baseline_price = Column(Numeric(6, 2))  # Configured baseline for surge detection
    surge_multiplier = Column(Numeric(4, 2))  # How much above baseline (1.5x, 2x, etc.)

    # Timestamps
    triggered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    play_date = Column(Date)
    old_price_captured_at = Column(DateTime(timezone=True))  # When the old/baseline price was captured

    # Acknowledgment
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledgment_notes = Column(Text)

    # Notification tracking
    notification_sent = Column(Boolean, default=False)
    notification_sent_at = Column(DateTime(timezone=True))
    notification_error = Column(Text)

    # Relationships
    company = relationship("Company")
    price = relationship("Price")
    showing = relationship("Showing")
    acknowledged_by_user = relationship("User", foreign_keys=[acknowledged_by])

    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('price_increase', 'price_decrease', 'surge_detected', 'new_offering', 'discontinued', 'significant_change', 'discount_day_overcharge')",
            name='valid_alert_type'
        ),
        Index('idx_price_alerts_company', 'company_id'),
        Index('idx_price_alerts_theater', 'company_id', 'theater_name'),
        Index('idx_price_alerts_triggered', 'triggered_at'),
        Index('idx_price_alerts_unacknowledged', 'company_id', 'is_acknowledged'),
        Index('idx_price_alerts_type', 'alert_type'),
    )

    def __repr__(self):
        return f"<PriceAlert(id={self.alert_id}, type='{self.alert_type}', theater='{self.theater_name}')>"


class AlertConfiguration(Base):
    """Per-company alert threshold and notification settings"""
    __tablename__ = 'alert_configurations'

    config_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False, unique=True)

    # Price change thresholds
    min_price_change_percent = Column(Numeric(5, 2), default=5.0)  # Alert if >= 5%
    min_price_change_amount = Column(Numeric(6, 2), default=1.00)  # Or >= $1.00

    # Alert type toggles
    alert_on_increase = Column(Boolean, default=True)
    alert_on_decrease = Column(Boolean, default=True)
    alert_on_new_offering = Column(Boolean, default=True)
    alert_on_discontinued = Column(Boolean, default=False)
    alert_on_surge = Column(Boolean, default=True)

    # Surge pricing settings
    surge_threshold_percent = Column(Numeric(5, 2), default=20.0)  # 20% above baseline = surge

    # Notification settings
    notification_enabled = Column(Boolean, default=True)
    webhook_url = Column(String(500))
    webhook_secret = Column(String(255))  # For HMAC signing
    notification_email = Column(String(255))
    email_frequency = Column(String(50), default='immediate')  # immediate, hourly, daily

    # Filters (JSON arrays as strings for SQLite compatibility)
    theaters_filter = Column(Text, default='[]')  # Empty = all theaters
    ticket_types_filter = Column(Text, default='[]')  # Empty = all types
    formats_filter = Column(Text, default='[]')  # Empty = all formats

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # Relationship
    company = relationship("Company")

    __table_args__ = (
        Index('idx_alert_config_company', 'company_id'),
    )

    def __repr__(self):
        return f"<AlertConfiguration(id={self.config_id}, company_id={self.company_id})>"

    @property
    def theaters_filter_list(self):
        """Parse theaters_filter JSON to list"""
        try:
            return json.loads(self.theaters_filter) if isinstance(self.theaters_filter, str) else self.theaters_filter or []
        except Exception:
            return []

    @property
    def ticket_types_filter_list(self):
        """Parse ticket_types_filter JSON to list"""
        try:
            return json.loads(self.ticket_types_filter) if isinstance(self.ticket_types_filter, str) else self.ticket_types_filter or []
        except Exception:
            return []

    @property
    def formats_filter_list(self):
        """Parse formats_filter JSON to list"""
        try:
            return json.loads(self.formats_filter) if isinstance(self.formats_filter, str) else self.formats_filter or []
        except Exception:
            return []


class PriceBaseline(Base):
    """
    Baseline prices for surge detection - per theater/format/ticket_type.

    Simplified matching (no day_of_week):
    1. theater + ticket_type + format + daypart (exact)
    2. theater + ticket_type + format + * (any daypart)
    3. theater + ticket_type + * + * (fallback)

    Note: day_of_week is deprecated for matching. Discount days are handled
    by DiscountDayProgram linked to CompanyProfile instead.
    """
    __tablename__ = 'price_baselines'

    baseline_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)

    theater_name = Column(String(255), nullable=False)
    ticket_type = Column(String(100), nullable=False)
    format = Column(String(100))  # NULL = applies to all formats
    daypart = Column(String(50))  # NULL = applies to all dayparts
    day_type = Column(String(20))  # 'weekday', 'weekend', or NULL = all days (DEPRECATED)
    day_of_week = Column(Integer)  # 0=Monday, 6=Sunday, NULL = all days (DEPRECATED for matching)

    baseline_price = Column(Numeric(6, 2), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)  # NULL = still active

    # New columns for simplified baseline system
    source = Column(String(50), default='unknown')  # 'fandango', 'enttelligence', 'manual'
    tax_status = Column(String(20), default='unknown')  # 'inclusive', 'exclusive', 'unknown'
    sample_count = Column(Integer)  # Number of price samples used to calculate baseline
    last_discovery_at = Column(DateTime(timezone=True))  # When this baseline was last recalculated
    migrated_from_granular = Column(Boolean, default=False)  # True if migrated from day_of_week granular baseline

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    created_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))

    # Relationships
    company = relationship("Company")
    created_by_user = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index('idx_baselines_company', 'company_id'),
        Index('idx_baselines_theater', 'company_id', 'theater_name'),
        Index('idx_baselines_effective', 'company_id', 'effective_from', 'effective_to'),
        # New index for simplified matching (no day_of_week)
        Index('idx_baselines_simplified', 'company_id', 'theater_name', 'ticket_type', 'format', 'daypart'),
    )

    def __repr__(self):
        return f"<PriceBaseline(id={self.baseline_id}, theater='{self.theater_name}', price={self.baseline_price})>"


# ============================================================================
# MARKET CONTEXT AND GEOSPATIAL TABLES
# ============================================================================

class TheaterMetadata(Base):
    """Geospatial and regional metadata for theaters"""
    __tablename__ = 'theater_metadata'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )

    metadata_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    theater_name = Column(String(255), nullable=False)

    # Location info
    address = Column(String(500))
    city = Column(String(100))
    state = Column(String(50))
    zip_code = Column(String(20))
    market = Column(String(100))  # Marcus-specific market (admin-editable)
    dma = Column(String(100))  # EntTelligence DMA/Designated Market Area (system-defined)
    circuit_name = Column(String(100))

    # Geospatial coordinates
    latitude = Column(Numeric(10, 8))
    longitude = Column(Numeric(11, 8))

    # Freshness
    last_geocode_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Core schema reference
    competitor_location_id = Column(Integer, nullable=True)  # FK to core.CompetitorLocations.Id

    # Relationships
    company = relationship("Company")

    __table_args__ = (
        UniqueConstraint('company_id', 'theater_name', name='uq_theater_metadata'),
        Index('idx_theater_geo', 'latitude', 'longitude'),
        Index('idx_theater_market', 'company_id', 'market'),
    )

    def __repr__(self):
        return f"<TheaterMetadata(theater='{self.theater_name}', city='{self.city}')>"


class MarketEvent(Base):
    """Contextual events impacting theater performance (holidays, breaks, etc.)"""
    __tablename__ = 'market_events'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )

    event_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)

    # Event info
    event_name = Column(String(255), nullable=False)
    event_type = Column(String(50), nullable=False)  # 'holiday', 'school_break', 'festival', 'weather'
    description = Column(Text)

    # Date range
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    # Scope
    scope = Column(String(50), default='global')  # 'global', 'market', 'theater'
    scope_value = Column(String(255)) # Market name or theater name (null for global)

    # Metrics
    impact_score = Column(Integer)  # 1-10
    is_recurring = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    created_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))

    # Relationships
    company = relationship("Company")

    __table_args__ = (
        Index('idx_market_event_date', 'start_date', 'end_date'),
        Index('idx_market_event_scope', 'company_id', 'scope', 'scope_value'),
    )

    def __repr__(self):
        return f"<MarketEvent(name='{self.event_name}', start={self.start_date})>"


class TheaterOperatingHours(Base):
    """Configured operating hours per theater and day of week"""
    __tablename__ = 'theater_operating_hours'
    __table_args__ = (
        {'schema': DB_SCHEMA},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    theater_name = Column(String(255), nullable=False)

    # Day of week (0-6, where 0 is Monday or Sunday? typically 0=Monday in Python/ISO)
    # We will use 0=Monday, 6=Sunday
    day_of_week = Column(Integer, nullable=False)

    open_time = Column(String(20))       # e.g., "10:00 AM"
    close_time = Column(String(20))      # e.g., "11:30 PM"
    first_showtime = Column(String(20))  # e.g., "10:30 AM"
    last_showtime = Column(String(20))   # e.g., "10:45 PM"

    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint('company_id', 'theater_name', 'day_of_week', name='uq_theater_op_hours'),
        Index('idx_theater_op_hours_lookup', 'company_id', 'theater_name'),
    )

    def __repr__(self):
        return f"<TheaterOperatingHours(theater='{self.theater_name}', day={self.day_of_week})>"


# ============================================================================
# ENTTELLIGENCE CACHE TABLES
# ============================================================================

class EntTelligencePriceCache(Base):
    """Cache for EntTelligence pricing data to optimize hybrid scrapes"""
    __tablename__ = 'enttelligence_price_cache'

    cache_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)

    # Showtime identifiers (composite key for lookup)
    play_date = Column(Date, nullable=False)
    theater_name = Column(String(255), nullable=False)
    film_title = Column(String(500), nullable=False)
    showtime = Column(String(20), nullable=False)
    format = Column(String(100))

    # Pricing data
    ticket_type = Column(String(100), nullable=False)
    price = Column(Numeric(6, 2), nullable=False)

    # Source and freshness tracking
    source = Column(String(50), default='enttelligence')
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # EntTelligence metadata
    circuit_name = Column(String(100))
    enttelligence_theater_id = Column(String(50))

    # Capacity / sales data (from programming audit)
    capacity = Column(Integer)       # Auditorium seat count
    available = Column(Integer)      # Remaining seats
    blocked = Column(Integer)        # Held/blocked seats

    # Film metadata
    release_date = Column(String(20))  # Film release date (YYYY-MM-DD)
    imdb_id = Column(String(20))
    movie_id = Column(String(20))
    theater_id = Column(String(20))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    company = relationship("Company")

    __table_args__ = (
        UniqueConstraint(
            'company_id', 'play_date', 'theater_name', 'film_title',
            'showtime', 'format', 'ticket_type',
            name='uq_ent_cache_entry'
        ),
        Index('idx_ent_cache_lookup', 'play_date', 'theater_name', 'film_title', 'showtime'),
        Index('idx_ent_cache_expires', 'expires_at'),
        Index('idx_ent_cache_circuit', 'circuit_name'),
        Index('idx_ent_cache_theater_date', 'company_id', 'play_date', 'theater_name'),
        Index('idx_ent_cache_release', 'release_date'),
    )

    @property
    def tickets_sold(self) -> int:
        """Compute tickets sold: capacity - available.
        EntTelligence invariant: blocked = capacity - available (always).
        'blocked' IS the sold/reserved count, not a separate deduction."""
        cap = self.capacity or 0
        avail = self.available or 0
        return max(0, cap - avail)

    def __repr__(self):
        return f"<EntTelligencePriceCache(theater='{self.theater_name}', film='{self.film_title}', price={self.price})>"


class TheaterNameMapping(Base):
    """Maps EntTelligence theater names to Fandango theater names"""
    __tablename__ = 'theater_name_mapping'

    mapping_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)

    # EntTelligence naming
    enttelligence_name = Column(String(255), nullable=False)
    enttelligence_theater_id = Column(String(50))
    circuit_name = Column(String(100))

    # Fandango naming
    fandango_name = Column(String(255), nullable=False)
    fandango_url = Column(String(500))

    # Mapping metadata
    match_confidence = Column(Numeric(3, 2), default=1.0)
    is_verified = Column(Boolean, default=False)
    verified_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    verified_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # Relationships
    company = relationship("Company")
    verifier = relationship("User")

    __table_args__ = (
        UniqueConstraint('company_id', 'enttelligence_name', name='uq_theater_mapping'),
        Index('idx_theater_mapping_fandango', 'fandango_name'),
        Index('idx_theater_mapping_circuit', 'circuit_name'),
    )

    def __repr__(self):
        return f"<TheaterNameMapping(ent='{self.enttelligence_name}', fandango='{self.fandango_name}')>"


class EntTelligenceSyncRun(Base):
    """Track EntTelligence sync jobs for monitoring"""
    __tablename__ = 'enttelligence_sync_runs'

    sync_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)

    # Sync metadata
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    status = Column(String(50), default='running')  # 'running', 'completed', 'failed'

    # Statistics
    circuits_synced = Column(Integer, default=0)
    theaters_synced = Column(Integer, default=0)
    prices_cached = Column(Integer, default=0)
    errors = Column(Integer, default=0)

    # Error tracking
    error_message = Column(Text)

    # Trigger info
    triggered_by = Column(String(50))  # 'startup', 'scheduled', 'manual'
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))

    # Relationships
    company = relationship("Company")
    user = relationship("User")

    __table_args__ = (
        Index('idx_sync_runs_status', 'status'),
        Index('idx_sync_runs_started', 'started_at'),
    )

    def __repr__(self):
        return f"<EntTelligenceSyncRun(id={self.sync_id}, status='{self.status}', prices={self.prices_cached})>"


# ============================================================================
# SCHEDULE MONITOR TABLES
# ============================================================================

class ScheduleBaseline(Base):
    """Snapshots of theater schedules for change detection"""
    __tablename__ = 'schedule_baselines'

    baseline_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)

    # Theater and film identification
    theater_name = Column(String(255), nullable=False)
    film_title = Column(String(500), nullable=False)
    play_date = Column(Date, nullable=False)

    # Schedule details (JSON array of {time, format, is_plf} objects)
    showtimes = Column(Text, nullable=False)  # JSON string for SQLite compatibility

    # Snapshot metadata
    snapshot_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    source = Column(String(50), default='enttelligence')  # 'enttelligence', 'fandango'

    # Effective period
    effective_from = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    effective_to = Column(DateTime(timezone=True))  # NULL = current baseline

    created_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))

    # Relationships
    company = relationship("Company")
    created_by_user = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        UniqueConstraint(
            'company_id', 'theater_name', 'film_title', 'play_date', 'effective_from',
            name='uq_schedule_baseline'
        ),
        Index('idx_schedule_baselines_company', 'company_id'),
        Index('idx_schedule_baselines_theater', 'company_id', 'theater_name'),
        Index('idx_schedule_baselines_film', 'company_id', 'film_title'),
        Index('idx_schedule_baselines_date', 'play_date'),
        Index('idx_schedule_baselines_effective', 'effective_from', 'effective_to'),
    )

    def __repr__(self):
        return f"<ScheduleBaseline(theater='{self.theater_name}', film='{self.film_title}', date={self.play_date})>"

    @property
    def showtimes_list(self):
        """Parse showtimes JSON string to list"""
        try:
            return json.loads(self.showtimes) if isinstance(self.showtimes, str) else self.showtimes or []
        except Exception:
            return []

    @showtimes_list.setter
    def showtimes_list(self, value):
        """Set showtimes from list"""
        self.showtimes = json.dumps(value)


class ScheduleAlert(Base):
    """Schedule change alerts (new films, new showtimes, removals)"""
    __tablename__ = 'schedule_alerts'

    alert_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)

    # Alert context
    theater_name = Column(String(255), nullable=False)
    film_title = Column(String(500))  # Nullable for theater-level alerts
    play_date = Column(Date)

    # Alert details
    alert_type = Column(String(50), nullable=False)  # new_film, new_showtime, removed_showtime, removed_film, format_added
    old_value = Column(Text)  # JSON - previous state (null for new items)
    new_value = Column(Text)  # JSON - current state (null for removed items)
    change_details = Column(Text)  # Human-readable description

    # Source tracking
    source = Column(String(50), default='enttelligence')
    baseline_id = Column(Integer, ForeignKey('schedule_baselines.baseline_id', ondelete='SET NULL'))

    # Timestamps
    triggered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    # Acknowledgment
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledgment_notes = Column(Text)

    # Notification tracking
    notification_sent = Column(Boolean, default=False)
    notification_sent_at = Column(DateTime(timezone=True))

    # Relationships
    company = relationship("Company")
    baseline = relationship("ScheduleBaseline")
    acknowledged_by_user = relationship("User", foreign_keys=[acknowledged_by])

    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('new_film', 'new_showtime', 'removed_showtime', 'removed_film', 'format_added', 'time_changed', 'new_schedule', 'event_added', 'presale_started')",
            name='valid_schedule_alert_type'
        ),
        Index('idx_schedule_alerts_company', 'company_id'),
        Index('idx_schedule_alerts_theater', 'company_id', 'theater_name'),
        Index('idx_schedule_alerts_triggered', 'triggered_at'),
        Index('idx_schedule_alerts_unacknowledged', 'company_id', 'is_acknowledged'),
        Index('idx_schedule_alerts_type', 'alert_type'),
    )

    def __repr__(self):
        return f"<ScheduleAlert(id={self.alert_id}, type='{self.alert_type}', theater='{self.theater_name}')>"

    @property
    def old_value_dict(self):
        """Parse old_value JSON string to dict"""
        try:
            return json.loads(self.old_value) if isinstance(self.old_value, str) and self.old_value else None
        except Exception:
            return None

    @property
    def new_value_dict(self):
        """Parse new_value JSON string to dict"""
        try:
            return json.loads(self.new_value) if isinstance(self.new_value, str) and self.new_value else None
        except Exception:
            return None


class ScheduleMonitorConfig(Base):
    """Per-company schedule monitoring configuration"""
    __tablename__ = 'schedule_monitor_config'

    config_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False, unique=True)

    # Monitoring settings
    is_enabled = Column(Boolean, default=True)
    check_frequency_hours = Column(Integer, default=6)  # How often to run scheduled checks

    # Alert toggles
    alert_on_new_film = Column(Boolean, default=True)
    alert_on_new_showtime = Column(Boolean, default=True)
    alert_on_removed_showtime = Column(Boolean, default=True)
    alert_on_removed_film = Column(Boolean, default=True)
    alert_on_format_added = Column(Boolean, default=True)
    alert_on_time_changed = Column(Boolean, default=False)  # Can be noisy
    alert_on_new_schedule = Column(Boolean, default=True)
    alert_on_event = Column(Boolean, default=True)
    alert_on_presale = Column(Boolean, default=True)

    # Filters (JSON arrays as strings for SQLite compatibility)
    theaters_filter = Column(Text, default='[]')  # Empty = all theaters
    films_filter = Column(Text, default='[]')  # Empty = all films
    circuits_filter = Column(Text, default='[]')  # Filter by circuit name

    # Look-ahead window
    days_ahead = Column(Integer, default=14)  # Monitor schedules up to N days out

    # Notification settings
    notification_enabled = Column(Boolean, default=True)
    webhook_url = Column(String(500))
    notification_email = Column(String(255))

    # Last check tracking
    last_check_at = Column(DateTime(timezone=True))
    last_check_status = Column(String(50))  # 'success', 'failed', 'partial'
    last_check_alerts_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # Relationships
    company = relationship("Company")

    __table_args__ = (
        Index('idx_schedule_monitor_config_company', 'company_id'),
    )

    def __repr__(self):
        return f"<ScheduleMonitorConfig(company_id={self.company_id}, enabled={self.is_enabled})>"

    @property
    def theaters_filter_list(self):
        """Parse theaters_filter JSON to list"""
        try:
            return json.loads(self.theaters_filter) if isinstance(self.theaters_filter, str) else self.theaters_filter or []
        except Exception:
            return []

    @property
    def films_filter_list(self):
        """Parse films_filter JSON to list"""
        try:
            return json.loads(self.films_filter) if isinstance(self.films_filter, str) else self.films_filter or []
        except Exception:
            return []

    @property
    def circuits_filter_list(self):
        """Parse circuits_filter JSON to list"""
        try:
            return json.loads(self.circuits_filter) if isinstance(self.circuits_filter, str) else self.circuits_filter or []
        except Exception:
            return []


# ============================================================================
# DISCOUNT PROGRAMS AND THEATER AMENITIES
# ============================================================================

class CompanyProfile(Base):
    """
    Discovered pricing profile for a theater circuit/company.
    Captures unique pricing structure, ticket types, daypart schemes, discount days, and premium formats.
    Used for apples-to-apples comparison within same circuit and surge detection.

    Supports versioning: when a profile is updated, a new version is created and the old one
    is marked as not current. This allows tracking profile changes over time.
    """
    __tablename__ = 'company_profiles'

    profile_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    circuit_name = Column(String(100), nullable=False)  # e.g., "Marcus Theatres", "AMC", "Regal"

    # Versioning support
    version = Column(Integer, default=1)  # Version number for this profile
    previous_profile_id = Column(Integer, ForeignKey('company_profiles.profile_id', ondelete='SET NULL'))  # Link to previous version
    is_current = Column(Boolean, default=True)  # Only one profile per circuit should be current

    # Discovery metadata
    discovered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # Ticket type patterns discovered (JSON array)
    ticket_types = Column(Text, default='[]')  # ["Adult", "Child", "Senior", "Matinee", "Early Bird", "Twilight"]

    # Daypart scheme: how this circuit handles dayparts
    # "ticket-type-based" = daypart comes from ticket_type field (e.g., "Matinee" = flat price all ages)
    # "time-based" = daypart determined by showtime, ticket_type has age splits
    # "hybrid" = mix of both
    daypart_scheme = Column(String(50), default='unknown')

    # Daypart boundaries (JSON object mapping daypart -> time range)
    daypart_boundaries = Column(Text, default='{}')  # {"Matinee": "before 4pm", "Prime": "4pm-8pm", ...}

    # Pricing structure flags
    has_flat_matinee = Column(Boolean, default=False)  # True if Matinee = all ages same price
    has_discount_days = Column(Boolean, default=False)

    # Detected discount days (JSON array)
    discount_days = Column(Text, default='[]')  # [{"day": "Tuesday", "day_of_week": 1, "price": 5.00, "program": "$5 Tuesdays"}]

    # Premium formats available (JSON array)
    premium_formats = Column(Text, default='[]')  # ["IMAX", "Dolby Cinema", "ScreenX", "4DX"]

    # Premium surcharges (JSON object mapping format -> surcharge amount)
    premium_surcharges = Column(Text, default='{}')  # {"IMAX": 5.00, "Dolby": 4.00}

    # Data quality metrics
    theater_count = Column(Integer, default=0)  # Number of theaters analyzed
    sample_count = Column(Integer, default=0)  # Total price samples used
    date_range_start = Column(Date)
    date_range_end = Column(Date)
    confidence_score = Column(Numeric(3, 2), default=0.0)  # 0-1 based on sample size and consistency

    # Relationships
    company = relationship("Company")
    previous_profile = relationship("CompanyProfile", remote_side=[profile_id], foreign_keys=[previous_profile_id])
    discount_day_programs = relationship("DiscountDayProgram", back_populates="profile", cascade="all, delete-orphan")
    gaps = relationship("CompanyProfileGap", back_populates="profile", cascade="all, delete-orphan")

    __table_args__ = (
        # Note: removed unique constraint since we now support versioning
        # Only one profile should be is_current=True per company/circuit
        Index('idx_company_profiles_company', 'company_id'),
        Index('idx_company_profiles_circuit', 'circuit_name'),
        Index('idx_company_profiles_current', 'company_id', 'circuit_name', 'is_current'),
    )

    def __repr__(self):
        return f"<CompanyProfile(id={self.profile_id}, circuit='{self.circuit_name}', v{self.version}, current={self.is_current})>"

    @property
    def ticket_types_list(self):
        """Parse ticket_types JSON to list"""
        try:
            return json.loads(self.ticket_types) if isinstance(self.ticket_types, str) else self.ticket_types or []
        except Exception:
            return []

    @ticket_types_list.setter
    def ticket_types_list(self, value):
        """Set ticket_types from list"""
        self.ticket_types = json.dumps(value)

    @property
    def discount_days_list(self):
        """Parse discount_days JSON to list"""
        try:
            return json.loads(self.discount_days) if isinstance(self.discount_days, str) else self.discount_days or []
        except Exception:
            return []

    @discount_days_list.setter
    def discount_days_list(self, value):
        """Set discount_days from list"""
        self.discount_days = json.dumps(value)

    @property
    def premium_formats_list(self):
        """Parse premium_formats JSON to list"""
        try:
            return json.loads(self.premium_formats) if isinstance(self.premium_formats, str) else self.premium_formats or []
        except Exception:
            return []

    @premium_formats_list.setter
    def premium_formats_list(self, value):
        """Set premium_formats from list"""
        self.premium_formats = json.dumps(value)

    @property
    def premium_surcharges_dict(self):
        """Parse premium_surcharges JSON to dict"""
        try:
            return json.loads(self.premium_surcharges) if isinstance(self.premium_surcharges, str) else self.premium_surcharges or {}
        except Exception:
            return {}

    @premium_surcharges_dict.setter
    def premium_surcharges_dict(self, value):
        """Set premium_surcharges from dict"""
        self.premium_surcharges = json.dumps(value)

    @property
    def daypart_boundaries_dict(self):
        """Parse daypart_boundaries JSON to dict"""
        try:
            return json.loads(self.daypart_boundaries) if isinstance(self.daypart_boundaries, str) else self.daypart_boundaries or {}
        except Exception:
            return {}

    @daypart_boundaries_dict.setter
    def daypart_boundaries_dict(self, value):
        """Set daypart_boundaries from dict"""
        self.daypart_boundaries = json.dumps(value)

    def is_discount_day(self, date):
        """Check if a given date falls on a discount day for this circuit"""
        day_of_week = date.weekday()  # 0=Monday, 6=Sunday
        for dd in self.discount_days_list:
            if dd.get('day_of_week') == day_of_week:
                return True
        return False

    def get_discount_program(self, date):
        """Get discount program info for a given date, or None if not a discount day"""
        day_of_week = date.weekday()
        for dd in self.discount_days_list:
            if dd.get('day_of_week') == day_of_week:
                return dd
        return None


class DiscountDayProgram(Base):
    """
    Circuit-level discount day programs linked to CompanyProfile.

    Examples:
    - "$5 Tuesdays" (flat price discount)
    - "Senior Wednesdays" (percentage off for specific ticket types)
    - "Kids Weekend" (amount off for Child ticket type on weekends)

    These are used by the simplified baseline system to:
    1. Detect discount days before comparing to baselines
    2. Avoid false surge alerts when prices return to normal after discount
    3. Show discount day context in price comparisons
    """
    __tablename__ = 'discount_day_programs'

    program_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    profile_id = Column(Integer, ForeignKey('company_profiles.profile_id', ondelete='CASCADE'))
    circuit_name = Column(String(100), nullable=False)

    # Program details
    program_name = Column(String(100), nullable=False)  # "$5 Tuesdays", "Senior Wednesdays"
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday

    # Discount specification
    discount_type = Column(String(20), nullable=False)  # 'flat_price', 'percentage_off', 'amount_off'
    discount_value = Column(Numeric(10, 2), nullable=False)  # e.g., 5.00 for $5, 20 for 20%, 3.00 for $3 off

    # Applicability (JSON arrays, NULL = applies to all)
    applicable_ticket_types = Column(Text)  # JSON: ["Adult", "Child", "Senior"] or NULL for all
    applicable_formats = Column(Text)  # JSON: ["Standard", "IMAX"] or NULL for all
    applicable_dayparts = Column(Text)  # JSON: ["matinee", "evening"] or NULL for all

    # Tracking and quality
    is_active = Column(Boolean, default=True)
    discovered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_verified_at = Column(DateTime(timezone=True))
    confidence_score = Column(Numeric(3, 2), default=0.0)  # 0-1 based on sample data
    sample_count = Column(Integer, default=0)

    # Source tracking
    source = Column(String(50), default='auto_discovery')  # 'auto_discovery', 'manual', 'enttelligence'
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))

    # Relationships
    company = relationship("Company")
    profile = relationship("CompanyProfile", back_populates="discount_day_programs")

    __table_args__ = (
        UniqueConstraint('company_id', 'circuit_name', 'day_of_week', 'program_name', name='uq_discount_day_program'),
        Index('idx_discount_day_programs_company', 'company_id'),
        Index('idx_discount_day_programs_circuit', 'company_id', 'circuit_name'),
        Index('idx_discount_day_programs_day', 'day_of_week'),
        Index('idx_discount_day_programs_profile', 'profile_id'),
    )

    def __repr__(self):
        return f"<DiscountDayProgram(id={self.program_id}, circuit='{self.circuit_name}', program='{self.program_name}')>"

    @property
    def applicable_ticket_types_list(self):
        """Parse applicable_ticket_types JSON to list"""
        try:
            if not self.applicable_ticket_types:
                return None  # NULL = applies to all
            return json.loads(self.applicable_ticket_types) if isinstance(self.applicable_ticket_types, str) else self.applicable_ticket_types
        except Exception:
            return None

    @applicable_ticket_types_list.setter
    def applicable_ticket_types_list(self, value):
        """Set applicable_ticket_types from list"""
        self.applicable_ticket_types = json.dumps(value) if value else None

    @property
    def applicable_formats_list(self):
        """Parse applicable_formats JSON to list"""
        try:
            if not self.applicable_formats:
                return None  # NULL = applies to all
            return json.loads(self.applicable_formats) if isinstance(self.applicable_formats, str) else self.applicable_formats
        except Exception:
            return None

    @applicable_formats_list.setter
    def applicable_formats_list(self, value):
        """Set applicable_formats from list"""
        self.applicable_formats = json.dumps(value) if value else None

    @property
    def applicable_dayparts_list(self):
        """Parse applicable_dayparts JSON to list"""
        try:
            if not self.applicable_dayparts:
                return None  # NULL = applies to all
            return json.loads(self.applicable_dayparts) if isinstance(self.applicable_dayparts, str) else self.applicable_dayparts
        except Exception:
            return None

    @applicable_dayparts_list.setter
    def applicable_dayparts_list(self, value):
        """Set applicable_dayparts from list"""
        self.applicable_dayparts = json.dumps(value) if value else None

    @property
    def day_name(self):
        """Get human-readable day name"""
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return days[self.day_of_week] if 0 <= self.day_of_week <= 6 else 'Unknown'

    def applies_to(self, ticket_type: str = None, format_type: str = None, daypart: str = None) -> bool:
        """
        Check if this discount program applies to the given parameters.
        NULL values in applicability fields mean "applies to all".
        """
        # Check ticket type
        if ticket_type and self.applicable_ticket_types_list:
            if ticket_type not in self.applicable_ticket_types_list:
                return False

        # Check format
        if format_type and self.applicable_formats_list:
            if format_type not in self.applicable_formats_list:
                return False

        # Check daypart
        if daypart and self.applicable_dayparts_list:
            if daypart not in self.applicable_dayparts_list:
                return False

        return True


class CompanyProfileGap(Base):
    """
    Track gaps/missing data in company profiles.

    Gaps are identified when:
    - A format is expected but not discovered (e.g., circuit has IMAX elsewhere)
    - A ticket type is missing from the profile
    - A daypart has insufficient data

    Gaps can be resolved when data is later discovered or manually added.
    """
    __tablename__ = 'company_profile_gaps'

    gap_id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey('company_profiles.profile_id', ondelete='CASCADE'), nullable=False)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)

    # Gap details
    gap_type = Column(String(50), nullable=False)  # 'format', 'ticket_type', 'daypart', 'day_of_week'
    expected_value = Column(String(100), nullable=False)  # e.g., 'IMAX', '3D', 'Senior', 'matinee'
    reason = Column(Text)  # Why we expected this (e.g., "Found at other theaters in circuit")

    # Tracking
    first_detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    resolution_notes = Column(Text)

    # Relationships
    profile = relationship("CompanyProfile", back_populates="gaps")
    company = relationship("Company")
    resolver = relationship("User")

    __table_args__ = (
        UniqueConstraint('profile_id', 'gap_type', 'expected_value', name='uq_profile_gap'),
        Index('idx_profile_gaps_profile', 'profile_id'),
        Index('idx_profile_gaps_type', 'gap_type'),
        Index('idx_profile_gaps_unresolved', 'profile_id', 'resolved_at'),
    )

    def __repr__(self):
        status = 'resolved' if self.resolved_at else 'open'
        return f"<CompanyProfileGap(id={self.gap_id}, type='{self.gap_type}', value='{self.expected_value}', status={status})>"

    @property
    def is_resolved(self):
        return self.resolved_at is not None


class TheaterOnboardingStatus(Base):
    """
    Track the onboarding workflow for new theaters into the baseline system.

    Onboarding steps:
    1. Add to market (step_market_added)
    2. Initial price collection (step_initial_scrape)
    3. Baseline discovery (step_baseline_discovered)
    4. Link to company profile (step_profile_linked)
    5. Review and confirm baselines (step_baseline_confirmed)

    This helps users understand which theaters are fully onboarded and which need attention.
    """
    __tablename__ = 'theater_onboarding_status'

    status_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    theater_name = Column(String(255), nullable=False)
    circuit_name = Column(String(100))
    market = Column(String(100))

    # Step 1: Add to Market
    step_market_added = Column(Boolean, default=False)
    step_market_added_at = Column(DateTime(timezone=True))

    # Step 2: Initial Price Collection
    step_initial_scrape = Column(Boolean, default=False)
    step_initial_scrape_at = Column(DateTime(timezone=True))
    step_initial_scrape_source = Column(String(50))  # 'fandango', 'enttelligence'
    step_initial_scrape_count = Column(Integer, default=0)

    # Step 3: Baseline Discovery
    step_baseline_discovered = Column(Boolean, default=False)
    step_baseline_discovered_at = Column(DateTime(timezone=True))
    step_baseline_count = Column(Integer, default=0)

    # Step 4: Link to Company Profile
    step_profile_linked = Column(Boolean, default=False)
    step_profile_linked_at = Column(DateTime(timezone=True))
    step_profile_id = Column(Integer, ForeignKey('company_profiles.profile_id', ondelete='SET NULL'))

    # Step 5: Confirm Baselines
    step_baseline_confirmed = Column(Boolean, default=False)
    step_baseline_confirmed_at = Column(DateTime(timezone=True))
    step_baseline_confirmed_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))

    # Coverage tracking (JSON arrays)
    formats_discovered = Column(Text, default='[]')  # JSON array of discovered formats
    ticket_types_discovered = Column(Text, default='[]')  # JSON array of discovered ticket types
    dayparts_discovered = Column(Text, default='[]')  # JSON array of discovered dayparts
    coverage_score = Column(Numeric(3, 2), default=0.0)  # 0-1 based on completeness

    # Status
    onboarding_status = Column(String(50), default='not_started')  # 'not_started', 'in_progress', 'complete', 'needs_review'
    last_updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    notes = Column(Text)

    # Relationships
    company = relationship("Company")
    profile = relationship("CompanyProfile")
    confirmed_by_user = relationship("User", foreign_keys=[step_baseline_confirmed_by])

    __table_args__ = (
        UniqueConstraint('company_id', 'theater_name', name='uq_theater_onboarding'),
        Index('idx_onboarding_company', 'company_id'),
        Index('idx_onboarding_status', 'company_id', 'onboarding_status'),
        Index('idx_onboarding_market', 'company_id', 'market'),
        Index('idx_onboarding_circuit', 'company_id', 'circuit_name'),
    )

    def __repr__(self):
        return f"<TheaterOnboardingStatus(theater='{self.theater_name}', status='{self.onboarding_status}')>"

    @property
    def formats_discovered_list(self):
        """Parse formats_discovered JSON to list"""
        try:
            return json.loads(self.formats_discovered) if isinstance(self.formats_discovered, str) else self.formats_discovered or []
        except Exception:
            return []

    @formats_discovered_list.setter
    def formats_discovered_list(self, value):
        """Set formats_discovered from list"""
        self.formats_discovered = json.dumps(value)

    @property
    def ticket_types_discovered_list(self):
        """Parse ticket_types_discovered JSON to list"""
        try:
            return json.loads(self.ticket_types_discovered) if isinstance(self.ticket_types_discovered, str) else self.ticket_types_discovered or []
        except Exception:
            return []

    @ticket_types_discovered_list.setter
    def ticket_types_discovered_list(self, value):
        """Set ticket_types_discovered from list"""
        self.ticket_types_discovered = json.dumps(value)

    @property
    def dayparts_discovered_list(self):
        """Parse dayparts_discovered JSON to list"""
        try:
            return json.loads(self.dayparts_discovered) if isinstance(self.dayparts_discovered, str) else self.dayparts_discovered or []
        except Exception:
            return []

    @dayparts_discovered_list.setter
    def dayparts_discovered_list(self, value):
        """Set dayparts_discovered from list"""
        self.dayparts_discovered = json.dumps(value)

    @property
    def completed_steps(self):
        """Return count of completed onboarding steps"""
        count = 0
        if self.step_market_added:
            count += 1
        if self.step_initial_scrape:
            count += 1
        if self.step_baseline_discovered:
            count += 1
        if self.step_profile_linked:
            count += 1
        if self.step_baseline_confirmed:
            count += 1
        return count

    @property
    def total_steps(self):
        """Return total number of onboarding steps"""
        return 5

    @property
    def progress_percent(self):
        """Return onboarding progress as percentage"""
        return int((self.completed_steps / self.total_steps) * 100)


class DiscountProgram(Base):
    """
    Track recurring discount programs at theaters (e.g., "$5 Tuesdays", "Senior Wednesdays").
    Used to avoid false surge alerts when prices return to normal after discount days.
    """
    __tablename__ = 'discount_programs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    theater_name = Column(String(255), nullable=False)
    circuit_name = Column(String(100))

    # Program details
    program_name = Column(String(100), nullable=False)  # "$5 Tuesday", "Senior Day"
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday

    # Discount specification
    discount_type = Column(String(20), nullable=False)  # 'flat_price', 'percentage', 'amount_off'
    discount_value = Column(Numeric(10, 2), nullable=False)  # e.g., 5.00 for $5, 20 for 20%

    # Applicability (NULL = applies to all)
    ticket_types = Column(String(255))  # Comma-separated, NULL = all
    formats = Column(String(255))  # Comma-separated, NULL = all
    dayparts = Column(String(100))  # Comma-separated, NULL = all

    # Tracking
    detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    confidence = Column(Numeric(3, 2), default=1.0)  # Detection confidence 0-1
    is_verified = Column(Boolean, default=False)  # Manually verified by user
    is_active = Column(Boolean, default=True)
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))

    # Relationships
    company = relationship("Company")

    __table_args__ = (
        Index('idx_discount_programs_company', 'company_id'),
        Index('idx_discount_programs_theater', 'company_id', 'theater_name'),
        Index('idx_discount_programs_day', 'company_id', 'day_of_week'),
    )

    def __repr__(self):
        return f"<DiscountProgram(id={self.id}, theater='{self.theater_name}', name='{self.program_name}')>"

    @property
    def ticket_types_list(self):
        """Parse comma-separated ticket_types to list"""
        if not self.ticket_types:
            return []
        return [t.strip() for t in self.ticket_types.split(',') if t.strip()]

    @property
    def formats_list(self):
        """Parse comma-separated formats to list"""
        if not self.formats:
            return []
        return [f.strip() for f in self.formats.split(',') if f.strip()]

    @property
    def day_name(self):
        """Get human-readable day name"""
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return days[self.day_of_week] if 0 <= self.day_of_week <= 6 else 'Unknown'


class TheaterAmenities(Base):
    """
    Track competitor theater features and amenities.
    Helps understand pricing context and competitive positioning.
    """
    __tablename__ = 'theater_amenities'

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    theater_name = Column(String(255), nullable=False)
    circuit_name = Column(String(100))

    # Seating
    has_recliners = Column(Boolean)
    has_reserved_seating = Column(Boolean)
    has_heated_seats = Column(Boolean)

    # Premium formats available
    has_imax = Column(Boolean)
    has_dolby_cinema = Column(Boolean)
    has_dolby_atmos = Column(Boolean)
    has_rpx = Column(Boolean)
    has_4dx = Column(Boolean)
    has_screenx = Column(Boolean)
    has_dbox = Column(Boolean)

    # Food & beverage
    has_dine_in = Column(Boolean)
    has_full_bar = Column(Boolean)
    has_premium_concessions = Column(Boolean)
    has_reserved_food_delivery = Column(Boolean)  # Seat-side service

    # Theater info
    screen_count = Column(Integer)
    premium_screen_count = Column(Integer)  # Total PLF screens
    year_built = Column(Integer)
    year_renovated = Column(Integer)

    # Per-format screen counts (e.g., 2 IMAX screens)
    imax_screen_count = Column(Integer)
    dolby_screen_count = Column(Integer)
    plf_other_count = Column(Integer)  # Other PLF (RPX, 4DX, etc.)

    # Circuit-branded PLF info (JSON string: {"superscreen": "Marcus SuperScreen DLX"})
    circuit_plf_info = Column(Text)

    # Metadata
    notes = Column(Text)
    source = Column(String(50))  # 'manual', 'scraped', 'website'
    last_verified = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))

    # Relationships
    company = relationship("Company")

    __table_args__ = (
        UniqueConstraint('company_id', 'theater_name', name='uq_theater_amenities'),
        Index('idx_theater_amenities_company', 'company_id'),
        Index('idx_theater_amenities_circuit', 'company_id', 'circuit_name'),
    )

    def __repr__(self):
        return f"<TheaterAmenities(id={self.id}, theater='{self.theater_name}')>"

    @property
    def premium_formats(self):
        """Return list of available premium formats"""
        formats = []
        if self.has_imax:
            formats.append('IMAX')
        if self.has_dolby_cinema:
            formats.append('Dolby Cinema')
        if self.has_dolby_atmos:
            formats.append('Dolby Atmos')
        if self.has_rpx:
            formats.append('RPX')
        if self.has_4dx:
            formats.append('4DX')
        if self.has_screenx:
            formats.append('ScreenX')
        if self.has_dbox:
            formats.append('D-BOX')
        return formats

    def get_circuit_plf(self) -> dict:
        """Parse circuit_plf_info JSON string to dict"""
        if not self.circuit_plf_info:
            return {}
        try:
            return json.loads(self.circuit_plf_info)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_circuit_plf(self, value: dict):
        """Set circuit_plf_info from dict"""
        if value:
            self.circuit_plf_info = json.dumps(value)
        else:
            self.circuit_plf_info = None

    @property
    def amenity_score(self):
        """Calculate a simple amenity score (0-10) based on features"""
        score = 0
        if self.has_recliners:
            score += 2
        if self.has_reserved_seating:
            score += 1
        if self.has_heated_seats:
            score += 1
        if self.has_dine_in:
            score += 2
        if self.has_full_bar:
            score += 1
        if self.has_premium_concessions:
            score += 1
        if len(self.premium_formats) > 0:
            score += min(2, len(self.premium_formats))  # Up to 2 points for premium formats
        return min(10, score)


# ============================================================================
# ALTERNATIVE CONTENT / SPECIAL EVENTS
# ============================================================================

class AlternativeContentFilm(Base):
    """
    Track films identified as Alternative Content (special events, Fathom, opera, etc.).

    These films are typically priced differently and should be excluded from
    discount day compliance checks to avoid false positives.

    Content Types:
    - fathom_event: Fathom Events (classic films, documentaries, anime)
    - opera_broadcast: Met Opera, Royal Opera, etc.
    - theater_broadcast: NT Live, Broadway HD
    - concert_film: Tour films, concert documentaries
    - anime_event: Ghibli Fest, Crunchyroll releases
    - sports_event: NFL, WWE, UFC
    - classic_rerelease: Anniversary editions, remasters
    - marathon: Double/triple features
    - special_presentation: Director Q&A, premieres
    """
    __tablename__ = 'alternative_content_films'

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)

    # Film identification
    film_title = Column(String(500), nullable=False)
    linked_film_id = Column(Integer, ForeignKey('films.film_id', ondelete='SET NULL'))  # Link to enriched film if matched
    normalized_title = Column(String(500))  # Cleaned title for matching

    # Classification
    content_type = Column(String(50), nullable=False)  # 'fathom_event', 'opera_broadcast', etc.
    content_source = Column(String(100))  # 'Fathom Events', 'Met Opera', 'Crunchyroll', etc.

    # Detection metadata
    detected_by = Column(String(50), nullable=False)  # 'auto_title', 'auto_price', 'auto_ticket_type', 'manual'
    detection_confidence = Column(Numeric(3, 2), default=Decimal('0.80'))  # 0.00 to 1.00
    detection_reason = Column(Text)  # Why it was flagged (keywords found, price patterns, etc.)

    # Tracking
    first_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    occurrence_count = Column(Integer, default=1)  # How many times we've seen this film

    # Manual verification
    is_verified = Column(Boolean, default=False)
    verified_by = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    verified_at = Column(DateTime(timezone=True))

    # Status
    is_active = Column(Boolean, default=True)  # False = no longer in theaters

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))

    # Relationships
    company = relationship("Company")
    linked_film = relationship("Film", foreign_keys=[linked_film_id])
    verifier = relationship("User", foreign_keys=[verified_by])

    __table_args__ = (
        Index('idx_ac_films_company', 'company_id'),
        Index('idx_ac_films_content_type', 'company_id', 'content_type'),
        Index('idx_ac_films_title', 'company_id', 'normalized_title'),
        Index('idx_ac_films_active', 'company_id', 'is_active'),
    )

    def __repr__(self):
        return f"<AlternativeContentFilm(title='{self.film_title}', type='{self.content_type}')>"


class CircuitACPricing(Base):
    """
    Track how each circuit prices Alternative Content.

    This allows us to understand each circuit's pricing strategy for special events
    and correctly identify the ticket types used for AC vs standard films.

    Example:
    - Marcus uses 'AC Loyalty Member' for discounted AC pricing
    - B&B uses 'B&B Event $14' as a flat event price
    """
    __tablename__ = 'circuit_ac_pricing'

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.company_id', ondelete='CASCADE'), nullable=False)
    circuit_name = Column(String(200), nullable=False)
    content_type = Column(String(50), nullable=False)  # 'fathom_event', 'opera_broadcast', 'all', etc.

    # Ticket type mappings
    standard_ticket_type = Column(String(100))  # 'AC Adult', 'Alternative Content', 'Event'
    discount_ticket_type = Column(String(100))  # 'AC Loyalty Member', 'AC Discount Day', NULL if no discount

    # Pricing patterns
    typical_price_min = Column(Numeric(10, 2))
    typical_price_max = Column(Numeric(10, 2))

    # Discount day behavior
    discount_day_applies = Column(Boolean, default=False)  # Does circuit discount apply to AC?
    discount_day_ticket_type = Column(String(100))  # What ticket type is used on discount days?
    discount_day_price = Column(Numeric(10, 2))  # Typical discount day price for AC

    # Premium format behavior
    premium_surcharge_applies = Column(Boolean, default=True)  # Do PLF surcharges apply to AC?

    # Documentation
    notes = Column(Text)
    source = Column(String(50))  # 'auto_discovery', 'manual', 'verified'

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))

    # Relationships
    company = relationship("Company")

    __table_args__ = (
        UniqueConstraint('company_id', 'circuit_name', 'content_type', name='uq_circuit_ac_pricing'),
        Index('idx_circuit_ac_pricing_circuit', 'company_id', 'circuit_name'),
    )

    def __repr__(self):
        return f"<CircuitACPricing(circuit='{self.circuit_name}', content_type='{self.content_type}')>"


# ============================================================================
# CIRCUIT PRESALES (Presale Tracking)
# ============================================================================

class CircuitPresale(Base):
    """Daily presale snapshots aggregated by circuit and film"""
    __tablename__ = 'circuit_presales'

    id = Column(Integer, primary_key=True, autoincrement=True)
    circuit_name = Column(String(255), nullable=False)
    film_title = Column(String(500), nullable=False)
    release_date = Column(Date, nullable=False)
    snapshot_date = Column(Date, nullable=False)
    days_before_release = Column(Integer, nullable=False)

    # Volume metrics
    total_tickets_sold = Column(Integer, default=0)
    total_revenue = Column(Numeric(12, 2), default=0)
    total_showtimes = Column(Integer, default=0)
    total_theaters = Column(Integer, default=0)

    # Performance metrics
    avg_tickets_per_show = Column(Float, default=0.0)
    avg_tickets_per_theater = Column(Float, default=0.0)
    avg_ticket_price = Column(Numeric(6, 2), default=0.0)

    # Format breakdown (tickets by format)
    tickets_imax = Column(Integer, default=0)
    tickets_dolby = Column(Integer, default=0)
    tickets_3d = Column(Integer, default=0)
    tickets_premium = Column(Integer, default=0)
    tickets_standard = Column(Integer, default=0)

    # Capacity metrics
    total_capacity = Column(Integer, default=0)
    total_available = Column(Integer, default=0)
    fill_rate_percent = Column(Float, default=0.0)

    # Metadata
    data_source = Column(String(50), default='enttelligence')
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint('circuit_name', 'film_title', 'snapshot_date',
                         name='uq_circuit_presale_snapshot'),
        Index('idx_circuit_presales_circuit', 'circuit_name'),
        Index('idx_circuit_presales_film', 'film_title', 'release_date'),
        Index('idx_circuit_presales_snapshot', 'snapshot_date'),
        Index('idx_circuit_presales_days_before', 'film_title', 'days_before_release'),
    )

    def __repr__(self):
        return f"<CircuitPresale(circuit='{self.circuit_name}', film='{self.film_title}', date={self.snapshot_date})>"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_table_classes():
    """Return all ORM model classes for introspection"""
    return {
        'Company': Company,
        'User': User,
        'AuditLog': AuditLog,
        'ScrapeRun': ScrapeRun,
        'Showing': Showing,
        'Price': Price,
        'Film': Film,
        'OperatingHours': OperatingHours,
        'UnmatchedFilm': UnmatchedFilm,
        'IgnoredFilm': IgnoredFilm,
        'UnmatchedTicketType': UnmatchedTicketType,
        'PriceAlert': PriceAlert,
        'AlertConfiguration': AlertConfiguration,
        'PriceBaseline': PriceBaseline,
        'TheaterMetadata': TheaterMetadata,
        'MarketEvent': MarketEvent,
        # EntTelligence cache tables
        'EntTelligencePriceCache': EntTelligencePriceCache,
        'TheaterNameMapping': TheaterNameMapping,
        'EntTelligenceSyncRun': EntTelligenceSyncRun,
        # Schedule monitor tables
        'ScheduleBaseline': ScheduleBaseline,
        'ScheduleAlert': ScheduleAlert,
        'ScheduleMonitorConfig': ScheduleMonitorConfig,
        # Discount programs and amenities (theater-level)
        'DiscountProgram': DiscountProgram,
        'TheaterAmenities': TheaterAmenities,
        # Company profiles and circuit-level discount programs
        'CompanyProfile': CompanyProfile,
        'DiscountDayProgram': DiscountDayProgram,
        'CompanyProfileGap': CompanyProfileGap,
        # Theater onboarding
        'TheaterOnboardingStatus': TheaterOnboardingStatus,
        # Alternative content / special events
        'AlternativeContentFilm': AlternativeContentFilm,
        'CircuitACPricing': CircuitACPricing,
        # Presale tracking
        'CircuitPresale': CircuitPresale,
    }


def create_all_tables(engine):
    """Create all tables in the database (for initial setup)"""
    Base.metadata.create_all(engine)


def drop_all_tables(engine):
    """Drop all tables in the database (for testing/cleanup)"""
    Base.metadata.drop_all(engine)
