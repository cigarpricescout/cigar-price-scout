# 💰 Affiliate Feed Integration

Start earning revenue from your existing traffic with affiliate feeds!

## 🎯 Quick Start (5 minutes)

### Step 1: Create `.env` File
```bash
# In your project root (c:\Users\briah\cigar-price-scout)
# Create a file named: .env

# Add these lines:
CJ_PERSONAL_ACCESS_TOKEN=your_token_here
CJ_WEBSITE_ID=101532120
CJ_COMPANY_ID=7711335
```

**Get your CJ token:**
1. Go to: https://developers.cj.com/
2. Login → Authentication → Personal Access Tokens
3. Create New Token → Copy it
4. Paste in `.env` file

### Step 2: Install Required Package
```bash
pip install python-dotenv
```

### Step 3: Test Connection
```bash
cd tools/affiliate
python test_cj_connection.py
```

Should see: ✅ "Successfully connected to CJ API!"

### Step 4: Run Daily Update
```bash
cd tools/affiliate_feeds
python daily_affiliate_updater.py
```

---

## 📊 **What This Does**

**Current:** You scrape Famous Smoke daily (slow, breaks if site changes)

**With Affiliate Feeds:**
- ✅ Pull Famous Smoke data from CJ API (fast, reliable)
- ✅ Get affiliate links automatically (earn 5-10% commission)
- ✅ Official product data (better accuracy)
- ✅ No scraping breakage

**Best part:** You earn money from traffic you already have!

---

## 🔄 **Integration with Daily Automation**

Add to your `automation/automated_cigar_price_system.py`:

```python
# After line 60, add:
def run_affiliate_updates(self):
    """Run affiliate feed updates before scrapers"""
    print("\n=== Running Affiliate Feed Updates ===")
    
    try:
        affiliate_script = self.project_root / 'tools' / 'affiliate_feeds' / 'daily_affiliate_updater.py'
        result = subprocess.run(
            ['python', str(affiliate_script)],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            print("✅ Affiliate feeds updated successfully")
            return True
        else:
            print(f"❌ Affiliate feed update failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Affiliate update error: {e}")
        return False

# Then in the main run() method, add before scraper updates:
def run(self):
    # ... existing code ...
    
    # NEW: Run affiliate updates first
    self.run_affiliate_updates()
    
    # Then run your existing scraper updates
    # ... rest of code ...
```

---

## 💰 **Revenue Potential**

**Assumptions:**
- You get 100 clicks/day to Famous Smoke
- 5% convert to sales (5 sales/day)
- Average order: $100
- Commission: 8%

**Monthly Revenue:**
- 5 sales/day × 30 days = 150 sales/month
- 150 × $100 × 8% = **$1,200/month**

**And that's just ONE retailer!**

---

## 📈 **Retailers You Can Add**

**CJ Affiliate (you're approved):**
- Famous Smoke Shop
- Gotham Cigars
- Cigars International (if approved)
- Thompson Cigar (if approved)

**Sovrn Commerce (you're approved):**
- Various retailers (check your Sovrn dashboard)

**AWIN (you're approved):**
- Check which cigar retailers are available

---

## 🔑 **Finding Advertiser IDs**

**For CJ:**
```python
# Use the test script
cd tools/affiliate
python test_cj_connection.py

# It will show all available advertisers
# Note the IDs for your approved retailers
```

**For Sovrn:**
- Login to: https://merchants.commerce.sovrn.com/
- Check available merchants
- Get API keys from settings

---

## 🎯 **Next Steps (After .env Setup)**

1. ✅ Test CJ connection
2. ✅ Run affiliate updater once manually
3. ✅ Compare prices: Affiliate feed vs scraper
4. ✅ Verify affiliate links work
5. ✅ Add to daily automation
6. ✅ Monitor commission earnings in CJ dashboard

---

## 📊 **Monitoring Revenue**

**CJ Dashboard:**
- Login: https://members.cj.com/
- View commissions: Reports → Performance Reports
- Track clicks, sales, revenue

**Expected timeline:**
- Day 1: Setup complete
- Week 1: First clicks showing up
- Week 2: First commissions pending
- Month 2: First payout ($100+ minimum)

---

## 🚨 **Important Notes**

**Affiliate links:**
- Already configured in `cj_famous_integration.py`
- Automatically includes your tracking ID
- No extra work needed!

**Data accuracy:**
- Affiliate feeds update daily (like your scrapers)
- Usually more accurate than scraping
- Official product data from retailers

**Commission tracking:**
- CJ handles all tracking automatically
- You just provide the feed data
- Commissions paid monthly

---

## 🎁 **Bonus: Sovrn Integration**

You already have `working_sovrn_api.py` - integrate it next!

**Sovrn benefits:**
- Price comparison API (not just affiliate links)
- Real-time price checks
- Multiple retailers in one API

---

## 💡 **Pro Tips**

**Start small:**
- Test with Famous Smoke first
- Verify prices match your scraper
- Confirm affiliate links work
- Then add more retailers

**Compare quality:**
- Run both (feed + scraper) for 1 week
- See which has better data
- Switch to feed-only if better

**Monitor earnings:**
- Check CJ dashboard weekly
- Track which products convert best
- Optimize based on data

---

## 📞 **Support**

**CJ API Docs:** https://developers.cj.com/
**Sovrn Docs:** https://dev.commerce.sovrn.com/
**Questions?** Check `tools/affiliate/` for working examples

---

**Ready to start earning? Add your CJ token to `.env` and run the test!** 🚀
