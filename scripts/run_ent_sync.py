"""
Standalone EntTelligence sync script.
Runs the cache sync directly without going through the API server.
Use this when the API is busy with a long scrape.

Usage:
    python scripts/run_ent_sync.py
    python scripts/run_ent_sync.py --days 14
"""
import sys
import os
import argparse
from datetime import date, timedelta

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from api.services.enttelligence_cache_service import EntTelligenceCacheService


def main():
    parser = argparse.ArgumentParser(description="Run EntTelligence cache sync")
    parser.add_argument("--days", type=int, default=7, help="Number of days ahead to sync (default: 7)")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD, default: today)")
    args = parser.parse_args()

    start = date.fromisoformat(args.start) if args.start else date.today()

    print(f"[EntSync] Syncing {args.days + 1} days starting {start.isoformat()}", flush=True)
    print(f"[EntSync] This calls EntTelligence API directly — does NOT use the PriceScout API server.", flush=True)
    print(flush=True)

    cache_service = EntTelligenceCacheService()

    # Show current cache stats
    stats = cache_service.get_cache_stats(company_id=1)
    print(f"[EntSync] Cache before: {stats['total_entries']:,} total, {stats['fresh_entries']:,} fresh", flush=True)
    print(f"[EntSync] Last fetch: {stats.get('last_fetch', 'never')}", flush=True)
    print(flush=True)

    total_fetched = 0
    total_cached = 0

    # Sync day-by-day for reliable performance
    for offset in range(args.days + 1):
        target = start + timedelta(days=offset)
        target_str = target.isoformat()
        print(f"[EntSync] Syncing {target_str}...", flush=True)
        result = cache_service.sync_prices_for_dates(
            company_id=1,
            start_date=target_str,
            end_date=target_str
        )
        fetched = result.get('records_fetched', 0)
        cached = result.get('records_cached', 0)
        total_fetched += fetched
        total_cached += cached
        print(f"  -> {fetched:,} showtimes, {cached:,} prices cached", flush=True)

    print(flush=True)
    print(f"[EntSync] Done! {args.days + 1} days synced.", flush=True)
    print(f"  Total showtimes fetched: {total_fetched:,}", flush=True)
    print(f"  Total prices cached: {total_cached:,}", flush=True)

    # Show updated stats
    stats_after = cache_service.get_cache_stats(company_id=1)
    print(f"  Cache after: {stats_after['total_entries']:,} total, {stats_after['fresh_entries']:,} fresh", flush=True)


if __name__ == "__main__":
    main()
