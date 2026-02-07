"""
Migration: Add capacity/sales and film metadata columns to enttelligence_price_cache

Adds columns for:
- capacity, available, blocked (auditorium seat tracking -> presale sales)
- release_date, imdb_id, movie_id, theater_id (film & theater metadata)

Also adds capacity columns to circuit_presales for fill-rate tracking.

Usage:
    python migrations/add_capacity_columns.py
"""

import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = "pricescout.db"


def backup_database():
    """Create timestamped backup before migration"""
    if not Path(DB_PATH).exists():
        print(f"Database not found: {DB_PATH}")
        return False

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"pricescout_backup_{timestamp}.db"

    shutil.copy2(DB_PATH, backup_path)
    print(f"Backup created: {backup_path}")
    return True


def add_column_if_missing(cursor, table, column, col_type, default=None):
    """Add a column to a table if it doesn't already exist."""
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}

    if column in existing:
        print(f"  [skip] {table}.{column} already exists")
        return False

    default_clause = f" DEFAULT {default}" if default is not None else ""
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}")
    print(f"  [added] {table}.{column} ({col_type})")
    return True


def migrate():
    print("\n" + "=" * 70)
    print("  MIGRATION: Add capacity/sales columns to EntTelligence cache")
    print("=" * 70)

    if not backup_database():
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # ---- enttelligence_price_cache ----
        print("\n--- enttelligence_price_cache ---")

        # Capacity / sales
        add_column_if_missing(cursor, 'enttelligence_price_cache', 'capacity', 'INTEGER')
        add_column_if_missing(cursor, 'enttelligence_price_cache', 'available', 'INTEGER')
        add_column_if_missing(cursor, 'enttelligence_price_cache', 'blocked', 'INTEGER')

        # Film metadata
        add_column_if_missing(cursor, 'enttelligence_price_cache', 'release_date', 'VARCHAR(20)')
        add_column_if_missing(cursor, 'enttelligence_price_cache', 'imdb_id', 'VARCHAR(20)')
        add_column_if_missing(cursor, 'enttelligence_price_cache', 'movie_id', 'VARCHAR(20)')
        add_column_if_missing(cursor, 'enttelligence_price_cache', 'theater_id', 'VARCHAR(20)')

        # Index on release_date for presale queries
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ent_cache_release
                ON enttelligence_price_cache(release_date)
            """)
            print("  [index] idx_ent_cache_release")
        except Exception:
            pass

        # ---- circuit_presales ----
        print("\n--- circuit_presales ---")

        # Ensure the table exists (in case migration hasn't run)
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='circuit_presales'
        """)
        if not cursor.fetchone():
            print("  [info] circuit_presales table does not exist yet, creating...")
            cursor.execute("""
                CREATE TABLE circuit_presales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    circuit_name VARCHAR(255) NOT NULL,
                    film_title VARCHAR(500) NOT NULL,
                    release_date DATE NOT NULL,
                    snapshot_date DATE NOT NULL,
                    days_before_release INTEGER NOT NULL,
                    total_tickets_sold INTEGER DEFAULT 0,
                    total_revenue DECIMAL(12,2) DEFAULT 0,
                    total_showtimes INTEGER DEFAULT 0,
                    total_theaters INTEGER DEFAULT 0,
                    avg_tickets_per_show REAL DEFAULT 0.0,
                    avg_tickets_per_theater REAL DEFAULT 0.0,
                    avg_ticket_price DECIMAL(6,2) DEFAULT 0.0,
                    tickets_imax INTEGER DEFAULT 0,
                    tickets_dolby INTEGER DEFAULT 0,
                    tickets_3d INTEGER DEFAULT 0,
                    tickets_premium INTEGER DEFAULT 0,
                    tickets_standard INTEGER DEFAULT 0,
                    total_capacity INTEGER DEFAULT 0,
                    total_available INTEGER DEFAULT 0,
                    fill_rate_percent REAL DEFAULT 0.0,
                    data_source VARCHAR(50) DEFAULT 'enttelligence',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(circuit_name, film_title, snapshot_date)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_circuit_presales_circuit ON circuit_presales(circuit_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_circuit_presales_film ON circuit_presales(film_title, release_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_circuit_presales_snapshot ON circuit_presales(snapshot_date DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_circuit_presales_days_before ON circuit_presales(film_title, days_before_release)")
            print("  [created] circuit_presales table with all columns")
        else:
            # Add new capacity columns if missing
            add_column_if_missing(cursor, 'circuit_presales', 'total_capacity', 'INTEGER', 0)
            add_column_if_missing(cursor, 'circuit_presales', 'total_available', 'INTEGER', 0)
            add_column_if_missing(cursor, 'circuit_presales', 'fill_rate_percent', 'REAL', 0.0)

        conn.commit()
        print("\nMigration completed successfully!")
        return True

    except Exception as e:
        print(f"\nMigration error: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
