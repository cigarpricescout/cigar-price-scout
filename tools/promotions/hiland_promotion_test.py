"""
Hiland Cigars Promotion Detection Test
Simple test to assess promotion integration complexity
Run this locally with: python hiland_promotion_test.py
"""

import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

def test_hiland_promotions():
    """Test promotion detection on Hiland Cigars"""
    
    print("HILAND CIGARS PROMOTION TEST")
    print("=" * 40)
    print("Testing: https://www.hilandscigars.com")
    print()
    
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        response = session.get('https://www.hilandscigars.com')
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        text_content = soup.get_text().lower()
        
        print("[SUCCESS] Successfully loaded Hiland Cigars homepage")
        print()
        
        # Test 1: Site-wide percentage discounts
        print("TEST 1: Site-wide percentage discounts")
        percent_patterns = [
            r'(\d+)%\s*off\s*(?:everything|entire|site|sitewide|all)',
            r'save\s*(\d+)%\s*(?:sitewide|site-wide|everything)',
            r'(\d+)%\s*discount\s*(?:on|for)\s*(?:everything|all)',
            r'black\s*friday\s*(\d+)%\s*off'
        ]
        
        found_discount = False
        for pattern in percent_patterns:
            match = re.search(pattern, text_content)
            if match:
                discount = match.group(1)
                print(f"   [FOUND] Site-wide discount: {discount}% off")
                found_discount = True
                break
        
        if not found_discount:
            print("   [NONE] No site-wide percentage discounts found")
        
        print()
        
        # Test 2: Free shipping thresholds
        print("TEST 2: Free shipping thresholds")
        shipping_patterns = [
            r'free\s*shipping\s*(?:on|for)?\s*(?:orders?)?\s*(?:over|above)?\s*\$(\d+)',
            r'\$(\d+)\s*(?:or more|and up)\s*(?:for)?\s*free\s*shipping'
        ]
        
        found_shipping = False
        for pattern in shipping_patterns:
            match = re.search(pattern, text_content)
            if match:
                threshold = match.group(1)
                print(f"   [FOUND] Free shipping threshold: ${threshold}")
                found_shipping = True
                break
        
        if not found_shipping:
            print("   [NONE] No free shipping thresholds found")
        
        print()
        
        # Test 3: Promotional banners
        print("TEST 3: Promotional banners/headers")
        banner_selectors = [
            '.promo-banner', '.promotion', '.site-wide-sale',
            '.header-promo', '.main-banner', '[class*="promo"]',
            '[class*="sale"]', '[class*="discount"]', '.alert',
            '.notification', '.banner'
        ]
        
        found_banner = False
        for selector in banner_selectors:
            banners = soup.select(selector)
            for banner in banners:
                banner_text = banner.get_text().strip()
                if 'sale' in banner_text.lower() or 'discount' in banner_text.lower() or '%' in banner_text:
                    if len(banner_text) < 200:  # Reasonable length
                        print(f"   [FOUND] Promotional banner:")
                        print(f"      Selector: {selector}")
                        print(f"      Text: {banner_text[:100]}...")
                        found_banner = True
                        break
            if found_banner:
                break
        
        if not found_banner:
            print("   [NONE] No promotional banners found")
        
        print()
        
        # Test 4: Page title/meta for sales
        print("TEST 4: Page title for sales keywords")
        title = soup.find('title')
        if title:
            title_text = title.get_text().lower()
            if any(word in title_text for word in ['sale', 'discount', 'black friday', 'special']):
                print(f"   [FOUND] Sales keywords in title: {title.get_text()}")
            else:
                print(f"   [NONE] No sales keywords in title: {title.get_text()}")
        
        print()
        
        # Test 5: Look for specific Black Friday content
        print("TEST 5: Black Friday specific content")
        bf_keywords = ['black friday', 'cyber', 'holiday sale', 'thanksgiving']
        bf_found = []
        
        for keyword in bf_keywords:
            if keyword in text_content:
                bf_found.append(keyword)
        
        if bf_found:
            print(f"   [FOUND] Black Friday keywords: {', '.join(bf_found)}")
        else:
            print("   [NONE] No Black Friday specific content found")
        
        print()
        print("=" * 40)
        print("ASSESSMENT:")
        
        # Provide integration assessment
        total_indicators = sum([
            found_discount,
            found_shipping, 
            found_banner,
            bool(bf_found)
        ])
        
        if total_indicators >= 3:
            print("RESULT: HIGH - Strong promotion detection possible")
            print("   This retailer shows clear promotional patterns")
            print("   Integration effort: ~2-3 hours")
        elif total_indicators >= 2:
            print("RESULT: MEDIUM - Moderate promotion detection possible")
            print("   Some promotional patterns detected")
            print("   Integration effort: ~4-6 hours")
        else:
            print("RESULT: LOW - Limited promotion detection possible")
            print("   Few clear promotional indicators")
            print("   Integration effort: ~8+ hours or may not be worthwhile")
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return False
    
    return True

if __name__ == "__main__":
    test_hiland_promotions()
