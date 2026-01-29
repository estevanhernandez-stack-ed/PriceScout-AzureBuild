"""
Migration: Add PLF screen count columns to theater_amenities table

Adds:
- imax_screen_count: Number of IMAX screens (e.g., 2)
- dolby_screen_count: Number of Dolby Cinema screens
- plf_other_count: Number of other PLF screens (RPX, 4DX, etc.)
- circuit_plf_info: JSON with circuit-branded PLF (e.g., Marcus SuperScreen)
"""
import sqlite3
from datetime import datetime


def migrate(db_path: str = "pricescout.db"):
    """Add PLF screen count columns to theater_amenities table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Adding PLF screen count columns to theater_amenities...")

    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='theater_amenities'")
        if not cursor.fetchone():
            print("  theater_amenities table does not exist, skipping")
            return

        # Check existing columns
        cursor.execute("PRAGMA table_info(theater_amenities)")
        columns = [col[1] for col in cursor.fetchall()]

        # Add imax_screen_count
        if 'imax_screen_count' in columns:
            print("  imax_screen_count column already exists")
        else:
            cursor.execute("""
                ALTER TABLE theater_amenities
                ADD COLUMN imax_screen_count INTEGER
            """)
            print("  Added imax_screen_count column")

        # Add dolby_screen_count
        if 'dolby_screen_count' in columns:
            print("  dolby_screen_count column already exists")
        else:
            cursor.execute("""
                ALTER TABLE theater_amenities
                ADD COLUMN dolby_screen_count INTEGER
            """)
            print("  Added dolby_screen_count column")

        # Add plf_other_count
        if 'plf_other_count' in columns:
            print("  plf_other_count column already exists")
        else:
            cursor.execute("""
                ALTER TABLE theater_amenities
                ADD COLUMN plf_other_count INTEGER
            """)
            print("  Added plf_other_count column")

        # Add circuit_plf_info (JSON as text)
        if 'circuit_plf_info' in columns:
            print("  circuit_plf_info column already exists")
        else:
            cursor.execute("""
                ALTER TABLE theater_amenities
                ADD COLUMN circuit_plf_info TEXT
            """)
            print("  Added circuit_plf_info column")

        conn.commit()
        print("Migration completed successfully!")

        # Show summary
        cursor.execute("SELECT COUNT(*) FROM theater_amenities")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM theater_amenities WHERE has_imax = 1")
        with_imax = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM theater_amenities WHERE has_dolby_cinema = 1")
        with_dolby = cursor.fetchone()[0]

        print(f"\nSummary:")
        print(f"  Total theater amenities records: {total}")
        print(f"  Theaters with IMAX: {with_imax}")
        print(f"  Theaters with Dolby Cinema: {with_dolby}")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
