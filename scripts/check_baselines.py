import sys
sys.path.insert(0, r"c:\Users\estev\Desktop\theatre-operations-platform\apps\pricescout-react")
from app.db_session import get_session
from sqlalchemy import text

with get_session() as session:
    result = session.execute(text(
        "SELECT theater_name, ticket_type, format, daypart, baseline_price, sample_count "
        "FROM price_baselines ORDER BY theater_name, ticket_type, format, daypart"
    ))
    rows = result.fetchall()
    print(f"Total baselines: {len(rows)}")
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
