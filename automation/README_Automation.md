# Automated Cigar Price System

Complete hands-off solution for daily cigar price updates with historical tracking and git automation.

## 🎯 What This System Does

**Completely automated daily workflow:**
1. **Runs all retailer price updates** (18+ retailers)
2. **Captures historical pricing data** for analytics
3. **Commits and pushes changes to git** automatically  
4. **Updates your Railway-deployed website** immediately
5. **Sends email notifications** about results
6. **Logs everything** for monitoring

**Zero manual intervention required once setup.**

---

## 🚀 Quick Setup (3 Steps)

### Step 1: Create Automation Folder and Install Files
```bash
# Create automation folder in your project root
mkdir automation
cd automation

# Copy these 4 files to the automation folder:
# - automated_cigar_price_system.py
# - setup_automation_scheduler.bat  
# - setup_configuration.py
# - README_Automation.md

# Ensure you have required packages (run from project root):
cd ..
pip install pandas beautifulsoup4 requests
```

### Step 2: Configure Settings
```bash
# From the automation folder:
cd automation
python setup_configuration.py
```
This will configure:
- Email notifications (optional but recommended)
- Git automation settings
- Historical data tracking
- Timeout and retry settings

### Step 3: Set Up Daily Schedule
```bash
# Run as Administrator from automation folder:
setup_automation_scheduler.bat
```
Choose your preferred time (6 AM, 2 PM, 10 PM, or custom).

**That's it! The system now runs automatically every day.**

---

## 🔍 How It Works

### Daily Automation Flow
```
6:00 AM (or your chosen time)
    ↓
1. Auto-discover all retailer update scripts in app/
2. Capture current prices/stock for comparison  
3. Run each retailer update script sequentially
4. Track all price/stock changes to database
5. Commit all CSV changes to git
6. Push changes to GitHub (Railway pulls automatically)
7. Send email notification with results
8. Log everything for monitoring
```

### File Structure (Clean Organization)
```
cigar-price-scout/
├── automation/                        # ← All automation files here
│   ├── automated_cigar_price_system.py    # Main automation engine
│   ├── setup_automation_scheduler.bat     # Windows scheduler setup
│   ├── setup_configuration.py             # Interactive config setup
│   ├── automation_config.json             # Settings (created by setup)
│   ├── run_automation.bat                 # Created by scheduler setup
│   └── logs/                               # Automation logs
│       ├── automation_20251124.log            # Daily automation logs
│       └── automation_output_*.log            # Task scheduler outputs
├── app/
│   ├── main.py                         # Your FastAPI backend
│   ├── update_atlantic_prices_final.py    # Retailer update scripts
│   ├── update_foxcigar_prices_final.py    # (Auto-discovered)
│   └── [all other update scripts]         # (Auto-discovered)
├── data/
│   ├── master_cigars.csv               # Master product database
│   └── historical_prices.db           # SQLite database for analytics
├── static/data/
│   ├── atlantic.csv                    # Updated automatically
│   ├── foxcigar.csv                    # Updated automatically  
│   └── [all other retailer CSVs]      # Updated automatically
└── tools/price_monitoring/retailers/
    ├── atlantic_extractor.py          # Price extraction logic
    └── [other extractor scripts]      # (Used by update scripts)
```

---

## 📊 Historical Data & Analytics

The system automatically tracks:
- **Price changes**: When prices increase/decrease
- **Stock changes**: When items go in/out of stock  
- **New products**: When retailers add new SKUs
- **Performance metrics**: Success rates, timing, errors

### Access Historical Data
```python
import sqlite3
import pandas as pd
conn = sqlite3.connect('data/historical_prices.db')

# Get price changes in last 30 days
price_changes = pd.read_sql("""
    SELECT retailer, cigar_id, date, old_price, new_price, change_type 
    FROM price_changes 
    WHERE date >= date('now', '-30 days')
    ORDER BY date DESC
""", conn)

# Get automation run history
automation_history = pd.read_sql("""
    SELECT run_date, retailers_successful, products_updated, duration_seconds
    FROM automation_runs 
    ORDER BY run_date DESC
""", conn)
```

---

## ⚙️ Configuration Options

Edit `automation/automation_config.json` to customize:

### Email Notifications
```json
{
  "email_notifications": {
    "enabled": true,
    "sender_email": "your-email@gmail.com",
    "sender_password": "your-app-password",
    "send_on_success": true,
    "send_on_failure": true
  }
}
```

### Git Automation  
```json
{
  "git_automation": {
    "enabled": true,
    "auto_commit": true,
    "auto_push": true,
    "commit_message_template": "Automated price update - {date}"
  }
}
```

### Performance Tuning
```json
{
  "price_update_settings": {
    "timeout_minutes": 30,
    "delay_between_retailers": 2,
    "retry_failed_retailers": true
  }
}
```

---

## 🔧 Manual Operations

### Test the Automation Now
```bash
cd automation
python automated_cigar_price_system.py
```

### Run Specific Retailer Only
```bash
# Use your existing script from project root:
cd ..
python local_auto_updater_clean.py atlantic
```

### Check Scheduled Task
```bash
# View task in Windows Task Scheduler, or:
schtasks /query /tn "CigarPriceScout_DailyAutomation"

# Run task manually:
schtasks /run /tn "CigarPriceScout_DailyAutomation"
```

### Monitor Logs
- **Automation logs**: `automation/logs/automation_YYYYMMDD.log`
- **Scheduler output**: `automation/logs/automation_output_YYYYMMDD.log`
- **Email notifications**: Real-time results

---

## 🚨 Troubleshooting

### Common Issues

**Git push fails:**
- Check your git credentials are stored
- Verify SSH key or HTTPS token is configured
- Test manually from project root: `git push origin main`

**Email notifications not working:**
- Use Gmail App Passwords instead of regular password
- Enable 2-factor authentication first
- Test with: `cd automation && python setup_configuration.py`

**Some retailers failing:**
- Check individual update scripts work manually from app/ folder
- Verify CSV files exist in `static/data/`
- Check timeout settings in `automation/automation_config.json`

**Railway not updating:**
- Verify git push succeeded in automation logs
- Check Railway is connected to correct GitHub repo
- Railway should pull changes automatically

### Get Help
1. Check latest log: `automation/logs/automation_[today].log`
2. Run test manually: `cd automation && python automated_cigar_price_system.py`  
3. Test individual retailer: `python local_auto_updater_clean.py [retailer]` (from project root)

---

## 🎯 Success Metrics

After setup, you should see:
- **Daily email reports** with update results
- **Fresh pricing data** on your website every day
- **Historical database** growing with analytics data
- **Git commits** showing daily automated updates in automation folder logs
- **95%+ success rate** across retailers

**The goal: Wake up every morning to fresh, accurate pricing data with zero effort required.**

---

## 🔮 Future Enhancements

With the historical database in place, you can easily add:
- **Price trend analytics**: "Lowest price in 30 days"
- **Stock alerts**: Email when favorite cigars come back
- **Retailer performance**: Which stores have best prices/availability
- **Customer insights**: Most searched cigars, price sensitivity
- **Retailer dashboard**: White-label analytics for your partners

The foundation is built for unlimited expansion!
