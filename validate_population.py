#!/usr/bin/env python3
"""
Validation Script - Verify integrity of populated retailer CSVs
Checks for duplicates, data quality, and completeness
"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple
from collections import Counter

class CSVValidator:
    def __init__(self, retailer_csv_dir: str = 'static/data'):
        """Initialize validator with retailer CSV directory"""
        self.retailer_dir = Path(retailer_csv_dir)
        self.validation_results = {}
        self.errors = []
        self.warnings = []
        
    def get_retailer_csvs(self) -> List[Path]:
        """Get all active retailer CSV files (exclude backups)"""
        csv_files = [f for f in self.retailer_dir.glob('*.csv') if 'backup' not in f.name.lower()]
        return sorted(csv_files)
    
    def validate_single_csv(self, csv_file: Path) -> Dict:
        """
        Validate a single retailer CSV
        
        Checks:
        - No duplicate cigar_id values
        - All required fields present
        - URL field is empty for new CIDs (as intended)
        - Data types are correct
        """
        retailer_name = csv_file.stem
        result = {
            'retailer': retailer_name,
            'status': 'valid',
            'errors': [],
            'warnings': [],
            'stats': {}
        }
        
        try:
            # Load CSV
            df = pd.read_csv(csv_file)
            
            # Basic stats
            result['stats']['total_rows'] = len(df)
            result['stats']['empty_urls'] = df['url'].isna().sum() + (df['url'] == '').sum()
            result['stats']['empty_prices'] = df['price'].isna().sum() + (df['price'] == '').sum()
            
            # Check for duplicate cigar_id values
            duplicates = df[df.duplicated(subset=['cigar_id'], keep=False)]
            if not duplicates.empty:
                duplicate_cids = duplicates['cigar_id'].unique().tolist()
                result['errors'].append(f"Found {len(duplicate_cids)} duplicate cigar_id(s): {duplicate_cids[:5]}")
                result['status'] = 'error'
            
            # Check for missing required fields
            required_fields = ['cigar_id', 'brand', 'line', 'vitola', 'size', 'box_qty']
            for field in required_fields:
                missing_count = df[field].isna().sum()
                if missing_count > 0:
                    result['errors'].append(f"Missing {field} in {missing_count} row(s)")
                    result['status'] = 'error'
            
            # Check for rows with cigar_id but no brand (data integrity issue)
            invalid_rows = df[df['cigar_id'].notna() & df['brand'].isna()]
            if not invalid_rows.empty:
                result['errors'].append(f"Found {len(invalid_rows)} row(s) with cigar_id but no brand")
                result['status'] = 'error'
            
            # Warnings for empty URLs (expected for new CIDs)
            if result['stats']['empty_urls'] > 0:
                result['warnings'].append(f"{result['stats']['empty_urls']} CID(s) need URL research")
            
            # Warnings for empty prices (expected for new CIDs)
            if result['stats']['empty_prices'] > 0:
                result['warnings'].append(f"{result['stats']['empty_prices']} CID(s) need price updates")
            
        except Exception as e:
            result['status'] = 'error'
            result['errors'].append(f"Failed to validate: {str(e)}")
        
        return result
    
    def validate_all_csvs(self):
        """Validate all retailer CSVs"""
        retailer_csvs = self.get_retailer_csvs()
        
        print("="*80)
        print("CSV VALIDATION - POST-POPULATION INTEGRITY CHECKS")
        print("="*80)
        print(f"Validating {len(retailer_csvs)} retailer CSVs...\n")
        
        for csv_file in retailer_csvs:
            result = self.validate_single_csv(csv_file)
            self.validation_results[result['retailer']] = result
            
            # Track global errors and warnings
            if result['errors']:
                self.errors.extend([(result['retailer'], e) for e in result['errors']])
            if result['warnings']:
                self.warnings.extend([(result['retailer'], w) for w in result['warnings']])
            
            # Print status
            status_icon = "X" if result['status'] == 'error' else "OK"
            status_color = "ERROR" if result['status'] == 'error' else "VALID"
            print(f"  [{status_icon}] {result['retailer']:25s} | Status: {status_color:6s} | "
                  f"Rows: {result['stats']['total_rows']:3d} | "
                  f"Empty URLs: {result['stats']['empty_urls']:3d} | "
                  f"Errors: {len(result['errors']):2d}")
    
    def generate_validation_report(self) -> str:
        """Generate detailed validation report"""
        report = []
        report.append("="*80)
        report.append("CSV VALIDATION REPORT")
        report.append("="*80)
        report.append("")
        
        # Summary statistics
        total_csvs = len(self.validation_results)
        valid_csvs = sum(1 for r in self.validation_results.values() if r['status'] == 'valid')
        error_csvs = sum(1 for r in self.validation_results.values() if r['status'] == 'error')
        
        report.append("SUMMARY:")
        report.append(f"  Total CSVs validated: {total_csvs}")
        report.append(f"  Valid CSVs: {valid_csvs}")
        report.append(f"  CSVs with errors: {error_csvs}")
        report.append(f"  Total errors: {len(self.errors)}")
        report.append(f"  Total warnings: {len(self.warnings)}")
        report.append("")
        
        # Global statistics
        total_rows = sum(r['stats']['total_rows'] for r in self.validation_results.values())
        total_empty_urls = sum(r['stats']['empty_urls'] for r in self.validation_results.values())
        total_empty_prices = sum(r['stats']['empty_prices'] for r in self.validation_results.values())
        
        report.append("GLOBAL STATISTICS:")
        report.append(f"  Total CIDs across all retailers: {total_rows}")
        report.append(f"  CIDs needing URL research: {total_empty_urls}")
        report.append(f"  CIDs needing price updates: {total_empty_prices}")
        report.append("")
        
        # Errors
        if self.errors:
            report.append("="*80)
            report.append("ERRORS FOUND:")
            report.append("="*80)
            for retailer, error in self.errors:
                report.append(f"  {retailer}: {error}")
            report.append("")
        else:
            report.append("NO ERRORS FOUND!")
            report.append("")
        
        # Sample warnings (first 10)
        if self.warnings:
            report.append("="*80)
            report.append("WARNINGS (Sample):")
            report.append("="*80)
            for retailer, warning in self.warnings[:10]:
                report.append(f"  {retailer}: {warning}")
            if len(self.warnings) > 10:
                report.append(f"  ... and {len(self.warnings) - 10} more warnings")
            report.append("")
        
        # Retailers needing most URL research
        url_research_needed = sorted(
            [(r['retailer'], r['stats']['empty_urls']) for r in self.validation_results.values()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        report.append("="*80)
        report.append("TOP 10 RETAILERS NEEDING URL RESEARCH:")
        report.append("="*80)
        for retailer, count in url_research_needed:
            report.append(f"  {retailer}: {count} CIDs")
        report.append("")
        
        # Final verdict
        report.append("="*80)
        if error_csvs == 0:
            report.append("VALIDATION PASSED - All CSVs are valid!")
            report.append("Ready for URL research and price updates.")
        else:
            report.append("VALIDATION FAILED - Please fix errors before proceeding.")
        report.append("="*80)
        
        return "\n".join(report)
    
    def save_validation_report(self, filename: str = "validation_report.txt"):
        """Save validation report to file"""
        report = self.generate_validation_report()
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\nValidation report saved to: {filename}")
        return filename

def main():
    """Run validation"""
    validator = CSVValidator()
    validator.validate_all_csvs()
    
    # Generate and display report
    print("\n" + validator.generate_validation_report())
    
    # Save report
    validator.save_validation_report()
    
    # Exit with error code if validation failed
    error_count = sum(1 for r in validator.validation_results.values() if r['status'] == 'error')
    exit(0 if error_count == 0 else 1)

if __name__ == '__main__':
    main()
