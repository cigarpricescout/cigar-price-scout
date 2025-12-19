import json
from datetime import datetime
from pathlib import Path

MIN_PROMO_PERCENT = 11

def load_promotions():
    """Load promotions.json file"""
    promo_file = Path(__file__).parent / "promotions.json"
    with open(promo_file, 'r') as f:
        return json.load(f)

def get_active_promos(retailer_key, today=None):
    """Get active promos for a specific retailer"""
    if today is None:
        today = datetime.now().date()
    
    all_promos = load_promotions()
    retailer_promos = all_promos.get(retailer_key, [])
    
    active = []
    for promo in retailer_promos:
        if not promo.get('active', False):
            continue
            
        discount = promo.get('discount', 0)
        if discount < MIN_PROMO_PERCENT:
            continue
        
        end_date_str = promo.get('end_date')
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                if today > end_date:
                    continue
            except Exception as e:
                continue
        
        active.append(promo)
    
    return active

def promo_applies(promo, product_row):
    """Check if promo applies to a specific product"""
    scope = promo.get('scope', 'sitewide')
    
    if scope == 'sitewide':
        # Check exclusions
        excluded = promo.get('excluded_brands', [])
        if product_row.get('brand') in excluded:
            return False
        return True
    
    elif scope == 'brand':
        allowed_brands = promo.get('brands', [])
        return product_row.get('brand') in allowed_brands
    
    elif scope == 'line':
        promo_brand = promo.get('brand')
        promo_lines = promo.get('lines', [])
        return (product_row.get('brand') == promo_brand and 
                product_row.get('line') in promo_lines)
    
    return False

def calculate_best_promo(retailer_key, product_row, today=None):
    """Calculate the best applicable promo for a product"""
    promos = get_active_promos(retailer_key, today)
    
    candidates = []
    for promo in promos:
        if not promo_applies(promo, product_row):
            continue
        
        # Scope scoring: more specific = higher priority
        scope_scores = {
            "cigar": 3, "line": 2, "brand": 1, "sitewide": 0
        }
        scope_score = scope_scores.get(promo.get('scope'), 0)
        discount = promo.get('discount', 0)
        
        candidates.append((scope_score, discount, promo))
    
    if not candidates:
        return ""
    
    # Sort by scope priority, then discount amount
    candidates.sort(key=lambda x: (-x[0], -x[1]))
    best_promo = candidates[0][2]
    
    # Calculate discounted price
    try:
        price_value = product_row.get('price', 0)
        if price_value is None or price_value == '':
            return ""  # Skip products without prices
        original_price = float(price_value)
    except (ValueError, TypeError):
        return ""  # Skip products with invalid prices
    
    discount_percent = best_promo.get('discount', 0)
    discounted_price = original_price * (1 - discount_percent / 100.0)
    
    code = best_promo.get('code', 'PROMO')
    return f"${discounted_price:.2f} [{int(discount_percent)}% off]|{code}"
