import sqlite3
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_FILE = Path("subtitles.db")

def init_database():
    """Initialize the database and create tables"""
    try:
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_subtitles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                file_type TEXT NOT NULL,
                processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

def is_already_processed(file_url):
    """Check if a file URL has already been processed"""
    try:
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM processed_subtitles WHERE file_url = ?', (file_url,))
        result = cursor.fetchone()
        conn.close()
        
        return result is not None
        
    except Exception as e:
        logger.error(f"Error checking processed file: {e}")
        return False

def add_processed_subtitle(file_url, title, source, file_type):
    """Add a subtitle file to the processed list"""
    try:
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO processed_subtitles (file_url, title, source, file_type)
            VALUES (?, ?, ?, ?)
        ''', (file_url, title, source, file_type))
        
        conn.commit()
        conn.close()
        logger.info(f"Recorded processed: {title} from {source}")
        
    except sqlite3.IntegrityError:
        logger.warning(f"File already in database: {file_url}")
    except Exception as e:
        logger.error(f"Error adding processed subtitle: {e}")

def get_processed_count():
    """Get total count of processed subtitles"""
    try:
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM processed_subtitles')
        count = cursor.fetchone()[0]
        conn.close()
        
        return count
        
    except Exception as e:
        logger.error(f"Error getting processed count: {e}")
        return 0

def get_recent_processed(limit=10):
    """Get recent processed subtitles"""
    try:
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT title, source, file_type, processed_date
            FROM processed_subtitles
            ORDER BY processed_date DESC
            LIMIT ?
        ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        logger.error(f"Error getting recent processed: {e}")
        return []
