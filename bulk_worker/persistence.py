import sqlite3
import os

DB_PATH = "recruitment_swarm.db"

def init_bulk_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bulk_tasks (
                company_name TEXT PRIMARY KEY,
                status TEXT DEFAULT 'pending', -- pending, active, completed, failed
                found_count INTEGER DEFAULT 0,
                error_log TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

def save_bulk_checkpoint(company, status, count=0, error=None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO bulk_tasks (company_name, status, found_count, error_log, last_updated)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (company, status, count, error))

def get_bulk_stats():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM bulk_tasks GROUP BY status")
        return dict(cursor.fetchall())

def get_pending_list():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT company_name FROM bulk_tasks WHERE status IN ('pending', 'failed')")
        return [row[0] for row in cursor.fetchall()]

def clear_bulk_tasks():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM bulk_tasks")