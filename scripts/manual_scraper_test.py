import asyncio
import time
from app.scraper import Scraper

async def test_scrape():
    scout = Scraper(headless=True)
    theater = {
        'name': 'Movie Tavern Hulen',
        'url': 'https://www.fandango.com/movie-tavern-hulen-aatzh/theater-page'
    }
    date = '2026-01-16'
    
    print(f"Starting scrape for {theater['name']} on {date}...")
    start_time = time.time()
    
    try:
        results = await scout.get_all_showings_for_theaters([theater], date)
        duration = time.time() - start_time
        print(f"Scrape completed in {duration:.2f} seconds.")
        
        showings = results.get(theater['name'], [])
        print(f"Found {len(showings)} showtimes.")
        for s in showings[:5]:
            print(f" - {s['film_title']} at {s['showtime']}")
            
    except Exception as e:
        print(f"Error during scrape: {e}")

if __name__ == "__main__":
    asyncio.run(test_scrape())
