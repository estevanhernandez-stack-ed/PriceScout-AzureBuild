from app.db_adapter import get_session, TheaterMetadata
with get_session() as s:
    theaters = s.query(TheaterMetadata).limit(10).all()
    for t in theaters:
        print(f"{t.theater_name}: {t.latitude}, {t.longitude}")
