"""
Showings management: upserting showtime data from scrapes.
"""

from sqlalchemy import and_
from app.db_session import get_session
from app.db_models import Showing
from app.simplified_baseline_service import normalize_daypart, normalize_format
from app import config


def upsert_showings(all_showings, play_date, company_id: int = None, enrich_films: bool = True):
    """Insert or update showings in database.

    Args:
        all_showings: Dict of {theater_name: [showing_data, ...]}
        play_date: Date for the showings
        company_id: Company ID (defaults to config or 1)
        enrich_films: If True, automatically enrich new films with OMDB metadata
    """
    import datetime

    if isinstance(play_date, str):
        play_date = datetime.datetime.strptime(play_date, '%Y-%m-%d').date()
    elif isinstance(play_date, datetime.datetime):
        play_date = play_date.date()

    if not all_showings:
        print(f"  [DB] [WARN] No showings to upsert")
        return

    unique_film_titles = set()

    try:
        with get_session() as session:
            if company_id is None:
                company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
            if not company_id:
                company_id = 1

            showing_count = 0
            for theater_name, showings in all_showings.items():
                print(f"  [DB] Processing {len(showings)} showings for {theater_name}")
                for showing_data in showings:
                    if 'film_title' in showing_data:
                        unique_film_titles.add(showing_data['film_title'])
                    showing_data.pop('play_date', None)

                    norm_fmt = normalize_format(showing_data['format']) or showing_data['format']
                    existing = session.query(Showing).filter(
                        and_(
                            Showing.company_id == company_id,
                            Showing.play_date == play_date,
                            Showing.theater_name == theater_name,
                            Showing.film_title == showing_data['film_title'],
                            Showing.showtime == showing_data['showtime'],
                            Showing.format == norm_fmt
                        )
                    ).first()

                    if not existing:
                        showing = Showing(
                            company_id=company_id,
                            play_date=play_date,
                            theater_name=theater_name,
                            film_title=showing_data['film_title'],
                            showtime=showing_data['showtime'],
                            format=normalize_format(showing_data['format']) or showing_data['format'],
                            daypart=normalize_daypart(showing_data['daypart']) or showing_data['daypart'],
                            is_plf=showing_data.get('is_plf', False),
                            ticket_url=showing_data.get('ticket_url')
                        )
                        session.add(showing)
                        showing_count += 1

            try:
                session.flush()
                print(f"  [DB] Upserted {showing_count} showings for {play_date.strftime('%Y-%m-%d')}.")
            except Exception as e:
                print(f"  [DB] [WARN] Some showings may already exist: {e}")
                session.rollback()
                for theater_name, showings in all_showings.items():
                    for showing_data in showings:
                        showing_data.pop('play_date', None)
                        try:
                            existing = session.query(Showing).filter(
                                and_(
                                    Showing.company_id == company_id,
                                    Showing.play_date == play_date,
                                    Showing.theater_name == theater_name,
                                    Showing.film_title == showing_data['film_title'],
                                    Showing.showtime == showing_data['showtime'],
                                    Showing.format == (normalize_format(showing_data['format']) or showing_data['format'])
                                )
                            ).first()
                            if not existing:
                                showing = Showing(
                                    company_id=company_id,
                                    play_date=play_date,
                                    theater_name=theater_name,
                                    film_title=showing_data['film_title'],
                                    showtime=showing_data['showtime'],
                                    format=normalize_format(showing_data['format']) or showing_data['format'],
                                    daypart=normalize_daypart(showing_data['daypart']) or showing_data['daypart'],
                                    is_plf=showing_data.get('is_plf', False),
                                    ticket_url=showing_data.get('ticket_url')
                                )
                                session.add(showing)
                                session.commit()
                        except Exception:
                            session.rollback()
                print(f"  [DB] Finished upserting showings for {play_date.strftime('%Y-%m-%d')} (some may have been skipped as duplicates).")

        # Auto-enrich new films with OMDB metadata
        if enrich_films and unique_film_titles:
            try:
                from app.db.film_enrichment import enrich_new_films
                enrich_result = enrich_new_films(list(unique_film_titles), async_mode=True)
                if enrich_result.get('pending', 0) > 0:
                    print(f"  [DB] Queued {enrich_result['pending']} films for background enrichment")
            except Exception as enrich_err:
                print(f"  [DB] [WARN] Film enrichment failed (non-fatal): {enrich_err}")

    except Exception as e:
        print(f"  [DB] [ERROR] Failed to upsert showings: {e}")
        import traceback
        traceback.print_exc()
        raise
