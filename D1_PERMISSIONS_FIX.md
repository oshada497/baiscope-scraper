# Cloudflare D1 API Token Permissions Fix

## Problem

Your API token is returning `SQLITE_AUTH` error, which means it doesn't have sufficient permissions to query/modify the D1 database.

## Solution

### Option 1: Create New API Token with D1 Permissions (Recommended)

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Click your profile → **API Tokens**
3. Click **Create Token**
4. Click **Get started** next to "Create Custom Token"
5. Configure:
   - **Token name**: `D1 Scraper Token`
   - **Permissions**:
     - Account → D1 → Edit
     - Account → Account Settings → Read
   - **Account Resources**: Include your account
   - **TTL**: No expiry or set long duration
6. Click **Continue to summary**
7. Click **Create Token**
8. **Copy the token** and save it securely

### Option 2: Edit Existing Token

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Profile → **API Tokens**
3. Find your existing token
4. Click **Edit**
5. Add permission: **Account → D1 → Edit**
6. Save

## Update Environment Variables

After creating/editing the token, update your environment variables:

### For Render.com

1. Go to your Render service
2. **Environment** tab
3. Update `CF_API_TOKEN` with the new token
4. Click **Save Changes**
5. Service will auto-redeploy

### For Local Testing

```bash
export CF_API_TOKEN="your_new_token_here"
```

## Verify New Token

Run this test:

```bash
python test_d1_connection.py
```

Expected output:
```
✅ D1 Enabled: True
✅ Tables found: [...]
✅ Database is fully compatible!
```

## What Happens Next

Once the token has proper permissions, the scraper will:

1. **Auto-detect** existing tables
2. **Automatically add** `source` column if missing (via `ALTER TABLE`)
3. **Create indexes** for efficient queries
4. **Migrate** existing data (sets `source='baiscope'` for old records)

**Note**: The migration is safe and non-destructive. Existing data won't be lost.

## Manual Migration (If Needed)

If you want to manually add the `source` column before running the scraper:

```sql
-- Add source column to discovered_urls
ALTER TABLE discovered_urls ADD COLUMN source TEXT DEFAULT 'baiscope';

-- Add source column to processed_urls  
ALTER TABLE processed_urls ADD COLUMN source TEXT DEFAULT 'baiscope';

-- Add source column to telegram_files
ALTER TABLE telegram_files ADD COLUMN source TEXT DEFAULT 'baiscope';

-- Add source column to scraper_state
ALTER TABLE scraper_state ADD COLUMN source TEXT DEFAULT 'baiscope';

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_source ON telegram_files(source);
CREATE INDEX IF NOT EXISTS idx_source_urls ON processed_urls(source);
```

You can run these in:
- Cloudflare Dashboard → D1 → Your Database → **Console** tab
- Or via API once token has permissions

## Database Schema Compatibility

The code is **fully backward compatible**:

- ✅ Works with databases that DON'T have `source` column (adds it automatically)
- ✅ Works with databases that ALREADY have `source` column (uses it)
- ✅ Preserves all existing data
- ✅ Migration runs only once

## Current Database Information

Based on your credentials:
- **Account ID**: `573f9a28fb2a48c7c065c9fe6223429b`
- **Database ID**: `2318c943-7efd-4dd5-97c1-36039621be59`
- **Current Token**: Has verification permissions but NOT D1 edit permissions

## Next Steps

1. ✅ Create new API token with D1 Edit permission
2. ✅ Update `CF_API_TOKEN` environment variable
3. ✅ Run `python test_d1_connection.py` to verify
4. ✅ Deploy to Render with new token
5. ✅ Scraper will auto-migrate database on first run
