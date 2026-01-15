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
        logger.info("Database table 'discovered_urls' ready")
        
    def get_processed_urls(self):
        """Get all processed URLs"""
        table_name = f"{self.table_prefix}subtitles"
        result = self.execute(f"SELECT url FROM {table_name}")
        if result:
            return set(row.get('url') for row in result)
        return set()
        
    def add_discovered_url(self, url, category="", page=0, source="subz"):
        return self.execute(
            "INSERT OR IGNORE INTO discovered_urls (url, category, page, source, status) VALUES (?, ?, ?, ?, 'pending')",
            [url, category, page, source]
        )
        
    def add_discovered_urls_batch(self, items, source="subz"):
        """
        Batch insert multiple discovered URLs
        items: list of (url, category, page) tuples
        """
        if not items:
            return None
            
        # D1 API supports multiple statements, but let's build a single multi-value INSERT for atomicity
        # However, D1 has a limit on bind variables. Let's do batches of 10.
        results = []
        batch_limit = 10
        
        for i in range(0, len(items), batch_limit):
            batch = items[i:i+batch_limit]
            placeholders = ",".join(["(?, ?, ?, ?, 'pending')"] * len(batch))
            sql = f"INSERT OR IGNORE INTO discovered_urls (url, category, page, source, status) VALUES {placeholders}"
            
            # Flatten params: url1, cat1, page1, src, url2, cat2, page2, src...
            params = []
            for item in batch:
                params.extend([item[0], item[1], item[2], source])
                
            res = self.execute(sql, params)
            if res:
                results.extend(res)
                
        return results

    def get_pending_urls(self, limit=10, source="subz"):
        """Get a list of pending URLs to process"""
        result = self.execute(
            "SELECT url, category FROM discovered_urls WHERE status = 'pending' AND source = ? LIMIT ?", 
            [source, limit]
        )
        if result:
            return [row for row in result]
        return []
        
    def update_url_status(self, url, status):
        """Update the status of a discovered URL"""
        return self.execute(
            "UPDATE discovered_urls SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE url = ?",
            [status, url]
        )
        
    def get_processed_filenames(self):
        """Get all normalized filenames"""
        table_name = f"{self.table_prefix}subtitles"
        result = self.execute(f"SELECT normalized_filename FROM {table_name} WHERE normalized_filename IS NOT NULL")
        if result:
            return set(row.get('normalized_filename') for row in result)
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
