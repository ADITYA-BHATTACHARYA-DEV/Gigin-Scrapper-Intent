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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            query TEXT,
            platform TEXT,
            url TEXT,
            intent TEXT,
            llm_response TEXT
        )
    ''')
    conn.commit()
    conn.close()

    if not os.path.exists(CSV_NAME):
        with open(CSV_NAME, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Query', 'Platform', 'URL', 'Intent', 'LLM Response'])

def save_to_all(data_item):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Defensive data retrieval
    query = data_item.get('query', 'N/A')
    platform = data_item.get('platform', 'N/A')
    url = data_item.get('url', 'N/A')
    intent = data_item.get('intent', 'Technical Lead')
    response = data_item.get('response', 'No analysis available')

    # SQLite Persistence
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO recruitment_results (timestamp, query, platform, url, intent, llm_response)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (timestamp, query, platform, url, intent, response))
    conn.commit()
    conn.close()

    # CSV Persistence
    with open(CSV_NAME, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, query, platform, url, intent, response])
def fetch_all():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recruitment_results ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows
