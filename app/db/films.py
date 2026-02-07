"""
Film metadata management: CRUD for films, unmatched films, ignored films.
"""

import pandas as pd
from datetime import datetime, UTC
from sqlalchemy import and_, or_, func
from app.db_session import get_session
from app.db_models import Film, Showing, UnmatchedFilm, IgnoredFilm
from app import config


def get_all_film_titles():
    """Get all unique film titles from showings"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(Showing.film_title).distinct()

        if company_id:
            query = query.filter(Showing.company_id == company_id)

        results = query.all()
        return [row[0] for row in results]


def get_film_metadata(film_title):
    """Get film metadata from films table"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(Film).filter(Film.film_title == film_title)

        if company_id:
            query = query.filter(Film.company_id == company_id)

        film = query.first()

        if not film:
            return None

        return {
            'film_title': film.film_title,
            'imdb_id': film.imdb_id,
            'genre': film.genre,
            'mpaa_rating': film.mpaa_rating,
            'director': film.director,
            'actors': film.actors,
            'plot': film.plot,
            'poster_url': film.poster_url,
            'metascore': film.metascore,
            'imdb_rating': float(film.imdb_rating) if film.imdb_rating else None,
            'release_date': film.release_date,
            'domestic_gross': film.domestic_gross,
            'runtime': film.runtime,
            'opening_weekend_domestic': film.opening_weekend_domestic,
            'last_omdb_update': film.last_omdb_update
        }


def save_film_metadata(film_data, company_id: int = None):
    """Save or update film metadata"""
    with get_session() as session:
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        if not company_id:
            company_id = 1

        film = session.query(Film).filter(
            and_(
                Film.company_id == company_id,
                Film.film_title == film_data['film_title']
            )
        ).first()

        if film:
            for key, value in film_data.items():
                if hasattr(film, key):
                    setattr(film, key, value)
            film.last_omdb_update = datetime.now(UTC)
        else:
            film = Film(
                company_id=company_id,
                last_omdb_update=datetime.now(UTC),
                **film_data
            )
            session.add(film)


def get_unmatched_films() -> pd.DataFrame:
    """Get list of films that couldn't be matched to OMDB."""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(UnmatchedFilm)

        if company_id:
            query = query.filter(UnmatchedFilm.company_id == company_id)

        results = query.all()
        data = [{'film_title': row.film_title, 'first_seen': row.first_seen} for row in results]
        return pd.DataFrame(data)


def add_unmatched_film(film_title, company_id: int = None):
    """Add or update unmatched film"""
    with get_session() as session:
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        if not company_id:
            company_id = 1

        film = session.query(UnmatchedFilm).filter(
            and_(
                UnmatchedFilm.company_id == company_id,
                UnmatchedFilm.film_title == film_title
            )
        ).first()

        if film:
            film.last_seen = datetime.now(UTC)
            film.occurrence_count += 1
        else:
            film = UnmatchedFilm(
                company_id=company_id,
                film_title=film_title,
                first_seen=datetime.now(UTC),
                last_seen=datetime.now(UTC),
                occurrence_count=1
            )
            session.add(film)


def get_ignored_films():
    """Get list of films that are ignored"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(IgnoredFilm.film_title)

        if company_id:
            query = query.filter(IgnoredFilm.company_id == company_id)

        results = query.all()
        return [row[0] for row in results]


def add_ignored_film(film_title, reason=None, company_id: int = None):
    """Add film to ignored list"""
    with get_session() as session:
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None)
        if not company_id:
            company_id = 1

        existing = session.query(IgnoredFilm).filter(
            and_(
                IgnoredFilm.company_id == company_id,
                IgnoredFilm.film_title == film_title
            )
        ).first()

        if not existing:
            film = IgnoredFilm(
                company_id=company_id,
                film_title=film_title,
                reason=reason
            )
            session.add(film)


def remove_ignored_film(film_title):
    """Remove film from ignored list"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(IgnoredFilm).filter(
            IgnoredFilm.film_title == film_title
        )

        if company_id:
            query = query.filter(IgnoredFilm.company_id == company_id)

        film = query.first()
        if film:
            session.delete(film)


def upsert_film_details(film_data: dict, company_id: int = None):
    """Save or update film metadata"""
    with get_session() as session:
        cid = company_id or getattr(config, 'CURRENT_COMPANY_ID', None)
        if not cid:
            cid = 1

        film = session.query(Film).filter(
            and_(
                Film.company_id == cid,
                Film.film_title == film_data['film_title']
            )
        ).first()

        if film:
            for key, value in film_data.items():
                if hasattr(film, key) and key != 'film_id':
                    setattr(film, key, value)
            film.last_omdb_update = datetime.now(UTC)
        else:
            filtered_data = {k: v for k, v in film_data.items()
                           if k not in ('film_id', 'last_omdb_update', 'company_id')}
            film = Film(
                company_id=cid,
                last_omdb_update=datetime.now(UTC),
                **filtered_data
            )
            session.add(film)

        session.flush()


def check_film_exists(film_title: str) -> bool:
    """Check if film metadata exists"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(Film).filter(Film.film_title == film_title)

        if company_id:
            query = query.filter(Film.company_id == company_id)

        return query.first() is not None


def get_film_details(film_title: str) -> dict | None:
    """Get film metadata"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(Film).filter(Film.film_title == film_title)

        if company_id:
            query = query.filter(Film.company_id == company_id)

        film = query.first()

        if not film:
            return None

        return {
            'film_title': film.film_title,
            'imdb_id': film.imdb_id,
            'genre': film.genre,
            'mpaa_rating': film.mpaa_rating,
            'director': film.director,
            'actors': film.actors,
            'plot': film.plot,
            'poster_url': film.poster_url,
            'metascore': film.metascore,
            'imdb_rating': float(film.imdb_rating) if film.imdb_rating else None,
            'release_date': film.release_date,
            'domestic_gross': film.domestic_gross,
            'runtime': film.runtime,
            'opening_weekend_domestic': film.opening_weekend_domestic,
            'last_omdb_update': film.last_omdb_update
        }


def get_all_unique_genres() -> list[str]:
    """Get all unique genres"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(Film.genre).distinct()

        if company_id:
            query = query.filter(Film.company_id == company_id)

        query = query.filter(Film.genre.isnot(None))

        results = query.all()
        return sorted([r[0] for r in results if r[0]])


def get_all_unique_ratings() -> list[str]:
    """Get all unique MPAA ratings"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(Film.mpaa_rating).distinct()

        if company_id:
            query = query.filter(Film.company_id == company_id)

        query = query.filter(Film.mpaa_rating.isnot(None))

        results = query.all()
        return sorted([r[0] for r in results if r[0]])


def log_unmatched_film(film_title: str, company_id: int = None):
    """Log film that couldn't be matched"""
    with get_session() as session:
        cid = company_id or getattr(config, 'CURRENT_COMPANY_ID', None)
        if not cid:
            cid = 1

        film = session.query(UnmatchedFilm).filter(
            and_(
                UnmatchedFilm.company_id == cid,
                UnmatchedFilm.film_title == film_title
            )
        ).first()

        if film:
            film.last_seen = datetime.now(UTC)
            film.occurrence_count += 1
        else:
            film = UnmatchedFilm(
                company_id=cid,
                film_title=film_title,
                first_seen=datetime.now(UTC),
                last_seen=datetime.now(UTC),
                occurrence_count=1
            )
            session.add(film)

        session.flush()


def delete_unmatched_film(film_title: str):
    """Remove film from unmatched list"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(UnmatchedFilm).filter(
            UnmatchedFilm.film_title == film_title
        )

        if company_id:
            query = query.filter(UnmatchedFilm.company_id == company_id)

        film = query.first()
        if film:
            session.delete(film)
            session.flush()


def get_films_missing_release_date() -> list[str]:
    """Get films without release dates"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(Film.film_title).filter(
            or_(Film.release_date.is_(None), Film.release_date == '')
        )

        if company_id:
            query = query.filter(Film.company_id == company_id)

        results = query.all()
        return [r[0] for r in results]


def get_films_missing_metadata() -> list[str]:
    """Get films without complete metadata"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(Showing.film_title).distinct().outerjoin(
            Film, and_(
                Film.film_title == Showing.film_title,
                Film.company_id == Showing.company_id
            )
        ).filter(Film.film_id.is_(None))

        if company_id:
            query = query.filter(Showing.company_id == company_id)

        results = query.all()
        return [r[0] for r in results]


def get_all_films_for_enrichment(as_df=False):
    """Get all films for metadata enrichment"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(Film)

        if company_id:
            query = query.filter(Film.company_id == company_id)

        if as_df:
            return pd.read_sql(query.statement, session.bind)
        else:
            results = query.all()
            return [
                {
                    'film_title': r.film_title,
                    'imdb_id': r.imdb_id,
                    'genre': r.genre,
                    'mpaa_rating': r.mpaa_rating,
                    'director': r.director,
                    'actors': r.actors,
                    'plot': r.plot,
                    'poster_url': r.poster_url,
                    'metascore': r.metascore,
                    'imdb_rating': float(r.imdb_rating) if r.imdb_rating else None,
                    'release_date': r.release_date,
                    'domestic_gross': r.domestic_gross,
                    'runtime': r.runtime,
                    'opening_weekend_domestic': r.opening_weekend_domestic,
                    'last_omdb_update': r.last_omdb_update
                } for r in results
            ]


def get_ignored_film_titles() -> list[str]:
    """Alias for get_ignored_films for backward compatibility"""
    return get_ignored_films()


def get_first_play_date_for_all_films() -> dict[str, str]:
    """Get the first date each film was seen in a scrape"""
    with get_session() as session:
        company_id = getattr(config, 'CURRENT_COMPANY_ID', None)

        query = session.query(
            Showing.film_title,
            func.min(Showing.play_date)
        ).group_by(Showing.film_title)

        if company_id:
            query = query.filter(Showing.company_id == company_id)

        results = query.all()
        return {r[0]: str(r[1]) for r in results}
