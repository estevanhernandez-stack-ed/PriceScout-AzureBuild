#!/usr/bin/env python
"""
Baseline Scrape Script

Automates Fandango scraping for a diverse set of theaters to populate baseline prices.
Targets different circuits and premium formats (IMAX, Dolby, 4DX, etc.) to ensure
comprehensive baseline coverage.

Usage:
    python scripts/baseline_scrape.py [--theaters N] [--dry-run]

Options:
    --theaters N    Number of theaters to scrape (default: 10)
    --dry-run       Show what would be scraped without running
"""
import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_theater_cache():
    """Load theater cache and return flattened list with market info."""
    cache_path = project_root / "app" / "theater_cache.json"

    if not cache_path.exists():
        print(f"ERROR: Theater cache not found at {cache_path}")
        return []

    with open(cache_path, 'r') as f:
        cache = json.load(f)

    theaters = []
    for market_name, market_data in cache.get("markets", {}).items():
        for theater in market_data.get("theaters", []):
            theaters.append({
                "market": market_name,
                "name": theater["name"],
                "url": theater["url"],
                "company": theater.get("company", "Unknown")
            })

    return theaters


def select_diverse_sample(theaters, count=10):
    """Select a diverse sample of theaters across circuits."""

    # Group by company/circuit
    by_circuit = {}
    for t in theaters:
        circuit = t["company"]
        if circuit not in by_circuit:
            by_circuit[circuit] = []
        by_circuit[circuit].append(t)

    print(f"\nTheaters by circuit:")
    for circuit, theater_list in sorted(by_circuit.items(), key=lambda x: -len(x[1])):
        print(f"  {circuit}: {len(theater_list)} theaters")

    # Prioritize premium theaters (IMAX, Dolby indicators in name)
    premium_keywords = ['IMAX', 'Dolby', 'Dine-In', 'DINE-IN', 'XD', 'Luxe', 'Prime']
    premium_theaters = [t for t in theaters if any(kw in t["name"] for kw in premium_keywords)]
    standard_theaters = [t for t in theaters if t not in premium_theaters]

    print(f"\nPremium theaters (IMAX/Dolby/etc.): {len(premium_theaters)}")
    print(f"Standard theaters: {len(standard_theaters)}")

    # Select mix: ~40% premium, ~60% standard, spread across circuits
    premium_count = min(int(count * 0.4), len(premium_theaters))
    standard_count = count - premium_count

    selected = []

    # Select premium theaters from different circuits
    circuits_used = set()
    random.shuffle(premium_theaters)
    for t in premium_theaters:
        if len(selected) >= premium_count:
            break
        if t["company"] not in circuits_used or len(circuits_used) >= len(by_circuit):
            selected.append(t)
            circuits_used.add(t["company"])

    # Fill remaining with standard theaters from different circuits
    random.shuffle(standard_theaters)
    for t in standard_theaters:
        if len(selected) >= count:
            break
        # Prefer circuits not yet represented
        if t["company"] not in circuits_used:
            selected.append(t)
            circuits_used.add(t["company"])

    # If still need more, add any remaining
    for t in standard_theaters + premium_theaters:
        if len(selected) >= count:
            break
        if t not in selected:
            selected.append(t)

    return selected


def run_scrape(theaters, dates, dry_run=False):
    """Run scrape for selected theaters using the API."""
    import requests

    API_BASE = "http://localhost:8000/api/v1"

    # First, authenticate
    print("\n1. Authenticating...")

    # Try to get token (using demo/test credentials)
    auth_response = requests.post(
        f"{API_BASE}/auth/token",
        data={"username": "admin", "password": "admin"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    if auth_response.status_code != 200:
        print(f"   Authentication failed: {auth_response.json()}")
        print("\n   Please log in via the React app first and provide valid credentials.")
        return False

    token = auth_response.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    print("   ✓ Authenticated")

    # Prepare scrape request
    theater_requests = [{"name": t["name"], "url": t["url"]} for t in theaters]
    date_strings = [d.strftime("%Y-%m-%d") for d in dates]

    print(f"\n2. Preparing scrape request...")
    print(f"   Theaters: {len(theater_requests)}")
    print(f"   Dates: {date_strings}")

    if dry_run:
        print("\n[DRY RUN] Would scrape:")
        for t in theaters:
            print(f"   - {t['name']} ({t['company']}) in {t['market']}")
        return True

    # Trigger the scrape
    print("\n3. Triggering scrape job...")
    scrape_response = requests.post(
        f"{API_BASE}/scrapes/trigger",
        json={
            "mode": "market",
            "theaters": theater_requests,
            "dates": date_strings,
            "use_cache": False  # Force fresh scrape for baselines
        },
        headers=headers
    )

    if scrape_response.status_code not in (200, 202):
        print(f"   Scrape trigger failed: {scrape_response.json()}")
        return False

    result = scrape_response.json()
    job_id = result.get("job_id")
    print(f"   ✓ Scrape job started: {job_id}")

    # Poll for completion
    print("\n4. Monitoring scrape progress...")
    import time

    while True:
        status_response = requests.get(
            f"{API_BASE}/scrapes/{job_id}/status",
            headers=headers
        )

        if status_response.status_code != 200:
            print(f"   Status check failed: {status_response.status_code}")
            break

        status = status_response.json()
        progress = status.get("progress", 0)
        state = status.get("status", "unknown")

        print(f"   Progress: {progress}% - {state}", end="\r")

        if state in ("completed", "failed", "cancelled"):
            print()
            break

        time.sleep(5)

    if state == "completed":
        print(f"\n   ✓ Scrape completed!")
        print(f"   Results: {status.get('results_count', 0)} price records")
        return True
    else:
        print(f"\n   ✗ Scrape ended with status: {state}")
        return False


def discover_baselines():
    """Run baseline discovery on scraped Fandango data."""
    import requests

    API_BASE = "http://localhost:8000/api/v1"

    print("\n5. Discovering baselines from scraped data...")

    # Authenticate again
    auth_response = requests.post(
        f"{API_BASE}/auth/token",
        data={"username": "admin", "password": "admin"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    if auth_response.status_code != 200:
        print(f"   Authentication failed")
        return

    token = auth_response.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Call Fandango baseline discovery
    response = requests.get(
        f"{API_BASE}/price-baselines/discover?lookback_days=30",
        headers=headers
    )

    if response.status_code == 200:
        baselines = response.json()
        print(f"   ✓ Discovered {len(baselines)} potential baselines")

        # Show sample
        for b in baselines[:5]:
            print(f"     - {b.get('theater_name', 'N/A')} | {b.get('format', 'N/A')} | ${b.get('baseline_price', 0):.2f}")
    else:
        print(f"   Discovery failed: {response.status_code}")


def main():
    parser = argparse.ArgumentParser(description="Baseline Scrape Script")
    parser.add_argument("--theaters", type=int, default=10, help="Number of theaters to scrape")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be scraped")
    parser.add_argument("--days", type=int, default=3, help="Number of days to scrape (default: 3)")
    args = parser.parse_args()

    print("=" * 60)
    print("BASELINE SCRAPE SCRIPT")
    print("=" * 60)

    # Load theaters
    theaters = load_theater_cache()
    if not theaters:
        return 1

    print(f"\nLoaded {len(theaters)} theaters from cache")

    # Select diverse sample
    selected = select_diverse_sample(theaters, args.theaters)

    print(f"\nSelected {len(selected)} theaters for baseline scrape:")
    for t in selected:
        print(f"  - {t['name']} ({t['company']})")

    # Determine dates (today + next few days to capture different dayparts)
    today = date.today()
    dates = [today + timedelta(days=i) for i in range(args.days)]

    print(f"\nDates to scrape: {[d.strftime('%Y-%m-%d') for d in dates]}")

    # Run scrape
    success = run_scrape(selected, dates, dry_run=args.dry_run)

    if success and not args.dry_run:
        discover_baselines()

    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
