"""
Simple Telegram Bot Handler
"""
import requests
import io
import time
import logging

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, bot_token, chat_id):
        self.enabled = bool(bot_token and chat_id)
        if not self.enabled:
            logger.warning("Telegram not configured")
            return
            
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.last_request = 0
        
    def _rate_limit(self):
        """Basic rate limiting"""
        elapsed = time.time() - self.last_request
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self.last_request = time.time()
        
    def send_message(self, text):
        """Send a text message"""
        if not self.enabled:
            return False
            
        self._rate_limit()
        try:
            response = requests.post(
                f"{self.base_url}/sendMessage",
                data={
                    'chat_id': self.chat_id,
                    'text': text[:4000],  # Telegram limit
                    'parse_mode': 'HTML'
                },
                timeout=30
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
            
    def upload_file(self, content, filename, caption=None, retries=3):
        """Upload a file to Telegram"""
        if not self.enabled:
            return None
            
        for attempt in range(retries):
            self._rate_limit()
            try:
                # Determine MIME type
                if filename.endswith('.zip'):
                    mime_type = 'application/zip'
                elif filename.endswith('.rar'):
                    mime_type = 'application/x-rar-compressed'
                else:
                    mime_type = 'application/x-subrip'
                    
                files = {
                    'document': (filename, io.BytesIO(content), mime_type)
                }
                data = {'chat_id': self.chat_id}
                if caption:
                    data['caption'] = caption[:1024]
                    data['parse_mode'] = 'HTML'
                    
                response = requests.post(
                    f"{self.base_url}/sendDocument",
                    data=data,
                    files=files,
                    timeout=60
                )
                
                if response.status_code == 200:
                    result = response.json().get('result', {})
                    document = result.get('document', {})
                    return {
                        'file_id': document.get('file_id', ''),
                        'file_size': document.get('file_size', 0)
                    }
                elif response.status_code == 429:
                    retry_after = response.json().get('parameters', {}).get('retry_after', 30)
                    logger.warning(f"Rate limited, waiting {retry_after}s")
                    time.sleep(retry_after + 1)
                    continue
                else:
                    logger.warning(f"Upload failed: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Upload error (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    time.sleep(3 * (attempt + 1))
                    
        return None
