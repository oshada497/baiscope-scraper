"""
Test D1 database connection and analyze schema using scraper code
"""
import os
import sys

# Set credentials
os.environ['CF_ACCOUNT_ID'] = '573f9a28fb2a48c7c065c9fe6223429b'
os.environ['CF_API_TOKEN'] = 'z0Iu5RM5DYRxKlbQMeC9Xg7uI4KgsKY6jlhlAkMZ'
os.environ['D1_DATABASE_ID'] = '2318c943-7efd-4dd5-97c1-36039621be59'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper_utils import CloudflareD1

print("="*60)
print("Testing D1 Database Connection")
print("="*60)

# Initialize D1
d1 = CloudflareD1(
    account_id='573f9a28fb2a48c7c065c9fe6223429b',
    api_token='z0Iu5RM5DYRxKlbQMeC9Xg7uI4KgsKY6jlhlAkMZ',
    database_id='2318c943-7efd-4dd5-97c1-36039621be59'
)

print(f"\nD1 Enabled: {d1.enabled}")

if d1.enabled:
    print("\n" + "="*60)
    print("Getting Table List...")
    print("="*60)
    
    result = d1.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    if result:
        tables = [row['name'] for row in result[0].get('results', [])]
        print(f"Tables found: {tables}")
        
        print("\n" + "="*60)
        print("Checking Table Schemas...")
        print("="*60)
        
        for table in tables:
            print(f"\n--- {table} ---")
            schema_result = d1.execute(f"PRAGMA table_info({table})")
            if schema_result:
                columns = schema_result[0].get('results', [])
                for col in columns:
                    print(f"  {col.get('name')}: {col.get('type')}")
        
        print("\n" + "="*60)
        print("Checking for 'source' Column...")
        print("="*60)
        
        critical_tables = ['discovered_urls', 'processed_urls', 'telegram_files']
        missing_source = []
        
        for table in critical_tables:
            if table in tables:
                schema_result = d1.execute(f"PRAGMA table_info({table})")
                if schema_result:
                    columns = [col.get('name') for col in schema_result[0].get('results', [])]
                    has_source = 'source' in columns
                    print(f"  {table}: {'✅ HAS source' if has_source else '❌ MISSING source'}")
                    if not has_source:
                        missing_source.append(table)
        
        print("\n" + "="*60)
        print("Getting Row Counts...")
        print("="*60)
        
        for table in tables:
            count_result = d1.execute(f"SELECT COUNT(*) as count FROM {table}")
            if count_result:
                count = count_result[0].get('results', [{}])[0].get('count', 0)
                print(f"  {table}: {count:,} rows")
        
        if missing_source:
            print("\n" + "="*60)
            print("⚠️  ACTION REQUIRED")
            print("="*60)
            print(f"\nThe following tables need 'source' column added:")
            for table in missing_source:
                print(f"  - {table}")
            print("\nThese columns will be added automatically when the scraper runs.")
            print("The code includes migration logic to add the column if it doesn't exist.")
        else:
            print("\n" + "="*60)
            print("✅ Database is fully compatible!")
            print("="*60)
            print("\nAll required columns exist. No migration needed.")
        
        # Test statistics by source
        print("\n" + "="*60)
        print("Statistics by Source...")
        print("="*60)
        
        for table in ['processed_urls', 'telegram_files']:
            if table in tables:
                # Try to get source breakdown
                source_result = d1.execute(f"SELECT source, COUNT(*) as count FROM {table} GROUP BY source")
                if source_result and source_result[0].get('results'):
                    print(f"\n{table}:")
                    for row in source_result[0].get('results', []):
                        source = row.get('source', 'unknown')
                        count = row.get('count', 0)
                        print(f"  {source}: {count:,} rows")
    else:
        print("❌ Failed to query database")
else:
    print("❌ D1 not enabled - check credentials")

print("\n" + "="*60)
print("Analysis Complete!")
print("="*60)
