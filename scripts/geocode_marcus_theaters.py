"""
Geocode all Marcus/Movie Tavern theaters missing lat/lon coordinates.
Uses Nominatim (OpenStreetMap) with 1-second rate limiting.
"""
import sys, os, time, requests
from urllib.parse import quote
from datetime import datetime, UTC

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

from app.db_session import get_session
from app.db_models import TheaterMetadata

USER_AGENT = "PriceScout/1.0 (theater geocoding)"


def geocode(query: str) -> dict | None:
    """Geocode a query string using Nominatim."""
    url = f"https://nominatim.openstreetmap.org/search?q={quote(query)}&format=json&limit=1&countrycodes=us"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data:
            return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"]),
                    "display": data[0].get("display_name", "")}
    except Exception as e:
        print(f"  [ERR] Geocoding failed: {e}")
    return None


def build_search_queries(theater) -> list[str]:
    """Build search queries in priority order."""
    name = theater.theater_name
    queries = []

    # If we have full address components, try that first
    if theater.address and theater.city and theater.state:
        queries.append(f"{theater.address}, {theater.city}, {theater.state}")

    # Theater name + city + state
    if theater.city and theater.state:
        queries.append(f"{name}, {theater.city}, {theater.state}")

    # Theater name + DMA (DMA often contains city/state info)
    if theater.dma:
        queries.append(f"{name}, {theater.dma}")

    # Just the theater name (often sufficient for well-known chains)
    queries.append(name)

    return queries


def main():
    geocoded = 0
    failed = 0
    skipped = 0

    with get_session() as session:
        # Get all Marcus/Movie Tavern theaters without coordinates
        theaters = session.query(TheaterMetadata).filter(
            TheaterMetadata.latitude.is_(None),
            TheaterMetadata.circuit_name.ilike('%marcus%'),
        ).order_by(TheaterMetadata.theater_name).all()

        print(f"Found {len(theaters)} Marcus/Movie Tavern theaters without coordinates")
        print()

        for theater in theaters:
            queries = build_search_queries(theater)
            print(f"[{geocoded + failed + skipped + 1}/{len(theaters)}] {theater.theater_name}")

            coords = None
            for q in queries:
                time.sleep(1)  # Nominatim rate limit
                print(f"  Trying: {q}")
                coords = geocode(q)
                if coords:
                    break

            if coords:
                theater.latitude = coords["lat"]
                theater.longitude = coords["lon"]
                theater.last_geocode_at = datetime.now(UTC)
                geocoded += 1
                print(f"  -> ({coords['lat']:.6f}, {coords['lon']:.6f})")
                print(f"     {coords['display'][:80]}")
            else:
                failed += 1
                print(f"  -> FAILED (no results)")

        session.flush()

    print()
    print(f"Done: {geocoded} geocoded, {failed} failed, {skipped} skipped")
    print(f"Total Marcus/Movie Tavern theaters with coords now: {38 + geocoded}")


if __name__ == "__main__":
    main()
