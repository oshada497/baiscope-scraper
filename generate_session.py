#!/usr/bin/env python3
"""
Generate Telethon session file for Telegram sync.
Run this in Replit Shell: python generate_session.py
After auth, upload sync_session.session to Render.
"""
import os
import asyncio
from telethon import TelegramClient

API_ID = os.environ.get('TELEGRAM_API_ID')
API_HASH = os.environ.get('TELEGRAM_API_HASH')
CHAT_ID = int(os.environ.get('TELEGRAM_CHAT_ID', '-1003442794989'))

async def main():
    if not API_ID or not API_HASH:
        print("ERROR: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set!")
        print("Add them to Replit Secrets first.")
        return
    
    print("=" * 50)
    print("Telegram Session Generator")
    print("=" * 50)
    print(f"API ID: {API_ID}")
    print(f"Chat ID: {CHAT_ID}")
    print()
    
    client = TelegramClient('sync_session', int(API_ID), API_HASH)
    
    await client.start()
    
    me = await client.get_me()
    print(f"\nLogged in as: {me.first_name} (@{me.username})")
    print(f"Session saved to: sync_session.session")
    
    print("\nTesting channel access...")
    try:
        entity = await client.get_entity(CHAT_ID)
        print(f"Channel found: {entity.title}")
        
        count = 0
        async for message in client.iter_messages(CHAT_ID, limit=10):
            if message.document:
                count += 1
        print(f"Can access documents: Yes ({count} docs in last 10 messages)")
        
    except Exception as e:
        print(f"Error accessing channel: {e}")
    
    await client.disconnect()
    
    print("\n" + "=" * 50)
    print("SUCCESS! Session file created.")
    print("Next steps:")
    print("1. Download 'sync_session.session' from Replit")
    print("2. Upload it to your Render deployment")
    print("3. Call /sync endpoint to index all files")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
