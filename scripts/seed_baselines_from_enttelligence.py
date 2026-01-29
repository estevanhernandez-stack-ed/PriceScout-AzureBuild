#!/usr/bin/env python
"""
Seed Baselines from EntTelligence Cache

Quickly populates baseline prices using existing EntTelligence cached data.
This is faster than scraping Fandango and provides good circuit-level baselines.

Usage:
    python scripts/seed_baselines_from_enttelligence.py [--circuit CIRCUIT]
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
os.chdir(project_root)  # Change to project root for relative imports


def main():
    parser = argparse.ArgumentParser(description="Seed baselines from EntTelligence cache")
    parser.add_argument("--circuit", help="Limit to specific circuit (e.g., 'AMC Entertainment Inc')")
    parser.add_argument("--lookback-days", type=int, default=30, help="Days to analyze (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Show analysis without saving")
    args = parser.parse_args()

    print("=" * 60)
    print("SEED BASELINES FROM ENTTELLIGENCE")
    print("=" * 60)

    # Import after path setup
    from app.enttelligence_baseline_discovery import (
        EntTelligenceBaselineDiscoveryService,
        refresh_enttelligence_baselines
    )
    from app.db_session import get_session
    from app.db_models import PriceBaseline

    # Check current baselines
    with get_session() as session:
        current_count = session.query(PriceBaseline).count()
        print(f"\nCurrent baselines in database: {current_count}")

    # Create service and analyze
    service = EntTelligenceBaselineDiscoveryService(company_id=1)

    print(f"\n1. Analyzing EntTelligence cache (last {args.lookback_days} days)...")

    # Get available circuits first
    analysis = service.analyze_by_circuit(lookback_days=args.lookback_days)

    circuits = analysis.get('circuits', {})
    print(f"\n   Circuits with data ({len(circuits)} total):")
    for circuit_name, circuit_data in list(circuits.items())[:10]:
        print(f"     - {circuit_name}: {circuit_data.get('theater_count', 0)} theaters, {circuit_data.get('record_count', 0)} records")

    print(f"\n   Overall stats:")
    stats = analysis.get('overall_stats', {})
    print(f"     Total records: {stats.get('total_records', 0)}")
    avg_price = stats.get('overall_avg_price', 0) or 0
    print(f"     Avg price: ${avg_price:.2f}")

    formats = analysis.get('format_breakdown', {})
    print(f"\n   Format breakdown ({len(formats)} formats):")
    for fmt_name, fmt_data in list(formats.items())[:8]:
        avg = fmt_data.get('avg_price', 0) or 0
        print(f"     - {fmt_name}: {fmt_data.get('count', 0)} records, avg ${avg:.2f}")

    # Discover baselines
    print(f"\n2. Discovering baseline prices...")

    baselines = service.discover_baselines(
        lookback_days=args.lookback_days
    )

    # Filter by circuit if specified
    if args.circuit:
        baselines = [b for b in baselines if args.circuit.lower() in (b.get('circuit_name', '') or '').lower()]

    print(f"   Found {len(baselines)} potential baselines")

    # Show sample
    print(f"\n   Sample discovered baselines:")
    for b in baselines[:10]:
        theater = b.get('theater_name', 'N/A')[:40]
        fmt = b.get('format', 'N/A')[:15]
        price = b.get('baseline_price', 0)
        samples = b.get('sample_count', 0)
        print(f"     - {theater:40} | {fmt:15} | ${price:.2f} | {samples} samples")

    if args.dry_run:
        print(f"\n[DRY RUN] Would save {len(baselines)} baselines (excluding premium formats)")
        return 0

    # Save baselines
    print(f"\n3. Saving baselines to database...")

    # Use the service directly to save with overwrite control
    saved_count = service.save_discovered_baselines(
        baselines=baselines,
        overwrite=False  # Don't overwrite existing
    )

    print(f"   [OK] Saved {saved_count} new baselines")

    # Final count
    with get_session() as session:
        final_count = session.query(PriceBaseline).count()
        print(f"\n   Total baselines now: {final_count}")

    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
