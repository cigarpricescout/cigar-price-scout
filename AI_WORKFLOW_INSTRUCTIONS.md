# AI Automation - Work Instructions

## One-Time Setup (do this now)

### 1. Set up the weekly scheduler
Open a terminal, navigate to the automation folder, and run the batch file:

```
cd C:\Users\briah\cigar-price-scout\automation
setup_weekly_discovery.bat
```

This creates a Windows scheduled task that runs every **Monday at 7:00 AM**.  
You only do this once. After that, it runs automatically.

### 2. Verify your API key is set
Open a new PowerShell terminal and run:

```
echo $env:ANTHROPIC_API_KEY
```

It should print your key starting with `sk-ant-`. If it's blank, set it:

```
setx ANTHROPIC_API_KEY "your-full-key-here"
```

Then restart the terminal.

---

## Weekly Workflow (5-15 minutes)

Every Monday morning you'll get a **Weekly Discovery Digest** email.  
Do the following whenever you have a few minutes that week:

### Step 1: Spot-check staged matches
Open this file in Excel or a text editor:

```
C:\Users\briah\cigar-price-scout\tools\ai\staged_matches.csv
```

Pick 2-3 rows at random. Click the URL. Confirm the product on the website matches the CID (brand, line, vitola, wrapper, box quantity).

### Step 2: Approve the batch (if spot-checks pass)
```
cd C:\Users\briah\cigar-price-scout
python tools/ai/url_discoverer.py --approve-batch
```

### Step 3: Review medium-confidence matches
Open this file:

```
C:\Users\briah\cigar-price-scout\tools\ai\pending_review.csv
```

For any bad matches, type a short reason in the **feedback** column (e.g., "wrong vitola", "this is a 5-pack not a box", "wrong wrapper").

Leave the feedback column empty for matches that look correct.

### Step 4: Process your reviews
```
python tools/ai/url_discoverer.py --reject-flagged
```

### Step 5: Publish to production
```
python tools/ai/url_discoverer.py --publish-approved
```

That's it. The next daily price update will fetch prices for the new entries and they'll appear on the website.

**If you skip a week:** Nothing breaks. Matches sit in staging until you review them.

---

## Adding a New Retailer (occasional, 10-20 minutes)

### Step 1: Add to the queue file
Open this file in any text editor:

```
C:\Users\briah\cigar-price-scout\tools\ai\new_retailer_queue.txt
```

Add an entry like this:

```
New Cigar Shop | newcigarshop
https://newcigarshop.com/products/padron-1964-maduro-box-25
https://newcigarshop.com/products/arturo-fuente-hemingway-classic
https://newcigarshop.com/products/oliva-serie-v-melanio-robusto
```

**Tips for picking URLs:**
- Use 3-5 product pages (more is better)
- Pick products you already have in your master database
- Include at least one that's out of stock if possible
- Make sure they're BOX listings, not singles or 5-packs

### Step 2: Process the queue
Either wait for Monday's scheduled run, or run manually:

```
cd C:\Users\briah\cigar-price-scout
python tools/ai/extractor_generator.py --process-queue
```

### Step 3: Review the report
Check the generated report:

```
C:\Users\briah\cigar-price-scout\tools\ai\generator_reports\<retailer_key>_report.txt
```

It shows test results for each sample URL. Verify the prices and box quantities look correct.

### Step 4: Approve if it looks good
```
python tools/ai/extractor_generator.py --approve <retailer_key>
```

Example: `python tools/ai/extractor_generator.py --approve newcigarshop`

The new retailer is now part of your automation system. The weekly discovery will start finding CIDs for it automatically.

---

## Morning Email - Health Monitor

Your existing morning email now includes a health section at the bottom.

**Most days:** It says `All Healthy (26 retailers): OK` — no action needed.

**If something breaks:** It tells you what's wrong. Example:

```
CRITICAL (1 issue):
  foxcigar: Success rate 45% is critically low. 24 of 44 products have no price.

Warnings (1 issue):
  smokeinn: 3 URLs returning 403 Forbidden. Likely rate-limiting.
```

**To diagnose a specific retailer:**
```
python tools/ai/extractor_monitor.py --diagnose foxcigar
```

---

## Running Things Manually

### Run URL discovery on demand
```
cd C:\Users\briah\cigar-price-scout
python tools/ai/url_discoverer.py --top-cids 50
```

Add `--retailer foxcigar` to limit to one retailer.

### Run the full weekly job on demand
```
python automation/run_weekly_discovery.py --top-cids 50
```

Add `--dry-run` to skip sending the email.

### Check extractor health on demand
```
python tools/ai/extractor_monitor.py
```

---

## File Locations

| What | Where |
|------|-------|
| Staged matches (spot-check these) | `tools/ai/staged_matches.csv` |
| Medium-confidence reviews | `tools/ai/pending_review.csv` |
| Discovery report | `tools/ai/discovery_report.txt` |
| Feedback history (auto-maintained) | `tools/ai/feedback_history.json` |
| New retailer queue | `tools/ai/new_retailer_queue.txt` |
| Generator reports | `tools/ai/generator_reports/` |
| Health monitor database | `data/extractor_health.db` |
| Automation logs | `automation/logs/` |
| Automation config | `automation/automation_config.json` |

---

## Costs

Claude API usage (console.anthropic.com):
- Weekly discovery run (50 CIDs x 26 retailers): ~$1-3
- New retailer generation: ~$0.50-1.00 per retailer
- Estimated monthly total: $5-15

Check your usage at: https://console.anthropic.com/settings/usage
