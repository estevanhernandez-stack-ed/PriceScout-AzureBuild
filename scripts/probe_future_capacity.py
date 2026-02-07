"""
Quick probe: Does EntTelligence return capacity/available/blocked for FUTURE dates?
Fetches a single future day and checks how many records have capacity data.
"""
import sys, os
from datetime import date, timedelta

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

from enttelligence_client import EntTelligenceClient

def main():
    client = EntTelligenceClient(
        base_url=os.getenv('ENTTELLIGENCE_BASE_URL', 'http://23.20.236.151:7582')
    )
    token_name = os.getenv('ENTTELLIGENCE_TOKEN_NAME', 'PriceScoutAzure')
    token_secret = os.getenv('ENTTELLIGENCE_TOKEN_SECRET', '')

    if not token_secret:
        print("ERROR: ENTTELLIGENCE_TOKEN_SECRET not set")
        return

    if not client.login(token_name, token_secret):
        print("ERROR: Failed to authenticate")
        return

    # Probe today, tomorrow, and further out
    for offset in [0, 1, 3, 7]:
        target = date.today() + timedelta(days=offset)
        target_str = target.isoformat()
        print(f"\n--- Probing {target_str} (today + {offset} days) ---")

        showtimes = client.get_programming_audit(target_str, target_str)
        print(f"  Total records: {len(showtimes):,}")

        if not showtimes:
            print("  No data returned")
            continue

        # Check capacity fields
        with_capacity = sum(1 for s in showtimes if s.get('capacity') and s.get('capacity') > 0)
        with_available = sum(1 for s in showtimes if s.get('available') is not None)
        with_blocked = sum(1 for s in showtimes if s.get('blocked') is not None)
        with_release = sum(1 for s in showtimes if s.get('release_date'))

        print(f"  With capacity > 0:  {with_capacity:,}")
        print(f"  With available:     {with_available:,}")
        print(f"  With blocked:       {with_blocked:,}")
        print(f"  With release_date:  {with_release:,}")

        # Show a sample record with capacity
        sample = next((s for s in showtimes if s.get('capacity') and s.get('capacity') > 0), None)
        if sample:
            cap = sample.get('capacity', 0)
            avail = sample.get('available', 0)
            blocked = sample.get('blocked', 0)
            sold = cap - avail - blocked
            print(f"\n  Sample record:")
            print(f"    Theater:  {sample.get('theater_name')}")
            print(f"    Film:     {sample.get('title')}")
            print(f"    Time:     {sample.get('show_time')}")
            print(f"    Format:   {sample.get('film_format')}")
            print(f"    Capacity: {cap}")
            print(f"    Available:{avail}")
            print(f"    Blocked:  {blocked}")
            print(f"    Sold:     {sold}  (capacity - available - blocked)")
            print(f"    Price:    ${sample.get('price_per_general', 0)}")
            print(f"    Release:  {sample.get('release_date')}")
        else:
            # Show first record's raw fields
            first = showtimes[0]
            print(f"\n  No records with capacity > 0. First record fields:")
            for k in sorted(first.keys()):
                print(f"    {k}: {first[k]}")

        # Deeper analysis of capacity/available/blocked relationship
        if with_capacity > 0:
            sold_count = 0
            blocked_eq_cap_minus_avail = 0
            avail_lt_cap = 0
            unique_combos = set()

            for s in showtimes:
                cap = s.get('capacity', 0) or 0
                avail = s.get('available', 0) or 0
                blocked = s.get('blocked', 0) or 0
                if cap <= 0:
                    continue
                sold = cap - avail - blocked
                if sold > 0:
                    sold_count += 1
                if blocked == (cap - avail):
                    blocked_eq_cap_minus_avail += 1
                if avail < cap:
                    avail_lt_cap += 1
                unique_combos.add((cap, avail, blocked))

            print(f"\n  Records with tickets_sold > 0:          {sold_count:,} / {with_capacity:,}")
            print(f"  Records where blocked == cap - avail:    {blocked_eq_cap_minus_avail:,} / {with_capacity:,}")
            print(f"  Records where available < capacity:      {avail_lt_cap:,} / {with_capacity:,}")
            print(f"  Unique (cap, avail, blocked) combos:     {len(unique_combos):,}")

            # Show some diverse examples
            print(f"\n  Sample (cap, avail, blocked) values:")
            for combo in sorted(unique_combos, key=lambda c: c[0], reverse=True)[:15]:
                cap, avail, blocked = combo
                sold = cap - avail - blocked
                print(f"    cap={cap:4d} avail={avail:4d} blocked={blocked:4d} -> sold={sold}")

            # Are there records where available < capacity but sold is still 0?
            # This would mean blocked is absorbing everything
            absorbed = sum(1 for s in showtimes
                         if (s.get('capacity', 0) or 0) > 0
                         and (s.get('available', 0) or 0) < (s.get('capacity', 0) or 0)
                         and (s.get('capacity', 0) or 0) - (s.get('available', 0) or 0) - (s.get('blocked', 0) or 0) == 0)
            print(f"\n  Records where avail < cap but sold=0 (blocked absorbs all): {absorbed:,}")

            # Maybe sold = capacity - available (ignore blocked)
            alt_sold = sum(1 for s in showtimes
                         if (s.get('capacity', 0) or 0) > 0
                         and (s.get('capacity', 0) or 0) - (s.get('available', 0) or 0) > 0)
            print(f"  Records where cap - avail > 0 (alt formula): {alt_sold:,}")

if __name__ == "__main__":
    main()
