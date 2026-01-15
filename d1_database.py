"""
Simple D1 Database Handler
"""
import requests
import logging

logger = logging.getLogger(__name__)

class D1Database:
    def __init__(self, account_id, api_token, database_id, table_prefix=''):
        self.enabled = bool(account_id and api_token and database_id)
        self.table_prefix = table_prefix  # e.g., 'cineru_' or 'subz_'
        
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
        table_name = f"{self.table_prefix}subtitles"
        
        self.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
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
        
        self.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}normalized 
            ON {table_name}(normalized_filename)
        """)
        
        logger.info(f"Database table '{table_name}' ready")
        
    def get_processed_urls(self):
        """Get all processed URLs"""
        table_name = f"{self.table_prefix}subtitles"
        result = self.execute(f"SELECT url FROM {table_name}")
        if result and len(result) > 0:
            return set(row.get('url') for row in result[0].get('results', []))
        return set()
        
    def get_processed_filenames(self):
        """Get all normalized filenames"""
        table_name = f"{self.table_prefix}subtitles"
        result = self.execute(f"SELECT normalized_filename FROM {table_name} WHERE normalized_filename IS NOT NULL")
        if result and len(result) > 0:
            return set(row.get('normalized_filename') for row in result[0].get('results', []))
        return set()
        
    def mark_processed(self, url, title):
        """Mark URL as processed (duplicate case)"""
        table_name = f"{self.table_prefix}subtitles"
        self.execute(f"""
            INSERT OR IGNORE INTO {table_name} (url, title) 
            VALUES ('{url.replace("'", "''")}', '{title.replace("'", "''")[:200]}')
        """)
        
    def save_file(self, url, title, filename, normalized_filename, file_id, file_size):
        """Save uploaded file info"""
        table_name = f"{self.table_prefix}subtitles"
        self.execute(f"""
            INSERT OR REPLACE INTO {table_name} 
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
