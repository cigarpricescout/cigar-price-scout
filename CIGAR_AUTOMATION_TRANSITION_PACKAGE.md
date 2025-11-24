# CIGAR PRICE SCOUT TRANSITION PACKAGE
## For New Claude Session - Automation System Rebuild

---

## BUSINESS CONTEXT & GOALS

**Company:** Cigar Price Scout (cigarpricescout.com)
**Business Model:** Cigar price comparison platform generating revenue through affiliate commissions
**Core Value Proposition:** Compare prices across 35+ online retailers for premium cigars (focusing on box purchases 20+ cigars)
**Target Market:** Premium cigar enthusiasts willing to invest in prestige products like Arturo Fuente Opus X

**Current Success Metrics:**
- 18 retailers successfully automated (93-95% success rate)
- 139 products tracked daily
- Proven 70-minute new retailer onboarding methodology
- FastAPI backend + HTML/CSS/JavaScript frontend
- Railway deployment with GitHub sync

---

## RAILWAY DEPLOYMENT CRISIS - LESSONS LEARNED

### What Happened Today
Started with a working automation system that successfully updated 18 retailers daily. Attempted to:
1. Add historical price tracking functionality 
2. Change schedule from 9:45 AM to 2:50 PM PST
3. Fix git sync to include subdirectories for historical data exports

### Railway Platform Issues Discovered
**CRITICAL INSIGHT:** Railway's deployment system is unreliable and has multiple conflicting configuration methods that can break working systems.

**Configuration Conflicts:**
- `railway.json` file can override dashboard settings without warning
- Root Directory setting vs actual file paths causes confusion
- Dockerfile vs Railpack builder switching breaks deployments unpredictably
- Cached deployments vs GitHub source creates "phantom" working versions

**Specific Problems Encountered:**
1. **Git Sync Authentication:** Initially failing due to token configuration
2. **Historical Export Failures:** Adding SQLite + pandas functionality broke deployments
3. **File Path Hell:** Railway looking in `/app/` vs `/app/automation/` vs working directory confusion
4. **Dependency Installation:** Railpack vs Dockerfile handling requirements.txt differently
5. **Deployment Amnesia:** Railway deploying cached versions instead of current GitHub code

### Key Lessons for Future Railway Use
1. **Never touch a working Railway deployment** - Railway's update process is unreliable
2. **Configuration files override dashboard** - Check for railway.json, nixpacks.toml, etc.
3. **Backup strategy essential** - Railway can lose working configurations without warning
4. **Start simple, add complexity gradually** - Don't add multiple features in one deployment
5. **Railway alternatives needed** - Platform reliability issues suggest need for backup deployment option

---

## CURRENT SYSTEM ARCHITECTURE

### File Structure (Expected)
```
/c/Users/briah/cigar-price-scout/
├── automation/
│   ├── automation_master.py (scheduler + orchestrator)
│   ├── app/ (retailer update scripts)
│   ├── requirements.txt (pandas, beautifulsoup4, requests, etc.)
│   ├── Dockerfile
│   └── railway.json
├── static/
│   ├── data/ (CSV files for each retailer)
│   └── index.html (main website)
├── main.py (FastAPI backend)
└── tools/ (scraping utilities)
```

### Working Components
- **18 Retailer Automations:** Atlantic, Fox Cigar, Nick's, Hiland's, Gotham, BnB, Neptune, Tampa Sweethearts, Tobacco Locker, Watch City, Cigars Direct, Absolute Cigars, Small Batch, Planet Cigars, Holt's, Smoke Inn, Two Guys, CC Crafter
- **CSV-Based Data Storage:** Each retailer has dedicated CSV with columns: title, url, brand, line, wrapper, vitola, size, box_qty, price, in_stock
- **Master Cigars Database:** Central product catalog with cigar_id format: BRAND|PARENT|LINE|VITOLA|PRODUCT|SIZE|WRAPPER|BOXQTY
- **Shipping/Tax Calculator:** State-based calculations for delivered pricing
- **Website Integration:** FastAPI serves comparison data to frontend

### Technical Stack
- **Backend:** Python 3.11, FastAPI, BeautifulSoup4, pandas
- **Frontend:** HTML/CSS/JavaScript with responsive design
- **Deployment:** Railway container with GitHub integration
- **Data Storage:** CSV files + SQLite for historical tracking
- **Web Scraping:** Retailer-specific extractors with error handling

---

## IMMEDIATE REQUIREMENTS FOR NEW CLAUDE

### File Structure Discovery
**FIRST PRIORITY:** Map the actual current file structure using gitbash commands:

```bash
# Confirm project location and structure
cd /c/Users/briah/cigar-price-scout
pwd
ls -la

# Check automation folder contents
ls -la automation/
ls -la automation/app/

# Verify CSV data files
ls -la static/data/*.csv | head -20

# Check for working automation scripts
find . -name "automation_master.py" -type f
find . -name "*update*prices*.py" -type f | head -10

# Git repository status
git status
git log --oneline -5
```

### Critical Questions to Answer
1. **What files actually exist and where?**
2. **What's the current git repository state?**
3. **Which automation scripts are functional?**
4. **What's in the working requirements.txt?**
5. **Are there multiple versions of automation_master.py?**

### Automation Requirements
- **Schedule:** Daily price updates (flexible on timing)
- **Reliability:** Must handle 18 retailers without breaking
- **Data Flow:** Update CSVs → Website reflects changes immediately
- **Error Handling:** Graceful failures, don't break entire cycle
- **Deployment:** Stable platform (Railway alternatives welcome)

---

## SUCCESS CRITERIA FOR NEW SYSTEM

### Must Have
1. **18 retailer price updates** running automatically daily
2. **CSV files updated** and accessible via git pull
3. **Website displays current pricing** immediately
4. **Zero manual intervention** required for daily operations
5. **Error recovery** - single retailer failures don't break system

### Nice to Have
- Historical price tracking and analytics
- Git sync for automated data backup
- Flexible scheduling (currently targeting 2:50 PM PST)
- Monitoring and alerting for failures

### Success Metrics
- **>90% retailer success rate** daily
- **130+ products updated** per cycle
- **<10 minute execution time**
- **Zero deployment issues** for 30+ days

---

## NEXT SESSION STRATEGY

1. **File Discovery Phase:** Map actual current state with gitbash
2. **Identify Working Components:** Determine what's functional vs broken
3. **Platform Assessment:** Evaluate Railway alternatives (DigitalOcean, AWS, local cron, etc.)
4. **Rebuild Strategy:** Start with minimal working automation, add features incrementally
5. **Testing Protocol:** Validate each component before deployment

The goal is a bulletproof automation system that prioritizes reliability over fancy features. The business depends on consistent price data more than perfect scheduling or advanced analytics.

---

*"Sometimes the best solution is to step back and rebuild from first principles rather than continuing to fight a broken system."*
