"""
Seed script for TheaterMetadata and MarketEvent tables.
"""
import os
import sys
from pathlib import Path
from datetime import date, timedelta

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db_adapter import get_session, TheaterMetadata, MarketEvent, Company

def seed():
    print("Seeding Market Context data...")
    with get_session() as session:
        # Get or create a company
        company = session.query(Company).first()
        if not company:
            print("Error: No company found to seed data for.")
            return
        
        # 1. Seed Theater Metadata
        theaters = [
            {"name": "Marcus Brookfield Movie Tavern", "city": "Brookfield", "state": "WI", "lat": 43.0389, "lon": -88.1065, "market": "Milwaukee"},
            {"name": "Marcus Ridge Cinema", "city": "New Berlin", "state": "WI", "lat": 43.0039, "lon": -88.1673, "market": "Milwaukee"},
            {"name": "Marcus Majestic Cinema of Brookfield", "city": "Brookfield", "state": "WI", "lat": 43.0130, "lon": -88.1750, "market": "Milwaukee"},
            {"name": "Movie Tavern Syracuse", "city": "Camillus", "state": "NY", "lat": 43.0392, "lon": -76.2524, "market": "Syracuse"},
            {"name": "Marcus Ronnie's Cinema + IMAX", "city": "St. Louis", "state": "MO", "lat": 38.5255, "lon": -90.3475, "market": "St. Louis"},
            {"name": "Movie Tavern Roswell", "city": "Roswell", "state": "GA", "lat": 34.0232, "lon": -84.3615, "market": "Atlanta"},
            {"name": "Marcus Point Cinemas", "city": "Madison", "state": "WI", "lat": 43.0731, "lon": -89.5185, "market": "Madison"},
            {"name": "Movie Tavern Aurora", "city": "Aurora", "state": "CO", "lat": 39.7294, "lon": -104.8319, "market": "Denver"},
        ]
        
        print(f"Adding {len(theaters)} theater metadata records...")
        for t in theaters:
            # Check if exists
            exists = session.query(TheaterMetadata).filter_by(
                company_id=company.company_id, 
                theater_name=t["name"]
            ).first()
            
            if not exists:
                meta = TheaterMetadata(
                    company_id=company.company_id,
                    theater_name=t["name"],
                    city=t["city"],
                    state=t["state"],
                    market=t["market"],
                    latitude=t["lat"],
                    longitude=t["lon"],
                    circuit_name="Marcus/Movie Tavern"
                )
                session.add(meta)
        
        # 2. Seed Market Events
        today = date.today()
        events = [
            {
                "name": "Martin Luther King Jr. Day",
                "type": "holiday",
                "start": today - timedelta(days=today.weekday() - 14), # Some date near today
                "end": today - timedelta(days=today.weekday() - 14),
                "scope": "global",
                "impact": 8
            },
            {
                "name": "Winter Storm Warning",
                "type": "weather",
                "start": today - timedelta(days=2),
                "end": today + timedelta(days=1),
                "scope": "market",
                "scope_val": "Milwaukee",
                "impact": 9,
                "desc": "Heavy snow expected, likely reducing morning attendance but boosting late evening 'Daily Lineup' if roads clear."
            },
            {
                "name": "Sundance Film Festival",
                "type": "festival",
                "start": today + timedelta(days=5),
                "end": today + timedelta(days=15),
                "scope": "global",
                "impact": 5,
                "desc": "Industry buzz event, impact on specialty film interest."
            },
            {
                "name": "Local School Winter Break",
                "type": "school_break",
                "start": today - timedelta(days=10),
                "end": today + timedelta(days=2),
                "scope": "market",
                "scope_val": "Madison",
                "impact": 7
            }
        ]
        
        print(f"Adding {len(events)} market events...")
        for e in events:
            # Check if exists
            exists = session.query(MarketEvent).filter_by(
                company_id=company.company_id,
                event_name=e["name"],
                start_date=e["start"]
            ).first()
            
            if not exists:
                event = MarketEvent(
                    company_id=company.company_id,
                    event_name=e["name"],
                    event_type=e["type"],
                    start_date=e["start"],
                    end_date=e["end"],
                    scope=e["scope"],
                    scope_value=e.get("scope_val"),
                    impact_score=e["impact"],
                    description=e.get("desc")
                )
                session.add(event)
        
        session.commit()
    print("Seeding COMPLETED successfully.")

if __name__ == "__main__":
    seed()
