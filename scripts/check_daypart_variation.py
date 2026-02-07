import sys
sys.path.insert(0, r"c:\Users\estev\Desktop\theatre-operations-platform\apps\pricescout-react")
from app.db_session import get_session
from sqlalchemy import text

with get_session() as session:
    # For each Marcus theater: show Adult 2D prices by daypart
    # This reveals if twilight/late are priced differently from evening/prime within ONE theater
    result = session.execute(text(
        "SELECT theater_name, daypart, AVG(baseline_price) as avg_price, "
        "       COUNT(*) as cnt, MIN(baseline_price) as min_p, MAX(baseline_price) as max_p "
        "FROM price_baselines "
        "WHERE theater_name LIKE 'Marcus%' "
        "AND ticket_type = 'Adult' "
        "AND (format = '2D' OR format = 'Standard' OR format IS NULL) "
        "GROUP BY theater_name, daypart "
        "ORDER BY theater_name, daypart"
    ))
    rows = result.fetchall()
    
    current = ""
    for r in rows:
        tn = r[0]
        if tn != current:
            current = tn
            print(f"\n{tn}:")
        dp = r[1] if r[1] else "-"
        avg = r[2]
        cnt = r[3]
        mn = r[4]
        mx = r[5]
        spread = f"  (range: ${mn:.2f}-${mx:.2f})" if mn != mx else ""
        print(f"  {dp:<15s}  avg=${avg:.2f}  n={cnt}{spread}")

    # Same for Movie Tavern
    print("\n" + "="*80)
    result = session.execute(text(
        "SELECT theater_name, daypart, AVG(baseline_price) as avg_price, "
        "       COUNT(*) as cnt, MIN(baseline_price) as min_p, MAX(baseline_price) as max_p "
        "FROM price_baselines "
        "WHERE theater_name LIKE 'Movie Tavern%' "
        "AND (ticket_type = 'Adult' OR ticket_type = 'General Admission') "
        "AND (format = '2D' OR format = 'Standard' OR format IS NULL) "
        "GROUP BY theater_name, daypart "
        "ORDER BY theater_name, daypart"
    ))
    rows = result.fetchall()
    
    current = ""
    for r in rows:
        tn = r[0]
        if tn != current:
            current = tn
            print(f"\n{tn}:")
        dp = r[1] if r[1] else "-"
        avg = r[2]
        cnt = r[3]
        mn = r[4]
        mx = r[5]
        spread = f"  (range: ${mn:.2f}-${mx:.2f})" if mn != mx else ""
        print(f"  {dp:<15s}  avg=${avg:.2f}  n={cnt}{spread}")
