import requests
from bs4 import BeautifulSoup
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_parsing():
    url = "https://subz.lk/category/movies/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    }
    
    logger.info(f"Fetching {url}...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        logger.info("Page fetched successfully.")
    except Exception as e:
        logger.error(f"Failed to fetch page: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    logger.info("Analyzing links...")
    found_links = []
    
    # Current Logic from subz_scraper.py
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if 'sinhala-subtitle' in href.lower() and href.startswith('http'):
            if href not in found_links:
                found_links.append(href)
    
    logger.info(f"Found {len(found_links)} links using current logic.")
    
    if found_links:
        logger.info("Sample links:")
        for l in found_links[:3]:
            logger.info(f" - {l}")
    else:
        logger.warning("No links found! The parsing logic might be broken.")
        # Debug: Print some links that WERE found to see structure
        logger.info("Printing first 5 links found on page (for debugging):")
        all_links = [l.get('href') for l in soup.find_all('a', href=True) if l.get('href', '').startswith('http')]
        for l in all_links[:5]:
            logger.info(f" - {l}")

if __name__ == "__main__":
    test_parsing()
