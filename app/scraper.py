import re
import json
import datetime
import os
import asyncio
import logging
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import random
from opentelemetry import trace
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Optional Streamlit import for when running in Streamlit context
try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False
    st = None

from app.config import DEBUG_DIR, CACHE_FILE
from app import config

# Get tracer for custom spans
tracer = trace.get_tracer(__name__)

# Retry decorator for methods that create their own browser context.
# Only retries on TimeoutError (transient network/page-load issues).
_scraper_retry = retry(
    stop=stop_after_attempt(config.SCRAPER_MAX_RETRIES),
    wait=wait_exponential(min=config.SCRAPER_RETRY_WAIT_MIN, max=config.SCRAPER_RETRY_WAIT_MAX),
    retry=retry_if_exception_type(TimeoutError),
    reraise=True,
    before_sleep=lambda rs: logger.info(f"Retrying {rs.fn.__name__} (attempt {rs.attempt_number}) after timeout"),
)

class Scraper:
    def __init__(self, headless=True, devtools=False):
        """Initialize scraper - parameters kept for compatibility but not used in this version"""
        self.headless = headless
        self.devtools = devtools

    async def close(self):
        """Close scraper resources. No-op since browsers are created/closed per method call."""
        pass

    def _sanitize_for_comparison(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', '', text)
        text = re.sub(r'\s\d+\s', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _sanitize_filename(self, name):
        return re.sub(r'[\\/*?:"<>|]', '', name).replace(' ', '_')

    def _parse_ticket_description(self, description: str) -> dict:
        desc_lower = description.lower()
        amenity_map = {
            'D-BOX': ['d-box', 'dbox'], 'IMAX': ['imax'], 'XD': ['xd'],
            'Dolby Cinema': ['dolby'], 'Recliner': ['recliner'],
            'Luxury': ['luxury'], '4DX': ['4dx'],
            'Promotion': ['promotion', 'tuesday', 'unseen', 'fathom']
        }
        base_type_map = {'Adult': ['adult'], 'Child': ['child'], 'Senior': ['senior'], 'Military': ['military'], 'Student': ['student'], 'Matinee': ['matinee']}
        found_amenities = []
        remaining_desc = desc_lower
        for amenity, keywords in amenity_map.items():
            for keyword in keywords:
                if keyword in remaining_desc:
                    found_amenities.append(amenity)
                    remaining_desc = remaining_desc.replace(keyword, '').strip()
        found_base_type = None
        for base_type, keywords in base_type_map.items():
            for keyword in keywords:
                if keyword in remaining_desc:
                    found_base_type = base_type
                    remaining_desc = remaining_desc.replace(keyword, '').strip()
                    break
            if found_base_type: break
        if not found_base_type:
            remaining_desc = description.split('(')[0].strip()
            if remaining_desc.lower() in ['general admission', 'admission']:
                found_base_type = "General Admission"
            else:
                found_base_type = remaining_desc
        return {"base_type": found_base_type, "amenities": sorted(list(set(found_amenities)))}

    def _classify_daypart(self, showtime_str: str) -> str:
        from app.simplified_baseline_service import classify_daypart
        result = classify_daypart(showtime_str)
        return result if result else "Unknown"

    def _strip_common_terms(self, name: str) -> str:
        # A set of common, low-value terms to remove for better matching
        common_terms = {
            'cinemas', 'cinema', 'movies', 'theatres', 'theatre', 'showplace',
            'imax', 'dolby', 'ultrascreen', 'xd',
            'dine-in', 'movie tavern', 'by marcus'
        }
        
        name_lower = name.lower()
        
        # Create a regex pattern to match any of the common terms as whole words
        sorted_terms = sorted(list(common_terms), key=len, reverse=True)
        pattern = r'\b(' + '|'.join(re.escape(term) for term in sorted_terms) + r')\b'
        
        # Replace found terms with an empty string
        stripped_name = re.sub(pattern, '', name_lower)

        # remove punctuation
        stripped_name = re.sub(r'[^\w\s/-]', '', stripped_name)

        # Clean up extra whitespace
        stripped_name = re.sub(r'\s+', ' ', stripped_name).strip()
        
        return stripped_name

    async def check_url_status(self, url: str) -> bool:
        """Checks if a URL is active by making a HEAD request."""
        if not url or url == "N/A":
            return False
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                response = await page.request.head(url)
                await browser.close()
                return response.status == 200
        except Exception:
            return False
            
    _JS_THEATERS_CONDITION = (
        "() => window.Fandango && window.Fandango.pageDetails "
        "&& window.Fandango.pageDetails.localTheaters "
        "&& window.Fandango.pageDetails.localTheaters.length > 0"
    )

    async def _extract_theaters_from_page(self, page, zip_code, date_str):
        """Load a Fandango ZIP page and extract the theater list."""
        url = f"https://www.fandango.com/{zip_code}_movietimes?date={date_str}"
        await page.goto(url, timeout=config.SCRAPER_NAV_TIMEOUT)
        await page.mouse.wheel(0, 2000)
        await page.wait_for_timeout(int(config.SCRAPER_RENDER_DELAY_SHORT * 1000))
        await page.wait_for_function(self._JS_THEATERS_CONDITION, timeout=config.SCRAPER_JS_WAIT)
        theaters_data = await page.evaluate('() => window.Fandango.pageDetails.localTheaters')
        return {
            t.get('name'): {"name": t.get('name'), "url": "https://www.fandango.com" + t.get('theaterPageUrl')}
            for t in theaters_data if t.get('name') and t.get('theaterPageUrl')
        }

    async def _get_theaters_from_zip_page(self, page, zip_code, date_str):
        logger.info(f"Checking ZIP: {zip_code} for date {date_str}")
        try:
            return await self._extract_theaters_from_page(page, zip_code, date_str)
        except Exception as e:
            logger.warning(f"Could not process ZIP {zip_code}. Error: {e}")
            return {}

    @_scraper_retry
    async def live_search_by_zip(self, zip_code, date_str):
        """Search for theaters by ZIP code on Fandango."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                return await self._extract_theaters_from_page(page, zip_code, date_str)
            finally:
                await browser.close()

    @_scraper_retry
    async def live_search_by_name(self, search_term):
        logger.info(f"Live searching for: {search_term}")
        results = {}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto("https://www.fandango.com", timeout=config.SCRAPER_NAV_TIMEOUT_LONG)
                await page.locator('[data-qa="search-input"]').fill(search_term)
                await page.locator('[data-qa="search-input"]').press('Enter')
                await page.wait_for_selector('[data-qa="search-results-item"]', timeout=config.SCRAPER_ELEMENT_WAIT_SHORT)
                soup = BeautifulSoup(await page.content(), 'html.parser')
                search_results_items = soup.select('[data-qa="search-results-item"]')
                for item in search_results_items:
                    link_elem = item.select_one('a[data-qa="search-results-item-link"]')
                    if link_elem:
                        href = link_elem.get('href')
                        if href and isinstance(href, str) and '/theater-page' in href:
                            name = link_elem.get_text(strip=True)
                            url = "https://www.fandango.com" + href
                            results[name] = {"name": name, "url": url}
            except Exception as e:
                logger.warning(f"Could not complete live name search. Error: {e}")
            await browser.close()
            return results

    @_scraper_retry
    async def discover_theater_url(self, theater_name: str) -> dict:
        """
        Discover a theater's Fandango URL using the search page.

        This is a more reliable method than live_search_by_name as it uses
        the direct search URL rather than UI-based selectors.

        Args:
            theater_name: Name of the theater to search for

        Returns:
            dict with keys:
                - found: bool
                - theater_name: str (the matched name from Fandango)
                - url: str (full Fandango URL)
                - theater_code: str (the unique Fandango theater code)
                - all_results: list of all theater matches found
                - error: str or None
        """
        import urllib.parse

        result = {
            "found": False,
            "theater_name": None,
            "url": None,
            "theater_code": None,
            "all_results": [],
            "error": None
        }

        try:
            # Build search URL
            encoded_name = urllib.parse.quote(theater_name)
            search_url = f"https://www.fandango.com/search?q={encoded_name}"
            logger.info(f"Searching: {search_url}")

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                await page.goto(search_url, timeout=config.SCRAPER_NAV_TIMEOUT)
                await page.wait_for_timeout(int(config.SCRAPER_RENDER_DELAY * 1000))  # Wait for dynamic content

                html_content = await page.content()
                await browser.close()

            soup = BeautifulSoup(html_content, 'html.parser')

            # Find all theater links (they contain '/theater-page' in the href)
            theater_links = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if '/theater-page' in href:
                    # Extract theater code from URL (e.g., 'AATZH' from '/amc-northpark-15-AATZH/theater-page')
                    code_match = re.search(r'-([A-Za-z0-9]+)/theater-page', href)
                    theater_code = code_match.group(1) if code_match else None

                    # Extract theater name from link text
                    name = link.get_text(strip=True)

                    # Skip navigation links like "Go Back to Top", etc.
                    skip_patterns = ['go back', 'top', 'more', 'see all', 'view all', 'load more']
                    if name and any(pat in name.lower() for pat in skip_patterns):
                        name = None

                    # If name is empty or invalid, extract from URL slug
                    if not name or len(name) < 5:
                        # Extract slug from URL: '/amc-northpark-15-AATZH/theater-page' -> 'amc-northpark-15'
                        slug_match = re.search(r'/([a-z0-9-]+)-[A-Za-z0-9]+/theater-page', href)
                        if slug_match:
                            slug = slug_match.group(1)
                            # Convert slug to title case: 'amc-northpark-15' -> 'AMC NorthPark 15'
                            name = ' '.join(word.capitalize() if not word.isdigit() else word
                                          for word in slug.replace('-', ' ').split())
                            # Handle common abbreviations
                            name = name.replace('Amc ', 'AMC ').replace('Cgv ', 'CGV ')

                    if name and href:
                        full_url = href if href.startswith('http') else f"https://www.fandango.com{href}"

                        theater_links.append({
                            "name": name,
                            "url": full_url,
                            "code": theater_code
                        })

            # Remove duplicates (same URL)
            seen_urls = set()
            unique_links = []
            for t in theater_links:
                if t['url'] not in seen_urls:
                    seen_urls.add(t['url'])
                    unique_links.append(t)

            result["all_results"] = unique_links

            if unique_links:
                # Find best match using fuzzy comparison
                search_sanitized = self._sanitize_for_comparison(theater_name)
                best_match = None
                best_score = 0

                for theater in unique_links:
                    match_sanitized = self._sanitize_for_comparison(theater['name'])

                    # Calculate similarity score
                    if search_sanitized == match_sanitized:
                        score = 100
                    elif search_sanitized in match_sanitized or match_sanitized in search_sanitized:
                        score = 80
                    else:
                        # Check word overlap
                        search_words = set(search_sanitized.split())
                        match_words = set(match_sanitized.split())
                        overlap = len(search_words & match_words)
                        total = len(search_words | match_words)
                        score = (overlap / total * 60) if total > 0 else 0

                    if score > best_score:
                        best_score = score
                        best_match = theater

                if best_match:
                    result["found"] = True
                    result["theater_name"] = best_match['name']
                    result["url"] = best_match['url']
                    result["theater_code"] = best_match['code']
                    logger.info(f"Found: {best_match['name']} ({best_match['code']})")
                    logger.info(f"URL: {best_match['url']}")
            else:
                logger.info(f"No theater results found for '{theater_name}'")
                result["error"] = "No theater results found"

        except Exception as e:
            logger.error(f"Error discovering theater URL: {e}")
            result["error"] = str(e)

        return result

    @_scraper_retry
    async def search_fandango_for_film_url(self, search_term: str) -> list[dict]:
        """
        Discover a movie's Fandango URL using the search page.
        """
        results = []
        search_url = f"https://www.fandango.com/search?q={search_term.replace(' ', '+')}"
        logger.info(f"Searching for: {search_term}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(search_url, timeout=config.SCRAPER_NAV_TIMEOUT)
                await page.wait_for_selector('.search__movie-title', timeout=config.SCRAPER_SELECTOR_WAIT)
                
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                movie_links = soup.select('.search__movie-title')
                for link in movie_links:
                    title = link.get_text(strip=True)
                    url = link.get('href')
                    if url:
                        if not url.startswith('http'):
                            url = "https://www.fandango.com" + url
                        results.append({"title": title, "url": url})
                        
                logger.info(f"Found {len(results)} potential movie matches.")
            except Exception as e:
                logger.warning(f"Could not complete search for '{search_term}'. Error: {e}")
            finally:
                await browser.close()
        return results

    @_scraper_retry
    async def get_film_details_from_fandango_url(self, url: str) -> dict:
        """
        Scrape detailed film information from a Fandango movie overview page.
        This is used as a fallback for OMDb, especially for runtime data.
        """
        if '/movie-overview' not in url:
            url = url.rstrip('/') + '/movie-overview'
            
        logger.info(f"Fetching details from: {url}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=config.SCRAPER_NAV_TIMEOUT_MEDIUM, wait_until="domcontentloaded")
                # Wait for any common movie page element
                try:
                    await page.wait_for_selector('.details-header__title, .movie-details__movie-title, .mop__title, h1', timeout=config.SCRAPER_JS_WAIT)
                except Exception:
                    logger.warning("Specific title selector not found, attempting to proceed with page content.")
                
                # Scroll a bit to trigger any lazy-loaded info
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(config.SCRAPER_RENDER_DELAY)
                
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                details = {
                    "film_title": None,
                    "mpaa_rating": "N/A",
                    "runtime": "N/A",
                    "genre": "N/A",
                    "plot": "N/A",
                    "poster_url": None,
                    "director": None,
                    "actors": None,
                    "last_omdb_update": datetime.datetime.now()
                }
                
                # Title - try multiple selectors
                title_elem = soup.select_one('.details-header__title, .movie-details__movie-title, .mop__title, h1[data-qa="movie-title"]')
                if not title_elem:
                    title_elem = soup.find('h1')
                
                if title_elem:
                    details["film_title"] = title_elem.get_text(strip=True)
                
                # Header info (Rating, Runtime)
                stats_elem = soup.select_one('.details-header__movie-stats, .movie-details__movie-info, .mop__movie-stats')
                if stats_elem:
                    info_text = stats_elem.get_text(separator=' ', strip=True)
                else:
                    # Fallback: look for anywhere in the body that looks like stats
                    info_text = soup.get_text(separator=' ', strip=True)
                
                # Runtime regex: "2 hr 30 min" or "120 min"
                runtime_match = re.search(r'(\d+\s*hr\s*\d+\s*min|\d+\s*min)', info_text, re.IGNORECASE)
                if runtime_match:
                    details["runtime"] = runtime_match.group(1).strip()
                
                # Rating regex
                rating_match = re.search(r'\b(G|PG|PG-13|R|NC-17|NR)\b', info_text)
                if rating_match:
                    details["mpaa_rating"] = rating_match.group(1)

                # Poster
                poster_elem = soup.select_one('.visual-thumb.details-img-carousel__img, .movie-details__poster-art img, .mop__poster, img[data-qa="poster-image"]')
                if poster_elem:
                    details["poster_url"] = poster_elem.get('src') or poster_elem.get('data-src')

                # Synopsis
                synopsis_elem = soup.select_one('.movie-details__synopsis, .details-synopsis, .mop__synopsis, [data-qa="movie-synopsis"]')
                if synopsis_elem:
                    details["plot"] = synopsis_elem.get_text(strip=True)

                # Info Labels (Genre, Release Date, etc.)
                # Fandango often uses <li> items with strong labels or divs with spans
                labels = soup.find_all(['li', 'div', 'p'])
                for label in labels:
                    text = label.get_text(separator=' ', strip=True)
                    if 'GENRE:' in text.upper():
                        val = text.split(':', 1)[1].strip()
                        if val: details["genre"] = val
                    elif 'DIRECTOR:' in text.upper():
                        val = text.split(':', 1)[1].strip()
                        if val: details["director"] = val
                    elif 'CAST:' in text.upper() or 'ACTORS:' in text.upper():
                        val = text.split(':', 1)[1].strip()
                        if val: details["actors"] = val

                return details
            except Exception as e:
                logger.error(f"Failed to scrape details from {url}. Error: {e}")
                return None
            finally:
                await browser.close()

    @_scraper_retry
    async def get_coming_soon_films(self) -> list[dict]:
        """
        Discover films from Fandango's 'Coming Soon' page.
        """
        results = []
        url = "https://www.fandango.com/movies-coming-soon"
        logger.info(f"Discovering upcoming films from Fandango...")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=config.SCRAPER_NAV_TIMEOUT_MEDIUM)
                # Scroll to trigger lazy loading of the full list
                for _ in range(5):
                    await page.mouse.wheel(0, 2000)
                    await asyncio.sleep(config.SCRAPER_SCROLL_DELAY)
                
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Fandango structure for 'Coming Soon' varies, but links to movie-overview are key
                movie_links = soup.find_all('a', href=re.compile(r'/movie-overview$|/[^/]+-[0-9]+/movie-overview'))
                
                # If no direct overview links, look for browse items
                if not movie_links:
                    movie_links = soup.select('.browse-movielist-item a, .browse-movie-link')
                
                seen_urls = set()
                for link in movie_links:
                    href = link.get('href')
                    if not href: continue
                    
                    if not href.startswith('http'):
                        href = "https://www.fandango.com" + href
                    
                    if href in seen_urls: continue
                    seen_urls.add(href)
                    
                    # Try to find title in or near the link
                    title = link.get_text(strip=True)
                    if not title or len(title) < 2:
                        # Try to get from sibling or child span
                        title_elem = link.select_one('span, .browse-movie-link__title')
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                    
                    if title and len(title) > 1:
                        results.append({
                            "film_title": title,
                            "url": href
                        })
                
                logger.info(f"Discovered {len(results)} upcoming films.")
            except Exception as e:
                logger.error(f"Failed to discover films. Error: {e}")
            finally:
                await browser.close()
        return results

    @_scraper_retry
    async def discover_films_from_main_page(self) -> list[dict]:
        """
        Discover 'Now Playing' films from Fandango's main page.
        """
        results = []
        url = "https://www.fandango.com/"
        logger.info(f"Scraping films from Fandango main page...")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=config.SCRAPER_NAV_TIMEOUT)
                await page.mouse.wheel(0, 1500)
                await asyncio.sleep(config.SCRAPER_RENDER_DELAY)
                
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Look for movie item containers in the 'Now Playing' or Featured sections
                movie_items = soup.select('.mop__item, .browse-movielist-item')
                for item in movie_items:
                    link = item.select_one('a')
                    title_elem = item.select_one('.mop__title, .browse-movie-link__title')
                    
                    if link and title_elem:
                        href = link.get('href')
                        if href:
                            if not href.startswith('http'):
                                href = "https://www.fandango.com" + href
                            
                            results.append({
                                "film_title": title_elem.get_text(strip=True),
                                "url": href
                            })
                            
                logger.info(f"Found {len(results)} films on the main page.")
            except Exception as e:
                logger.error(f"Failed to scrape main page. Error: {e}")
            finally:
                await browser.close()
        return results

    async def build_theater_cache(self, markets_json_path):
        with open(markets_json_path, 'r') as f:
            markets_data = json.load(f)

        temp_cache = {"metadata": {"last_updated": datetime.datetime.now().isoformat()}, "markets": {}}
        total_theaters_to_find = 0
        total_theaters_found = 0
        
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        date_str = tomorrow.strftime('%Y-%m-%d')

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            for parent_company, regions in markets_data.items():
                for region_name, markets in regions.items():
                    for market_name, market_info in markets.items():
                        logger.info(f"Processing Market: {market_name}")
                        theaters_in_market = market_info.get('theaters', [])
                        total_theaters_to_find += len(theaters_in_market)

                        found_theaters_for_market = []
                        theaters_to_find_in_fallback = []

                        logger.info("Phase 1: Starting fast ZIP code scrape...")
                        zip_pool = {t.get('zip') for t in theaters_in_market if t.get('zip')}
                        market_zip_cache = {}
                        for zip_code in zip_pool:
                            zip_results = await self._get_theaters_from_zip_page(page, zip_code, date_str)
                            market_zip_cache.update(zip_results)

                        for theater_from_json in theaters_in_market:
                            name_to_find = theater_from_json['name']
                            found = False
                            sanitized_target_name = self._sanitize_for_comparison(name_to_find)
                            for live_name, live_data in market_zip_cache.items():
                                sanitized_live_name = self._sanitize_for_comparison(live_name)
                                if sanitized_target_name in sanitized_live_name or sanitized_live_name in sanitized_target_name:
                                    found_theaters_for_market.append({'name': live_name, 'url': live_data['url']})
                                    found = True
                                    break
                            if not found:
                                theaters_to_find_in_fallback.append(name_to_find)

                        logger.info(f"Phase 1: Found {len(found_theaters_for_market)} theaters via ZIP scrape.")

                        if theaters_to_find_in_fallback:
                            logger.info(f"Phase 2: Starting targeted fallback search for {len(theaters_to_find_in_fallback)} theater(s)...")
                            for theater_name in theaters_to_find_in_fallback:
                                search_results = await self.live_search_by_name(theater_name)
                                if search_results:
                                    found_name, found_data = next(iter(search_results.items()))
                                    logger.info(f"Fallback found '{theater_name}' as '{found_name}'")
                                    found_theaters_for_market.append({'name': found_name, 'url': found_data['url']})
                                else:
                                    logger.warning(f"Fallback could not find '{theater_name}'.")

                        temp_cache["markets"][market_name] = {"theaters": found_theaters_for_market}
                        total_theaters_found += len(found_theaters_for_market)

            await browser.close()

        logger.info("Sanity Check")
        logger.info(f"Found {total_theaters_found} out of {total_theaters_to_find} total theaters.")

        if total_theaters_to_find > 0 and (total_theaters_found / total_theaters_to_find) >= 0.75:
            logger.info("Sanity check passed. Overwriting old cache.")
            with open(CACHE_FILE, 'w') as f:
                json.dump(temp_cache, f, indent=2)
            return temp_cache
        else:
            logger.error("Sanity check failed. Preserving existing cache to prevent errors.")
            return False

    async def test_single_market(self, market_name, markets_data):
        temp_cache = {"markets": {}}
        total_theaters_found = 0
        
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        date_str = tomorrow.strftime('%Y-%m-%d')

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            for parent_company, regions in markets_data.items():
                for region_name, markets in regions.items():
                    if market_name in markets:
                        market_info = markets[market_name]
                        logger.info(f"Processing Market: {market_name}")
                        theaters_in_market = market_info.get('theaters', [])
                        
                        found_theaters_for_market = []
                        theaters_to_find_in_fallback = []

                        logger.info("Phase 1: Starting fast ZIP code scrape...")
                        zip_pool = {t.get('zip') for t in theaters_in_market if t.get('zip')}
                        market_zip_cache = {}
                        for zip_code in zip_pool:
                            zip_results = await self._get_theaters_from_zip_page(page, zip_code, date_str)
                            market_zip_cache.update(zip_results)

                        for theater_from_json in theaters_in_market:
                            name_to_find = theater_from_json['name']
                            found = False
                            sanitized_target_name = self._sanitize_for_comparison(name_to_find)
                            for live_name, live_data in market_zip_cache.items():
                                sanitized_live_name = self._sanitize_for_comparison(live_name)
                                if sanitized_target_name in sanitized_live_name or sanitized_live_name in sanitized_target_name:
                                    found_theaters_for_market.append({'name': live_name, 'url': live_data['url']})
                                    found = True
                                    break
                            if not found:
                                theaters_to_find_in_fallback.append(name_to_find)

                        logger.info(f"Phase 1: Found {len(found_theaters_for_market)} theaters via ZIP scrape.")

                        if theaters_to_find_in_fallback:
                            logger.info(f"Phase 2: Starting targeted fallback search for {len(theaters_to_find_in_fallback)} theater(s)...")
                            for theater_name in theaters_to_find_in_fallback:
                                search_results = await self.live_search_by_name(theater_name)
                                if search_results:
                                    found_name, found_data = next(iter(search_results.items()))
                                    logger.info(f"Fallback found '{theater_name}' as '{found_name}'")
                                    found_theaters_for_market.append({'name': found_name, 'url': found_data['url']})
                                else:
                                    logger.warning(f"Fallback could not find '{theater_name}'.")

                        temp_cache["markets"][market_name] = {"theaters": found_theaters_for_market}
                        total_theaters_found += len(found_theaters_for_market)
                        break
            await browser.close()
        
        return temp_cache

    async def _get_movies_from_theater_page(self, page, theater, date):
        full_url = f"{theater['url']}?date={date}"
        html_content = ""
        try:
            # Use domcontentloaded instead of load - Fandango's ads/tracking prevent networkidle
            await page.goto(full_url, timeout=config.SCRAPER_NAV_TIMEOUT_LONG, wait_until="domcontentloaded")
            # Wait for the showtime structure to render (JS needs time to hydrate)
            try:
                await page.locator('li.shared-movie-showtimes, a.showtime-btn').first.wait_for(timeout=config.SCRAPER_ELEMENT_WAIT)
            except Exception:
                # If showtime elements not found, wait a bit for JS to render and try again
                import asyncio
                await asyncio.sleep(config.SCRAPER_RETRY_DELAY)
                # Check if we have any content at all
                showtime_count = await page.locator('li.shared-movie-showtimes').count()
                if showtime_count == 0:
                    logger.warning(f"No showtime elements found for {theater['name']} after waiting")

            html_content = await page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            showings = []
            
            # New Fandango structure uses li.shared-movie-showtimes
            movie_blocks = soup.select('li.shared-movie-showtimes')
            
            if not movie_blocks and html_content:
                # Always save debug HTML when no movies found — helps diagnose scraper issues
                try:
                    os.makedirs(DEBUG_DIR, exist_ok=True)
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"debug_{self._sanitize_filename(theater['name'])}_{timestamp}.html"
                    filepath = os.path.join(DEBUG_DIR, filename)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    logger.debug(f"No films found for {theater['name']}. Saved HTML snapshot to {filepath}")
                except Exception as e:
                    logger.debug(f"Failed to save HTML snapshot for {theater['name']}: {e}")
            
            for movie_block in movie_blocks:
                # Get film title from new structure
                film_title_elem = movie_block.select_one('h3.shared-movie-showtimes__movie-title a')
                film_title = film_title_elem.get_text(strip=True) if film_title_elem else "Unknown Title"

                # Strip standard format indicators from title - "(2D)" is standard and shouldn't be in title
                import re
                film_title = re.sub(r'\s*\(2D\)\s*$', '', film_title, flags=re.IGNORECASE)
                film_title = re.sub(r'\s*-\s*2D\s*$', '', film_title, flags=re.IGNORECASE)
                film_title = re.sub(r'\s+2D\s*$', '', film_title, flags=re.IGNORECASE)
                film_title = film_title.strip()


                # NEW STRUCTURE: Loop through format groups (each group = one format with its showtimes)
                # Each movie can have multiple formats (Standard, IMAX, UltraScreen, etc.)
                # First, get the showtimes section, then get amenity groups from there (prevents finding nested/duplicate groups)
                showtimes_section = movie_block.select_one('section.shared-movie-showtimes__showtimes')
                if not showtimes_section:
                    # Fallback if structure is different
                    showtimes_section = movie_block

                # Get amenity groups - these should be direct children of the showtimes section
                amenity_groups = [child for child in showtimes_section.find_all('section', class_='shared-showtimes__amenity-group', recursive=False)]

                # If no direct children found, try deeper search as fallback
                if not amenity_groups:
                    amenity_groups = showtimes_section.select('section.shared-showtimes__amenity-group')

                # DEBUG: Track all showtimes across all amenity groups to detect combined formats
                # (e.g., same showtime appearing in both "3D" and "Premium Format" groups)
                from collections import defaultdict
                time_to_formats = defaultdict(list)  # Maps showtime -> list of formats

                # First pass: collect all times and their formats
                for amenity_group in amenity_groups:
                    format_title_elem = amenity_group.select_one('h4.shared-showtimes__title')
                    movie_format = format_title_elem.get_text(strip=True) if format_title_elem else "2D"

                    showtime_links = amenity_group.select('a.showtime-btn')
                    for link in showtime_links:
                        # Extract time from aria-label
                        aria_label = link.get('aria-label', '')
                        time_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:o\'clock\s*)?(?:AM|PM|am|pm))', aria_label, re.IGNORECASE)

                        if time_match:
                            time_str = time_match.group(1).replace("o'clock", "").strip()
                            time_str = re.sub(r'\s+', '', time_str)  # Normalize
                            if not ':' in time_str:
                                time_str = re.sub(r'(\d{1,2})(am|pm)', r'\1:00\2', time_str, flags=re.IGNORECASE)
                            time_to_formats[time_str].append(movie_format)

                # DEBUG: Log amenity group count and detect combined formats for first movie
                if len(showings) == 0:
                    logger.debug(f"Movie '{film_title}' has {len(amenity_groups)} amenity groups")
                    logger.debug(f"Showtimes section found: {showtimes_section is not movie_block}")
                    for idx, ag in enumerate(amenity_groups):
                        fmt_elem = ag.select_one('h4.shared-showtimes__title')
                        fmt_text = fmt_elem.get_text(strip=True) if fmt_elem else "NO TITLE"
                        btn_count = len(ag.select('a.showtime-btn'))
                        logger.debug(f"Group {idx+1}: '{fmt_text}' with {btn_count} buttons")

                    # Check for combined formats (same time in multiple groups)
                    combined = {time: fmts for time, fmts in time_to_formats.items() if len(fmts) > 1}
                    if combined:
                        logger.debug(f"Found {len(combined)} showtimes with combined formats:")
                        for time, fmts in sorted(combined.items()):
                            logger.debug(f"{time}: {fmts}")
                    else:
                        logger.debug(f"No combined formats detected (each showtime in only one group)")

                # Second pass: process amenity groups and combine formats when needed
                for amenity_group in amenity_groups:
                    # Extract the format from the h4 title element
                    format_title_elem = amenity_group.select_one('h4.shared-showtimes__title')
                    if format_title_elem:
                        movie_format = format_title_elem.get_text(strip=True)
                    else:
                        movie_format = "2D"  # Default fallback

                    # Get all showtime buttons within this specific format group
                    showtime_links = amenity_group.select('a.showtime-btn')

                    for link in showtime_links:
                        # Extract time from aria-label (e.g., "Buy tickets for 7 o'clock PM showtime")
                        aria_label = link.get('aria-label', '')
                        time_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:o\'clock\s*)?(?:AM|PM|am|pm))', aria_label, re.IGNORECASE)

                        if time_match:
                            time_str = time_match.group(1).replace("o'clock", "").strip()
                            # Normalize time format
                            time_str = re.sub(r'\s+', '', time_str)  # Remove spaces
                            if not ':' in time_str:
                                # Add :00 if missing minutes
                                time_str = re.sub(r'(\d{1,2})(am|pm)', r'\1:00\2', time_str, flags=re.IGNORECASE)
                        else:
                            # Fallback: try to find time in button text
                            time_label_elem = link.select_one('.showtime-btn-label')
                            time_str = time_label_elem.get_text(strip=True) if time_label_elem else link.get_text(strip=True)

                        href = link.get('href')
                        if href and isinstance(href, str):
                            # Handle both full URLs and relative paths
                            if href.startswith('http'):
                                ticket_url = href
                            elif 'jump.aspx' in href:
                                ticket_url_suffix = href.split('jump.aspx')[-1]
                                ticket_url = "https://tickets.fandango.com/transaction/ticketing/mobile/jump.aspx" + ticket_url_suffix
                            else:
                                ticket_url = "https://tickets.fandango.com" + href

                            if film_title != "Unknown Title" and time_str and ticket_url:
                                # Validate time format
                                if re.match(r'\d{1,2}:\d{2}\s*[ap]m?', time_str, re.IGNORECASE):
                                    showings.append({
                                        "film_title": film_title,
                                        "format": movie_format,
                                        "showtime": time_str,
                                        "daypart": self._classify_daypart(time_str),
                                        "ticket_url": ticket_url
                                    })
            
            logger.info(f"Found {len(showings)} showings for {theater['name']}")
            return showings
        except Exception as e:
            logger.exception(f"Failed to get movies for {theater['name']}")
            return []

    async def _get_prices_and_capacity(self, page, showing_details):
        showtime_url = showing_details['ticket_url']
        results = {"tickets": [], "capacity": "N/A", "error": None}
        try:
            logger.info(f"Loading ticket URL: {showtime_url[:80]}...")
            await page.goto(showtime_url, timeout=config.SCRAPER_NAV_TIMEOUT_LONG)
            logger.debug(f"Page loaded, waiting for dynamic content...")
            await page.wait_for_timeout(int(config.SCRAPER_RENDER_DELAY_LONG * 1000))

            logger.debug(f"Searching for pricing data...")
            scripts = await page.query_selector_all('script')
            found_commerce = False

            for script in scripts:
                content = await script.inner_html()
                if content and 'window.Commerce.models' in content:
                    found_commerce = True
                    logger.debug(f"Found window.Commerce.models")

                    start_text = 'window.Commerce.models = '
                    start_index = content.find(start_text)
                    if start_index != -1:
                        json_start = content.find('{', start_index)
                        open_braces, json_end = 0, -1
                        for i in range(json_start, len(content)):
                            if content[i] == '{': open_braces += 1
                            elif content[i] == '}': open_braces -= 1
                            if open_braces == 0:
                                json_end = i + 1; break
                        if json_end != -1:
                            data = json.loads(content[json_start:json_end])
                            logger.debug(f"Parsed JSON successfully")

                            ticket_types = data.get('tickets', {}).get('seatingAreas', [{}])[0].get('ticketTypes', [])
                            logger.debug(f"Found {len(ticket_types)} ticket types")

                            for tt in ticket_types:
                                description, price = tt.get('description'), tt.get('price')
                                if description and price is not None:
                                    parsed_ticket = self._parse_ticket_description(description)
                                    results["tickets"].append({
                                        "type": parsed_ticket["base_type"],
                                        "price": f"${price:.2f}",
                                        "amenities": parsed_ticket["amenities"]
                                    })

                            seating_info = data.get('seating', {})
                            total_seats = seating_info.get('totalSeats')
                            available_seats = seating_info.get('availableSeats')
                            if available_seats is not None and total_seats is not None:
                                results["capacity"] = f"{available_seats} / {total_seats}"

                            if results["tickets"]:
                                logger.info(f"Successfully extracted {len(results['tickets'])} prices")
                                return results

            if not found_commerce:
                logger.warning(f"window.Commerce.models not found on page!")
                results["error"] = "window.Commerce.models not found"

        except Exception as e:
            logger.error(f"Scraping error: {e}")
            import traceback
            traceback.print_exc()
            results["error"] = f'Scraping failed: {e}'
        return results

    async def get_all_showings_for_theaters(self, theaters, date):
        """Get all movie showings for given theaters on a specific date.
        
        This method creates a custom span for telemetry tracking with business metrics.
        """
        with tracer.start_as_current_span(
            "scraper.get_all_showings_for_theaters",
            attributes={
                "scraper.theater_count": len(theaters),
                "scraper.date": str(date)
            }
        ) as span:
            try:
                showings_by_theater = {}
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    for theater in theaters:
                        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
                        page = await context.new_page()
                        showings = await self._get_movies_from_theater_page(page, theater, date)
                        showings_by_theater[theater['name']] = showings
                        await context.close()
                
                # Add business metrics to span
                total_showings = sum(len(shows) for shows in showings_by_theater.values())
                span.set_attribute("scraper.total_showings_found", total_showings)
                span.set_attribute("scraper.theaters_processed", len(showings_by_theater))
                
                return showings_by_theater
            except Exception as e:
                span.set_attribute("scraper.error", str(e))
                span.set_attribute("scraper.error_type", type(e).__name__)
                raise

    async def scrape_details(self, theaters, selected_showtimes, status_container=None, progress_callback=None):
        """Scrape detailed pricing information for selected showtimes.

        This method creates a custom span for telemetry tracking with business metrics.

        Args:
            theaters: List of theater dicts with 'name' and 'url'
            selected_showtimes: Dict of {date: {theater_name: {film: {showtime: [showing_info]}}}}
            status_container: Legacy Streamlit container (deprecated)
            progress_callback: Optional callable(current, total) to report progress
        """
        with tracer.start_as_current_span(
            "scraper.scrape_details",
            attributes={
                "scraper.theater_count": len(theaters),
                "scraper.date_count": len(selected_showtimes)
            }
        ) as span:
            try:
                all_price_data = []
                showings_to_scrape = []

                logger.info(f"Building showings list...")
                logger.debug(f"selected_showtimes structure: {list(selected_showtimes.keys())}")

                # selected_showtimes has structure: {date: {theater_name: {film_title: {showtime: [showing_info_list]}}}}
                # We need to iterate through dates first to find the theater data
                for date_str, daily_selections in selected_showtimes.items():
                    logger.debug(f"Processing date: {date_str}")
                    for theater in theaters:
                        theater_name = theater['name']
                        if theater_name in daily_selections:
                            logger.debug(f"Found theater '{theater_name}' in selections for {date_str}")
                            for film, times in daily_selections[theater_name].items():
                                for time_str, showing_info_list in times.items():
                                    for showing_info in showing_info_list:
                                        showings_to_scrape.append({**showing_info, "theater_name": theater_name})

                logger.info(f"Starting price scrape for {len(showings_to_scrape)} showings")
                span.set_attribute("scraper.showings_to_scrape", len(showings_to_scrape))

                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)  # Back to headless for production
                    total_showings = len(showings_to_scrape)
                    for idx, showing in enumerate(showings_to_scrape, 1):
                        logger.info(f"Processing showing {idx}/{total_showings}: {showing['film_title']} at {showing.get('theater_name', 'Unknown')}")
                        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
                        page = await context.new_page()
                        scrape_results = await self._get_prices_and_capacity(page, showing)
                        await context.close()

                        # Report progress if callback provided
                        if progress_callback:
                            try:
                                progress_callback(idx, total_showings)
                            except Exception as cb_err:
                                logger.warning(f"Progress callback error: {cb_err}")
                        else:
                            logger.debug(f"No progress callback provided")

                        if scrape_results["error"]:
                            logger.error(f"Scraping {showing['film_title']} at {showing.get('theater_name', 'Unknown')}: {scrape_results['error']}")
                            continue
                        
                        for ticket in scrape_results['tickets']:
                            initial_format = showing['format']
                            final_amenities = ticket['amenities']
                            combined_format_list = [initial_format] + final_amenities
                            unique_formats = sorted(list(set(combined_format_list)))
                            if len(unique_formats) > 1 and "2D" in unique_formats:
                                unique_formats.remove("2D")

                            price_point = {
                                # snake_case keys for React frontend compatibility
                                "theater_name": showing['theater_name'], "film_title": showing['film_title'],
                                "format": ", ".join(unique_formats), "showtime": showing['showtime'],
                                "daypart": showing['daypart'], "ticket_type": ticket['type'], "price": ticket['price'],
                                "capacity": scrape_results.get('capacity', 'N/A'),
                                # Also include title case for backward compatibility with Streamlit
                                "Theater Name": showing['theater_name'], "Film Title": showing['film_title'],
                                "Format": ", ".join(unique_formats), "Showtime": showing['showtime'],
                                "Daypart": showing['daypart'], "Ticket Type": ticket['type'], "Price": ticket['price'],
                                "Capacity": scrape_results.get('capacity', 'N/A')
                            }
                            all_price_data.append(price_point)

                # Add business metrics to span
                span.set_attribute("scraper.price_points_collected", len(all_price_data))
                span.set_attribute("scraper.showings_scraped", len(showings_to_scrape))
                
                # Track unique films
                unique_films = set(price['film_title'] for price in all_price_data)
                span.set_attribute("scraper.unique_films", len(unique_films))

                return all_price_data, showings_to_scrape
            except Exception as e:
                span.set_attribute("scraper.error", str(e))
                span.set_attribute("scraper.error_type", type(e).__name__)
                raise

    async def run_diagnostic_scrape(self, markets_to_test, date):
        diagnostic_results = []
        theaters_to_test = []
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        for market_name in markets_to_test:
            theaters = cache.get("markets", {}).get(market_name, {}).get("theaters", [])
            for theater in theaters:
                theater['market'] = market_name
                theaters_to_test.append(theater)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            for i, theater in enumerate(theaters_to_test):
                logger.info(f"Testing {i+1}/{len(theaters_to_test)}: {theater['name']}")
                context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
                page = await context.new_page()
                result_row = {"Market": theater['market'], "Theater Name": theater['name'], "Status": "Failed", "Details": "No showtimes found", "Sample Price": "N/A"}
                try:
                    showings = await self._get_movies_from_theater_page(page, theater, date)
                    if showings:
                        first_showing = showings[0]
                        price_results = await self._get_prices_and_capacity(page, first_showing)
                        if price_results['tickets']:
                            first_ticket = price_results['tickets'][0]
                            result_row.update({
                                "Status": "Success",
                                "Details": f"Scraped '{first_showing['film_title']}' at {first_showing['showtime']}",
                                "Sample Price": f"{first_ticket['type']}: {first_ticket['price']}"
                            })
                        else:
                            result_row["Details"] = "Failed to extract price from ticket page."
                    diagnostic_results.append(result_row)
                except Exception as e:
                    result_row["Details"] = f"An unexpected error occurred: {str(e)}"
                    diagnostic_results.append(result_row)
                finally:
                    await context.close()
        return diagnostic_results