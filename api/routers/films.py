"""
Films API Router

Endpoints for film metadata lookup and enrichment via OMDb and Fandango.

Endpoints:
    GET    /api/v1/films                        - List all films with metadata
    GET    /api/v1/films/{film_title}            - Get metadata for a specific film
    POST   /api/v1/films/{film_title}/enrich     - Enrich film with OMDb metadata
    POST   /api/v1/films/discover/fandango       - Discover films from Fandango
"""

from fastapi import APIRouter, Security, HTTPException, Query, BackgroundTasks
from api.routers.auth import get_current_user, User
from app import config
from app.db.films import get_all_films_for_enrichment, get_film_metadata
from app.db.film_enrichment import backfill_film_details_from_fandango_single, enrich_new_films
from app.db.utils import run_async_safe
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class FilmMetadata(BaseModel):
    film_title: str
    imdb_id: Optional[str] = None
    genre: Optional[str] = None
    mpaa_rating: Optional[str] = None
    director: Optional[str] = None
    actors: Optional[str] = None
    plot: Optional[str] = None
    poster_url: Optional[str] = None
    metascore: Optional[int] = None
    imdb_rating: Optional[float] = None
    release_date: Optional[str] = None
    domestic_gross: Optional[int] = None
    runtime: Optional[str] = None
    opening_weekend_domestic: Optional[int] = None
    last_omdb_update: Optional[datetime] = None

class EnrichResponse(BaseModel):
    success: bool
    message: str
    data: Optional[FilmMetadata] = None

@router.get("/films", response_model=List[FilmMetadata], tags=["Films"])
async def get_films(
    current_user: User = Security(get_current_user, scopes=["read:prices"])
):
    """
    Get all films in the database for the current company.
    """
    try:
        # get_all_films_for_enrichment returns a list of dicts
        films_data = get_all_films_for_enrichment()
        
        # Convert to Pydantic models
        films = []
        for f in films_data:
            # Handle possible N/A strings from legacy code
            cleaned_f = {k: (None if v == 'N/A' else v) for k, v in f.items()}
            films.append(FilmMetadata(**cleaned_f))
        return films
    except Exception as e:
        logger.exception("Failed to list films: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/films/{film_title}", response_model=FilmMetadata, tags=["Films"])
async def get_film(
    film_title: str,
    current_user: User = Security(get_current_user, scopes=["read:prices"])
):
    """
    Get metadata for a specific film.
    """
    metadata = get_film_metadata(film_title)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Film '{film_title}' not found.")

    # Handle possible N/A strings
    cleaned_m = {k: (None if v == 'N/A' else v) for k, v in metadata.items()}
    return FilmMetadata(**cleaned_m)

@router.post("/films/{film_title}/enrich", response_model=EnrichResponse, tags=["Films"])
async def enrich_film(
    film_title: str,
    background_tasks: BackgroundTasks,
    current_user: User = Security(get_current_user, scopes=["write:prices"])
):
    """
    Trigger OMDb and Fandango enrichment for a specific film.
    """
    try:
        # We'll run it synchronously for now since it's a single film and quick
        # But for high volume, BackgroundTasks would be better.
        updated = backfill_film_details_from_fandango_single(film_title)

        if updated:
            metadata = get_film_metadata(film_title)
            cleaned_m = {k: (None if v == 'N/A' else v) for k, v in metadata.items()}
            return EnrichResponse(
                success=True,
                message=f"Film '{film_title}' enriched successfully.",
                data=FilmMetadata(**cleaned_m)
            )
        else:
            return EnrichResponse(
                success=False,
                message=f"Could not find OMDb or Fandango details for '{film_title}'."
            )
    except Exception as e:
        logger.exception("Failed to enrich film '%s': %s", film_title, e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/films/discover/fandango", tags=["Films"])
async def discover_fandango(
    background_tasks: BackgroundTasks,
    current_user: User = Security(get_current_user, scopes=["write:prices"])
):
    """
    Discover 'Coming Soon' films from Fandango and enrich them.
    Runs in the background.
    """
    try:
        background_tasks.add_task(_run_fandango_discovery)
        return {"message": "Fandango discovery started in background."}
    except Exception as e:
        logger.exception("Failed to start Fandango discovery: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

def _run_fandango_discovery():
    from app.scraper import Scraper
    import asyncio
    
    async def run():
        scraper = Scraper()
        # 1. Discover film titles from Fandango
        films = await scraper.get_coming_soon_films()
        
        # 2. Extract titles
        titles = [f.get('film_title') for f in films if f.get('film_title')]
        
        if titles:
            logger.info(f"Found {len(titles)} titles. Passing to enrichment pipeline...")
            # 3. Use the centralized enrichment logic (which now has Fandango fallback)
            # This is already running in a background thread, so we can call sync
            enrich_new_films(titles, async_mode=False)

    # Playwright needs its own loop
    run_async_safe(run())
