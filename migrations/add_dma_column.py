"""
Migration: Add DMA column to theater_metadata table

This separates:
- market: Marcus-specific market names (admin-editable)
- dma: EntTelligence DMA/Designated Market Area (system-defined)
"""
import sqlite3
from datetime import datetime

def migrate(db_path: str = "pricescout.db"):
    """Add dma column to theater_metadata table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Adding DMA column to theater_metadata...")

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(theater_metadata)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'dma' in columns:
            print("  DMA column already exists, skipping creation")
        else:
            # Add the dma column
            cursor.execute("""
                ALTER TABLE theater_metadata
                ADD COLUMN dma VARCHAR(100)
            """)
            print("  Added dma column")

            # Create index for dma queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_theater_dma ON theater_metadata (company_id, dma)
            """)
            print("  Created index on dma column")

        # Copy EntTelligence DMA values from market to dma for non-Marcus markets
        # Marcus markets have zip codes or "Area" in their names
        cursor.execute("""
            UPDATE theater_metadata
            SET dma = market
            WHERE market IS NOT NULL
            AND market NOT LIKE '%Area%'
            AND market NOT LIKE '% 5%'
            AND market NOT LIKE '% 6%'
            AND market NOT LIKE '% 7%'
            AND market NOT LIKE '% 4%'
            AND market NOT LIKE '% 3%'
            AND dma IS NULL
        """)
        dma_copied = cursor.rowcount
        print(f"  Copied {dma_copied} DMA values from market column")

        # Clear market for non-Marcus theaters (where we just copied to dma)
        # This leaves market only for Marcus-specific markets
        cursor.execute("""
            UPDATE theater_metadata
            SET market = NULL
            WHERE dma IS NOT NULL
            AND market = dma
        """)
        market_cleared = cursor.rowcount
        print(f"  Cleared {market_cleared} duplicate market values (now in dma)")

        conn.commit()
        print("Migration completed successfully!")

        # Show summary
        cursor.execute("SELECT COUNT(*) FROM theater_metadata WHERE market IS NOT NULL")
        with_market = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM theater_metadata WHERE dma IS NOT NULL")
        with_dma = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM theater_metadata")
        total = cursor.fetchone()[0]

        print(f"\nSummary:")
        print(f"  Total theaters: {total}")
        print(f"  With Marcus market: {with_market}")
        print(f"  With EntTelligence DMA: {with_dma}")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
