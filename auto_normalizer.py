#!/usr/bin/env python3
"""
CIGAR PRICE SCOUT - AUTO-NORMALIZATION ADDON
=============================================

This addon integrates into your existing scraper to automatically normalize
data against your master cigars database before saving to fox_cigar.csv.

SIMPLE INTEGRATION:
1. Copy this file to your project directory
2. Add these 3 lines to your existing scraper.py:

    from auto_normalizer import CigarAutoNormalizer
    
    # In your save_products_csv method, add before df.to_csv():
    normalizer = CigarAutoNormalizer('data/master_cigars.tsv')
    df = normalizer.auto_normalize_dataframe(df)

That's it! Your fox_cigar.csv will now contain clean, normalized data.
"""

import pandas as pd
import numpy as np
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional
import os

class CigarAutoNormalizer:
    """Simple auto-normalizer that integrates into existing scraper workflow"""
    
    def __init__(self, master_cigars_path: str):
        """Initialize with master cigars database"""
        self.master_df = self._load_master_cigars(master_cigars_path)
        
        if not self.master_df.empty:
            self.brand_index = {brand: group for brand, group in self.master_df.groupby('Brand')}
            self.wrapper_aliases = self._build_wrapper_aliases()
            print(f"Auto-normalizer loaded: {len(self.master_df)} master cigars, {len(self.brand_index)} brands")
        else:
            print("WARNING: Auto-normalizer: Master cigars file not found - normalization disabled")
            self.brand_index = {}
            self.wrapper_aliases = {}
    
    def _load_master_cigars(self, path: str) -> pd.DataFrame:
        """Load master cigars database from various possible locations"""
        possible_paths = [
            path,
            os.path.join('data', 'master_cigars.tsv'),
            os.path.join('..', 'data', 'master_cigars.tsv'),
            'master_cigars.tsv'
        ]
        
        for attempt_path in possible_paths:
            try:
                if os.path.exists(attempt_path):
                    return pd.read_csv(attempt_path, sep='\t')
            except Exception as e:
                continue
        
        return pd.DataFrame()
    
    def _build_wrapper_aliases(self) -> Dict[str, str]:
        """Build wrapper alias mapping from master data + common aliases"""
        aliases = {}
        
        # Extract from master data
        for _, row in self.master_df.iterrows():
            wrapper = str(row['Wrapper']).strip()
            wrapper_alias = str(row['Wrapper_Alias']).strip()
            if wrapper != 'nan' and wrapper_alias != 'nan':
                aliases[wrapper_alias.lower()] = wrapper
                aliases[wrapper.lower()] = wrapper
        
        # Add common industry aliases
        common_aliases = {
            'natural': 'Connecticut Shade',
            'connecticut': 'Connecticut Shade',
            'conn': 'Connecticut Shade',
            'ct': 'Connecticut Shade',
            'shade': 'Connecticut Shade',
            'shade grown': 'Connecticut Shade',
            'ecuador connecticut': 'Connecticut Shade',
            'ecuadorian connecticut': 'Connecticut Shade',
            'maduro': 'Connecticut Broadleaf',
            'connecticut broadleaf': 'Connecticut Broadleaf',
            'broadleaf': 'Connecticut Broadleaf',
            'habano': 'Nicaraguan Habano',
            'nicaraguan': 'Nicaraguan Habano',
            'nicaraguan habano': 'Nicaraguan Habano',
            'ecuadorian habano': 'Ecuadorian Habano',
            'ecuador habano': 'Ecuadorian Habano',
            'sun grown': 'Ecuadorian Sungrown',
            'sungrown': 'Ecuadorian Sungrown',
            'ecuadorian sungrown': 'Ecuadorian Sungrown',
            'cameroon': 'Cameroon',
            'corojo': 'Honduran Corojo',
            'honduran corojo': 'Honduran Corojo',
            'san andres': 'Mexican San Andres',
            'mexican san andres': 'Mexican San Andres',
            'mexican': 'Mexican San Andres'
        }
        
        aliases.update(common_aliases)
        return aliases
    
    def normalize_wrapper(self, raw_wrapper: str) -> str:
        """Normalize wrapper using alias mapping"""
        if pd.isna(raw_wrapper) or not raw_wrapper or raw_wrapper == 'Unknown':
            return 'Unknown'
        
        clean_wrapper = str(raw_wrapper).strip().lower()
        
        # Direct alias lookup
        if clean_wrapper in self.wrapper_aliases:
            return self.wrapper_aliases[clean_wrapper]
        
        # Fuzzy matching for partial matches
        best_match = None
        best_score = 0.7
        
        for alias, canonical in self.wrapper_aliases.items():
            score = SequenceMatcher(None, clean_wrapper, alias).ratio()
            if score > best_score:
                best_score = score
                best_match = canonical
        
        return best_match if best_match else raw_wrapper
    
    def find_master_match(self, brand: str, line: str, wrapper: str, vitola: str) -> Optional[Dict]:
        """Find exact match in master database"""
        if not self.brand_index or brand not in self.brand_index:
            return None
        
        brand_cigars = self.brand_index[brand]
        
        # Filter by line if available
        if line and line != 'Unknown':
            filtered = brand_cigars[brand_cigars['Line'] == line]
            if not filtered.empty:
                brand_cigars = filtered
        
        # Filter by wrapper if available  
        if wrapper and wrapper != 'Unknown':
            normalized_wrapper = self.normalize_wrapper(wrapper)
            filtered = brand_cigars[
                (brand_cigars['Wrapper'] == normalized_wrapper) |
                (brand_cigars['Wrapper_Alias'] == normalized_wrapper)
            ]
            if not filtered.empty:
                brand_cigars = filtered
        
        # Filter by vitola if available
        if vitola and vitola != 'Unknown':
            filtered = brand_cigars[brand_cigars['Vitola'] == vitola]
            if not filtered.empty:
                brand_cigars = filtered
        
        if len(brand_cigars) >= 1:
            return brand_cigars.iloc[0].to_dict()
        
        return None
    
    def normalize_single_product(self, product_row: pd.Series) -> pd.Series:
        """Normalize a single product row"""
        product = product_row.copy()
        
        # Extract current values
        brand = str(product.get('brand', 'Unknown'))
        line = str(product.get('line', 'Unknown'))
        wrapper = str(product.get('wrapper', 'Unknown'))
        vitola = str(product.get('vitola', 'Unknown'))
        
        # Normalize wrapper
        original_wrapper = wrapper
        normalized_wrapper = self.normalize_wrapper(wrapper)
        product['wrapper'] = normalized_wrapper
        
        # Find master match and enrich
        master_match = self.find_master_match(brand, line, wrapper, vitola)
        
        if master_match:
            # Enrich with master data while preserving retailer info
            enrichments = {
                'wrapper': master_match['Wrapper'],
                'wrapper_alias': master_match['Wrapper_Alias'], 
                'vitola': master_match['Vitola'],
                'length': master_match['Length'],
                'ring_gauge': master_match['Ring Gauge'],
                'size': f"{master_match['Length']}x{master_match['Ring Gauge']}",
                'binder': master_match['Binder'],
                'filler': master_match['Filler'],
                'strength': master_match['Strength'],
                'master_box_qty': master_match['Box Quantity'],
                'shape': master_match['Shape'],
                'confidence_score': 1.0
            }
            
            for key, value in enrichments.items():
                product[key] = value
        else:
            # No master match - mark as scraper-only data
            product['confidence_score'] = 0.7
            if normalized_wrapper != original_wrapper:
                product['wrapper_alias'] = original_wrapper
        
        return product
    
    def auto_normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Auto-normalize entire DataFrame - MAIN INTEGRATION FUNCTION"""
        if self.master_df.empty:
            print("WARNING: Skipping normalization - master cigars database not available")
            return df
        
        print("Auto-normalizing scraped data against master database...")
        
        # Apply normalization to each row
        normalized_rows = []
        master_matches = 0
        
        for _, row in df.iterrows():
            normalized_row = self.normalize_single_product(row)
            normalized_rows.append(normalized_row)
            
            if normalized_row.get('confidence_score', 0) == 1.0:
                master_matches += 1
        
        # Create new DataFrame with normalized data
        normalized_df = pd.DataFrame(normalized_rows)
        
        # Show results
        total_products = len(normalized_df)
        wrapper_improvements = sum(1 for _, row in normalized_df.iterrows() 
                                 if pd.notna(row.get('wrapper_alias')))
        
        print(f"Normalization complete: {master_matches}/{total_products} master matches, {wrapper_improvements} wrapper improvements")
        
        return normalized_df

# Example usage function
def integrate_with_existing_scraper():
    """
    Example of how to integrate this into your existing scraper.py
    
    In your save_products_csv method, replace:
        df.to_csv(filepath, index=False)
    
    With:
        from auto_normalizer import CigarAutoNormalizer
        normalizer = CigarAutoNormalizer('data/master_cigars.tsv')
        df = normalizer.auto_normalize_dataframe(df)
        df.to_csv(filepath, index=False)
    """
    pass

if __name__ == "__main__":
    # Test the normalizer
    print("CIGAR PRICE SCOUT - AUTO-NORMALIZER TEST")
    print("=" * 50)
    
    normalizer = CigarAutoNormalizer('data/master_cigars.tsv')
    
    # Test with sample data
    test_data = {
        'title': ['Ashton Classic Majesty', 'Oliva Serie V Robusto'],
        'brand': ['Ashton', 'Oliva'],
        'line': ['Classic', 'Serie V'],
        'wrapper': ['Natural', 'Sun Grown'],
        'vitola': ['Cordial', 'Robusto'],
        'price': [218.75, 203.94],
        'retailer': ['Fox Cigar', 'Fox Cigar']
    }
    
    test_df = pd.DataFrame(test_data)
    print("BEFORE normalization:")
    print(test_df)
    
    normalized_df = normalizer.auto_normalize_dataframe(test_df)
    print("\nAFTER normalization:")
    print(normalized_df)
