#!/usr/bin/env python
"""
Market-by-Market Baseline Scrape

Systematically scrapes one theater per market to build comprehensive baseline data.
This captures ticket types (Adult, Child, Senior), formats (IMAX, Dolby), and dayparts.

Usage:
    python scripts/scrape_markets_for_baselines.py [--markets N] [--dry-run]

Options:
    --markets N     Number of markets to scrape (default: all)
    --dry-run       Show what would be scraped without running
    --circuit NAME  Filter to specific circuit (e.g., "Marcus")
"""
import argparse
import json
import sys
import time
import requests
from pathlib import Path
from datetime import date, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_markets_from_cache():
    """Load all markets and their theaters from cache."""
    cache_path = project_root / "app" / "theater_cache.json"

    if not cache_path.exists():
        print(f"ERROR: Theater cache not found at {cache_path}")
        return {}

    with open(cache_path, 'r') as f:
        cache = json.load(f)

    return cache.get("markets", {})


def select_representative_theater(theaters):
    """
    Select the best theater to represent a market.
    Prioritizes premium theaters (IMAX, Dolby) to capture more formats.
    """
    premium_keywords = ['IMAX', 'Dolby', 'DINE-IN', 'Dine-In', 'XD', 'Luxe', 'Prime', 'CineBistro']

    # First, look for premium theaters
    for theater in theaters:
        name = theater.get("name", "")
        if any(kw in name for kw in premium_keywords):
            return theater

    # Otherwise, pick the first one (usually the main theater)
    return theaters[0] if theaters else None


def get_auth_token(api_base):
    """Get authentication token from the API."""
    # Try common credentials
    credentials = [
        ("admin", "admin"),
        ("admin", "admin123"),
    ]

    for username, password in credentials:
        response = requests.post(
            f"{api_base}/auth/token",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if response.status_code == 200:
            return response.json().get("access_token")

    return None


def scrape_market(theater, dates, headers, api_base, dry_run=False):
    """Scrape a single theater for baseline data."""
    theater_request = {"name": theater["name"], "url": theater["url"]}
    date_strings = [d.strftime("%Y-%m-%d") for d in dates]

    if dry_run:
        return {"status": "dry_run", "theater": theater["name"]}

    # Trigger scrape
    response = requests.post(
        f"{api_base}/scrapes/trigger",
        json={
            "mode": "market",
            "theaters": [theater_request],
            "dates": date_strings,
            "use_cache": False  # Force fresh scrape
        },
        headers=headers
    )

    if response.status_code not in (200, 202):
        return {"status": "failed", "theater": theater["name"], "error": response.text}

    result = response.json()
    job_id = result.get("job_id")

    # Wait for completion (with timeout)
    max_wait = 120  # 2 minutes per theater
    start = time.time()

    while time.time() - start < max_wait:
        status_response = requests.get(
            f"{api_base}/scrapes/{job_id}/status",
            headers=headers
        )

        if status_response.status_code != 200:
            break

        status = status_response.json()
        state = status.get("status", "unknown")

        if state == "completed":
            return {
                "status": "completed",
                "theater": theater["name"],
                "results": status.get("results_count", 0)
            }
        elif state in ("failed", "cancelled"):
            return {
                "status": state,
                "theater": theater["name"],
                "error": status.get("error", "Unknown error")
            }

        time.sleep(5)

    return {"status": "timeout", "theater": theater["name"]}


def main():
    parser = argparse.ArgumentParser(description="Market-by-Market Baseline Scrape")
    parser.add_argument("--markets", type=int, help="Number of markets to scrape (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be scraped")
    parser.add_argument("--circuit", help="Filter to specific circuit")
    parser.add_argument("--days", type=int, default=2, help="Days to scrape (default: 2)")
    args = parser.parse_args()

    print("=" * 60)
    print("MARKET-BY-MARKET BASELINE SCRAPE")
    print("=" * 60)

    # Load markets
    markets = load_markets_from_cache()
    if not markets:
        return 1

    print(f"\nLoaded {len(markets)} markets from cache")

    # Build scrape plan
    scrape_plan = []
    for market_name, market_data in markets.items():
        theaters = market_data.get("theaters", [])
        if not theaters:
            continue

        # Filter by circuit if specified
        if args.circuit:
            theaters = [t for t in theaters if args.circuit.lower() in t.get("company", "").lower()]
            if not theaters:
                continue

        # Select representative theater
        theater = select_representative_theater(theaters)
        if theater:
            scrape_plan.append({
                "market": market_name,
                "theater": theater,
                "circuit": theater.get("company", "Unknown")
            })

    # Limit markets if specified
    if args.markets:
        scrape_plan = scrape_plan[:args.markets]

    print(f"\nScrape plan: {len(scrape_plan)} markets")

    # Show circuit breakdown
    circuits = {}
    for item in scrape_plan:
        circuit = item["circuit"]
        circuits[circuit] = circuits.get(circuit, 0) + 1

    print("\nCircuit breakdown:")
    for circuit, count in sorted(circuits.items(), key=lambda x: -x[1])[:10]:
        print(f"  {circuit}: {count} markets")

    # Show sample
    print("\nSample theaters to scrape:")
    for item in scrape_plan[:10]:
        print(f"  - {item['market']}: {item['theater']['name']} ({item['circuit']})")

    if args.dry_run:
        print(f"\n[DRY RUN] Would scrape {len(scrape_plan)} theaters")
        return 0

    # Authenticate
    api_base = "http://localhost:8000/api/v1"
    print("\nAuthenticating...")

    token = get_auth_token(api_base)
    if not token:
        print("ERROR: Could not authenticate. Please check credentials.")
        return 1

    headers = {"Authorization": f"Bearer {token}"}
    print("  [OK] Authenticated")

    # Determine dates
    today = date.today()
    dates = [today + timedelta(days=i) for i in range(args.days)]
    print(f"\nDates: {[d.strftime('%Y-%m-%d') for d in dates]}")

    # Execute scrapes
    print(f"\nStarting scrapes...")
    results = {"completed": 0, "failed": 0, "timeout": 0}

    for i, item in enumerate(scrape_plan, 1):
        print(f"\n[{i}/{len(scrape_plan)}] {item['market']}: {item['theater']['name']}...", end=" ", flush=True)

        result = scrape_market(item["theater"], dates, headers, api_base)
        status = result.get("status", "unknown")

        if status == "completed":
            print(f"OK ({result.get('results', 0)} records)")
            results["completed"] += 1
        elif status == "failed":
            print(f"FAILED: {result.get('error', 'Unknown')[:50]}")
            results["failed"] += 1
        elif status == "timeout":
            print("TIMEOUT")
            results["timeout"] += 1
        else:
            print(f"UNKNOWN: {status}")

    # Summary
    print("\n" + "=" * 60)
    print("SCRAPE SUMMARY")
    print("=" * 60)
    print(f"  Completed: {results['completed']}")
    print(f"  Failed:    {results['failed']}")
    print(f"  Timeout:   {results['timeout']}")

    # Discover baselines from new data
    if results["completed"] > 0:
        print("\nDiscovering baselines from scraped data...")
        response = requests.get(
            f"{api_base}/price-baselines/discover?lookback_days=7",
            headers=headers
        )
        if response.status_code == 200:
            baselines = response.json()
            print(f"  Found {len(baselines.get('baselines', []))} potential baselines")

    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
