import requests
from bs4 import BeautifulSoup
import re
import time

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

urls = [
    ('https://www.coronacigar.com/arturo-fuente-hemingway-cameroon-best-seller/', 'IN STOCK'),
    ('https://www.coronacigar.com/arturo-fuente-hemingway-sun-grown-classic/', 'OUT OF STOCK'),
]

for url, status in urls:
    print(f"\n{'='*70}")
    print(f"{status}: {url}")
    print('='*70)
    
    time.sleep(1)
    response = session.get(url, timeout=10)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find email fields and print context
    email_fields = soup.find_all('input', {'type': 'email'})
    for i, field in enumerate(email_fields):
        print(f"\nEmail Field {i+1}:")
        print(f"  name: {field.get('name', 'N/A')}")
        print(f"  placeholder: {field.get('placeholder', 'N/A')}")
        
        # Get parent context
        parent = field.find_parent(['div', 'section', 'form'])
        if parent:
            parent_text = parent.get_text()[:300]  # First 300 chars
            print(f"  Parent context: {parent_text.strip()[:150]}...")
            
            # Check for "notify" text in parent
            if 'notify' in parent_text.lower():
                print("  >>> NOTIFY CONTEXT FOUND <<<")
