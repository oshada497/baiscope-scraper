from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
import time
import random

def get_page(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    }
    try:
        response = curl_requests.get(
            url,
            impersonate="chrome124",
            timeout=30,
            headers=headers
        )
        return response
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

sites = [
    "https://cineru.lk/",
    "https://sinhalasub.lk/home/",
    "https://subz.lk/",
    "https://zoom.lk/"
]

for site in sites:
    print(f"\n--- Analyzing {site} ---")
    resp = get_page(site)
    if resp:
        soup = BeautifulSoup(resp.text, 'html.parser')
        try:
            print(f"Title: {soup.title.string}")
        except:
             print(f"Title: {soup.title.string.encode('utf-8')}")
        
        # specific checks
        links = soup.find_all('a', href=True)
        print(f"Found {len(links)} links.")
        
        # Try to find a movie/subtitle page link
        article_link = None
        for link in links:
            href = link['href']
            # Heuristics for a detail page
            if site in href and len(href) > len(site) + 10:
                article_link = href
                break
        
        if article_link:
            print(f"Fetching article: {article_link}")
            art_resp = get_page(article_link)
            if art_resp:
                art_soup = BeautifulSoup(art_resp.text, 'html.parser')
                # Look for download links
                downloads = art_soup.find_all('a', href=True)
                dl_found = False
                for dl in downloads:
                    dl_href = dl['href']
                    dl_text = dl.get_text(strip=True).lower()
                    if '.zip' in dl_href or '.srt' in dl_href or 'download' in dl_text:
                        print(f"  Possible download link: {dl_href} Text: {dl_text}")
                        dl_found = True
                if not dl_found:
                    print("  No obvious download links found.")
    else:
        print("Failed to fetch homepage.")
