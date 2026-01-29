from app.db_adapter import get_session, Showing
with get_session() as session:
    theaters = session.query(Showing.theater_name).distinct().all()
    for t in theaters:
        print(t[0])
