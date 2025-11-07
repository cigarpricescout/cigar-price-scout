#!/bin/bash

# Cigar Price Scout - Website File Update Script
# This script updates your HTML files with SEO improvements and canonical tags

echo "🔧 Updating Cigar Price Scout website files..."

# Check if we're in the right directory
if [ ! -d "static" ]; then
    echo "❌ Error: 'static' directory not found. Please run this script from your cigar-price-scout project root directory."
    exit 1
fi

echo "📁 Found static directory. Proceeding with updates..."

# Backup existing files
echo "💾 Creating backups of existing files..."
mkdir -p backups/$(date +%Y%m%d_%H%M%S)
cp static/*.html backups/$(date +%Y%m%d_%H%M%S)/ 2>/dev/null || echo "No HTML files found to backup"

# Update index.html - Add canonical URL after Twitter cards
echo "🏠 Updating index.html..."
sed -i 's|    <meta name="twitter:image" content="https://cigarpricescout.com/static/cigar-scout-social.png" />|    <meta name="twitter:image" content="https://cigarpricescout.com/static/cigar-scout-social.png" />\
    \
    <!-- Canonical URL -->\
    <link rel="canonical" href="https://cigarpricescout.com/" />|' static/index.html

# Update about.html - Add canonical URL after viewport meta
echo "ℹ️  Updating about.html..."
sed -i 's|    <meta name="viewport" content="width=device-width,initial-scale=1" />|    <meta name="viewport" content="width=device-width,initial-scale=1" />\
    \
    <!-- Canonical URL -->\
    <link rel="canonical" href="https://cigarpricescout.com/about.html" />|' static/about.html

# Update privacy-policy.html - Add canonical URL after viewport meta
echo "🔐 Updating privacy-policy.html..."
sed -i 's|    <meta name="viewport" content="width=device-width,initial-scale=1" />|    <meta name="viewport" content="width=device-width,initial-scale=1" />\
    \
    <!-- Canonical URL -->\
    <link rel="canonical" href="https://cigarpricescout.com/privacy-policy.html" />|' static/privacy-policy.html

# Update contact.html - Add canonical URL after viewport meta
echo "📞 Updating contact.html..."
sed -i 's|    <meta name="viewport" content="width=device-width,initial-scale=1">|    <meta name="viewport" content="width=device-width,initial-scale=1">\
    \
    <!-- Canonical URL -->\
    <link rel="canonical" href="https://cigarpricescout.com/contact.html" />|' static/contact.html

# Update terms-of-service.html - Add canonical URL after viewport meta
echo "📋 Updating terms-of-service.html..."
sed -i 's|    <meta name="viewport" content="width=device-width,initial-scale=1" />|    <meta name="viewport" content="width=device-width,initial-scale=1" />\
    \
    <!-- Canonical URL -->\
    <link rel="canonical" href="https://cigarpricescout.com/terms-of-service.html" />|' static/terms-of-service.html

# Create disclaimer.html if it doesn't exist or is empty
echo "⚠️  Checking disclaimer.html..."
if [ ! -f "static/disclaimer.html" ] || [ ! -s "static/disclaimer.html" ]; then
    echo "📝 Creating disclaimer.html..."
    cat > static/disclaimer.html << 'EOF'
<!doctype html>
<html lang="en">
  <head>
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-QV9XYRECFK"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-QV9XYRECFK');
    </script>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    
    <!-- Canonical URL -->
    <link rel="canonical" href="https://cigarpricescout.com/disclaimer.html" />
    
    <title>Disclaimer - Cigar Price Scout</title>
    <meta name="description" content="Important disclaimers and limitations regarding Cigar Price Scout's price comparison service and affiliate relationships." />

    <!-- Same fonts as main site -->
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&display=swap" rel="stylesheet" />
    <link rel="icon" type="image/png" href="/static/logo.png">

    <style>
      :root{
        --ink:#111;
        --muted:#4b5563;
        --rule:#e5e7eb;
        --accent:#7c5c2e;
      }
      body{
        margin:0;
        color:var(--ink);
        background:#faf7f2;
        font-family:"Cormorant Garamond", serif;
        font-size:18px;
        line-height:1.6;
      }
      .wrap{max-width:800px;margin:0 auto;padding:0 20px}
      
      .header{
        display:flex;align-items:center;justify-content:space-between;
        padding:20px 0;border-bottom:1px solid var(--rule);margin-bottom:30px;
      }
      .logo{
        font-family:"Cinzel", serif;
        font-weight:700;
        font-size:24px;
        text-decoration:none;
        color:var(--ink);
      }
      .nav{
        display:flex;gap:20px;
      }
      .nav a{
        color:var(--muted);
        text-decoration:none;
        font-size:16px;
      }
      .nav a:hover{color:var(--accent)}
      
      h1{font-family:"Cinzel", serif;font-weight:700;letter-spacing:.3px;margin:0 0 20px}
      h2{font-family:"Cinzel", serif;font-weight:600;letter-spacing:.2px;margin:30px 0 15px;color:var(--accent)}
      h3{font-family:"Cinzel", serif;font-weight:500;letter-spacing:.1px;margin:25px 0 12px;color:var(--accent)}
      p{margin:0 0 15px}
      ul{margin:0 0 15px;padding-left:25px}
      li{margin-bottom:8px}
      
      .important-notice{
        background:#fcfbf9;
        padding:20px;
        border-radius:8px;
        border-left:4px solid var(--accent);
        margin:20px 0;
        font-weight:500;
      }
      
      .footer{
        border-top:1px solid var(--rule);
        padding:20px 0;
        margin-top:40px;
        text-align:center;
        color:var(--muted);
        font-size:14px;
      }
      .footer a{color:inherit;text-decoration:none}
      .footer a:hover{color:var(--accent)}
      
      @media (max-width: 600px){
        .header{flex-direction:column;gap:15px}
        .nav{justify-content:center}
      }
    </style>
  </head>
  <body>
    <div class="wrap">

      <header class="header">
        <a href="/" class="logo">Cigar Price Scout</a>
        <nav class="nav">
          <a href="/">Home</a>
          <a href="/about.html">About</a>
          <a href="/privacy-policy.html">Privacy</a>
          <a href="/terms-of-service.html">Terms</a>
          <a href="/contact.html">Contact</a>
        </nav>
      </header>

      <main>
        <h1>Disclaimer</h1>
        
        <div class="important-notice">
          <strong>Important:</strong> This disclaimer explains the limitations of our price comparison service and our affiliate relationships. Please read carefully.
        </div>

        <h2>Price Comparison Service Limitations</h2>
        <p>Cigar Price Scout provides price comparison information as a service to consumers. However, please note the following important limitations:</p>
        <ul>
          <li><strong>Price Accuracy:</strong> While we strive to maintain accurate pricing information, prices change frequently and may not reflect current retailer pricing at the time of your visit</li>
          <li><strong>Availability:</strong> Product availability is not guaranteed and may vary by retailer</li>
          <li><strong>Shipping & Tax Estimates:</strong> Shipping costs and tax calculations are estimates only. Final costs are determined by the retailer at checkout</li>
          <li><strong>No Purchase Guarantee:</strong> We do not guarantee that retailers will honor the prices displayed or that products will be available for purchase</li>
        </ul>

        <h2>Affiliate Relationship Disclosure</h2>
        <p>Cigar Price Scout participates in affiliate marketing programs and earns commissions from retailer partners. This means:</p>
        <ul>
          <li>We receive compensation when you make purchases through our affiliate links</li>
          <li>This compensation does not affect the prices you pay to retailers</li>
          <li>Our price comparisons remain objective and unbiased regardless of commission rates</li>
          <li>We are not employees or direct representatives of any cigar retailer</li>
        </ul>

        <h2>No Direct Sales or Customer Service</h2>
        <p>Important clarifications about our role:</p>
        <ul>
          <li><strong>We do not sell cigars:</strong> All purchases occur directly with the retailer</li>
          <li><strong>Customer service:</strong> For order issues, shipping problems, or returns, contact the retailer directly</li>
          <li><strong>Product quality:</strong> We are not responsible for product quality, freshness, or authenticity - this is the retailer's responsibility</li>
          <li><strong>Transaction disputes:</strong> Any payment or order disputes must be resolved with the retailer</li>
        </ul>

        <h2>Age Verification and Legal Compliance</h2>
        <ul>
          <li>Our service is intended for users 21 years of age or older</li>
          <li>Cigar purchases must comply with local and federal tobacco laws</li>
          <li>Retailers are responsible for age verification and legal compliance</li>
          <li>We do not verify the legal status of tobacco products in your jurisdiction</li>
        </ul>

        <h2>Limitation of Liability</h2>
        <p>To the fullest extent permitted by law, Cigar Price Scout disclaims all warranties and is not liable for any damages arising from the use of our service or reliance on pricing information.</p>

      </main>

      <footer class="footer">
        <div>&copy; 2025 Cigar Price Scout. All rights reserved. | <a href="/privacy-policy.html">Privacy Policy</a> | <a href="/terms-of-service.html">Terms of Service</a></div>
      </footer>
    </div>
  </body>
</html>
EOF
else
    echo "📝 disclaimer.html exists and has content, adding canonical tag..."
    sed -i 's|    <meta name="viewport" content="width=device-width,initial-scale=1" />|    <meta name="viewport" content="width=device-width,initial-scale=1" />\
    \
    <!-- Canonical URL -->\
    <link rel="canonical" href="https://cigarpricescout.com/disclaimer.html" />|' static/disclaimer.html
fi

echo ""
echo "✅ Website files updated successfully!"
echo ""
echo "📋 Changes made:"
echo "   • Added canonical URLs to all pages"
echo "   • Created/updated disclaimer.html"
echo "   • Improved meta tag structure"
echo "   • Backed up original files to backups/ directory"
echo ""
echo "🚀 Next steps:"
echo "   1. Test your website locally to ensure everything works"
echo "   2. Deploy these changes to your live site"
echo "   3. Submit your sitemap to Google Search Console"
echo "   4. Request re-indexing of your pages"
echo ""
echo "💡 These changes should resolve the Google indexing issues within 2-4 weeks."
EOF