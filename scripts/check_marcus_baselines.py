import sys
sys.path.insert(0, r"c:\Users\estev\Desktop\theatre-operations-platform\apps\pricescout-react")
from app.db_session import get_session
from sqlalchemy import text

with get_session() as session:
    # Get all Marcus baselines grouped to understand the spread
    result = session.execute(text(
        "SELECT theater_name, ticket_type, format, daypart, baseline_price, "
        "       day_type, day_of_week, effective_from, effective_to "
        "FROM price_baselines "
        "WHERE theater_name LIKE '%Marcus%' OR theater_name LIKE '%Movie Tavern%' "
        "ORDER BY theater_name, ticket_type, daypart, baseline_price"
    ))
    rows = result.fetchall()
    print(f"Marcus/Movie Tavern baselines: {len(rows)}")
    
    current = ""
    for r in rows:
        tn = r[0]
        if tn != current:
            current = tn
            print(f"\n  {tn}:")
        tt = r[1]
        fm = r[2] if r[2] else "Standard"
        dp = r[3] if r[3] else "-"
        price = r[4]
        dt = r[5] if r[5] else "-"
        dow = r[6] if r[6] else "-"
        ef = r[7] if r[7] else ""
        et = r[8] if r[8] else ""
        print(f"    {tt:<25s} | {fm:<18s} | {dp:<12s} | ${price:<8.2f} | day_type={dt:<10s} | dow={dow}")

    # Also show distinct Adult daypart prices for a single Marcus theater
    print("\n" + "="*80)
    print("Single theater example - first Marcus theater found:")
    result = session.execute(text(
        "SELECT theater_name, ticket_type, format, daypart, baseline_price "
        "FROM price_baselines "
        "WHERE theater_name LIKE 'Marcus%' "
        "AND ticket_type = 'Adult' "
        "ORDER BY theater_name LIMIT 1"
    ))
    first = result.fetchone()
    if first:
        tn = first[0]
        print(f"  Theater: {tn}")
        result2 = session.execute(text(
            "SELECT ticket_type, format, daypart, baseline_price "
            "FROM price_baselines "
            "WHERE theater_name = :tn AND ticket_type = 'Adult' "
            "ORDER BY daypart, baseline_price"
        ), {"tn": tn})
        for r in result2.fetchall():
            dp = r[2] if r[2] else "-"
            print(f"    Adult | {(r[1] or 'Standard'):<18s} | {dp:<12s} | ${r[3]:.2f}")
