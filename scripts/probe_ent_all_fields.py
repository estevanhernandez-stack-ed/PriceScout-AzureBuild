"""
EntTelligence Field Discovery Script
Calls every API endpoint with minimal data and dumps all available field names,
types, and sample values. Used to audit what data EntTelligence provides vs
what PriceScout currently extracts.
"""

import os
import sys
import json
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

from enttelligence_client import EntTelligenceClient


def print_fields(label: str, records: list):
    """Print all field names, types, and sample values from a list of records."""
    print(f"\n{'='*80}")
    print(f"  {label}")
    print(f"{'='*80}")

    if not records:
        print("  (no records returned)")
        return

    print(f"  Records returned: {len(records)}")
    sample = records[0]

    # Collect all unique keys across first few records (in case schema varies)
    all_keys = set()
    for r in records[:10]:
        all_keys.update(r.keys())

    print(f"  Total unique fields: {len(all_keys)}")
    print(f"\n  {'Field Name':<35} {'Type':<15} {'Sample Value'}")
    print(f"  {'-'*35} {'-'*15} {'-'*50}")

    for key in sorted(all_keys):
        val = sample.get(key)
        val_type = type(val).__name__
        # Truncate long values
        val_str = str(val)
        if len(val_str) > 60:
            val_str = val_str[:57] + "..."
        print(f"  {key:<35} {val_type:<15} {val_str}")

    # Also dump full first record as JSON for reference
    print(f"\n  --- Full sample record (JSON) ---")
    print(f"  {json.dumps(sample, indent=4, default=str)}")


def main():
    TOKEN_NAME = os.getenv("ENTTELLIGENCE_TOKEN_NAME", "PriceScoutAzure")
    TOKEN_SECRET = os.getenv("ENTTELLIGENCE_TOKEN_SECRET", "")

    if not TOKEN_SECRET:
        print("[ERR] ENTTELLIGENCE_TOKEN_SECRET not set. Set it as an environment variable.")
        return

    client = EntTelligenceClient()

    print("Authenticating...")
    if not client.login(TOKEN_NAME, TOKEN_SECRET):
        print("[ERR] Authentication failed")
        return

    # Use a recent date (yesterday) to maximize data availability
    probe_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    # Use a title likely in wide release - pick something current
    probe_title = "Captain America: Brave New World"
    fallback_title = "Wicked"

    print(f"\nProbe date: {probe_date}")
    print(f"Probe title: {probe_title} (fallback: {fallback_title})")

    # ----------------------------------------------------------------
    # 1. Programming Audit (our primary data source)
    # ----------------------------------------------------------------
    print("\n[1/7] Calling get_programming_audit...")
    audit = client.get_programming_audit(start_date=probe_date, end_date=probe_date)
    print_fields("PROGRAMMING AUDIT (programAuditSummaryByRange)", audit)

    # ----------------------------------------------------------------
    # 2. Showtimes by title
    # ----------------------------------------------------------------
    print("\n[2/7] Calling get_showtimes_by_title...")
    showtimes = client.get_showtimes_by_title(probe_title, probe_date)
    if not showtimes:
        print(f"  No results for '{probe_title}', trying fallback...")
        showtimes = client.get_showtimes_by_title(fallback_title, probe_date)
    print_fields("SHOWTIMES BY TITLE (presales-showtime-movie_title)", showtimes)

    # ----------------------------------------------------------------
    # 3. Theater analysis
    # ----------------------------------------------------------------
    print("\n[3/7] Calling get_theater_analysis...")
    theater_analysis = client.get_theater_analysis(probe_title)
    if not theater_analysis:
        theater_analysis = client.get_theater_analysis(fallback_title)
    print_fields("THEATER ANALYSIS (title-analysis-theater)", theater_analysis)

    # ----------------------------------------------------------------
    # 4. Circuit analysis
    # ----------------------------------------------------------------
    print("\n[4/7] Calling get_circuit_analysis...")
    circuit_analysis = client.get_circuit_analysis(probe_title)
    if not circuit_analysis:
        circuit_analysis = client.get_circuit_analysis(fallback_title)
    print_fields("CIRCUIT ANALYSIS (title-analysis-circuit)", circuit_analysis)

    # ----------------------------------------------------------------
    # 5. Market analysis
    # ----------------------------------------------------------------
    print("\n[5/7] Calling get_market_analysis...")
    market_analysis = client.get_market_analysis(probe_title)
    if not market_analysis:
        market_analysis = client.get_market_analysis(fallback_title)
    print_fields("MARKET ANALYSIS (title-analysis-market)", market_analysis)

    # ----------------------------------------------------------------
    # 6. Movie metadata
    # ----------------------------------------------------------------
    print("\n[6/7] Calling get_movies...")
    movies = client.get_movies(titles=[probe_title, fallback_title])
    print_fields("MOVIE METADATA (titlesWithFilter)", movies)

    # ----------------------------------------------------------------
    # 7. Theater metadata
    # ----------------------------------------------------------------
    print("\n[7/7] Calling get_theaters...")
    theaters = client.get_theaters(theater_names=["Marcus Ridge Cinema", "AMC Mayfair Mall 18"])
    print_fields("THEATER METADATA (theatresWithFilter)", theaters)

    # ----------------------------------------------------------------
    # Summary: fields we extract vs fields available
    # ----------------------------------------------------------------
    print(f"\n{'='*80}")
    print("  EXTRACTION GAP ANALYSIS")
    print(f"{'='*80}")

    currently_extracted = {
        'theater_name', 'title', 'date_sh', 'show_date', 'show_time', 'time_sh',
        'circuit_name', 'price_per_general', 'film_format', 'dma'
    }

    if audit:
        audit_keys = set(audit[0].keys())
        not_extracted = audit_keys - currently_extracted
        print(f"\n  Programming Audit fields we EXTRACT: {len(currently_extracted & audit_keys)}")
        print(f"  Programming Audit fields we IGNORE:  {len(not_extracted)}")
        if not_extracted:
            print(f"\n  IGNORED FIELDS (potential data we're missing):")
            for key in sorted(not_extracted):
                val = audit[0].get(key)
                print(f"    - {key}: {type(val).__name__} = {str(val)[:60]}")
    else:
        print("\n  (No audit data to compare)")

    print(f"\n{'='*80}")
    print("  DONE")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
