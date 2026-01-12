"""
Check D1 schema with provided credentials.
"""
import requests
import json
import os
import sys

# New Credentials provided by user
ACCOUNT_ID = "573f9a28fb2a48c7c065c9fe6223429b"
API_TOKEN = "yWfSFrta9yFuCzZxaNLD0F6IEifjBmM7uIkEG02q"
DATABASE_ID = "2318c943-7efd-4dd5-97c1-36039621be59"

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

print("="*60)
print("Checking D1 Schema with NEW Credentials")
print("="*60)

# Query Table Info
query_url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query"

def execute_sql(sql):
    payload = {"sql": sql}
    try:
        response = requests.post(query_url, headers=headers, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error: {e}")
        return None

# Get tables
print("\nFetching tables...")
result = execute_sql("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")

if result and result.get("success"):
    tables = [row["name"] for row in result["result"][0]["results"]]
    print(f"Tables found: {tables}")
    
    required_tables = ['discovered_urls', 'processed_urls', 'telegram_files']
    
    for table in required_tables:
        if table in tables:
            print(f"\nChecking table: {table}")
            schema_res = execute_sql(f"PRAGMA table_info({table})")
            if schema_res.get("success"):
                columns = [col["name"] for col in schema_res["result"][0]["results"]]
                print(f"  Columns: {columns}")
                
                if table == 'discovered_urls':
                    if 'status' in columns:
                        print("  ✅ status column present")
                    else:
                        print("  ❌ status column MISSING")
                
                if 'source' in columns:
                    print("  ✅ source column present")
                else:
                    print("  ❌ source column MISSING")
        else:
            print(f"\n❌ Table {table} NOT FOUND")

else:
    print("❌ Failed to connect or query database.")
    if result:
        print(f"Error: {result.get('errors')}")

print("\nCheck complete.")
