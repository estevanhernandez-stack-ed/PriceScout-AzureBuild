"""
EntTelligence API Client
Wrapper for querying movie showtime and pricing data from Tableau-backed API
"""

import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json


class EntTelligenceClient:
    """Client for EntTelligence REST API (Tableau data wrapper)"""
    
    def __init__(self, base_url: str = "http://23.20.236.151:7582"):
        self.base_url = base_url
        self.token = None
        self.user_id = None
        self.token_expiry = None
        
    def login(self, token_name: str, token_secret: str, site: str = "enttelligence") -> bool:
        """
        Authenticate to API using Personal Access Token
        
        Args:
            token_name: PAT name (e.g., "PriceScout")
            token_secret: PAT secret from Tableau
            site: Site content URL (default: "enttelligence")
            
        Returns:
            bool: True if authentication successful
        """
        url = f"{self.base_url}/users/login"
        
        payload = {
            "credentials": {
                "personalAccessTokenName": token_name,
                "personalAccessTokenSecret": token_secret,
                "site": {"contentUrl": site}
            }
        }
        
        try:
            response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("success"):
                credentials = data["message"]["credentials"]
                self.token = credentials["token"]
                self.user_id = credentials["user"]["id"]
                
                # Parse expiry (format: "325:05:46")
                expiry_str = credentials.get("estimatedTimeToExpiration", "0:0:0")
                hours, mins, secs = map(int, expiry_str.split(":"))
                self.token_expiry = datetime.now() + timedelta(hours=hours, minutes=mins, seconds=secs)
                
                print(f"[OK] Authenticated successfully")
                print(f"     Token expires: {self.token_expiry.strftime('%Y-%m-%d %H:%M:%S')}")
                return True
            else:
                print(f"[ERR] Authentication failed: {data.get('message')}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"[ERR] Authentication error: {e}")
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication"""
        if not self.token or not self.user_id:
            raise ValueError("Not authenticated. Call login() first.")

        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-tableau-auth": self.token,
            "user_id": self.user_id
        }
    
    def get_showtimes_by_title(self, title: str, date: str, dbr: Optional[int] = None) -> List[Dict]:
        """
        Get all showtimes for a specific title and date
        
        Args:
            title: Movie title
            date: Date in YYYY-MM-DD format
            dbr: Days Before Release (optional, for filtering presales)
            
        Returns:
            List of showtime records with pricing and capacity
        """
        url = f"{self.base_url}/enttelligence/presales-showtime-movie_title/{title}/{date}"
        if dbr is not None:
            url += f"/{dbr}"
        
        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            
            data = response.json()
            return data.get("message", []) if data.get("success") else []
            
        except requests.exceptions.RequestException as e:
            print(f"[ERR] Error fetching showtimes: {e}")
            return []
    
    def get_theater_analysis(self, title: str) -> List[Dict]:
        """
        Get theater-level analysis for a title (aggregated per theater)
        
        Args:
            title: Movie title
            
        Returns:
            List of theater records with aggregated pricing/capacity
        """
        url = f"{self.base_url}/enttelligence/title-analysis-theater/{title}"
        
        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            
            data = response.json()
            return data.get("message", []) if data.get("success") else []
            
        except requests.exceptions.RequestException as e:
            print(f"[ERR] Error fetching theater analysis: {e}")
            return []
    
    def get_circuit_analysis(self, title: str) -> List[Dict]:
        """
        Get circuit-level analysis for a title
        
        Args:
            title: Movie title
            
        Returns:
            List of circuit records (Marcus Theatres, AMC, Regal, etc.)
        """
        url = f"{self.base_url}/enttelligence/title-analysis-circuit/{title}"
        
        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            
            data = response.json()
            return data.get("message", []) if data.get("success") else []
            
        except requests.exceptions.RequestException as e:
            print(f"[ERR] Error fetching circuit analysis: {e}")
            return []
    
    def get_market_analysis(self, title: str) -> List[Dict]:
        """
        Get market-level (DMA) analysis for a title
        
        Args:
            title: Movie title
            
        Returns:
            List of market records with aggregated data
        """
        url = f"{self.base_url}/enttelligence/title-analysis-market/{title}"
        
        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            
            data = response.json()
            return data.get("message", []) if data.get("success") else []
            
        except requests.exceptions.RequestException as e:
            print(f"[ERR] Error fetching market analysis: {e}")
            return []
    
    def get_programming_audit(self, start_date: str, end_date: Optional[str] = None, 
                             title: Optional[str] = None, movie_id: Optional[int] = None) -> List[Dict]:
        """
        Get programming audit (all showtimes) for a date range
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD), optional
            title: Filter by title, optional
            movie_id: Filter by movie_id, optional
            
        Returns:
            List of all showtime records in date range
        """
        url = f"{self.base_url}/enttelligence/programAuditSummaryByRange"
        
        payload = {
            "start_date": start_date
        }
        
        if end_date:
            payload["end_date"] = end_date
        if title:
            payload["title"] = title
        if movie_id:
            payload["movie_id"] = movie_id
        
        try:
            response = requests.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            
            data = response.json()
            return data.get("message", []) if data.get("success") else []
            
        except requests.exceptions.RequestException as e:
            print(f"[ERR] Error fetching programming audit: {e}")
            return []
    
    def get_movies(self, titles: Optional[List[str]] = None, 
                   imdb_ids: Optional[List[str]] = None,
                   movie_ids: Optional[List[int]] = None) -> List[Dict]:
        """
        Get movie metadata
        
        Args:
            titles: List of movie titles
            imdb_ids: List of IMDB IDs
            movie_ids: List of internal movie IDs
            
        Returns:
            List of movie records with metadata
        """
        url = f"{self.base_url}/enttelligence/titlesWithFilter"
        
        payload = {
            "titles": titles or [],
            "imdb_id": imdb_ids or [],
            "movie_ids": movie_ids or []
        }
        
        try:
            response = requests.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            
            data = response.json()
            return data.get("message", []) if data.get("success") else []
            
        except requests.exceptions.RequestException as e:
            print(f"[ERR] Error fetching movies: {e}")
            return []
    
    def get_theaters(self, theater_names: Optional[List[str]] = None,
                    theater_ids: Optional[List[int]] = None) -> List[Dict]:
        """
        Get theater metadata
        
        Args:
            theater_names: List of theater names
            theater_ids: List of theater IDs
            
        Returns:
            List of theater records with address, DMA, circuit
        """
        url = f"{self.base_url}/enttelligence/theatresWithFilter"
        
        payload = {
            "theaters": theater_names or [],
            "theater_ids": theater_ids or []
        }
        
        try:
            response = requests.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            
            data = response.json()
            return data.get("message", []) if data.get("success") else []
            
        except requests.exceptions.RequestException as e:
            print(f"[ERR] Error fetching theaters: {e}")
            return []


def main():
    """Test the API client"""
    
    # Credentials (from env or defaults)
    import os
    TOKEN_NAME = os.getenv("ENTTELLIGENCE_TOKEN_NAME", "PriceScoutAzure")
    TOKEN_SECRET = os.getenv("ENTTELLIGENCE_TOKEN_SECRET", "9bgGO/6JThSZOMJ1lcJyPg==:ZPROExrFNScatIFa7bAemM80KQEkpXBc")
    
    # Create client
    client = EntTelligenceClient()
    
    # Authenticate
    if not client.login(TOKEN_NAME, TOKEN_SECRET):
        print("Authentication failed")
        return
    
    print("\n" + "="*80)
    print("TESTING ENTTELLIGENCE API")
    print("="*80)
    
    # Test 1: Get showtimes for a title on a specific date
    print("\nTest 1: Get showtimes for 'Wicked' on 2025-12-10")
    showtimes = client.get_showtimes_by_title("Wicked", "2025-12-10")
    print(f"   Found {len(showtimes)} showtimes")
    if showtimes:
        print(f"   Sample: {showtimes[0]['theater_name']} - {showtimes[0]['time_sh']} - ${showtimes[0]['price_per_general']}")

    # Test 2: Get theater-level analysis
    print("\nTest 2: Theater analysis for 'Wicked'")
    theaters = client.get_theater_analysis("Wicked")
    print(f"   Found {len(theaters)} theaters")

    # Filter to Marcus theaters
    marcus_theaters = [t for t in theaters if 'Marcus' in t.get('theater_name', '') or 'Movie Tavern' in t.get('theater_name', '')]
    print(f"   Marcus theaters: {len(marcus_theaters)}")

    # Test 3: Get circuit analysis
    print("\nTest 3: Circuit analysis for 'Wicked'")
    circuits = client.get_circuit_analysis("Wicked")
    print(f"   Found {len(circuits)} circuits")
    for circuit in circuits[:5]:
        print(f"   - {circuit['circuit_name']}: {circuit['location_count']} locations, avg ${circuit.get('price_per_general', 0):.2f}")

    # Test 4: Get movie metadata
    print("\nTest 4: Get movie metadata")
    movies = client.get_movies(titles=["Wicked", "Gladiator II"])
    print(f"   Found {len(movies)} movies")
    for movie in movies:
        print(f"   - {movie['title']} ({movie['release_date']}) - {movie.get('rating', 'NR')} - {movie.get('runtime', 'N/A')} min")

    print("\n" + "="*80)
    print("API TEST COMPLETE")
    print("="*80)


if __name__ == "__main__":
    main()
