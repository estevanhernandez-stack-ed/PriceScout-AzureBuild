import sys
import os

# Add project root to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)
sys.path.insert(0, project_dir)

from app import config
from app.db_session import get_session
from sqlalchemy import text

with get_session() as session:
    # Check AMC baselines that have day_of_week info for Tues (2) and Wed (3)
    result = session.execute(text(
        "SELECT theater_name, ticket_type, format, daypart, baseline_price, day_type, day_of_week "
        "FROM price_baselines "
        "WHERE theater_name LIKE 'AMC%' "
        "AND day_of_week IN ('2', '3', 'Tuesday', 'Wednesday') "
        "ORDER BY theater_name, day_of_week, ticket_type "
        "LIMIT 100"
    ))
    rows = result.fetchall()
    print(f"AMC Tue/Wed baselines: {len(rows)}")
    for r in rows:
        print(f"  {r[0]:<35s} | {r[1]:<15s} | {(r[2] or 'Std'):<10s} | {(r[3] or '-'):<10s} | ${r[4]:.2f} | {r[5] or '-'} | dow={r[6]}")

    # Also check what day_of_week values exist in baselines
    print("\n" + "="*80)
    result = session.execute(text(
        "SELECT DISTINCT day_of_week, COUNT(*) FROM price_baselines GROUP BY day_of_week ORDER BY day_of_week"
    ))
    rows = result.fetchall()
    print("Distinct day_of_week values:")
    for r in rows:
        print(f"  '{r[0]}': {r[1]} baselines")

    # Check what day_type values exist
    print()
    result = session.execute(text(
        "SELECT DISTINCT day_type, COUNT(*) FROM price_baselines GROUP BY day_type ORDER BY day_type"
    ))
    rows = result.fetchall()
    print("Distinct day_type values:")
    for r in rows:
        print(f"  '{r[0]}': {r[1]} baselines")

    # Check the EntTelligence cache directly for AMC prices on a Tuesday
    # 2026-02-03 is a Monday, 2026-02-04 is Tuesday
    print("\n" + "="*80)
    print("EntTelligence cache - AMC prices on Tuesday 2026-02-04:")
    try:
        import sqlite3
        db_path = config.DB_FILE or os.path.join(config.PROJECT_DIR, 'pricescout.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT theater_name, circuit_name, ticket_type, price, format, showtime "
            "FROM enttelligence_price_cache "
            "WHERE play_date = '2026-02-04' "
            "AND circuit_name = 'AMC Entertainment Inc' "
            "AND ticket_type = 'Adult' "
            "ORDER BY theater_name, showtime "
            "LIMIT 50"
        )
        rows = cursor.fetchall()
        print(f"AMC Adult prices on Tue 2026-02-04: {len(rows)} records")
        for r in rows:
            print(f"  {r[0]:<40s} | {r[2]:<8s} | ${r[3]:.2f} | {r[4] or 'Std':<10s} | {r[5]}")
        
        # Compare with a non-discount day (Wednesday for AMC is also discount, try Thursday)
        # 2026-02-05 is Wednesday, 2026-02-06 is Thursday
        print("\nAMC Adult prices on Thu 2026-02-06 (same theaters):")
        cursor.execute(
            "SELECT theater_name, ticket_type, price, format, showtime "
            "FROM enttelligence_price_cache "
            "WHERE play_date = '2026-02-05' "
            "AND circuit_name = 'AMC Entertainment Inc' "
            "AND ticket_type = 'Adult' "
            "ORDER BY theater_name, showtime "
            "LIMIT 50"
        )
        rows2 = cursor.fetchall()
        print(f"AMC Adult prices on Wed 2026-02-05: {len(rows2)} records")
        for r in rows2:
            print(f"  {r[0]:<40s} | {r[1]:<8s} | ${r[2]:.2f} | {r[3] or 'Std':<10s} | {r[4]}")
        conn.close()
    except Exception as e:
        print(f"Cache query error: {e}")
