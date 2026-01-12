"""
Analyze existing D1 database schema and verify compatibility
"""
import requests
import json

# Credentials
ACCOUNT_ID = "573f9a28fb2a48c7c065c9fe6223429b"
DATABASE_ID = "2318c943-7efd-4dd5-97c1-36039621be59"
API_TOKEN = "z0Iu5RM5DYRxKlbQMeC9Xg7uI4KgsKY6jlhlAkMZ"

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

print("="*60)
print("1. Verifying API Token...")
print("="*60)

# Verify token
verify_url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/tokens/verify"
response = requests.get(verify_url, headers=headers)
print(f"Status: {response.status_code}")
print(json.dumps(response.json(), indent=2))

print("\n" + "="*60)
print("2. Getting Database Tables...")
print("="*60)

# Get tables
query_url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query"
get_tables_query = {
    "sql": "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
}

response = requests.post(query_url, headers=headers, json=get_tables_query)
print(f"Status: {response.status_code}")
result = response.json()
print(json.dumps(result, indent=2))

if result.get("success"):
    tables = [row["name"] for row in result["result"][0]["results"]]
    print(f"\nTables found: {tables}")
    
    print("\n" + "="*60)
    print("3. Analyzing Table Schemas...")
    print("="*60)
    
    for table in tables:
        print(f"\n--- Table: {table} ---")
        schema_query = {
            "sql": f"PRAGMA table_info({table})"
        }
        response = requests.post(query_url, headers=headers, json=schema_query)
        if response.status_code == 200:
            schema_result = response.json()
            if schema_result.get("success"):
                columns = schema_result["result"][0]["results"]
                for col in columns:
                    print(f"  {col['name']}: {col['type']}")
    
    print("\n" + "="*60)
    print("4. Checking for 'source' column...")
    print("="*60)
    
    # Check if source column exists in key tables
    for table in ['discovered_urls', 'processed_urls', 'telegram_files']:
        if table in tables:
            schema_query = {"sql": f"PRAGMA table_info({table})"}
            response = requests.post(query_url, headers=headers, json=schema_query)
            if response.status_code == 200:
                schema_result = response.json()
                columns = [col['name'] for col in schema_result["result"][0]["results"]]
                has_source = 'source' in columns
                print(f"{table}: source column exists = {has_source}")
                if not has_source:
                    print(f"  ⚠️  NEED TO ADD source column to {table}")
    
    print("\n" + "="*60)
    print("5. Getting Row Counts...")
    print("="*60)
    
    for table in tables:
        count_query = {"sql": f"SELECT COUNT(*) as count FROM {table}"}
        response = requests.post(query_url, headers=headers, json=count_query)
        if response.status_code == 200:
            count_result = response.json()
            if count_result.get("success"):
                count = count_result["result"][0]["results"][0]["count"]
                print(f"{table}: {count} rows")

print("\n" + "="*60)
print("Analysis Complete!")
print("="*60)
