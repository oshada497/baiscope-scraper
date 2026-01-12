"""
Manual migration script to add missing columns to D1 database.
Run this once to fix the schema.
"""
import os
import sys

# Set credentials from test_d1_connection.py
os.environ['CF_ACCOUNT_ID'] = '573f9a28fb2a48c7c065c9fe6223429b'
os.environ['CF_API_TOKEN'] = 'z0Iu5RM5DYRxKlbQMeC9Xg7uI4KgsKY6jlhlAkMZ'
os.environ['D1_DATABASE_ID'] = '2318c943-7efd-4dd5-97c1-36039621be59'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper_utils import CloudflareD1

print("="*60)
print("Starting Manual D1 Migration")
print("="*60)

d1 = CloudflareD1(
    account_id=os.environ['CF_ACCOUNT_ID'],
    api_token=os.environ['CF_API_TOKEN'],
    database_id=os.environ['D1_DATABASE_ID']
)

if not d1.enabled:
    print("❌ Failed to connect to D1")
    exit(1)

# List of migrations to run
migrations = [
    "ALTER TABLE telegram_files ADD COLUMN source TEXT DEFAULT 'baiscope'",
    "ALTER TABLE discovered_urls ADD COLUMN source TEXT DEFAULT 'baiscope'",
    "ALTER TABLE discovered_urls ADD COLUMN status TEXT DEFAULT 'pending'",
    "ALTER TABLE processed_urls ADD COLUMN source TEXT DEFAULT 'baiscope'",
    "ALTER TABLE scraper_state ADD COLUMN source TEXT DEFAULT 'baiscope'"
]

print("\nRunning migrations...")
for sql in migrations:
    print(f"Executing: {sql}")
    try:
        result = d1.execute(sql)
        # D1 might return error if column exists, or None/Empty result on success
        print("  -> Attempted")
    except Exception as e:
        print(f"  -> Error (might already exist): {e}")

print("\n" + "="*60)
print("Verifying Schema")
print("="*60)

tables = ['discovered_urls', 'processed_urls', 'telegram_files']
for table in tables:
    print(f"\nChecking table: {table}")
    schema_result = d1.execute(f"PRAGMA table_info({table})")
    if schema_result:
        columns = [col.get('name') for col in schema_result[0].get('results', [])]
        print(f"  Columns: {columns}")
        
        # Check specific columns
        if table == 'discovered_urls':
            if 'status' in columns:
                print("  ✅ 'status' column exists")
            else:
                print("  ❌ 'status' column MISSING")
        
        if 'source' in columns:
            print("  ✅ 'source' column exists")
        else:
            print("  ❌ 'source' column MISSING")

print("\nMigration check complete.")
