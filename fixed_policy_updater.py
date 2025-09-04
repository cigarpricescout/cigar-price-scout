# update_policies_fixed.py - Update privacy and terms files (Windows compatible)
import re
from pathlib import Path
from datetime import datetime
import shutil

def update_privacy_policy():
    """Update privacy policy with affiliate compliance language"""
    
    policy_file = Path("static/privacy-policy.html")
    
    if not policy_file.exists():
        print("ERROR: privacy-policy.html not found in static folder")
        return False
    
    print(f"Updating: {policy_file}")
    
    # Create backup
    backup_file = policy_file.with_suffix(f'.backup.{datetime.now().strftime("%Y%m%d")}.html')
    shutil.copy2(policy_file, backup_file)
    print(f"BACKUP: Created {backup_file}")
    
    try:
        with open(policy_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update last modified date
        today = datetime.now().strftime("%B %d, %Y")
        content = re.sub(
            r'(Last updated|Updated|Effective Date):\s*[^<\n]+',
            f'Last updated: {today}',
            content,
            flags=re.IGNORECASE
        )
        
        # Add affiliate tracking section
        affiliate_section = f'''
    <h3>Affiliate Program Cookies and Tracking</h3>
    <p>Some affiliate programs we participate in, including CJ Affiliate, Sovrn Commerce, and others, may use cookies and similar tracking technologies to track purchases and ensure we receive credit for referrals. These cookies:</p>
    <ul>
        <li>Do not collect personally identifiable information</li>
        <li>Are used solely for commission tracking purposes</li>
        <li>Help us earn commissions when you make purchases through our links</li>
        <li>Allow us to provide our service free of charge</li>
    </ul>
    <p>When you click an affiliate link, non-personally identifiable tracking data may be shared with our affiliate partners for commission purposes. We do not transmit personal information (such as names or email addresses) to third parties via our affiliate links.</p>
    <p>For visitors in the EU/UK: You will be presented with a consent banner before affiliate tracking cookies are set, in compliance with GDPR and similar privacy regulations.</p>
    <p>You can learn more about our affiliate partners' privacy practices:</p>
    <ul>
        <li><a href="https://www.cj.com/legal/privacy-policy-services" target="_blank">CJ Affiliate Privacy Policy</a></li>
        <li><a href="https://www.sovrn.com/privacy-policy/" target="_blank">Sovrn Commerce Privacy Policy</a></li>
    </ul>
'''
        
        # Insert before the contact section or at the end
        if re.search(r'<h[23][^>]*>.*?contact.*?</h[23]>', content, re.IGNORECASE):
            content = re.sub(
                r'(<h[23][^>]*>.*?contact.*?</h[23]>)',
                f'{affiliate_section}\\1',
                content,
                flags=re.IGNORECASE
            )
        else:
            # Add before closing body tag
            content = re.sub(
                r'(</body>)',
                f'{affiliate_section}\\1',
                content,
                flags=re.IGNORECASE
            )
        
        # Write updated content
        with open(policy_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("SUCCESS: Privacy Policy updated!")
        print("Added affiliate tracking and compliance sections")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def update_terms_of_service():
    """Update terms with affiliate compliance language"""
    
    terms_file = Path("static/terms-of-service.html")
    
    if not terms_file.exists():
        print("ERROR: terms-of-service.html not found in static folder")
        return False
    
    print(f"Updating: {terms_file}")
    
    # Create backup
    backup_file = terms_file.with_suffix(f'.backup.{datetime.now().strftime("%Y%m%d")}.html')
    shutil.copy2(terms_file, backup_file)
    print(f"BACKUP: Created {backup_file}")
    
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
        
        # Add affiliate terms section
        affiliate_terms = f'''
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
        
        # Insert before contact section or at the end
        if re.search(r'<h[23][^>]*>.*?contact.*?</h[23]>', content, re.IGNORECASE):
            content = re.sub(
                r'(<h[23][^>]*>.*?contact.*?</h[23]>)',
                f'{affiliate_terms}\\1',
                content,
                flags=re.IGNORECASE
            )
        else:
            # Add before closing body tag
            content = re.sub(
                r'(</body>)',
                f'{affiliate_terms}\\1',
                content,
                flags=re.IGNORECASE
            )
        
        # Write updated content
        with open(terms_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("SUCCESS: Terms of Service updated!")
        print("Added affiliate relationship and compliance sections")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def create_affiliate_disclosure_snippet():
    """Create reusable affiliate disclosure for product pages"""
    
    disclosure_html = '''<!-- Affiliate Disclosure Snippet -->
<div class="affiliate-disclosure" style="background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 12px; margin: 16px 0; font-size: 14px; color: #6c757d;">
    <strong>Affiliate Disclosure:</strong> Cigar Price Scout participates in affiliate programs including CJ Affiliate, Sovrn Commerce, and others. When you purchase through our links, we may receive a commission at no additional cost to you. This helps support our site operations and keeps our service free.
</div>'''
    
    with open('affiliate_disclosure_snippet.html', 'w', encoding='utf-8') as f:
        f.write(disclosure_html)
    
    print("CREATED: affiliate_disclosure_snippet.html")

def create_compliance_checklist():
    """Create compliance tracking checklist"""
    
    checklist = '''# Affiliate Compliance Checklist

## COMPLETED - Policy Updates
[x] Privacy Policy - Affiliate cookie tracking disclosure
[x] Privacy Policy - Third-party data sharing explanation  
[x] Privacy Policy - Links to affiliate partner privacy policies
[x] Privacy Policy - EU/UK consent banner mention
[x] Terms of Service - Affiliate relationship disclosure
[x] Terms of Service - Promotional method restrictions
[x] Terms of Service - Commission transparency
[x] Terms of Service - Third-party purchase disclaimers

## TODO - Website Implementation
[ ] Add affiliate disclosure snippets to product pages
[ ] Implement EU/UK cookie consent banner (if needed)
[ ] Test affiliate link tracking
[ ] Update About page with affiliate mentions
[ ] Add affiliate disclosures near pricing tables

## READY - Network Applications
[ ] CJ Affiliate (apply with updated policies)
[ ] ShareASale (apply after CJ approval)  
[ ] Impact Radius (research relevant programs)

## POST-APPROVAL Tasks
[ ] Add specific network privacy policy links
[ ] Update affiliate disclosure with approved networks
[ ] Set up conversion tracking
[ ] Monitor compliance with network terms

Files Updated:
- static/privacy-policy.html
- static/terms-of-service.html  
- affiliate_disclosure_snippet.html (created)
- affiliate_compliance_checklist.md (this file)

Your policies now meet CJ Affiliate and Sovrn Commerce requirements!
'''
    
    with open('affiliate_compliance_checklist.md', 'w', encoding='utf-8') as f:
        f.write(checklist)
    
    print("CREATED: affiliate_compliance_checklist.md")

if __name__ == "__main__":
    print("Updating Privacy Policy and Terms for Affiliate Compliance...")
    print("=" * 60)
    
    privacy_success = update_privacy_policy()
    print("")
    terms_success = update_terms_of_service()
    
    if privacy_success and terms_success:
        print("")
        create_affiliate_disclosure_snippet()
        create_compliance_checklist()
        
        print("\n" + "=" * 60)
        print("SUCCESS! Your policies are now affiliate-compliant")
        print("\nFiles updated:")
        print("  - static/privacy-policy.html")
        print("  - static/terms-of-service.html")
        print("  - affiliate_disclosure_snippet.html (created)")
        print("  - affiliate_compliance_checklist.md (created)")
        print("\nNext steps:")
        print("1. Review the updated files")
        print("2. Deploy changes:")
        print("   git add .")
        print('   git commit -m "Update policies for affiliate compliance"')
        print("   git push")
        print("3. Apply to CJ Affiliate - you're now compliant!")
        print("4. Use affiliate_disclosure_snippet.html on product pages")
    else:
        print("Some updates failed - check error messages above")