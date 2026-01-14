"""
Simple D1 Database Handler
"""
import requests
import logging

logger = logging.getLogger(__name__)

class D1Database:
    def __init__(self, account_id, api_token, database_id):
        self.enabled = bool(account_id and api_token and database_id)
        if not self.enabled:
            logger.warning("D1 not configured - running without persistence")
            return
            
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        
    def execute(self, sql):
        """Execute SQL query"""
        if not self.enabled:
            return None
            
        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json={"sql": sql},
                timeout=30
            )
            data = response.json()
            if data.get('success'):
                return data.get('result', [])
            else:
                logger.error(f"D1 error: {data.get('errors')}")
                return None
        except Exception as e:
            logger.error(f"D1 execute error: {e}")
            return None
            
    def create_tables(self):
        """Create database tables"""
        self.execute("""
            CREATE TABLE IF NOT EXISTS subtitles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                filename TEXT,
                normalized_filename TEXT,
                file_id TEXT,
                file_size INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.execute("""
            CREATE INDEX IF NOT EXISTS idx_normalized 
            ON subtitles(normalized_filename)
        """)
        
        logger.info("Database tables ready")
        
    def get_processed_urls(self):
        """Get all processed URLs"""
        result = self.execute("SELECT url FROM subtitles")
        if result and len(result) > 0:
            return set(row.get('url') for row in result[0].get('results', []))
        return set()
        
    def get_processed_filenames(self):
        """Get all normalized filenames"""
        result = self.execute("SELECT normalized_filename FROM subtitles WHERE normalized_filename IS NOT NULL")
        if result and len(result) > 0:
            return set(row.get('normalized_filename') for row in result[0].get('results', []))
        return set()
        
    def mark_processed(self, url, title):
        """Mark URL as processed (duplicate case)"""
        self.execute(f"""
            INSERT OR IGNORE INTO subtitles (url, title) 
            VALUES ('{url.replace("'", "''")}', '{title.replace("'", "''")[:200]}')
        """)
        
    def save_file(self, url, title, filename, normalized_filename, file_id, file_size):
        """Save uploaded file info"""
        self.execute(f"""
            INSERT OR REPLACE INTO subtitles 
            (url, title, filename, normalized_filename, file_id, file_size)
            VALUES (
                '{url.replace("'", "''")}',
                '{title.replace("'", "''")[:200]}',
                '{filename.replace("'", "''")}',
                '{normalized_filename}',
                '{file_id}',
                {file_size}
            )
        """)
