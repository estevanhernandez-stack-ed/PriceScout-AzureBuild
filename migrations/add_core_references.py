"""
Migration: Add core schema reference columns to PriceScout tables.

Links PriceScout's app-specific tables to the shared core.* schema in
TheatreOperationsDB, fulfilling Accords requirements R3.2, R3.4, R3.5.

New columns (all nullable, non-breaking):
  - competitive.companies.core_division_id   → core.Divisions.Id
  - competitive.users.core_personnel_id      → core.Personnel.Id
  - competitive.theater_metadata.competitor_location_id → core.CompetitorLocations.Id

Usage:
  python -m migrations.add_core_references --dry-run    # Preview SQL
  python -m migrations.add_core_references              # Execute migration
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db_session import get_session, engine
from sqlalchemy import text, inspect


SCHEMA = os.getenv('DB_SCHEMA', 'competitive')


def detect_db_type():
    url = str(engine.url)
    if 'sqlite' in url:
        return 'sqlite'
    if 'mssql' in url or 'pyodbc' in url:
        return 'mssql'
    if 'postgres' in url:
        return 'postgresql'
    return 'unknown'


# Column additions (schema-aware for MSSQL, plain for SQLite/PostgreSQL)
COLUMNS = [
    {
        'table': 'companies',
        'column': 'core_division_id',
        'type': 'INT',
        'description': 'FK to core.Divisions.Id',
    },
    {
        'table': 'users',
        'column': 'core_personnel_id',
        'type': 'INT',
        'description': 'FK to core.Personnel.Id',
    },
    {
        'table': 'theater_metadata',
        'column': 'competitor_location_id',
        'type': 'INT',
        'description': 'FK to core.CompetitorLocations.Id',
    },
]

# FK constraints (MSSQL only — core schema must exist)
FK_CONSTRAINTS = [
    {
        'table': 'companies',
        'column': 'core_division_id',
        'ref_table': 'core.Divisions',
        'ref_column': 'Id',
        'constraint': 'FK_companies_core_divisions',
    },
    {
        'table': 'users',
        'column': 'core_personnel_id',
        'ref_table': 'core.Personnel',
        'ref_column': 'Id',
        'constraint': 'FK_users_core_personnel',
    },
    {
        'table': 'theater_metadata',
        'column': 'competitor_location_id',
        'ref_table': 'core.CompetitorLocations',
        'ref_column': 'Id',
        'constraint': 'FK_theater_metadata_core_competitors',
    },
]

# Auto-mapping queries (MSSQL only)
AUTO_MAP_QUERIES = [
    {
        'description': 'Map companies to core.Divisions by name match',
        'sql': f"""
            UPDATE {SCHEMA}.companies
            SET core_division_id = d.Id
            FROM core.Divisions d
            WHERE {SCHEMA}.companies.company_name LIKE '%' + d.Name + '%'
              AND {SCHEMA}.companies.core_division_id IS NULL
        """,
    },
]


def column_exists(inspector, table_name, column_name):
    """Check if a column already exists in a table."""
    try:
        columns = inspector.get_columns(table_name, schema=SCHEMA)
        return any(c['name'] == column_name for c in columns)
    except Exception:
        # SQLite doesn't support schema parameter
        try:
            columns = inspector.get_columns(table_name)
            return any(c['name'] == column_name for c in columns)
        except Exception:
            return False


def run_migration(dry_run=False):
    db_type = detect_db_type()
    print(f"Database type: {db_type}")
    print(f"Schema: {SCHEMA}")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print("=" * 60)

    insp = inspect(engine)

    # Step 1: Add columns
    print("\n--- Step 1: Add Columns ---")
    for col_def in COLUMNS:
        table = col_def['table']
        column = col_def['column']
        col_type = col_def['type']

        if column_exists(insp, table, column):
            print(f"  SKIP: {table}.{column} already exists")
            continue

        if db_type == 'sqlite':
            sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
        elif db_type == 'mssql':
            sql = f"ALTER TABLE {SCHEMA}.{table} ADD {column} {col_type} NULL"
        else:
            sql = f"ALTER TABLE {SCHEMA}.{table} ADD COLUMN {column} {col_type}"

        print(f"  ADD: {table}.{column} ({col_def['description']})")
        print(f"       SQL: {sql}")

        if not dry_run:
            with engine.begin() as conn:
                conn.execute(text(sql))
            print(f"       DONE")

    # Step 2: Add FK constraints (MSSQL only)
    if db_type == 'mssql':
        print("\n--- Step 2: Add FK Constraints ---")
        for fk_def in FK_CONSTRAINTS:
            table = fk_def['table']
            constraint = fk_def['constraint']
            column = fk_def['column']
            ref = f"{fk_def['ref_table']}({fk_def['ref_column']})"

            # Check if constraint already exists
            check_sql = f"""
                SELECT 1 FROM sys.foreign_keys
                WHERE name = '{constraint}'
            """

            with engine.connect() as conn:
                result = conn.execute(text(check_sql)).fetchone()
                if result:
                    print(f"  SKIP: {constraint} already exists")
                    continue

            sql = f"""
                ALTER TABLE {SCHEMA}.{table}
                ADD CONSTRAINT {constraint}
                FOREIGN KEY ({column}) REFERENCES {ref} ON DELETE SET NULL
            """

            print(f"  FK: {SCHEMA}.{table}.{column} → {ref}")
            print(f"      Constraint: {constraint}")

            if not dry_run:
                with engine.begin() as conn:
                    conn.execute(text(sql))
                print(f"      DONE")
    else:
        print(f"\n--- Step 2: FK Constraints skipped (requires MSSQL with core schema) ---")

    # Step 3: Auto-map existing data (MSSQL only)
    if db_type == 'mssql':
        print("\n--- Step 3: Auto-Map Existing Data ---")
        for mapping in AUTO_MAP_QUERIES:
            print(f"  {mapping['description']}")
            if not dry_run:
                with engine.begin() as conn:
                    result = conn.execute(text(mapping['sql']))
                    print(f"      Rows updated: {result.rowcount}")
            else:
                print(f"      SQL: {mapping['sql'].strip()}")
    else:
        print(f"\n--- Step 3: Auto-mapping skipped (requires MSSQL with core schema) ---")

    print("\n" + "=" * 60)
    if dry_run:
        print("DRY RUN complete. No changes made.")
    else:
        print("Migration complete.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Add core schema references to PriceScout tables')
    parser.add_argument('--dry-run', action='store_true', help='Preview SQL without executing')
    args = parser.parse_args()
    run_migration(dry_run=args.dry_run)
