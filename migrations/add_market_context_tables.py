"""
Migration script to add TheaterMetadata and MarketEvent tables.
"""
import os
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db_session import get_engine
from app.db_models import Base, TheaterMetadata, MarketEvent

def migrate():
    print("Starting migration: Add Market Context and Geospatial Tables")
    engine = get_engine()
    
    # We use Base.metadata.create_all which will only create missing tables
    # For safety in production, we check each table individually
    from sqlalchemy import inspect
    inspector = inspect(engine)
    
    existing_tables = inspector.get_table_names(schema=TheaterMetadata.__table_args__[0].get('schema') if hasattr(TheaterMetadata, '__table_args__') and isinstance(TheaterMetadata.__table_args__[0], dict) else None)
    
    tables_to_create = []
    if 'theater_metadata' not in existing_tables:
        tables_to_create.append(TheaterMetadata.__table__)
        print(" - Prepared table: theater_metadata")
    else:
        print(" - Table theater_metadata already exists")
        
    if 'market_events' not in existing_tables:
        tables_to_create.append(MarketEvent.__table__)
        print(" - Prepared table: market_events")
    else:
        print(" - Table market_events already exists")

    if tables_to_create:
        Base.metadata.create_all(engine, tables=tables_to_create)
        print("Migration COMPLETED successfully.")
    else:
        print("Nothing to migrate.")

if __name__ == "__main__":
    migrate()
