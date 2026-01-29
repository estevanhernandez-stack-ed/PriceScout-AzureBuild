from app.db_adapter import get_session, Showing
with get_session() as s:
    count = s.query(Showing.theater_name).distinct().count()
    print(f"Distinct theater names in Showing: {count}")
    names = [r[0] for r in s.query(Showing.theater_name).distinct().all()]
    print(f"Sample names: {names[:5]}")
