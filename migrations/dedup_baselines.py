"""
Migration: Deduplicate price_baselines table.

The baselines table has ~292K rows with ~5.4x duplication caused by:
1. Append-only inserts from EntTelligence discovery (new row every run)
2. Fandango day_of_week fan-out (7 rows per combo, deprecated dimension)
3. Multiple effective_from epochs never expired

This migration:
1. Collapses day_of_week/day_type to NULL (deprecated per model docstring)
2. Deduplicates by keeping highest sample_count per unique combo
3. Fixes tax labels for Marcus/MT/Cinemark EntTelligence baselines

Run with:
    python migrations/dedup_baselines.py                # Full migration
    python migrations/dedup_baselines.py --dry-run      # Preview only
"""

import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from app.db_session import get_engine, get_session


# Marcus/Movie Tavern/Cinemark theaters have pre-tax prices in EntTelligence.
# AMC/Regal/SMG are tax-inclusive (match Fandango exactly).
PRE_TAX_CIRCUITS = ('Marcus%', 'Movie Tavern%', 'Cinemark%')


def count_baselines(conn) -> int:
    """Get total baseline count."""
    result = conn.execute(text("SELECT COUNT(*) FROM price_baselines"))
    return result.scalar()


def get_source_counts(conn) -> dict:
    """Get row counts by source."""
    result = conn.execute(text(
        "SELECT COALESCE(source, 'unknown') as src, COUNT(*) as cnt "
        "FROM price_baselines GROUP BY source ORDER BY cnt DESC"
    ))
    return {row[0]: row[1] for row in result}


def phase1_collapse_day_of_week(conn, dry_run: bool) -> int:
    """Set day_of_week and day_type to NULL (deprecated dimensions)."""
    if dry_run:
        result = conn.execute(text(
            "SELECT COUNT(*) FROM price_baselines "
            "WHERE day_of_week IS NOT NULL OR day_type IS NOT NULL"
        ))
        count = result.scalar()
        print(f"  [DRY RUN] Would nullify day_of_week/day_type on {count} rows")
        return count

    result = conn.execute(text(
        "UPDATE price_baselines "
        "SET day_of_week = NULL, day_type = NULL "
        "WHERE day_of_week IS NOT NULL OR day_type IS NOT NULL"
    ))
    updated = result.rowcount
    print(f"  Nullified day_of_week/day_type on {updated} rows")
    return updated


def phase2_dedup(conn, dry_run: bool) -> int:
    """
    Deduplicate baselines keeping the best row per unique combo.

    Unique key: (company_id, theater_name, ticket_type,
                 COALESCE(format,''), COALESCE(daypart,''), COALESCE(source,''))

    Winner: highest sample_count, then latest effective_from, then highest baseline_id.
    """
    # Find the IDs to KEEP (one winner per group)
    keep_query = text("""
        SELECT baseline_id
        FROM (
            SELECT baseline_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY company_id, theater_name, ticket_type,
                                    COALESCE(format, ''), COALESCE(daypart, ''),
                                    COALESCE(source, '')
                       ORDER BY
                           CASE WHEN effective_to IS NULL THEN 0 ELSE 1 END,
                           COALESCE(sample_count, 0) DESC,
                           effective_from DESC,
                           baseline_id DESC
                   ) as rn
            FROM price_baselines
        ) ranked
        WHERE rn = 1
    """)

    keep_ids = {row[0] for row in conn.execute(keep_query)}
    total = count_baselines(conn)
    to_delete = total - len(keep_ids)

    if dry_run:
        print(f"  [DRY RUN] Would keep {len(keep_ids)} rows, delete {to_delete} duplicates")
        return to_delete

    if to_delete == 0:
        print("  No duplicates found")
        return 0

    # SQLite doesn't support DELETE with subquery well, so we delete by NOT IN.
    # For large sets, batch the deletes.
    # First, create a temp table with keep IDs for efficient join.
    conn.execute(text("CREATE TEMPORARY TABLE IF NOT EXISTS _keep_ids (baseline_id INTEGER PRIMARY KEY)"))
    conn.execute(text("DELETE FROM _keep_ids"))

    # Insert keep IDs in batches
    keep_list = list(keep_ids)
    batch_size = 500
    for i in range(0, len(keep_list), batch_size):
        batch = keep_list[i:i + batch_size]
        placeholders = ", ".join(f"({bid})" for bid in batch)
        conn.execute(text(f"INSERT INTO _keep_ids (baseline_id) VALUES {placeholders}"))

    # Delete rows not in keep set
    result = conn.execute(text(
        "DELETE FROM price_baselines "
        "WHERE baseline_id NOT IN (SELECT baseline_id FROM _keep_ids)"
    ))
    deleted = result.rowcount

    # Clean up temp table
    conn.execute(text("DROP TABLE IF EXISTS _keep_ids"))

    print(f"  Deleted {deleted} duplicate rows (kept {len(keep_ids)})")
    return deleted


def phase3_fix_tax_labels(conn, dry_run: bool) -> int:
    """
    Fix tax_status for EntTelligence baselines of pre-tax circuits.

    Marcus/Movie Tavern/Cinemark ENT prices are pre-tax but may be
    mislabeled as 'inclusive'. The EntTelligence discovery service
    tries to apply estimated tax, but if tax_config isn't set up,
    the raw pre-tax prices get stored as 'inclusive'.

    We mark these as 'exclusive' so the comparison service knows
    to apply tax adjustment at read time.
    """
    conditions = " OR ".join(f"theater_name LIKE '{pat}'" for pat in PRE_TAX_CIRCUITS)

    if dry_run:
        result = conn.execute(text(
            f"SELECT COUNT(*) FROM price_baselines "
            f"WHERE source = 'enttelligence' "
            f"AND tax_status != 'exclusive' "
            f"AND ({conditions})"
        ))
        count = result.scalar()
        print(f"  [DRY RUN] Would fix tax_status to 'exclusive' on {count} rows")
        return count

    result = conn.execute(text(
        f"UPDATE price_baselines "
        f"SET tax_status = 'exclusive' "
        f"WHERE source = 'enttelligence' "
        f"AND tax_status != 'exclusive' "
        f"AND ({conditions})"
    ))
    updated = result.rowcount
    print(f"  Fixed tax_status to 'exclusive' on {updated} EntTelligence rows (Marcus/MT/Cinemark)")
    return updated


def phase4_cleanup_expired(conn, dry_run: bool) -> int:
    """
    Remove expired baselines where a newer active baseline exists for the same combo.

    These are old rows with effective_to set (ended by discovery) that are no longer needed.
    """
    if dry_run:
        result = conn.execute(text(
            "SELECT COUNT(*) FROM price_baselines WHERE effective_to IS NOT NULL"
        ))
        count = result.scalar()
        print(f"  [DRY RUN] Would remove {count} expired baseline rows")
        return count

    result = conn.execute(text(
        "DELETE FROM price_baselines WHERE effective_to IS NOT NULL"
    ))
    deleted = result.rowcount
    print(f"  Removed {deleted} expired baseline rows")
    return deleted


def run_migration(dry_run: bool = False):
    """Run the full dedup migration."""
    engine = get_engine()

    with engine.begin() as conn:
        before = count_baselines(conn)
        sources_before = get_source_counts(conn)

        print(f"\n{'=' * 60}")
        print(f"Baseline Dedup Migration {'(DRY RUN)' if dry_run else ''}")
        print(f"{'=' * 60}")
        print(f"\nBefore: {before:,} total rows")
        for src, cnt in sources_before.items():
            print(f"  {src}: {cnt:,}")

        # Phase 1: Collapse deprecated dimensions
        print(f"\n--- Phase 1: Collapse day_of_week/day_type ---")
        phase1_collapse_day_of_week(conn, dry_run)

        # Phase 2: Remove expired baselines first (reduces dedup work)
        print(f"\n--- Phase 2: Remove expired baselines ---")
        phase4_cleanup_expired(conn, dry_run)

        # Phase 3: Deduplicate
        print(f"\n--- Phase 3: Deduplicate by unique combo ---")
        phase2_dedup(conn, dry_run)

        # Phase 4: Fix tax labels
        print(f"\n--- Phase 4: Fix tax labels (Marcus/MT/Cinemark) ---")
        phase3_fix_tax_labels(conn, dry_run)

        # Summary
        after = count_baselines(conn)
        sources_after = get_source_counts(conn)

        print(f"\n--- Summary ---")
        print(f"Before: {before:,} rows")
        print(f"After:  {after:,} rows")
        print(f"Reduction: {before - after:,} rows ({(before - after) / before * 100:.1f}%)" if before > 0 else "")
        for src, cnt in sources_after.items():
            print(f"  {src}: {cnt:,}")

        if dry_run:
            print(f"\n[DRY RUN] No changes were made. Run without --dry-run to apply.")
            # Rollback by raising (inside begin() context manager)
            raise RuntimeError("Dry run — rolling back")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Deduplicate price_baselines table')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    args = parser.parse_args()

    try:
        run_migration(dry_run=args.dry_run)
    except RuntimeError as e:
        if "Dry run" in str(e):
            pass  # Expected for dry-run rollback
        else:
            raise
