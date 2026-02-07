"""
Database Adapter Layer for PriceScout
Version: 3.0.0
Date: February 2026

RE-EXPORT HUB: All functions have been moved to modular packages in app/db/.
This file exists purely for backward compatibility — all callers that import from
``app.db_adapter`` continue to work without changes.

New code should import directly from the subpackage:
    from app.db import init_database, set_current_company
    from app.db.checkpoint import create_checkpoint
"""

# ---------------------------------------------------------------------------
# ORM Session & Models (re-exported so callers can do
#   ``from app.db_adapter import get_session, Showing``)
# ---------------------------------------------------------------------------
from app.db_session import get_session, get_engine, legacy_db_connection  # noqa: F401
from app.db_models import (  # noqa: F401
    Company, User, ScrapeRun, ScrapeCheckpoint, Showing, Price, Film,
    OperatingHours, UnmatchedFilm, IgnoredFilm, UnmatchedTicketType,
    TheaterMetadata, MarketEvent, TheaterOperatingHours,
)

# App config (some callers do ``from app.db_adapter import config``)
from app import config  # noqa: F401

# ---------------------------------------------------------------------------
# Core — init, company context
# ---------------------------------------------------------------------------
from app.db.core import (  # noqa: F401
    init_database,
    set_current_company,
    get_current_company,
    get_db_connection,
)

# ---------------------------------------------------------------------------
# Utilities — async helpers, raw SQL
# ---------------------------------------------------------------------------
from app.db.utils import (  # noqa: F401
    run_async_safe,
    execute_raw_sql,
    execute_raw_sql_pandas,
    update_database_schema,
    migrate_schema,
    _parse_time_to_minutes,
)

# ---------------------------------------------------------------------------
# Checkpoint tracking (crash-resilient scrapes)
# ---------------------------------------------------------------------------
from app.db.checkpoint import (  # noqa: F401
    create_checkpoint,
    complete_checkpoint,
    fail_checkpoint,
    get_completed_theaters,
    get_job_progress,
    cleanup_old_checkpoints,
)

# ---------------------------------------------------------------------------
# Progress journal (file-based recovery)
# ---------------------------------------------------------------------------
from app.db.journal import (  # noqa: F401
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

# ---------------------------------------------------------------------------
# Scrape run management
# ---------------------------------------------------------------------------
from app.db.scrape_runs import (  # noqa: F401
    create_scrape_run,
    update_scrape_run_status,
)

# ---------------------------------------------------------------------------
# Queries — theater/market lookups, historical data, analysis
# ---------------------------------------------------------------------------
from app.db.queries import (  # noqa: F401
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

# ---------------------------------------------------------------------------
# Film metadata management
# ---------------------------------------------------------------------------
from app.db.films import (  # noqa: F401
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

# ---------------------------------------------------------------------------
# Film enrichment (OMDb, Fandango, backfill)
# ---------------------------------------------------------------------------
from app.db.film_enrichment import (  # noqa: F401
    backfill_film_details_from_fandango_single,
    enrich_new_films,
    _enrich_films_sync,
    backfill_film_details_from_fandango,
    backfill_imdb_ids_from_fandango,
    backfill_showtimes_data_from_fandango,
)

# ---------------------------------------------------------------------------
# Price management
# ---------------------------------------------------------------------------
from app.db.prices import (  # noqa: F401
    save_prices,
    get_prices_for_run,
)

# ---------------------------------------------------------------------------
# Showings management
# ---------------------------------------------------------------------------
from app.db.showings import (  # noqa: F401
    upsert_showings,
)

# ---------------------------------------------------------------------------
# Operating hours management
# ---------------------------------------------------------------------------
from app.db.operating_hours import (  # noqa: F401
    save_operating_hours,
    save_full_operating_hours_run,
    delete_operating_hours,
    get_operating_hours_for_theaters_and_dates,
    get_all_op_hours_dates,
)

# ---------------------------------------------------------------------------
# Ticket type management
# ---------------------------------------------------------------------------
from app.db.ticket_types import (  # noqa: F401
    get_ticket_type_usage_counts,
    log_unmatched_ticket_type,
    get_unmatched_ticket_types,
    delete_unmatched_ticket_type,
)
