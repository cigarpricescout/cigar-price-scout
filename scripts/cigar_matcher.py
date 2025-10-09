import csv
from pathlib import Path
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)

class CigarMatcher:
    """
    Matches affiliate feed products against master cigar list
    to fill in missing/incorrect metadata
    """
    
    def __init__(self, master_file_path):
        self.master_cigars = []
        self.load_master_file(master_file_path)
    
    def load_master_file(self, file_path):
        """Load master cigar database"""
        master_path = Path(file_path)
        
        if not master_path.exists():
            logger.error(f"Master file not found: {file_path}")
            return
        
        with open(master_path, 'r', encoding='utf-8') as f:
            # Assuming tab-separated like your examples
            reader = csv.DictReader(f, delimiter='\t')
            
            for row in reader:
                self.master_cigars.append({
                    'brand': row.get('Brand', '').strip(),
                    'line': row.get('Line', '').strip(),
                    'wrapper': row.get('Wrapper', '').strip(),
                    'wrapper_alias': row.get('Wrapper_Alias', '').strip(),
                    'vitola': row.get('Vitola', '').strip(),
                    'length': row.get('Length', '').strip(),
                    'ring_gauge': row.get('Ring Gauge', '').strip(),
                    'binder': row.get('Binder', '').strip(),
                    'filler': row.get('Filler', '').strip(),
                    'strength': row.get('Strength', '').strip(),
                    'box_qty': row.get('Box Quantity', '25').strip(),
                    'shape': row.get('Shape', 'Parejo').strip()
                })
        
        logger.info(f"Loaded {len(self.master_cigars)} cigars from master file")
    
    def normalize_string(self, s):
        """Normalize strings for matching"""
        if not s:
            return ""
        return s.lower().strip().replace('-', ' ').replace('  ', ' ')
    
    def similarity_score(self, str1, str2):
        """Calculate similarity between two strings (0-1)"""
        return SequenceMatcher(None, 
                             self.normalize_string(str1), 
                             self.normalize_string(str2)).ratio()
    
    def find_matches(self, brand, line, title=""):
        """
        Find all matching cigars from master list
        Returns list of matching cigars with confidence scores
        """
        matches = []
        brand_norm = self.normalize_string(brand)
        line_norm = self.normalize_string(line)
        
        for cigar in self.master_cigars:
            cigar_brand_norm = self.normalize_string(cigar['brand'])
            cigar_line_norm = self.normalize_string(cigar['line'])
            
            # Brand must match closely (>0.85 similarity)
            brand_score = self.similarity_score(brand, cigar['brand'])
            if brand_score < 0.85:
                continue
            
            # Line must match closely (>0.80 similarity)
            line_score = self.similarity_score(line, cigar['line'])
            if line_score < 0.80:
                continue
            
            # Calculate overall confidence
            confidence = (brand_score * 0.5) + (line_score * 0.5)
            
            matches.append({
                'cigar': cigar,
                'confidence': confidence
            })
        
        # Sort by confidence
        matches.sort(key=lambda x: x['confidence'], reverse=True)
        
        return matches
    
    def get_best_match(self, brand, line, title=""):
        """
        Get the single best match
        Returns None if no good match found
        """
        matches = self.find_matches(brand, line, title)
        
        if not matches:
            return None
        
        # Return best match if confidence > 0.85
        if matches[0]['confidence'] >= 0.85:
            return matches[0]['cigar']
        
        return None
    
    def get_all_vitolas_for_line(self, brand, line):
        """
        Get all vitolas for a brand+line combination
        Used when affiliate feed has generic "Arturo Fuente Gran Reserva"
        """
        matches = self.find_matches(brand, line)
        
        if not matches:
            return []
        
        # Extract unique vitolas
        vitolas = []
        seen = set()
        
        for match in matches:
            cigar = match['cigar']
            key = f"{cigar['vitola']}_{cigar['wrapper']}_{cigar['length']}x{cigar['ring_gauge']}"
            
            if key not in seen:
                seen.add(key)
                vitolas.append(cigar)
        
        return vitolas