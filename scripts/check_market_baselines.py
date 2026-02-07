import sys
sys.path.insert(0, r"c:\Users\estev\Desktop\theatre-operations-platform\apps\pricescout-react")
from app.db_session import get_session
from sqlalchemy import text

with get_session() as session:
    # First: what are ALL distinct ticket_type values?
    result = session.execute(text(
        "SELECT DISTINCT ticket_type FROM price_baselines ORDER BY ticket_type"
    ))
    types = [r[0] for r in result.fetchall()]
    print(f"All distinct ticket types ({len(types)}):")
    for t in types:
        print(f"  {t}")

    print("\n" + "="*80)

    # Now get baselines for theaters that appear to be Movie Tavern, AMC, LOOK, or Regal
    # (matching the screenshot)
    result = session.execute(text(
        "SELECT theater_name, ticket_type, format, daypart, baseline_price, sample_count "
        "FROM price_baselines "
        "WHERE theater_name LIKE '%Movie Tavern%' "
        "   OR theater_name LIKE '%AMC%' "
        "   OR theater_name LIKE '%LOOK%' "
        "   OR theater_name LIKE '%Regal%' "
        "ORDER BY theater_name, ticket_type, format, daypart "
        "LIMIT 500"
    ))
    rows = result.fetchall()
    print(f"\nBaselines for Movie Tavern/AMC/LOOK/Regal: {len(rows)}")
    current_theater = ""
    for r in rows:
        tn = r[0]
        tt = r[1]
        fm = r[2] if r[2] else "Standard"
        dp = r[3] if r[3] else "-"
        price = r[4]
        n = r[5]
        if tn != current_theater:
            current_theater = tn
            print(f"\n  {tn}:")
        print(f"    {tt:<30s} | {fm:<20s} | {dp:<15s} | ${price:.2f}  n={n}")

    print("\n" + "="*80)

    # Summary: distinct ticket_type per circuit pattern
    for pattern in ['Movie Tavern%', 'AMC%', 'LOOK%', 'Regal%']:
        result = session.execute(text(
            f"SELECT DISTINCT ticket_type FROM price_baselines WHERE theater_name LIKE '{pattern}' ORDER BY ticket_type"
        ))
        types = [r[0] for r in result.fetchall()]
        print(f"\n{pattern} ticket types: {types}")
