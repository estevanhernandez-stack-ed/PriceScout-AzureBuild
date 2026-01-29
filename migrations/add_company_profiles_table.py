"""
Migration script to add CompanyProfile table.

Run with:
    python migrations/add_company_profiles_table.py
"""
import os
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db_session import get_engine
from app.db_models import Base, CompanyProfile

def migrate():
    print("Starting migration: Add CompanyProfile table")
    engine = get_engine()

    # Check if table already exists
    from sqlalchemy import inspect
    inspector = inspect(engine)

    # Get existing tables
    existing_tables = inspector.get_table_names()

    tables_to_create = []
    if 'company_profiles' not in existing_tables:
        tables_to_create.append(CompanyProfile.__table__)
        print(" - Prepared table: company_profiles")
    else:
        print(" - Table company_profiles already exists")

    if tables_to_create:
        Base.metadata.create_all(engine, tables=tables_to_create)
        print("Migration COMPLETED successfully.")
    else:
        print("Nothing to migrate.")

if __name__ == "__main__":
    migrate()
