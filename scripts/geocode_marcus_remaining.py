"""
Second pass: geocode remaining Marcus/Movie Tavern theaters with targeted queries.
These theaters failed Nominatim lookup by name, so we use known city/state info.
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

# Manually-curated search queries for theaters that failed generic Nominatim lookup.
# These are based on known theater locations from the Marcus Theatres website.
TARGETED_QUERIES = {
    # St Louis Metro (MO)
    "Marcus Arnold Cine":             ["Marcus Wehrenberg Arnold 14 cinema Arnold Missouri"],
    "Marcus Arnold Cinemas":          ["Marcus Wehrenberg Arnold 14 cinema Arnold Missouri"],
    "Marcus Chesterfield Cine":       ["Marcus Chesterfield Galaxy 14 Cine Chesterfield Missouri"],
    "Marcus Chesterfield Cinema":     ["Marcus Chesterfield Galaxy 14 Cine Chesterfield Missouri"],
    "Marcus Des Peres Cine":          ["Marcus Des Peres cinema Des Peres Missouri"],
    "Marcus Des Peres Cinema":        ["Marcus Des Peres cinema Des Peres Missouri"],
    "Marcus Mid Rivers Cine":         ["Marcus Mid Rivers 14 cinema Saint Peters Missouri"],
    "Marcus Mid Rivers Cinema":       ["Marcus Mid Rivers 14 cinema Saint Peters Missouri"],
    "Marcus O'Fallon Cine":           ["Marcus OFallon 15 cinema O'Fallon Illinois"],
    "Marcus O'Fallon Cinema":         ["Marcus OFallon 15 cinema O'Fallon Illinois"],
    "Marcus Ronnie's Cine + IMAX":    ["Marcus Ronnies cinema St Louis Missouri"],
    "Marcus Ronnie's Cinema + IMAX":  ["Marcus Ronnies cinema St Louis Missouri"],

    # Illinois / Chicago DMA
    "Marcus Bloomington Cine + IMAX": ["Marcus Bloomington cinema Bloomington Illinois"],
    "Marcus Bloomington Cinema + IMAX": ["Marcus Bloomington cinema Bloomington Illinois"],

    # Wisconsin
    "Marcus Bay Park Cinema":         ["Marcus Bay Park Cinema Ashwaubenon Wisconsin"],
    "Marcus Bay Park Cinemas":        ["Marcus Bay Park Cinema Ashwaubenon Wisconsin"],
    "Marcus La Crosse Cinema":        ["Marcus La Crosse Cinema Onalaska Wisconsin"],
    "Marcus La Crosse Cinemas":       ["Marcus La Crosse Cinema Onalaska Wisconsin"],
    "Marcus Oshkosh Cinema":          ["Marcus cinema Oshkosh Wisconsin"],
    "Marcus Majestic Cinema of Brookfield": ["Marcus Majestic Cinema Brookfield Wisconsin"],
    "Marcus Cinema at the Renaissance":     ["Marcus Renaissance Cinema Sturtevant Wisconsin"],
    "Marcus Gurnee Mills Cinema":     ["Marcus Gurnee Mills cinema Gurnee Illinois"],
    "Movie Tavern at Brookfield Square": ["Movie Tavern Brookfield Square Wisconsin"],

    # Iowa
    "Marcus Cedar Rapids Cine":       ["Marcus Cedar Rapids cinema Cedar Rapids Iowa"],
    "Marcus Cedar Rapids Cinema":     ["Marcus Cedar Rapids cinema Cedar Rapids Iowa"],

    # Nebraska / Lincoln
    "Marcus East Park Cinema":        ["Marcus East Park Cinema Lincoln Nebraska"],
    "Marcus East Park Cinemas":       ["Marcus East Park Cinema Lincoln Nebraska"],
    "Marcus South Pointe Cinema":     ["Marcus South Pointe Cinema Lincoln Nebraska"],
    "Marcus South Pointe Cinemas":    ["Marcus South Pointe Cinema Lincoln Nebraska"],

    # Minnesota
    "Marcus Rochester Cine + IMAX":   ["Marcus Rochester cinema Rochester Minnesota"],
    "Marcus Rochester Cinema + IMAX": ["Marcus Rochester cinema Rochester Minnesota"],

    # Missouri other
    "Marcus Eagles Landing Cinema":   ["Marcus Eagles Landing cinema Jefferson City Missouri"],

    # Movie Tavern locations (known addresses)
    "Movie Tavern at Brannon Crossing":     ["Movie Tavern Nicholasville Kentucky"],
    "Movie Tavern Brannon Crossing":        ["Movie Tavern Nicholasville Kentucky"],
    "Movie Tavern at Horizon Village":      ["Movie Tavern Woodstock Georgia"],
    "Movie Tavern Horizon Village":         ["Movie Tavern Woodstock Georgia"],
    "Movie Tavern at Sandy Plains Village": ["Movie Tavern Marietta Georgia"],
    "Movie Tavern Northlake Festival":      ["Movie Tavern Tucker Georgia"],
    "Movie Tavern Tucker Cinema":           ["Movie Tavern Tucker Georgia"],
    "Movie Tavern Citiplace":               ["Movie Tavern Baton Rouge Louisiana"],
    "Movie Tavern Citiplace Cinema":        ["Movie Tavern Baton Rouge Louisiana"],
    "Movie Tavern Collegeville Cinema":     ["Movie Tavern Collegeville Pennsylvania"],
    "Movie Tavern Northshore":              ["Movie Tavern Covington Louisiana", "Movie Tavern Slidell Louisiana"],
    "Movie Tavern at High Street":          ["Movie Tavern Williamsburg Virginia"],
    "Movie Tavern Roswell":                 ["Movie Tavern Roswell Georgia"],
    "Movie Tavern Covington":               ["Movie Tavern Covington Louisiana"],
}


def geocode(query: str) -> dict | None:
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
        print(f"  [ERR] {e}")
    return None


def main():
    geocoded = 0
    failed = 0

    with get_session() as session:
        missing = session.query(TheaterMetadata).filter(
            TheaterMetadata.latitude.is_(None),
            TheaterMetadata.circuit_name.ilike('%marcus%'),
        ).order_by(TheaterMetadata.theater_name).all()

        print(f"Second pass: {len(missing)} theaters still need coordinates")
        print()

        for theater in missing:
            name = theater.theater_name
            queries = TARGETED_QUERIES.get(name, [name])

            print(f"[{geocoded + failed + 1}/{len(missing)}] {name}")

            coords = None
            for q in queries:
                time.sleep(1.1)  # Nominatim rate limit
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
                print(f"  -> FAILED")

        session.flush()

    print()
    print(f"Second pass: {geocoded} geocoded, {failed} failed")


if __name__ == "__main__":
    main()
