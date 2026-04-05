import sqlite3
import csv
import os
from datetime import datetime

DB_NAME = "recruitment_data.db"
CSV_NAME = "candidates_export.csv"

def init_storage():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recruitment_results (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT,
            query        TEXT,
            platform     TEXT,
            url          TEXT,
            intent       TEXT,
            intent_level TEXT DEFAULT '',
            score        INTEGER DEFAULT 0,
            llm_response TEXT,
            reach_out    TEXT DEFAULT '',
            status       TEXT DEFAULT 'pending_review',
            outcome      TEXT DEFAULT ''
        )
    ''')
    conn.commit()

    for col, typedef in [
       ("intent_level", "TEXT DEFAULT ''"),
    ("score",        "INTEGER DEFAULT 0"),
    ("reach_out",    "TEXT DEFAULT ''"),
    ("status",       "TEXT DEFAULT 'pending_review'"),
    ("outcome",      "TEXT DEFAULT ''"),
    ("result_type",  "TEXT DEFAULT 'other'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE recruitment_results ADD COLUMN {col} {typedef}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    conn.close()

    if not os.path.exists(CSV_NAME):
        with open(CSV_NAME, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Timestamp', 'Query', 'Platform', 'URL',
                'Intent', 'Intent Level', 'Score',
                'LLM Response', 'Reach-out', 'Status'
            ])

def is_duplicate(url: str, query: str = '') -> bool:
    """Returns True only if this exact URL+query combo was already saved."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM recruitment_results WHERE url = ? AND query = ?",
        (url, query)
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def save_to_all(data_item: dict):
    timestamp    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    query        = data_item.get('query', 'N/A')
    platform     = data_item.get('platform', 'N/A')
    url          = data_item.get('url', 'N/A')
    intent       = data_item.get('intent', 'Technical Lead')
    intent_level = data_item.get('intent_level', '')
    score        = data_item.get('score', 0)
    response     = data_item.get('response', '')
    reach_out    = data_item.get('reach_out', '')
    result_type = data_item.get('result_type', 'other')
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
       INSERT INTO recruitment_results
        (timestamp, query, platform, url, intent, intent_level, score,
         llm_response, reach_out, result_type)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (timestamp, query, platform, url, intent, intent_level,
      score, response, reach_out, result_type))
    conn.commit()
    conn.close()

    with open(CSV_NAME, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp, query, platform, url,
            intent, intent_level, score, response, reach_out, 'pending_review'
        ])

def update_status(url: str, status: str, outcome: str = ''):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE recruitment_results SET status=?, outcome=? WHERE url=?",
        (status, outcome, url)
    )
    conn.commit()
    conn.close()

def clear_all():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM recruitment_results")
    conn.commit()
    conn.close()
    if os.path.exists(CSV_NAME):
        with open(CSV_NAME, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Timestamp', 'Query', 'Platform', 'URL',
                'Intent', 'Intent Level', 'Score',
                'LLM Response', 'Reach-out', 'Status'
            ])

def fetch_all():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recruitment_results ORDER BY score DESC, id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def fetch_by_status(status: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM recruitment_results WHERE status=? ORDER BY score DESC",
        (status,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

def fetch_kpis() -> dict:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM recruitment_results")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM recruitment_results WHERE status='approved'")
    approved = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM recruitment_results WHERE score >= 7")
    high_intent = cursor.fetchone()[0]
    cursor.execute("SELECT platform, COUNT(*) FROM recruitment_results GROUP BY platform")
    by_platform = dict(cursor.fetchall())
    conn.close()
    return {
        "total_detected": total,
        "approved":       approved,
        "high_intent":    high_intent,
        "by_platform":    by_platform,
    }