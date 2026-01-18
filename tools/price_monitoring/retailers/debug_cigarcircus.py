#!/usr/bin/env python3
"""
Debug script to check if price appears in raw HTML
"""

import requests
import time

url = "https://www.cigarcircus.com/shop/arturo-fuente-hemingway-hemingway-short-story-21607#attribute_values=2731,2806,2823,2891,2935,3116,3156,3001"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

time.sleep(1)
response = requests.get(url, headers=headers, timeout=10)

print(f"Status: {response.status_code}")
print(f"Content length: {len(response.text)} characters")
print()

# Check for key strings
search_terms = ['207.90', '207', 'Box of 25', '34.95']

for term in search_terms:
    count = response.text.count(term)
    print(f"'{term}': {count} occurrences")
    
    if count > 0 and term in ['207.90', '207']:
        # Show context around first occurrence
        idx = response.text.find(term)
        start = max(0, idx - 100)
        end = min(len(response.text), idx + 100)
        context = response.text[start:end]
        print(f"  Context: ...{context}...")
        print()
