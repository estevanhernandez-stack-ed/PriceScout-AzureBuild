"""
Database Migration: Add scrape_checkpoints table for crash-resilient scraping
Created: 2026-01-28
Purpose: Enable resume capability for long-running scrapes after power outages or crashes

Creates the scrape_checkpoints table that tracks:
- Which theaters have been fully scraped (showings and/or prices)
- When the scrape started and completed
- Any errors that occurred
- Counts of showings/prices saved
"""

from sqlalchemy import create_engine, text
import sys
import os
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import config

def get_db_url():
    """Get database URL from environment or use SQLite default"""
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        return db_url
    # Default SQLite path
    db_path = ROOT / 'pricescout.db'
    return f'sqlite:///{db_path}'


def create_checkpoints_table():
    """Create the scrape_checkpoints table"""

    db_url = get_db_url()
    engine = create_engine(db_url)
    is_sqlite = 'sqlite' in db_url

    print("Creating scrape_checkpoints table...")
    print(f"Database: {db_url.split('@')[-1] if '@' in db_url else db_url}\n")

    # Table creation SQL - SQLite compatible
    if is_sqlite:
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS scrape_checkpoints (
            checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES scrape_runs(run_id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
            job_id VARCHAR(100) NOT NULL,
            theater_name VARCHAR(255) NOT NULL,
            market VARCHAR(255),
            play_date DATE NOT NULL,
            phase VARCHAR(50) NOT NULL,
            status VARCHAR(50) DEFAULT 'completed',
            showings_count INTEGER DEFAULT 0,
            prices_count INTEGER DEFAULT 0,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT
        )
        """
    else:
        # PostgreSQL version
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS scrape_checkpoints (
            checkpoint_id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES scrape_runs(run_id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
            job_id VARCHAR(100) NOT NULL,
            theater_name VARCHAR(255) NOT NULL,
            market VARCHAR(255),
            play_date DATE NOT NULL,
            phase VARCHAR(50) NOT NULL,
            status VARCHAR(50) DEFAULT 'completed',
            showings_count INTEGER DEFAULT 0,
            prices_count INTEGER DEFAULT 0,
            started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP WITH TIME ZONE,
            error_message TEXT
        )
        """

    indexes_to_add = [
        ("idx_checkpoints_job", "CREATE INDEX IF NOT EXISTS idx_checkpoints_job ON scrape_checkpoints (job_id)"),
        ("idx_checkpoints_run", "CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON scrape_checkpoints (run_id)"),
        ("idx_checkpoints_theater", "CREATE INDEX IF NOT EXISTS idx_checkpoints_theater ON scrape_checkpoints (theater_name, play_date)"),
    ]

    # Unique constraint for SQLite
    if is_sqlite:
        unique_constraint = "CREATE UNIQUE INDEX IF NOT EXISTS unique_checkpoint ON scrape_checkpoints (job_id, theater_name, play_date, phase)"
    else:
        unique_constraint = """
        DO $$ BEGIN
            ALTER TABLE scrape_checkpoints
            ADD CONSTRAINT unique_checkpoint UNIQUE (job_id, theater_name, play_date, phase);
        EXCEPTION
            WHEN duplicate_table THEN NULL;
        END $$;
        """

    with engine.connect() as conn:
        # Create table
        try:
            print("Creating table: scrape_checkpoints...")
            conn.execute(text(create_table_sql))
            conn.commit()
            print("  [OK] Table created successfully")
        except Exception as e:
            print(f"  [WARN] Table creation: {str(e)}")

        # Add indexes
        for idx_name, sql in indexes_to_add:
            try:
                print(f"Creating index: {idx_name}...")
                conn.execute(text(sql))
                conn.commit()
                print(f"  [OK] {idx_name} created successfully")
            except Exception as e:
                print(f"  [WARN] {idx_name}: {str(e)}")

        # Add unique constraint
        try:
            print("Adding unique constraint: unique_checkpoint...")
            conn.execute(text(unique_constraint))
            conn.commit()
            print("  [OK] Unique constraint added successfully")
        except Exception as e:
            print(f"  [WARN] Unique constraint: {str(e)}")

    print("\n[OK] Migration complete!")
    print("\nTable added: scrape_checkpoints")
    print("  - Tracks checkpoint status for each theater during scrapes")
    print("  - Enables resume capability after crashes")
    print("  - Stores showings/prices counts and error messages")


def verify_table():
    """Verify the table exists and show its structure"""
    db_url = get_db_url()
    engine = create_engine(db_url)
    is_sqlite = 'sqlite' in db_url

    print("\nVerifying scrape_checkpoints table...")

    with engine.connect() as conn:
        if is_sqlite:
            # Check if table exists
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scrape_checkpoints'"
            ))
            tables = [row[0] for row in result]
            if 'scrape_checkpoints' in tables:
                print("  [OK] Table exists")

                # Show columns
                result = conn.execute(text("PRAGMA table_info(scrape_checkpoints)"))
                columns = [row[1] for row in result]
                print(f"  Columns: {', '.join(columns)}")

                # Show indexes
                result = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='scrape_checkpoints'"
                ))
                indexes = [row[0] for row in result]
                print(f"  Indexes: {', '.join(indexes)}")
            else:
                print("  [ERROR] Table does not exist")
        else:
            # PostgreSQL
            result = conn.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name='scrape_checkpoints'
                ORDER BY ordinal_position
            """))
            columns = [(row[0], row[1]) for row in result]
            if columns:
                print("  [OK] Table exists")
                print("  Columns:")
                for col_name, col_type in columns:
                    print(f"    - {col_name}: {col_type}")
            else:
                print("  [ERROR] Table does not exist")


if __name__ == "__main__":
    try:
        create_checkpoints_table()
        verify_table()
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
