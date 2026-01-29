"""
Migration: Add Circuit Presales Tracking

Creates circuit_presales table to track presale buildup and acceleration
across Top 12 circuits for competitive intelligence.

Usage:
    python migrations/add_circuit_presales.py
"""

import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = "pricescout.db"

def backup_database():
    """Create timestamped backup before migration"""
    if not Path(DB_PATH).exists():
        print(f"⚠️  Database not found: {DB_PATH}")
        return False
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"pricescout_backup_{timestamp}.db"
    
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return True

def create_circuit_presales_table():
    """Create circuit_presales table for nationwide presale tracking"""
    
    print("\n" + "="*70)
    print("🎟️  CIRCUIT PRESALES TRACKING MIGRATION")
    print("="*70)
    
    # Backup first
    if not backup_database():
        return False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Create circuit_presales table
        print("\n📊 Creating circuit_presales table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS circuit_presales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                circuit_name VARCHAR(255) NOT NULL,
                film_title VARCHAR(500) NOT NULL,
                release_date DATE NOT NULL,
                snapshot_date DATE NOT NULL,
                days_before_release INTEGER NOT NULL,
                
                -- Volume metrics
                total_tickets_sold INTEGER DEFAULT 0,
                total_revenue DECIMAL(12,2) DEFAULT 0,
                total_showtimes INTEGER DEFAULT 0,
                total_theaters INTEGER DEFAULT 0,
                
                -- Performance metrics
                avg_tickets_per_show REAL DEFAULT 0.0,
                avg_tickets_per_theater REAL DEFAULT 0.0,
                avg_ticket_price DECIMAL(6,2) DEFAULT 0.0,
                
                -- Format breakdown (presale tickets by format)
                tickets_imax INTEGER DEFAULT 0,
                tickets_dolby INTEGER DEFAULT 0,
                tickets_3d INTEGER DEFAULT 0,
                tickets_premium INTEGER DEFAULT 0,
                tickets_standard INTEGER DEFAULT 0,
                
                -- Metadata
                data_source VARCHAR(50) DEFAULT 'enttelligence',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE(circuit_name, film_title, snapshot_date)
            )
        """)
        print("   ✅ circuit_presales table created")
        
        # Create indexes
        print("\n📝 Creating indexes...")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_circuit_presales_circuit 
            ON circuit_presales(circuit_name)
        """)
        print("   ✅ idx_circuit_presales_circuit")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_circuit_presales_film 
            ON circuit_presales(film_title, release_date)
        """)
        print("   ✅ idx_circuit_presales_film")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_circuit_presales_snapshot 
            ON circuit_presales(snapshot_date DESC)
        """)
        print("   ✅ idx_circuit_presales_snapshot")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_circuit_presales_days_before 
            ON circuit_presales(film_title, days_before_release)
        """)
        print("   ✅ idx_circuit_presales_days_before")
        
        conn.commit()
        
        # Verify table creation
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='circuit_presales'
        """)
        
        if cursor.fetchone():
            print("\n✅ Migration completed successfully!")
            print("\n📋 Table structure:")
            cursor.execute("PRAGMA table_info(circuit_presales)")
            columns = cursor.fetchall()
            for col in columns:
                print(f"   - {col[1]} ({col[2]})")
            return True
        else:
            print("\n❌ Migration failed - table not created")
            return False
            
    except Exception as e:
        print(f"\n❌ Migration error: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    success = create_circuit_presales_table()
    exit(0 if success else 1)
