"""
PriceScout Database Package
Modular database adapter layer for multi-tenant theater data

Modules:
- core: Database initialization and company context
- utils: Utilities, async helpers, raw SQL
- checkpoint: Checkpoint tracking for crash-resilient scrapes
- journal: File-based progress recovery
- scrape_runs: Scrape run management
- queries: Theater/market lookups, historical data, analysis
- films: Film metadata CRUD
- film_enrichment: OMDb integration and backfill
- prices: Price save/query
- showings: Showtime upserts
- operating_hours: Operating hours management
- ticket_types: Ticket type tracking

Usage:
    from app.db import init_database, set_current_company
    from app.db.checkpoint import create_checkpoint
    from app.db.films import get_film_metadata
"""

# Core functions - database init and company context
from app.db.core import (
    init_database,
    set_current_company,
    get_current_company,
    get_db_connection,
)

# Utility functions
from app.db.utils import (
    run_async_safe,
    execute_raw_sql,
    execute_raw_sql_pandas,
    update_database_schema,
    migrate_schema,
    _parse_time_to_minutes,
)

# Checkpoint tracking (crash-resilient scrapes)
from app.db.checkpoint import (
    create_checkpoint,
    complete_checkpoint,
    fail_checkpoint,
    get_completed_theaters,
    get_job_progress,
    cleanup_old_checkpoints,
)

# Progress journal (file-based recovery)
from app.db.journal import (
    PROGRESS_JOURNAL_DIR,
    get_journal_path,
    write_progress_journal,
    read_progress_journal,
    update_theater_progress,
    get_resumable_theaters,
    start_scrape_journal,
    complete_scrape_journal,
    list_incomplete_jobs,
    cleanup_old_journals,
)

# Scrape run management
from app.db.scrape_runs import (
    create_scrape_run,
    update_scrape_run_status,
)

# Queries - theater/market lookups, historical data, analysis
from app.db.queries import (
    get_dates_for_theaters,
    get_common_films_for_theaters_dates,
    get_theater_comparison_summary,
    get_market_at_a_glance_data,
    calculate_operating_hours_from_showings,
    get_all_theaters,
    get_all_markets,
    get_theaters_by_market,
    get_configured_operating_hours,
    get_scrape_runs,
    query_historical_data,
    get_unique_column_values,
    get_dates_for_theater,
    get_films_for_theater_date,
    get_final_prices,
    get_available_films,
    get_available_dates,
    get_available_dayparts,
    get_theaters_with_data,
    get_common_dates_for_theaters,
    backfill_play_dates,
    consolidate_ticket_types,
)

# Film metadata management
from app.db.films import (
    get_all_film_titles,
    get_film_metadata,
    save_film_metadata,
    get_unmatched_films,
    add_unmatched_film,
    get_ignored_films,
    add_ignored_film,
    remove_ignored_film,
    upsert_film_details,
    check_film_exists,
    get_film_details,
    get_all_unique_genres,
    get_all_unique_ratings,
    log_unmatched_film,
    delete_unmatched_film,
    get_films_missing_release_date,
    get_films_missing_metadata,
    get_all_films_for_enrichment,
    get_ignored_film_titles,
    get_first_play_date_for_all_films,
)

# Film enrichment (OMDb, Fandango, backfill)
from app.db.film_enrichment import (
    backfill_film_details_from_fandango_single,
    enrich_new_films,
    _enrich_films_sync,
    backfill_film_details_from_fandango,
    backfill_imdb_ids_from_fandango,
    backfill_showtimes_data_from_fandango,
)

# Price management
from app.db.prices import (
    save_prices,
    get_prices_for_run,
)

# Showings management
from app.db.showings import (
    upsert_showings,
)

# Operating hours management
from app.db.operating_hours import (
    save_operating_hours,
    save_full_operating_hours_run,
    delete_operating_hours,
    get_operating_hours_for_theaters_and_dates,
    get_all_op_hours_dates,
)

# Ticket type management
from app.db.ticket_types import (
    get_ticket_type_usage_counts,
    log_unmatched_ticket_type,
    get_unmatched_ticket_types,
    delete_unmatched_ticket_type,
)

__all__ = [
    # Core
    'init_database', 'set_current_company', 'get_current_company', 'get_db_connection',
    # Utils
    'run_async_safe', 'execute_raw_sql', 'execute_raw_sql_pandas',
    'update_database_schema', 'migrate_schema', '_parse_time_to_minutes',
    # Checkpoint
    'create_checkpoint', 'complete_checkpoint', 'fail_checkpoint',
    'get_completed_theaters', 'get_job_progress', 'cleanup_old_checkpoints',
    # Journal
    'PROGRESS_JOURNAL_DIR', 'get_journal_path', 'write_progress_journal',
    'read_progress_journal', 'update_theater_progress', 'get_resumable_theaters',
    'start_scrape_journal', 'complete_scrape_journal', 'list_incomplete_jobs', 'cleanup_old_journals',
    # Scrape runs
    'create_scrape_run', 'update_scrape_run_status',
    # Queries
    'get_dates_for_theaters', 'get_common_films_for_theaters_dates',
    'get_theater_comparison_summary', 'get_market_at_a_glance_data',
    'calculate_operating_hours_from_showings', 'get_all_theaters', 'get_all_markets',
    'get_theaters_by_market', 'get_configured_operating_hours',
    'get_scrape_runs', 'query_historical_data',
    'get_unique_column_values', 'get_dates_for_theater', 'get_films_for_theater_date',
    'get_final_prices', 'get_available_films', 'get_available_dates',
    'get_available_dayparts', 'get_theaters_with_data', 'get_common_dates_for_theaters',
    'backfill_play_dates', 'consolidate_ticket_types',
    # Films
    'get_all_film_titles', 'get_film_metadata', 'save_film_metadata',
    'get_unmatched_films', 'add_unmatched_film', 'get_ignored_films',
    'add_ignored_film', 'remove_ignored_film', 'upsert_film_details',
    'check_film_exists', 'get_film_details', 'get_all_unique_genres',
    'get_all_unique_ratings', 'log_unmatched_film', 'delete_unmatched_film',
    'get_films_missing_release_date', 'get_films_missing_metadata',
    'get_all_films_for_enrichment', 'get_ignored_film_titles', 'get_first_play_date_for_all_films',
    # Film enrichment
    'backfill_film_details_from_fandango_single', 'enrich_new_films', '_enrich_films_sync',
    'backfill_film_details_from_fandango', 'backfill_imdb_ids_from_fandango',
    'backfill_showtimes_data_from_fandango',
    # Prices
    'save_prices', 'get_prices_for_run',
    # Showings
    'upsert_showings',
    # Operating hours
    'save_operating_hours', 'save_full_operating_hours_run',
    'delete_operating_hours', 'get_operating_hours_for_theaters_and_dates', 'get_all_op_hours_dates',
    # Ticket types
    'get_ticket_type_usage_counts', 'log_unmatched_ticket_type',
    'get_unmatched_ticket_types', 'delete_unmatched_ticket_type',
]
