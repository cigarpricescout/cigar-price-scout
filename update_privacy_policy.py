# update_privacy_policy.py - Add affiliate network compliance language
import re
from pathlib import Path
from datetime import datetime

def update_privacy_policy():
    """Update privacy policy with affiliate network compliance language"""
    
    # Find privacy policy file
    possible_files = [
        "privacy.html",
        "privacy-policy.html", 
        "templates/privacy.html",
        "static/privacy.html",
        "pages/privacy.html"
    ]
    
    policy_file = None
    for file_path in possible_files:
        if Path(file_path).exists():
            policy_file = Path(file_path)
            break
    
    if not policy_file:
        print("Privacy policy file not found. Please specify the correct path.")
        return False
    
    print(f"Updating: {policy_file}")
    
    # Create backup
    backup_file = policy_file.with_suffix(f'.backup.{datetime.now().strftime("%Y%m%d")}.html')
    import shutil
    shutil.copy2(policy_file, backup_file)
    print(f"Backup created: {backup_file}")
    
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
        
        # Add affiliate tracking section to cookies section
        affiliate_cookies_text = f'''
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
        
        # Insert after existing cookies section or before closing of privacy policy
        if re.search(r'<h[23][^>]*>.*?cookies?.*?</h[23]>', content, re.IGNORECASE):
            # Add after existing cookies section
            content = re.sub(
                r'(</ul>\s*</p>?\s*)(.*?<h[23])',
                f'\\1{affiliate_cookies_text}\\2',
                content,
                flags=re.IGNORECASE | re.DOTALL,
                count=1
            )
        else:
            # Add before the end of the privacy policy
            content = re.sub(
                r'(<h[23][^>]*>.*?contact.*?</h[23]>)',
                f'{affiliate_cookies_text}\\1',
                content,
                flags=re.IGNORECASE
            )
        
        # Update third-party data sharing section
        third_party_addition = '''
        <h3>Affiliate Partner Data Sharing</h3>
        <p>When you click affiliate links on our site, we may share non-personally identifiable information with our affiliate network partners (such as CJ Affiliate and Sovrn Commerce) to:</p>
        <ul>
            <li>Track referrals and ensure proper commission attribution</li>
            <li>Measure the effectiveness of our recommendations</li>
            <li>Comply with affiliate program requirements</li>
        </ul>
        <p>This data sharing is limited to transaction tracking and does not include any personally identifiable information.</p>
        '''
        
        # Add to third-party sharing section
        content = re.sub(
            r'(<h[23][^>]*>.*?third.party.*?</h[23]>.*?</p>)',
            f'\\1{third_party_addition}',
            content,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # Write updated content
        with open(policy_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Privacy Policy updated successfully!")
        print("Added sections for:")
        print("  - Affiliate program cookies and tracking")
        print("  - Third-party data sharing with affiliate networks") 
        print("  - Links to CJ and Sovrn privacy policies")
        print("  - EU/UK consent banner mention")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating privacy policy: {e}")
        return False

def create_affiliate_disclosure_snippet():
    """Create a reusable affiliate disclosure snippet"""
    
    disclosure_html = '''
<!-- Affiliate Disclosure Snippet - Add to product pages -->
<div class="affiliate-disclosure" style="background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 12px; margin: 16px 0; font-size: 14px; color: #6c757d;">
    <strong>Affiliate Disclosure:</strong> Cigar Price Scout participates in affiliate programs including CJ Affiliate, Sovrn Commerce, and others. When you purchase through our links, we may receive a commission at no additional cost to you. This helps support our site operations and keeps our service free.
</div>
'''
    
    with open('affiliate_disclosure_snippet.html', 'w', encoding='utf-8') as f:
        f.write(disclosure_html)
    
    print("✅ Created affiliate_disclosure_snippet.html")
    print("Use this snippet on pages with affiliate links")

if __name__ == "__main__":
    print("Updating Privacy Policy for Affiliate Compliance...")
    print("=" * 60)
    
    if update_privacy_policy():
        create_affiliate_disclosure_snippet()
        print("\n" + "=" * 60)
        print("✅ SUCCESS! Your privacy policy is now affiliate-compliant")
        print("\nNext steps:")
        print("1. Review the updated privacy policy")
        print("2. Run the terms update script") 
        print("3. Add affiliate disclosure snippets to product pages")
        print("4. Deploy changes:")
        print("   git add .")
        print('   git commit -m "Update privacy policy for affiliate compliance"')
        print("   git push")
    else:
        print("❌ Update failed - please check file paths and try again")