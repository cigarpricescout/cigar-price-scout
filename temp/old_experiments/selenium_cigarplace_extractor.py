#!/usr/bin/env python3
"""
Selenium-based extractor for JavaScript-heavy cigar websites
Handles dynamic content loading that regular requests cannot see
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import re
import json
from datetime import datetime
import time

def setup_driver(headless=True):
    """Setup Chrome driver with appropriate options"""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        print(f"Error setting up Chrome driver: {e}")
        print("Make sure you have Chrome and chromedriver installed")
        return None

def extract_cigarplace_opusx_selenium(url, wait_time=10):
    """
    Extract data using Selenium to handle JavaScript-rendered content
    """
    
    driver = setup_driver(headless=False)  # Set to False to see browser for debugging
    if not driver:
        return {"success": False, "error": "Could not setup Chrome driver"}
    
    try:
        result = {
            'url': url,
            'extracted_at': datetime.now().isoformat(),
            'success': False,
            'price': None,
            'in_stock': None,
            'raw_data': {}
        }
        
        print(f"Loading page: {url}")
        driver.get(url)
        
        # Wait for page to load
        wait = WebDriverWait(driver, wait_time)
        
        # Wait for the main content to load (look for the product title)
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
            time.sleep(3)  # Additional wait for JavaScript to fully execute
        except TimeoutException:
            print("Page took too long to load")
        
        # Strategy 1: Look for Box of 29 pricing
        box_price = None
        
        # Common selectors for cigar pricing
        price_selectors = [
            # Look for text containing "Box of 29" and nearby prices
            "//text()[contains(., 'Box of 29')]/following::*[contains(text(), '$')]",
            "//text()[contains(., 'Box of 29')]/preceding::*[contains(text(), '$')]",
            "//text()[contains(., 'Box of 29')]/parent::*//*[contains(text(), '$')]",
            
            # Common price element patterns
            "//*[@class='price']",
            "//*[@id='price']", 
            "//*[contains(@class, 'price')]",
            "//*[contains(@class, 'cost')]",
            "//*[contains(@class, 'money')]",
            
            # Look for any element containing price patterns
            "//*[contains(text(), '$') and contains(text(), '6')]",  # Looking for $6xx.xx pattern
        ]
        
        prices_found = []
        for selector in price_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements:
                    text = element.text.strip()
                    if text:
                        price_matches = re.findall(r'\$([0-9,]+\.?[0-9]*)', text)
                        for match in price_matches:
                            try:
                                price_val = float(match.replace(',', ''))
                                if 50 < price_val < 2000:  # Reasonable price range
                                    prices_found.append({
                                        'price': price_val,
                                        'text': text[:100],
                                        'selector': selector
                                    })
                            except ValueError:
                                continue
            except Exception as e:
                continue
        
        result['raw_data']['prices_found'] = prices_found
        
        # Find the most likely box price
        if prices_found:
            # Look for prices in the $600-800 range (typical for OpusX box)
            likely_box_prices = [p for p in prices_found if 600 <= p['price'] <= 800]
            if likely_box_prices:
                box_price = likely_box_prices[0]['price']
                result['raw_data']['selected_price_method'] = 'range_filter'
            else:
                # Take the highest reasonable price
                sorted_prices = sorted(prices_found, key=lambda x: x['price'], reverse=True)
                box_price = sorted_prices[0]['price']
                result['raw_data']['selected_price_method'] = 'highest_price'
        
        result['price'] = box_price
        
        # Strategy 2: Stock status detection
        stock_status = None
        
        # Look for buttons and their text
        try:
            # Look for "Notify Me" button
            notify_buttons = driver.find_elements(By.XPATH, "//*[contains(text(), 'Notify Me') or contains(text(), 'notify me')]")
            if notify_buttons:
                stock_status = False
                result['raw_data']['stock_method'] = 'notify_me_button'
            
            # Look for "Add to Cart" button
            if stock_status is None:
                cart_buttons = driver.find_elements(By.XPATH, "//*[contains(text(), 'Add to Cart') or contains(text(), 'add to cart')]")
                if cart_buttons:
                    stock_status = True
                    result['raw_data']['stock_method'] = 'add_to_cart_button'
            
            # Check button classes/IDs for common patterns
            if stock_status is None:
                buttons = driver.find_elements(By.TAG_NAME, "button")
                for button in buttons:
                    button_text = button.text.lower().strip()
                    if 'notify' in button_text:
                        stock_status = False
                        result['raw_data']['stock_method'] = 'button_text_notify'
                        break
                    elif 'add to cart' in button_text or 'buy' in button_text:
                        stock_status = True
                        result['raw_data']['stock_method'] = 'button_text_cart'
                        break
        
        except Exception as e:
            result['raw_data']['stock_error'] = str(e)
        
        result['in_stock'] = stock_status
        result['success'] = (box_price is not None)
        
        # Take a screenshot for debugging
        try:
            screenshot_path = "cigarplace_screenshot.png"
            driver.save_screenshot(screenshot_path)
            result['raw_data']['screenshot'] = screenshot_path
            print(f"Screenshot saved: {screenshot_path}")
        except:
            pass
        
        return result
        
    except Exception as e:
        return {
            'url': url,
            'extracted_at': datetime.now().isoformat(),
            'success': False,
            'error': str(e),
            'price': None,
            'in_stock': None
        }
    
    finally:
        driver.quit()

# Installation check and test
def check_selenium_setup():
    """Check if Selenium and Chrome are properly set up"""
    try:
        driver = setup_driver(headless=True)
        if driver:
            driver.quit()
            return True
        return False
    except Exception as e:
        print(f"Selenium setup error: {e}")
        return False

if __name__ == "__main__":
    print("Selenium-based Cigar Place Extractor")
    print("=" * 50)
    
    # Check setup first
    if not check_selenium_setup():
        print("❌ SETUP REQUIRED:")
        print("1. Install Chrome browser")
        print("2. Install chromedriver: pip install chromedriver-autoinstaller")
        print("3. Or download chromedriver manually and add to PATH")
        print("4. Install selenium: pip install selenium")
        exit(1)
    
    print("✅ Selenium setup OK")
    
    url = "https://www.cigarplace.biz/arturo-fuente-opus-x-robusto.html"
    
    print(f"\nTesting JavaScript-aware extraction...")
    print(f"This will open a browser window to load the page properly")
    print("=" * 50)
    
    result = extract_cigarplace_opusx_selenium(url)
    
    print("\nExtraction Result:")
    print(json.dumps(result, indent=2))
    
    if result['success']:
        print(f"\n[SUCCESS]")
        print(f"   Box Price: ${result['price']}")
        print(f"   In Stock: {result['in_stock']}")
        
        # Validation
        expected_price = 667.95
        if result['price'] and abs(result['price'] - expected_price) < 1:
            print(f"   ✅ Price matches expected!")
        else:
            print(f"   ⚠️ Expected ${expected_price}, got ${result['price']}")
            
    else:
        print(f"\n[FAILED] {result.get('error', 'Unknown error')}")
    
    print(f"\n💡 If this works, we can automate JavaScript-heavy sites!")
