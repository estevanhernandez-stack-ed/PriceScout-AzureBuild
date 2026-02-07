#!/usr/bin/env python3
"""
Add circuit_benchmarks table for nationwide circuit performance tracking
"""
import sqlite3
from datetime import datetime

DB_PATH = "pricescout.db"

def add_circuit_benchmarks_table():
    """Create circuit_benchmarks table for nationwide competitive intelligence"""
    
    # Backup first
    backup_path = f"pricescout_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    print(f"📦 Creating backup: {backup_path}")
    import shutil
    shutil.copy2(DB_PATH, backup_path)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\n🏗️  Creating circuit_benchmarks table...")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS circuit_benchmarks (
            benchmark_id INTEGER PRIMARY KEY AUTOINCREMENT,
            circuit_name VARCHAR(255) NOT NULL,
            week_ending_date DATE NOT NULL,
            period_start_date DATE,

            -- Volume metrics
            total_showtimes INTEGER DEFAULT 0,
            total_capacity INTEGER DEFAULT 0,
            total_theaters INTEGER DEFAULT 0,
            total_films INTEGER DEFAULT 0,

            -- Programming metrics
            avg_screens_per_film REAL DEFAULT 0.0,
            avg_showtimes_per_theater REAL DEFAULT 0.0,

            -- Format breakdown (percentages)
            format_standard_pct REAL DEFAULT 0.0,
            format_imax_pct REAL DEFAULT 0.0,
            format_dolby_pct REAL DEFAULT 0.0,
            format_3d_pct REAL DEFAULT 0.0,
            format_other_premium_pct REAL DEFAULT 0.0,

            -- PLF aggregate
            plf_total_pct REAL DEFAULT 0.0,

            -- Daypart breakdown (percentages)
            daypart_matinee_pct REAL DEFAULT 0.0,
            daypart_evening_pct REAL DEFAULT 0.0,
            daypart_late_pct REAL DEFAULT 0.0,

            -- Pricing (if available)
            avg_price_general REAL,
            avg_price_child REAL,
            avg_price_senior REAL,

            -- Metadata
            data_source VARCHAR(50) DEFAULT 'enttelligence',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(circuit_name, week_ending_date)
        )
    """)
    
    print("   ✅ circuit_benchmarks table created")
    
    # Add indexes for performance
    print("\n📊 Creating indexes...")
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_circuit_benchmarks_circuit 
        ON circuit_benchmarks(circuit_name)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_circuit_benchmarks_week 
        ON circuit_benchmarks(week_ending_date DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_circuit_benchmarks_lookup 
        ON circuit_benchmarks(circuit_name, week_ending_date)
    """)
    
    print("   ✅ Indexes created")
    
    conn.commit()
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='circuit_benchmarks'")
    if cursor.fetchone()[0] == 1:
        print("\n✅ Migration successful!")
        print(f"   Backup saved: {backup_path}")
    else:
        print("\n❌ Migration failed - table not created")
    
    conn.close()

if __name__ == "__main__":
    print("="*70)
    print("CIRCUIT BENCHMARKS TABLE MIGRATION")
    print("="*70)
    add_circuit_benchmarks_table()
