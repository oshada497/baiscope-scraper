import os
import asyncio
import logging
import requests
import re
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeFilename

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CloudflareD1Sync:
    def __init__(self, account_id, api_token, database_id):
        self.account_id = account_id
        self.api_token = api_token
        self.database_id = database_id
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        self.enabled = bool(account_id and api_token and database_id)
    
    def execute(self, sql, params=None):
        if not self.enabled:
            return None
            
        try:
            payload = {"sql": sql}
            if params:
                payload["params"] = params
            
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=30)
            data = response.json()
            
            if data.get("success"):
                return data.get("result", [])
            else:
                logger.error(f"D1 query error: {data.get('errors')}")
                return None
        except Exception as e:
            logger.error(f"D1 execute error: {e}")
            return None
    
    def init_sync_table(self):
        self.execute("""
            CREATE TABLE IF NOT EXISTS telegram_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT UNIQUE NOT NULL,
                file_unique_id TEXT,
                filename TEXT,
                normalized_filename TEXT,
                file_size INTEGER,
                title TEXT,
                source_url TEXT,
                category TEXT,
                message_id INTEGER,
                uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.execute("CREATE INDEX IF NOT EXISTS idx_normalized_filename ON telegram_files(normalized_filename)")
        logger.info("D1 sync table initialized with normalized_filename index")
    
    def file_exists(self, normalized_filename):
        result = self.execute(
            "SELECT 1 FROM telegram_files WHERE normalized_filename = ?",
            [normalized_filename]
        )
        if result and len(result) > 0:
            return len(result[0].get("results", [])) > 0
        return False
    
    def get_all_normalized_filenames(self):
        result = self.execute("SELECT normalized_filename FROM telegram_files WHERE normalized_filename IS NOT NULL")
        if result and len(result) > 0:
            return set(row.get("normalized_filename", "") for row in result[0].get("results", []) if row.get("normalized_filename"))
        return set()
    
    def save_synced_file(self, file_id, file_unique_id, filename, normalized_filename, file_size, message_id):
        return self.execute(
            """INSERT OR IGNORE INTO telegram_files 
               (file_id, file_unique_id, filename, normalized_filename, file_size, message_id, uploaded_at) 
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            [file_id, file_unique_id, filename, normalized_filename, file_size, message_id]
        )
    
    def get_sync_count(self):
        result = self.execute("SELECT COUNT(*) as count FROM telegram_files")
        if result and len(result) > 0:
            results = result[0].get("results", [])
            if results:
                return results[0].get("count", 0)
        return 0


def normalize_filename(filename):
    if not filename:
        return ""
    name = filename.lower()
    name = re.sub(r'\.[^.]+$', '', name)
    name = re.sub(r'[^a-z0-9\u0D80-\u0DFF]', '', name)
    return name


class TelegramChannelSync:
    def __init__(self, api_id, api_hash, chat_id, d1_client):
        self.api_id = api_id
        self.api_hash = api_hash
        self.chat_id = chat_id
        self.d1 = d1_client
        self.client = None
        self.synced_count = 0
        self.skipped_count = 0
    
    async def connect(self):
        self.client = TelegramClient('sync_session', self.api_id, self.api_hash)
        await self.client.start()
        logger.info("Connected to Telegram MTProto API")
    
    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            logger.info("Disconnected from Telegram")
    
    async def sync_channel_files(self, limit=None, offset_id=0):
        logger.info(f"Starting sync from channel {self.chat_id}")
        
        self.d1.init_sync_table()
        
        existing_files = self.d1.get_all_normalized_filenames()
        logger.info(f"Found {len(existing_files)} existing files in D1")
        
        batch = []
        batch_size = 100
        total_messages = 0
        
        async for message in self.client.iter_messages(self.chat_id, limit=limit, offset_id=offset_id):
            total_messages += 1
            
            if message.document:
                filename = None
                for attr in message.document.attributes:
                    if isinstance(attr, DocumentAttributeFilename):
                        filename = attr.file_name
                        break
                
                if filename and filename.lower().endswith('.srt'):
                    normalized = normalize_filename(filename)
                    
                    if normalized in existing_files:
                        self.skipped_count += 1
                        continue
                    
                    file_data = {
                        'file_id': str(message.document.id),
                        'file_unique_id': str(message.document.access_hash),
                        'filename': filename,
                        'normalized_filename': normalized,
                        'file_size': message.document.size,
                        'message_id': message.id
                    }
                    batch.append(file_data)
                    existing_files.add(normalized)
                    
                    if len(batch) >= batch_size:
                        await self._save_batch(batch)
                        batch = []
            
            if total_messages % 1000 == 0:
                logger.info(f"Processed {total_messages} messages, synced {self.synced_count}, skipped {self.skipped_count}")
        
        if batch:
            await self._save_batch(batch)
        
        logger.info(f"Sync complete! Processed {total_messages} messages")
        logger.info(f"Synced: {self.synced_count}, Skipped (already exists): {self.skipped_count}")
        
        return self.synced_count
    
    async def _save_batch(self, batch):
        for file_data in batch:
            result = self.d1.save_synced_file(
                file_data['file_id'],
                file_data['file_unique_id'],
                file_data['filename'],
                file_data['normalized_filename'],
                file_data['file_size'],
                file_data['message_id']
            )
            if result is not None:
                self.synced_count += 1
        
        logger.info(f"Saved batch of {len(batch)} files, total synced: {self.synced_count}")


async def run_sync():
    API_ID = os.environ.get('TELEGRAM_API_ID')
    API_HASH = os.environ.get('TELEGRAM_API_HASH')
    CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '-1003442794989')
    
    CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID') or os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    CF_API_TOKEN = os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN')
    D1_DATABASE_ID = os.environ.get('D1_DATABASE_ID')
    
    if not all([API_ID, API_HASH]):
        logger.error("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH!")
        return 0
    
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, D1_DATABASE_ID]):
        logger.error("Missing D1 database credentials!")
        return 0
    
    d1_client = CloudflareD1Sync(CF_ACCOUNT_ID, CF_API_TOKEN, D1_DATABASE_ID)
    
    syncer = TelegramChannelSync(
        api_id=int(API_ID),
        api_hash=API_HASH,
        chat_id=int(CHAT_ID),
        d1_client=d1_client
    )
    
    await syncer.connect()
    
    try:
        count = await syncer.sync_channel_files()
        return count
    finally:
        await syncer.disconnect()


def sync_existing_files():
    return asyncio.run(run_sync())


if __name__ == "__main__":
    sync_existing_files()
