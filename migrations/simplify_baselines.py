"""
Migration script to simplify the baseline system.

This migration:
1. Adds new columns to price_baselines (source, tax_status, sample_count, last_discovery_at)
2. Adds versioning columns to company_profiles (version, previous_profile_id, is_current)
3. Creates new tables (discount_day_programs, company_profile_gaps, theater_onboarding_status)
4. Migrates granular baselines (with day_of_week) to simplified form (aggregate across days)
5. Extracts discount days from baselines into discount_day_programs

Run with:
    python migrations/simplify_baselines.py                    # Apply schema changes only
    python migrations/simplify_baselines.py --migrate-data     # Also migrate baseline data
    python migrations/simplify_baselines.py --dry-run          # Preview data migration without changes
"""
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, UTC
from decimal import Decimal
from collections import defaultdict

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from app.db_session import get_engine, get_session
from app.db_models import (
    Base, PriceBaseline, CompanyProfile,
    DiscountDayProgram, CompanyProfileGap, TheaterOnboardingStatus
)


def add_column_if_not_exists(conn, table_name: str, column_name: str, column_type: str, default: str = None):
    """Add a column to a table if it doesn't already exist."""
    inspector = inspect(conn)
    columns = [c['name'] for c in inspector.get_columns(table_name)]

    if column_name not in columns:
        default_clause = f" DEFAULT {default}" if default else ""
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}{default_clause}"
        conn.execute(text(sql))
        print(f"  + Added column: {table_name}.{column_name}")
        return True
    else:
        print(f"  - Column exists: {table_name}.{column_name}")
        return False


def migrate_schema():
    """Apply schema changes (new columns and tables)."""
    print("\n=== Phase 1: Schema Migration ===\n")
    engine = get_engine()
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    with engine.begin() as conn:
        # 1. Add new columns to price_baselines
        print("Updating price_baselines table...")
        add_column_if_not_exists(conn, 'price_baselines', 'source', "VARCHAR(50)", "'unknown'")
        add_column_if_not_exists(conn, 'price_baselines', 'tax_status', "VARCHAR(20)", "'unknown'")
        add_column_if_not_exists(conn, 'price_baselines', 'sample_count', "INTEGER", None)
        add_column_if_not_exists(conn, 'price_baselines', 'last_discovery_at', "TIMESTAMP", None)
        add_column_if_not_exists(conn, 'price_baselines', 'migrated_from_granular', "BOOLEAN", "0")

        # 2. Add versioning columns to company_profiles
        print("\nUpdating company_profiles table...")
        add_column_if_not_exists(conn, 'company_profiles', 'version', "INTEGER", "1")
        add_column_if_not_exists(conn, 'company_profiles', 'previous_profile_id', "INTEGER", None)
        add_column_if_not_exists(conn, 'company_profiles', 'is_current', "BOOLEAN", "1")

    # 3. Create new tables
    print("\nCreating new tables...")
    tables_to_create = []

    if 'discount_day_programs' not in existing_tables:
        tables_to_create.append(DiscountDayProgram.__table__)
        print("  + Prepared: discount_day_programs")
    else:
        print("  - Exists: discount_day_programs")

    if 'company_profile_gaps' not in existing_tables:
        tables_to_create.append(CompanyProfileGap.__table__)
        print("  + Prepared: company_profile_gaps")
    else:
        print("  - Exists: company_profile_gaps")

    if 'theater_onboarding_status' not in existing_tables:
        tables_to_create.append(TheaterOnboardingStatus.__table__)
        print("  + Prepared: theater_onboarding_status")
    else:
        print("  - Exists: theater_onboarding_status")

    if tables_to_create:
        Base.metadata.create_all(engine, tables=tables_to_create)
        print(f"\nCreated {len(tables_to_create)} new table(s).")

    print("\nSchema migration complete.")


def analyze_baselines(session: Session):
    """Analyze existing baselines to understand the migration scope."""
    print("\n=== Baseline Analysis ===\n")

    # Count total baselines
    total = session.query(PriceBaseline).count()
    print(f"Total baselines: {total:,}")

    # Count baselines with day_of_week set
    granular = session.query(PriceBaseline).filter(PriceBaseline.day_of_week.isnot(None)).count()
    print(f"Granular baselines (with day_of_week): {granular:,}")

    # Count unique combinations without day_of_week
    from sqlalchemy import func
    unique_combos = session.query(
        func.count(func.distinct(
            PriceBaseline.company_id.concat('-').concat(
                PriceBaseline.theater_name).concat('-').concat(
                PriceBaseline.ticket_type).concat('-').concat(
                func.coalesce(PriceBaseline.format, '')).concat('-').concat(
                func.coalesce(PriceBaseline.daypart, ''))
        ))
    ).scalar() or 0
    print(f"Unique (theater, ticket, format, daypart) combinations: {unique_combos:,}")

    # Estimate reduction
    if granular > 0:
        reduction_pct = ((granular - unique_combos) / granular) * 100
        print(f"Estimated reduction: {reduction_pct:.1f}%")
        print(f"Expected simplified baselines: ~{unique_combos:,}")

    return {
        'total': total,
        'granular': granular,
        'unique_combos': unique_combos
    }


def detect_discount_days(prices_by_day: dict, min_variance_threshold: float = 0.03,
                         min_below_avg_threshold: float = 0.15) -> list:
    """
    Detect discount days from price data grouped by day of week.

    A day is considered a discount day if:
    - Price variance for that day is <= 3% (consistent flat pricing)
    - Price is >= 15% below the overall average

    Returns list of detected discount day info.
    """
    if not prices_by_day:
        return []

    # Calculate overall average (excluding potential discount days first pass)
    all_prices = []
    for day_prices in prices_by_day.values():
        all_prices.extend(day_prices)

    if not all_prices:
        return []

    overall_avg = sum(all_prices) / len(all_prices)

    discount_days = []
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    for day_num, day_prices in prices_by_day.items():
        if len(day_prices) < 3:  # Need minimum samples
            continue

        day_avg = sum(day_prices) / len(day_prices)
        day_min = min(day_prices)
        day_max = max(day_prices)

        # Calculate variance as percentage
        if day_avg > 0:
            variance_pct = (day_max - day_min) / day_avg
        else:
            variance_pct = 0

        # Calculate how much below average
        below_avg_pct = (overall_avg - day_avg) / overall_avg if overall_avg > 0 else 0

        # Check if this is a discount day
        if variance_pct <= min_variance_threshold and below_avg_pct >= min_below_avg_threshold:
            # Generate program name
            price_str = f"${day_avg:.0f}" if day_avg == int(day_avg) else f"${day_avg:.2f}"
            program_name = f"{price_str} {days_of_week[day_num]}s"

            discount_days.append({
                'day_of_week': day_num,
                'day_name': days_of_week[day_num],
                'price': float(day_avg),
                'program_name': program_name,
                'sample_count': len(day_prices),
                'variance_pct': float(variance_pct),
                'below_avg_pct': float(below_avg_pct)
            })

    return discount_days


def migrate_baselines_data(session: Session, dry_run: bool = True):
    """
    Migrate granular baselines to simplified form.

    For each (theater, ticket_type, format, daypart) combination:
    1. Group all day_of_week baselines
    2. Detect discount days (significantly lower, flat pricing)
    3. Calculate weighted average of NON-discount days as the baseline
    4. Create DiscountDayProgram entries for detected discount days
    5. Create single simplified baseline
    """
    print(f"\n=== {'DRY RUN: ' if dry_run else ''}Baseline Data Migration ===\n")

    # Get all granular baselines grouped by theater/ticket/format/daypart
    granular_baselines = session.query(PriceBaseline).filter(
        PriceBaseline.day_of_week.isnot(None)
    ).order_by(
        PriceBaseline.company_id,
        PriceBaseline.theater_name,
        PriceBaseline.ticket_type,
        PriceBaseline.format,
        PriceBaseline.daypart
    ).all()

    if not granular_baselines:
        print("No granular baselines found to migrate.")
        return {'simplified': 0, 'discount_programs': 0}

    # Group baselines
    groups = defaultdict(list)
    for baseline in granular_baselines:
        key = (
            baseline.company_id,
            baseline.theater_name,
            baseline.ticket_type,
            baseline.format or '',
            baseline.daypart or ''
        )
        groups[key].append(baseline)

    print(f"Found {len(granular_baselines):,} granular baselines in {len(groups):,} groups")

    # Track circuit discount days to avoid duplicates
    circuit_discount_days = defaultdict(set)  # (company_id, circuit) -> set of day_of_week

    simplified_count = 0
    discount_program_count = 0

    for key, baselines in groups.items():
        company_id, theater_name, ticket_type, format_type, daypart = key

        # Get circuit name from theater name
        circuit_name = None
        known_circuits = ['Marcus', 'Movie Tavern', 'AMC', 'Regal', 'Cinemark', 'B&B', 'LOOK']
        for circuit in known_circuits:
            if theater_name.lower().startswith(circuit.lower()):
                circuit_name = circuit
                break

        # Group prices by day of week
        prices_by_day = defaultdict(list)
        for b in baselines:
            if b.day_of_week is not None:
                prices_by_day[b.day_of_week].append(float(b.baseline_price))

        # Detect discount days
        discount_days = detect_discount_days(prices_by_day)
        discount_day_nums = {dd['day_of_week'] for dd in discount_days}

        # Calculate simplified baseline from non-discount days
        non_discount_prices = []
        non_discount_samples = 0
        for b in baselines:
            if b.day_of_week not in discount_day_nums:
                non_discount_prices.append(float(b.baseline_price))
                non_discount_samples += 1

        if non_discount_prices:
            simplified_price = sum(non_discount_prices) / len(non_discount_prices)
        elif prices_by_day:
            # Fallback to overall average if all days are discount days
            all_prices = [float(b.baseline_price) for b in baselines]
            simplified_price = sum(all_prices) / len(all_prices)
        else:
            continue

        # Get effective dates from existing baselines
        effective_from = min(b.effective_from for b in baselines if b.effective_from)
        effective_to = None  # Still active

        if not dry_run:
            # Create simplified baseline
            simplified = PriceBaseline(
                company_id=company_id,
                theater_name=theater_name,
                ticket_type=ticket_type,
                format=format_type or None,
                daypart=daypart or None,
                day_of_week=None,  # Simplified - no day_of_week
                day_type=None,
                baseline_price=Decimal(str(round(simplified_price, 2))),
                effective_from=effective_from,
                effective_to=effective_to,
                source='enttelligence',  # Assuming EntTelligence source
                tax_status='exclusive',  # EntTelligence is tax-exclusive
                sample_count=len(baselines),
                last_discovery_at=datetime.now(UTC),
                migrated_from_granular=True
            )
            session.add(simplified)

        simplified_count += 1

        # Create discount day programs (circuit-level, not per-theater)
        if circuit_name and discount_days:
            for dd in discount_days:
                dd_key = (company_id, circuit_name, dd['day_of_week'])
                if dd_key not in circuit_discount_days:
                    circuit_discount_days[dd_key] = set()

                # Only create if we haven't seen this circuit/day combo
                if dd['day_of_week'] not in circuit_discount_days[(company_id, circuit_name)]:
                    if not dry_run:
                        program = DiscountDayProgram(
                            company_id=company_id,
                            circuit_name=circuit_name,
                            program_name=dd['program_name'],
                            day_of_week=dd['day_of_week'],
                            discount_type='flat_price',
                            discount_value=Decimal(str(round(dd['price'], 2))),
                            applicable_ticket_types=None,  # Applies to all
                            applicable_formats=None,  # Applies to all
                            applicable_dayparts=None,  # Applies to all
                            is_active=True,
                            discovered_at=datetime.now(UTC),
                            confidence_score=Decimal('0.80'),  # High confidence from migration
                            sample_count=dd['sample_count'],
                            source='migration'
                        )
                        session.add(program)

                    circuit_discount_days[(company_id, circuit_name)].add(dd['day_of_week'])
                    discount_program_count += 1

    if not dry_run:
        session.commit()
        print(f"\nCreated {simplified_count:,} simplified baselines")
        print(f"Created {discount_program_count:,} discount day programs")
    else:
        print(f"\n[DRY RUN] Would create {simplified_count:,} simplified baselines")
        print(f"[DRY RUN] Would create {discount_program_count:,} discount day programs")

    return {
        'simplified': simplified_count,
        'discount_programs': discount_program_count
    }


def migrate():
    """Main migration entry point."""
    parser = argparse.ArgumentParser(description='Simplify baseline system migration')
    parser.add_argument('--migrate-data', action='store_true',
                        help='Migrate baseline data (not just schema)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview data migration without making changes')
    args = parser.parse_args()

    print("=" * 60)
    print("BASELINE SIMPLIFICATION MIGRATION")
    print("=" * 60)

    # Phase 1: Schema migration (always runs)
    migrate_schema()

    # Analyze current state
    with get_session() as session:
        stats = analyze_baselines(session)

    # Phase 2: Data migration (optional)
    if args.migrate_data or args.dry_run:
        with get_session() as session:
            results = migrate_baselines_data(session, dry_run=args.dry_run)
    else:
        print("\n[INFO] Run with --migrate-data to migrate baseline data")
        print("[INFO] Run with --dry-run to preview data migration")

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    migrate()
