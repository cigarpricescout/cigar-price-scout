"""
CigarsDirect Stock Detection Test
Shows exactly what stock-related text is found on pages
"""

import requests
from bs4 import BeautifulSoup
import re
import time

def test_stock_detection(url):
    """Test what stock indicators are actually found on a page"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        page_text = soup.get_text().lower()
        
        print(f"=== TESTING: {url} ===")
        
        # Check for key stock phrases
        stock_phrases = [
            'add to cart',
            'sold out',
            'out of stock', 
            'notify me on restock',
            'notify me when available',
            'in stock',
            'ready to ship',
            'in stock, ready to ship'
        ]
        
        found_phrases = []
        for phrase in stock_phrases:
            if phrase in page_text:
                found_phrases.append(phrase)
        
        print(f"Stock phrases found: {found_phrases}")
        
        # Check buttons specifically
        buttons = soup.find_all(['button', 'input'])
        button_texts = []
        for button in buttons:
            button_text = button.get_text(strip=True)
            if button_text and len(button_text) < 50:  # Reasonable button text length
                button_texts.append(button_text)
        
        print(f"Button texts: {button_texts}")
        
        # Look for forms
        forms = soup.find_all('form')
        form_actions = [form.get('action', '') for form in forms if form.get('action')]
        print(f"Form actions: {form_actions}")
        
        # Simple decision based on current logic
        if 'sold out' in page_text or 'notify me on restock' in page_text:
            predicted_stock = False
        elif 'add to cart' in page_text or 'in stock' in page_text:
            predicted_stock = True
        else:
            predicted_stock = False
            
        print(f"Predicted stock status: {'IN STOCK' if predicted_stock else 'OUT OF STOCK'}")
        print()
        
        return predicted_stock
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    # Test both URLs from your screenshots
    test_urls = [
        "https://www.cigarsdirect.com/products/padron-1964-anniversary-exclusivo-maduro?variant=19713316257889",  # Should be OUT OF STOCK
        "https://www.cigarsdirect.com/products/padron-1964-anniversary-corona-maduro?_pos=1&_sid=24119eb13&_ss=r"  # Should be IN STOCK
    ]
    
    for url in test_urls:
        test_stock_detection(url)
        time.sleep(2)
