"""
Market Context Service
Manages theater metadata (geospatial) and market events.
"""
import logging
import os
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.db_session import get_session
from app.db_models import TheaterMetadata, MarketEvent, Company, TheaterOperatingHours
from enttelligence_client import EntTelligenceClient
from app import config

import time
from urllib.parse import quote
import requests

class MarketContextService:
    def __init__(self):
        self._ent_client = None
        self._user_agent = "PriceScout-MarketContext/1.0"

    def _get_ent_client(self) -> EntTelligenceClient:
        if self._ent_client is None:
            self._ent_client = EntTelligenceClient()
            token_name = os.getenv("ENTTELLIGENCE_TOKEN_NAME", "PriceScoutAzure")
            token_secret = os.getenv("ENTTELLIGENCE_TOKEN_SECRET", "")
            if token_secret and self._ent_client.login(token_name, token_secret):
                pass
            else:
                logger.warning("Could not authenticate with EntTelligence for Market Context")
        return self._ent_client

    def get_theaters_metadata(self, company_id: int) -> List[TheaterMetadata]:
        with get_session() as session:
            return session.query(TheaterMetadata).filter_by(company_id=company_id).all()

    def get_market_events(self, company_id: int, start_date: datetime, end_date: datetime, market: Optional[str] = None) -> List[MarketEvent]:
        with get_session() as session:
            query = session.query(MarketEvent).filter(
                MarketEvent.company_id == company_id,
                or_(
                    and_(MarketEvent.start_date <= end_date, MarketEvent.end_date >= start_date),
                    and_(MarketEvent.start_date >= start_date, MarketEvent.start_date <= end_date)
                )
            )
            
            if market:
                query = query.filter(or_(MarketEvent.scope == 'global', MarketEvent.scope_value == market))
            
            return query.all()

    def get_theater_operating_hours(self, company_id: int, theater_name: str) -> List[TheaterOperatingHours]:
        """Get configured operating hours for a specific theater"""
        with get_session() as session:
            return session.query(TheaterOperatingHours).filter_by(
                company_id=company_id,
                theater_name=theater_name
            ).order_by(TheaterOperatingHours.day_of_week).all()

    def update_theater_operating_hours(self, company_id: int, theater_name: str, hours_list: List[Dict[str, Any]]):
        """Update or create operating hours configuration for a theater"""
        with get_session() as session:
            for h_data in hours_list:
                day = h_data.get('day_of_week')
                if day is None: continue
                
                oh = session.query(TheaterOperatingHours).filter_by(
                    company_id=company_id,
                    theater_name=theater_name,
                    day_of_week=day
                ).first()
                
                if not oh:
                    oh = TheaterOperatingHours(
                        company_id=company_id,
                        theater_name=theater_name,
                        day_of_week=day
                    )
                    session.add(oh)
                
                oh.open_time = h_data.get('open_time')
                oh.close_time = h_data.get('close_time')
                oh.first_showtime = h_data.get('first_showtime')
                oh.last_showtime = h_data.get('last_showtime')
            
            session.commit()
            return True

    def geocode_address(self, address: str) -> Optional[Dict[str, float]]:
        """
        Geocodes an address using Nominatim (OpenStreetMap).
        """
        if not address:
            return None
            
        try:
            url = f"https://nominatim.openstreetmap.org/search?q={quote(address)}&format=json&limit=1"
            headers = {"User-Agent": self._user_agent}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data and len(data) > 0:
                return {
                    "lat": float(data[0]["lat"]),
                    "lon": float(data[0]["lon"])
                }
        except Exception as e:
            logger.error(f"Geocoding failed for {address}: {e}")
            
        return None

    def sync_theaters_from_enttelligence(self, company_id: int, theater_names: List[str]) -> Dict[str, Any]:
        """
        Fetches metadata for theaters from EntTelligence and updates local cache.
        Also geocodes addresses if coordinates are missing.
        """
        client = self._get_ent_client()
        if not client or not client.token:
            return {"status": "error", "message": "EntTelligence client not authenticated"}

        processed = 0
        updated = 0
        geocoded = 0
        errors = 0
        
        try:
            logger.info(f"Synchronizing context for {len(theater_names)} theaters...")
            
            with get_session() as session:
                for name in theater_names:
                    # Fetch individually for maximum reliability
                    try:
                        ent_results = client.get_theaters(theater_names=[name])
                        if not ent_results:
                            # logger.warning(f"No EntTelligence data for '{name}'")
                            continue
                        
                        ent_t = ent_results[0]
                        processed += 1
                        
                        meta = session.query(TheaterMetadata).filter_by(
                            company_id=company_id,
                            theater_name=name
                        ).first()
                        
                        if not meta:
                            meta = TheaterMetadata(
                                company_id=company_id,
                                theater_name=name
                            )
                            session.add(meta)
                        
                        # Update metadata
                        meta.address = ent_t.get('address')
                        meta.city = ent_t.get('city')
                        meta.state = ent_t.get('state')
                        meta.zip_code = ent_t.get('zip')
                        meta.market = ent_t.get('dma')
                        meta.circuit_name = ent_t.get('circuit_name')
                        
                        # Geocode if coordinates are missing
                        if not meta.latitude or not meta.longitude:
                            addr_parts = [meta.address, meta.city, meta.state]
                            if meta.zip_code and meta.zip_code != 'None':
                                addr_parts.append(meta.zip_code)
                            
                            full_address = ", ".join([p for p in addr_parts if p])
                            if full_address:
                                coords = self.geocode_address(full_address)
                                if coords:
                                    meta.latitude = coords["lat"]
                                    meta.longitude = coords["lon"]
                                    meta.last_geocode_at = datetime.now(UTC)
                                    geocoded += 1
                                # Respect Nominatim rate limits
                                time.sleep(1)
                        
                        updated += 1
                    except Exception as e:
                        logger.error(f"Failed to sync '{name}': {e}")
                        errors += 1
                
                session.commit()
                
            return {
                "status": "success",
                "processed": processed,
                "updated": updated,
                "geocoded": geocoded,
                "errors": errors
            }
        except Exception as e:
            return {"status": "error", "message": f"Sync failed: {str(e)}"}

    def populate_default_events(self, company_id: int):
        """
        Populates default market events if they don't exist.
        """
        from datetime import date, timedelta
        
        today = date.today()
        # Seed some upcoming events for demo purposes
        # In a real app, this would pull from a global holidays provider or similar
        default_events = [
            {
                "name": "Martin Luther King Jr. Day",
                "type": "holiday",
                "start": date(today.year, 1, 19), # 2026 date
                "end": date(today.year, 1, 19),
                "scope": "global",
                "score": 8,
                "desc": "Federal holiday, strong family matinee potential."
            },
            {
                "name": "Valentine's Day Weekend",
                "type": "event",
                "start": date(today.year, 2, 13),
                "end": date(today.year, 2, 15),
                "scope": "global",
                "score": 7,
                "desc": "Date night peak, impact on romance and rom-com titles."
            },
            {
                "name": "Presidents' Day",
                "type": "holiday",
                "start": date(today.year, 2, 16),
                "end": date(today.year, 2, 16),
                "scope": "global",
                "score": 8,
                "desc": "School holiday, high daytime occupancy."
            }
        ]
        
        with get_session() as session:
            for e_data in default_events:
                exists = session.query(MarketEvent).filter_by(
                    company_id=company_id,
                    event_name=e_data["name"],
                    start_date=e_data["start"]
                ).first()
                
                if not exists:
                    event = MarketEvent(
                        company_id=company_id,
                        event_name=e_data["name"],
                        event_type=e_data["type"],
                        start_date=e_data["start"],
                        end_date=e_data["end"],
                        scope=e_data["scope"],
                        impact_score=e_data["score"],
                        description=e_data["desc"]
                    )
                    session.add(event)
            session.commit()

# Singleton
_market_context_service = MarketContextService()

def get_market_context_service() -> MarketContextService:
    return _market_context_service
