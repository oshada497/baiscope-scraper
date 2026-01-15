# How to Get Cineru.lk Cookies

## Step 1: Visit Cineru.lk in Browser

1. Open Chrome/Firefox
2. Go to https://cineru.lk
3. Wait for Cloudflare challenge to complete
4. Make sure the site loads properly

## Step 2: Copy Cookies

### Method 1: Using Browser DevTools (Easiest)

**Chrome:**
1. Press `F12` to open DevTools
2. Go to **Application** tab
3. Click **Cookies** → `https://cineru.lk`
4. You'll see cookies like:
   - `cf_clearance` ← **This is the important one**
   - `__cf_bm`
   - Other cookies

5. **Copy the cookies** into this format:
```json
{
  "cf_clearance": "VALUE_HERE",
  "__cf_bm": "VALUE_HERE"
}
```

**Firefox:**
1. Press `F12`
2. Go to **Storage** tab
3. Click **Cookies** → `https://cineru.lk`
4. Same process as Chrome

### Method 2: Using Cookie Export Extension

**Chrome Extension:**
1. Install "EditThisCookie" or "Cookie-Editor"
2. Visit cineru.lk
3. Click extension icon
4. Click "Export" → Copy JSON
5. Remove brackets and format as shown above

## Step 3: Set Environment Variable in Render

1. Go to Render Dashboard
2. Click your service (baiscope-scraper)
3. Go to **Environment** tab
4. Add new variable:
   - **Key**: `CINERU_COOKIES`
   - **Value** (paste your cookies JSON):
     ```json
     {"cf_clearance":"YOUR_CLEARANCE_VALUE","__cf_bm":"YOUR_BM_VALUE"}
     ```
5. Click **Save**
6. Render will redeploy automatically

## Step 4: Test

```bash
curl https://baiscope-scraper.onrender.com/scrape/cineru
```

---

## Example Cookie Format

```json
{"cf_clearance":"a1b2c3d4e5f6-YOUR-CLEARANCE-TOKEN-abcdef123456","__cf_bm":"xyzABC123-YOUR-BM-TOKEN-xyz789"}
```

**Important:**
- Cookie must be valid JSON (use double quotes `"`, not single quotes)
- Don't add spaces or newlines
- Paste entire JSON on one line

---

## How Long Do Cookies Last?

- `cf_clearance`: Usually **24 hours** to **30 days**
- When cookies expire, scraper will get 403 errors
- Just repeat this process to get new cookies

---

## Automating Cookie Refresh

### Option 1: Manual Refresh (Simple)
- When scraper fails with 403
- Visit cineru.lk in browser
- Copy new cookies
- Update CINERU_COOKIES in Render

### Option 2: Browser Extension API
- Some extensions can auto-export cookies
- Can set up cron job to update Render env variable
- More complex but fully automated

---

## Troubleshooting

### "403 Forbidden" still happening
- Cookies expired - get new ones
- Make sure JSON format is correct
- Try visiting cineru.lk in **Incognito mode** first, then copy cookies

### "Invalid JSON" error
- Check double quotes (not single)
- No trailing commas
- Use online JSON validator

### Cookies not working
- Make sure you waited for Cloudflare challenge to complete fully
- Try getting cookies from different browser (Chrome vs Firefox)
- Clear browser cache, revisit site, get fresh cookies

---

## Quick Copy Template

Visit cineru.lk, pass Cloudflare, then paste this in DevTools Console:

```javascript
// Run this in browser console on cineru.lk
const cookies = document.cookie.split('; ').reduce((acc, cookie) => {
  const [key, value] = cookie.split('=');
  if (key.includes('cf_')) acc[key] = value;
  return acc;
}, {});
console.log(JSON.stringify(cookies));
```

This will print the cookies in correct JSON format - just copy and paste!

---

## Next Steps

1. ✅ Visit cineru.lk
2. ✅ Copy cookies
3. ✅ Add to Render as `CINERU_COOKIES`
4. ✅ Redeploy automatically happens
5. ✅ Test with `/scrape/cineru`

Much simpler than FlareSolverr! 🎉
