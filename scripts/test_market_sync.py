import requests
import json
import os

def test_sync():
    # Use /api/v1/auth/token with form data
    url = "http://localhost:8000/api/v1/market-context/sync/theaters"
    auth_url = "http://localhost:8000/api/v1/auth/token"
    
    # admin/admin123 confirmed created
    login_data = {"username": "admin", "password": "admin123"}
    
    try:
        print(f"Logging in to {auth_url}...")
        r = requests.post(auth_url, data=login_data) # 'data' for form-encoded
        if r.status_code != 200:
            print(f"Login failed: {r.status_code} - {r.text}")
            return
            
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        print("Triggering sync for sample theaters...")
        # Endpoints expect JSON list
        sync_data = ["Marcus Ridge Cinema", "Movie Tavern Brookfield", "Marcus Point Cinemas"]
        r = requests.post(url, json=sync_data, headers=headers)
        if r.status_code != 200:
            print(f"Sync failed: {r.status_code} - {r.text}")
            return
            
        print(f"Sync Result: {json.dumps(r.json(), indent=2)}")
        
        print("\nFetching metadata...")
        r = requests.get("http://localhost:8000/api/v1/market-context/theaters", headers=headers)
        r.raise_for_status()
        theaters = r.json()
        print(f"Found {len(theaters)} theaters in metadata table.")
        for t in theaters:
            if t['theater_name'] in sync_data:
                print(f" - {t['theater_name']}: {t['address']}, {t['city']}, {t['state']}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_sync()
