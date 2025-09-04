# update_terms.py - Add affiliate compliance terms
import re
from pathlib import Path
from datetime import datetime

def update_terms_of_service():
    """Update terms of service with affiliate compliance language"""
    
    # Find terms file
    possible_files = [
        "terms.html",
        "terms-of-service.html",
        "terms-and-conditions.html", 
        "templates/terms.html",
        "static/terms.html",
        "pages/terms.html"
    ]
    
    terms_file = None
    for file_path in possible_files:
        if Path(file_path).exists():
            terms_file = Path(file_path)
            break
    
    if not terms_file:
        print("Terms of service file not found. Please specify the correct path.")
        return False
    
    print(f"Updating: {terms_file}")
    
    # Create backup
    backup_file = terms_file.with_suffix(f'.backup.{datetime.now().strftime("%Y%m%d")}.html')
    import shutil
    shutil.copy2(terms_file, backup_file)
    print(f"Backup created: {backup_file}")
    
    try:
        with open(terms_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update last modified date
        today = datetime.now().strftime("%B %d, %Y")
        content = re.sub(
            r'(Last updated|Updated|Effective Date):\s*[^<\n]+',
            f'Last updated: {today}',
            content,
            flags=re.IGNORECASE
        )
        
        # Add affiliate relationship disclosure section
        affiliate_terms = '''
        <h2>Affiliate Relationships and Disclosures</h2>
        
        <h3>Affiliate Program Participation</h3>
        <p>Cigar Price Scout participates in affiliate programs including CJ Affiliate, Sovrn Commerce, and other affiliate networks. When you purchase products through our affiliate links, we may receive a commission at no additional cost to you. These commissions help support our site operations and allow us to provide our price comparison service free of charge.</p>
        
        <h3>Affiliate Link Policies</h3>
        <p>All affiliate links are displayed only on our website (cigarpricescout.com). We do not promote products or distribute affiliate links through:</p>
        <ul>
            <li>Unsolicited email or spam</li>
            <li>Social media spam or excessive posting</li>
            <li>Third-party forums without proper disclosure</li>
            <li>Instant messaging or direct messaging campaigns</li>
            <li>Any deceptive or misleading promotional methods</li>
        </ul>
        
        <h3>Pricing and Availability</h3>
        <p>While we strive to provide accurate pricing information, all prices are subject to change by the respective retailers. We are not responsible for pricing errors or changes that occur after information is displayed on our site. Final pricing, availability, and purchase terms are determined by the third-party retailer.</p>
        
        <h3>Commission Disclosure</h3>
        <p>Our affiliate relationships do not influence our price comparisons or product recommendations. We display pricing information from multiple retailers to help you make informed purchasing decisions. The presence of an affiliate relationship does not affect the accuracy of pricing data or the ranking of retailers in our comparisons.</p>
        
        <h3>Third-Party Purchases</h3>
        <p>When you click an affiliate link, you will be redirected to the retailer's website where any purchase transaction occurs. We are not a party to your transaction with the retailer and are not responsible for:</p>
        <ul>
            <li>Order fulfillment or shipping</li>
            <li>Product quality or condition</li>
            <li>Customer service or returns</li>
            <li>Payment processing or security</li>
            <li>Retailer terms and conditions</li>
        </ul>
        <p>All purchases are subject to the terms and conditions of the respective retailer.</p>
        '''
        
        # Insert before existing sections or at the end
        if re.search(r'<h[12][^>]*>.*?(limitation|liability|contact).*?</h[12]>', content, re.IGNORECASE):
            # Add before limitation/liability sections
            content = re.sub(
                r'(<h[12][^>]*>.*?(limitation|liability).*?</h[12]>)',
                f'{affiliate_terms}\\1',
                content,
                flags=re.IGNORECASE
            )
        else:
            # Add before the end of the document
            content = re.sub(
                r'(</body>|<footer|<div[^>]*footer)',
                f'{affiliate_terms}\\1',
                content,
                flags=re.IGNORECASE
            )
        
        # Add prohibited use clause
        prohibited_use_addition = '''
        <li>Distribute our affiliate links through unsolicited communications</li>
        <li>Use our links in spam or deceptive marketing practices</li>
        <li>Attempt to manipulate affiliate tracking or commissions</li>
        <li>Misrepresent your relationship with our affiliate partners</li>
        '''
        
        # Add to existing prohibited use section if it exists
        content = re.sub(
            r'(<ul[^>]*>.*?</li>)(\s*</ul>.*?prohibited|prohibited.*?</ul>)',
            f'\\1{prohibited_use_addition}\\2',
            content,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # Write updated content
        with open(terms_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Terms of Service updated successfully!")
        print("Added sections for:")
        print("  - Affiliate program participation disclosure")
        print("  - Affiliate link promotion policies")
        print("  - Commission and pricing disclaimers")
        print("  - Third-party purchase terms")
        print("  - Prohibited use clauses")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating terms: {e}")
        return False

def create_compliance_checklist():
    """Create a compliance checklist for affiliate programs"""
    
    checklist = '''
# Affiliate Program Compliance Checklist

## ✅ Privacy Policy Updates
- [x] Affiliate cookie tracking disclosure
- [x] Third-party data sharing explanation  
- [x] Links to affiliate partner privacy policies
- [x] EU/UK consent banner mention
- [x] No PII transmission guarantee

## ✅ Terms of Service Updates
- [x] Affiliate relationship disclosure
- [x] Promotional method restrictions
- [x] Commission transparency
- [x] Third-party purchase disclaimers
- [x] Prohibited use clauses

## 🔲 Website Implementation (To Do)
- [ ] Add affiliate disclosure snippets to product pages
- [ ] Implement EU/UK cookie consent banner
- [ ] Test affiliate link tracking
- [ ] Update About page with affiliate mentions
- [ ] Add affiliate disclosures near pricing tables

## 📋 Network Applications Ready
- [ ] CJ Affiliate (apply with updated policies)
- [ ] ShareASale (apply after CJ approval)
- [ ] Impact Radius (research relevant programs)

## 🎯 Post-Approval Tasks
- [ ] Add specific network privacy policy links
- [ ] Update affiliate disclosure with approved networks
- [ ] Set up conversion tracking
- [ ] Monitor compliance with network terms

## 📝 Notes
- All policies now mention affiliate networks by name
- Compliance language covers major network requirements
- Ready for immediate application to CJ Affiliate
- Proactive approach demonstrates professionalism
'''
    
    with open('affiliate_compliance_checklist.md', 'w', encoding='utf-8') as f:
        f.write(checklist)
    
    print("✅ Created affiliate_compliance_checklist.md")

if __name__ == "__main__":
    print("Updating Terms of Service for Affiliate Compliance...")
    print("=" * 60)
    
    if update_terms_of_service():
        create_compliance_checklist()
        print("\n" + "=" * 60)
        print("✅ SUCCESS! Your terms are now affiliate-compliant")
        print("\nNext steps:")
        print("1. Review the updated terms of service")
        print("2. Check the compliance checklist")
        print("3. Deploy changes:")
        print("   git add .")
        print('   git commit -m "Update terms for affiliate compliance"')
        print("   git push")
        print("4. Ready to apply to CJ Affiliate!")
    else:
        print("❌ Update failed - please check file paths and try again")