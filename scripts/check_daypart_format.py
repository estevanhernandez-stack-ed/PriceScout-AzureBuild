import sys
sys.path.insert(0, r"c:\Users\estev\Desktop\theatre-operations-platform\apps\pricescout-react")
from app.db_session import get_session
from sqlalchemy import text

with get_session() as session:
    # Distinct dayparts
    result = session.execute(text("SELECT DISTINCT daypart, COUNT(*) FROM price_baselines GROUP BY daypart ORDER BY daypart"))
    rows = result.fetchall()
    print("Distinct dayparts:")
    for r in rows:
        print(f"  '{r[0]}' : {r[1]} baselines")

    print()

    # Distinct formats
    result = session.execute(text("SELECT DISTINCT format, COUNT(*) FROM price_baselines GROUP BY format ORDER BY format"))
    rows = result.fetchall()
    print("Distinct formats:")
    for r in rows:
        print(f"  '{r[0]}' : {r[1]} baselines")

    print()

    # Check which discovery source created which baselines
    result = session.execute(text("SELECT DISTINCT source FROM price_baselines"))
    print("Baseline sources:", [r[0] for r in result.fetchall()])

    # Check Movie Tavern baselines specifically
    result = session.execute(text(
        "SELECT theater_name, ticket_type, format, daypart, baseline_price "
        "FROM price_baselines "
        "WHERE theater_name LIKE '%Movie Tavern%' "
        "ORDER BY theater_name, ticket_type, format, daypart"
    ))
    rows = result.fetchall()
    print(f"\nMovie Tavern baselines ({len(rows)}):")
    current = ""
    for r in rows:
        if r[0] != current:
            current = r[0]
            print(f"\n  {r[0]}:")
        print(f"    {r[1]:<30s} | {(r[2] or 'Standard'):<20s} | {(r[3] or '-'):<15s} | ${r[4]:.2f}")
