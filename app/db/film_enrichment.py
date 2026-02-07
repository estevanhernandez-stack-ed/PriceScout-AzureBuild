"""
Film enrichment: OMDb integration, Fandango fallback, backfill operations.
"""

from sqlalchemy import and_, or_
from app.db_session import get_session
from app.db_models import Film, Showing, IgnoredFilm
from app.db.utils import run_async_safe
from app.db.films import upsert_film_details, add_unmatched_film, log_unmatched_film
from app import config
from thefuzz import fuzz


def backfill_film_details_from_fandango_single(title: str) -> int:
    """
    Backfill film details for a single film title using OMDb with Fandango fallback.
    Returns 1 if updated, 0 otherwise.
    """
    company_id = getattr(config, 'CURRENT_COMPANY_ID', None) or 1
    result = _enrich_films_sync([title], company_id)
    return result.get('enriched', 0)


def enrich_new_films(film_titles: list, async_mode: bool = False) -> dict:
    """
    Automatically enrich films with OMDb/Fandango metadata.

    Args:
        film_titles: List of film titles to potentially enrich
        async_mode: If True, run enrichment in background (non-blocking)

    Returns:
        dict with counts: enriched, failed, skipped
    """
    if not film_titles:
        return {'enriched': 0, 'failed': 0, 'skipped': 0}

    company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
    if not company_id:
        print("  [ENRICH] No company ID set, skipping enrichment")
        return {'enriched': 0, 'failed': 0, 'skipped': len(film_titles)}

    unique_titles = list(set(film_titles))

    with get_session() as session:
        complete = session.query(Film.film_title).filter(
            and_(
                Film.company_id == company_id,
                Film.film_title.in_(unique_titles),
                Film.runtime.isnot(None),
                Film.runtime != 'N/A'
            )
        ).all()
        complete_titles = {row[0] for row in complete}

        ignored = session.query(IgnoredFilm.film_title).filter(
            and_(
                IgnoredFilm.company_id == company_id,
                IgnoredFilm.film_title.in_(unique_titles)
            )
        ).all()
        ignored_titles = {row[0] for row in ignored}

    titles_to_enrich = [t for t in unique_titles if t not in complete_titles and t not in ignored_titles]

    if not titles_to_enrich:
        return {'enriched': 0, 'failed': 0, 'skipped': len(unique_titles)}

    print(f"  [ENRICH] Found {len(titles_to_enrich)} films that need detail enrichment/updates")

    if async_mode:
        import threading
        thread = threading.Thread(target=_enrich_films_sync, args=(titles_to_enrich, company_id))
        thread.start()
        return {'enriched': 0, 'failed': 0, 'skipped': len(complete_titles) + len(ignored_titles), 'pending': len(titles_to_enrich)}
    else:
        return _enrich_films_sync(titles_to_enrich, company_id)


def _enrich_films_sync(film_titles: list, company_id: int) -> dict:
    """Synchronously enrich films with OMDb data and Fandango fallback."""
    enriched = 0
    failed = 0

    try:
        from app.omdb_client import OMDbClient
        omdb = OMDbClient()
    except Exception as e:
        print(f"  [ENRICH] Could not initialize OMDB client: {e}")
        return {'enriched': 0, 'failed': len(film_titles), 'skipped': 0}

    from app.scraper import Scraper
    scraper = Scraper()

    for title in film_titles:
        film_data = None
        try:
            from app.utils import clean_film_title
            cleaned_title = clean_film_title(title)

            print(f"  [ENRICH] Trying OMDb for '{title}'...")
            film_data = omdb.get_film_details(cleaned_title)

            needs_fallback = not film_data or not film_data.get('runtime') or film_data.get('runtime') == 'N/A'

            if needs_fallback:
                print(f"  [ENRICH] OMDb results insufficient for '{title}'. Attempting Fandango fallback...")
                try:
                    search_results = run_async_safe(scraper.search_fandango_for_film_url(cleaned_title))
                    if search_results:
                        best_match = None
                        for res in search_results:
                            if fuzz.ratio(title.lower(), res['title'].lower()) > 85:
                                best_match = res
                                break

                        if not best_match:
                            best_match = search_results[0]

                        print(f"  [ENRICH] Scrapping Fandango details from: {best_match['url']}")
                        fandango_data = run_async_safe(scraper.get_film_details_from_fandango_url(best_match['url']))

                        if fandango_data:
                            if not film_data:
                                film_data = fandango_data
                            else:
                                for key, value in fandango_data.items():
                                    if not film_data.get(key) or film_data[key] in [None, 'N/A']:
                                        film_data[key] = value
                except Exception as ex:
                    print(f"  [ENRICH] Fandango fallback failed for '{title}': {ex}")

            if film_data:
                film_data['film_title'] = title
                upsert_film_details(film_data, company_id=company_id)
                print(f"  [ENRICH] Successfully enriched: {title}")
                enriched += 1
            else:
                log_unmatched_film(title, company_id=company_id)
                print(f"  [ENRICH] Failed to find any data for: {title}")
                failed += 1

        except Exception as e:
            print(f"  [ENRICH] Unexpected error enriching '{title}': {e}")
            try:
                log_unmatched_film(title, company_id=company_id)
            except Exception:
                pass
            failed += 1

    print(f"  [ENRICH] Batch Complete: {enriched} enriched, {failed} failed")
    return {'enriched': enriched, 'failed': failed, 'skipped': 0}


def backfill_film_details_from_fandango() -> int:
    """
    Backfill film details from OMDB for films missing complete metadata.
    Returns number of films updated.
    """
    from app.omdb_client import OMDbClient

    count = 0

    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        if not company_id:
            company_ids = session.query(Showing.company_id).distinct().all()
            company_ids = [c[0] for c in company_ids if c[0]]
        else:
            company_ids = [company_id]

        if not company_ids:
            return 0

        try:
            omdb = OMDbClient()
        except ValueError:
            return 0

        for cid in company_ids:
            original_company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
            config.CURRENT_COMPANY_ID = cid

            try:
                showing_films = session.query(Showing.film_title).filter(
                    Showing.company_id == cid
                ).distinct().all()
                showing_titles = {r[0] for r in showing_films}

                existing_films = session.query(Film.film_title).filter(
                    and_(
                        Film.company_id == cid,
                        or_(
                            Film.runtime.is_(None),
                            Film.runtime == '',
                            Film.runtime == 'N/A',
                            Film.mpaa_rating.is_(None),
                            Film.mpaa_rating == '',
                            Film.mpaa_rating == 'N/A'
                        )
                    )
                ).all()
                films_needing_update = {r[0] for r in existing_films}

                all_film_titles = session.query(Film.film_title).filter(
                    Film.company_id == cid
                ).all()
                existing_titles = {r[0] for r in all_film_titles}
                missing_titles = showing_titles - existing_titles

                titles_to_fetch = missing_titles | films_needing_update

                for title in titles_to_fetch:
                    try:
                        film_details = omdb.get_film_details(title)
                        if film_details and film_details.get('runtime'):
                            film_details['film_title'] = title
                            upsert_film_details(film_details)
                            count += 1
                        else:
                            add_unmatched_film(title)
                    except Exception as e:
                        print(f"Error fetching details for '{title}': {e}")
                        add_unmatched_film(title)
                        continue
            finally:
                config.CURRENT_COMPANY_ID = original_company_id

    return count


def backfill_imdb_ids_from_fandango() -> int:
    """
    Backfill IMDB IDs for films that don't have them.
    Returns number of films updated.
    """
    from app.omdb_client import OMDbClient

    count = 0

    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        if not company_id:
            company_ids = session.query(Film.company_id).distinct().all()
            company_ids = [c[0] for c in company_ids if c[0]]
        else:
            company_ids = [company_id]

        if not company_ids:
            return 0

        try:
            omdb = OMDbClient()
        except ValueError:
            return 0

        for cid in company_ids:
            original_company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
            config.CURRENT_COMPANY_ID = cid

            try:
                films_without_ids = session.query(Film.film_title).filter(
                    and_(
                        Film.company_id == cid,
                        or_(
                            Film.imdb_id.is_(None),
                            Film.imdb_id == '',
                            Film.imdb_id == 'N/A'
                        )
                    )
                ).all()

                for (title,) in films_without_ids:
                    try:
                        film_details = omdb.get_film_details(title)
                        if film_details and film_details.get('imdb_id'):
                            film_details['film_title'] = title
                            upsert_film_details(film_details)
                            count += 1
                    except Exception as e:
                        print(f"Error fetching IMDB ID for '{title}': {e}")
                        continue
            finally:
                config.CURRENT_COMPANY_ID = original_company_id

    return count


def backfill_showtimes_data_from_fandango() -> int:
    """
    Ensure all films in showings have corresponding entries in films table.
    Returns number of films created.
    """
    count = 0

    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        if not company_id:
            company_ids = session.query(Showing.company_id).distinct().all()
            company_ids = [c[0] for c in company_ids if c[0]]
        else:
            company_ids = [company_id]

        if not company_ids:
            return 0

        for cid in company_ids:
            showing_films = session.query(Showing.film_title).filter(
                Showing.company_id == cid
            ).distinct().all()
            showing_titles = {r[0] for r in showing_films}

            existing_films = session.query(Film.film_title).filter(
                Film.company_id == cid
            ).all()
            existing_titles = {r[0] for r in existing_films}

            missing_titles = showing_titles - existing_titles

            for title in missing_titles:
                film = Film(
                    company_id=cid,
                    film_title=title
                )
                session.add(film)
                count += 1

        if count > 0:
            session.flush()

    return count
