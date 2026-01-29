import requests
import json
import os

def sync_all():
    auth_url = "http://localhost:8000/api/v1/auth/token"
    login_data = {"username": "admin", "password": "admin123"}
    
    try:
        r = requests.post(auth_url, data=login_data)
        r.raise_for_status()
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        print("Triggering sync for ALL theaters...")
        sync_url = "http://localhost:8000/api/v1/market-context/sync/theaters"
        r = requests.post(sync_url, json=None, headers=headers)
        print(f"Sync Result: {json.dumps(r.json(), indent=2)}")
        res = r.json()
        print(f"Geocoded: {res.get('geocoded', 0)} new theaters.")
        
        print("\nFetching metadata summary...")
        r = requests.get("http://localhost:8000/api/v1/market-context/theaters", headers=headers)
        r.raise_for_status()
        theaters = r.json()
        print(f"Total theaters in metadata: {len(theaters)}")
        
        # Count by DMA/Market
        markets = {}
        for t in theaters:
            m = t.get('market') or 'Unknown'
            markets[m] = markets.get(m, 0) + 1
        
        print("\nTheaters by Market:")
        for m, count in sorted(markets.items(), key=lambda x: x[1], reverse=True):
            print(f" - {m}: {count}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    sync_all()
