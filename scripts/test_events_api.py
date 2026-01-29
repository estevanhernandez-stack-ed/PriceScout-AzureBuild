import requests
import json
from datetime import date, timedelta

def test_events():
    auth_url = "http://localhost:8000/api/v1/auth/token"
    login_data = {"username": "admin", "password": "admin123"}
    
    try:
        r = requests.post(auth_url, data=login_data)
        r.raise_for_status()
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        today = date.today()
        start = today - timedelta(days=30)
        end = today + timedelta(days=60)
        
        print(f"Fetching events from {start} to {end}...")
        url = f"http://localhost:8000/api/v1/market-context/events?start_date={start}&end_date={end}"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        events = r.json()
        
        print(f"Found {len(events)} events:")
        for e in events:
            print(f" - {e['event_name']} ({e['start_date']} to {e['end_date']}): Type={e['event_type']}, Score={e['impact_score']}")
            if e.get('description'):
                print(f"   Desc: {e['description']}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_events()
