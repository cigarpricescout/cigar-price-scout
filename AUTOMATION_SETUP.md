# 🤖 GitHub Actions Automation Setup

Your daily pricing updates can now run automatically on GitHub's servers (no local machine needed!).

## ✅ What This Does

Every day at 6:00 AM EST, GitHub Actions will:
1. ✅ Run your pricing automation script
2. ✅ Update all retailer CSV files
3. ✅ Update historical database
4. ✅ Commit and push changes to GitHub
5. ✅ Trigger Railway deployment automatically
6. ✅ Generate a summary report

**You don't need to do anything!** Wake up to fresh prices every day.

---

## 🚀 One-Time Setup (5 minutes)

### Step 1: Enable GitHub Actions (if not already enabled)
1. Go to: https://github.com/cigarpricescout/cigar-price-scout/settings/actions
2. Under "Actions permissions", select **"Allow all actions and reusable workflows"**
3. Click **Save**

### Step 2: Verify Workflow Permissions
1. Go to: https://github.com/cigarpricescout/cigar-price-scout/settings/actions
2. Scroll to **"Workflow permissions"**
3. Select **"Read and write permissions"** (allows commits)
4. Check ☑️ **"Allow GitHub Actions to create and approve pull requests"**
5. Click **Save**

### Step 3: Push the Workflow File
```bash
# The workflow file is already created at:
# .github/workflows/daily-pricing-update.yml

# Just commit and push:
git add .github/workflows/daily-pricing-update.yml AUTOMATION_SETUP.md
git commit -m "Add GitHub Actions automation for daily pricing updates"
git push
```

### Step 4: Test It (Manual Run)
1. Go to: https://github.com/cigarpricescout/cigar-price-scout/actions
2. Click **"Daily Pricing Update"** in the left sidebar
3. Click **"Run workflow"** button (top right)
4. Click green **"Run workflow"** to confirm
5. Watch it run! (takes 5-10 minutes)

---

## 📅 Schedule

**Automatic runs:** Every day at 6:00 AM EST (11:00 AM UTC)

**Manual runs:** Anytime you want via the Actions tab

**View runs:** https://github.com/cigarpricescout/cigar-price-scout/actions

---

## 🔍 Monitoring

### View Live Progress
1. Go to: https://github.com/cigarpricescout/cigar-price-scout/actions
2. Click on any run to see live logs
3. Each step shows detailed output

### Check Results
- ✅ Green checkmark = Success
- ❌ Red X = Failed (check logs)
- 🟡 Yellow circle = Running

### Summary Report
Each run creates a summary showing:
- Timestamp
- Last 20 lines of automation log
- Changed files
- Commit details

---

## 📧 Email Notifications (Optional)

Want email alerts? Set up GitHub notifications:

1. Go to: https://github.com/settings/notifications
2. Under **"Actions"**, check:
   - ☑️ Email: Notify me when a workflow run fails
3. You'll get emails only if automation fails

---

## 🆚 GitHub Actions vs Local Task Scheduler

### ✅ GitHub Actions (NEW - Recommended)
- ✅ Runs on GitHub's servers (no local machine needed)
- ✅ Free (2000 minutes/month, your script uses ~10 min/day = 300 min/month)
- ✅ Logs saved forever
- ✅ Works from anywhere (vacation, sick day, power outage)
- ✅ Easy to monitor via web browser
- ✅ Automatic Railway deployment

### ❌ Local Task Scheduler (OLD)
- ❌ Requires your computer to be on
- ❌ Manual git push needed
- ❌ Logs only on local machine
- ❌ Stops working if computer sleeps/restarts

**Recommendation:** Use GitHub Actions, disable local Task Scheduler

---

## 🛑 Disable Local Task Scheduler (Optional)

If you want to fully switch to GitHub Actions:

1. Open Task Scheduler (Windows)
2. Find **"CigarPriceScout_DailyAutomation"**
3. Right-click → **Disable** (or Delete)

---

## 🐛 Troubleshooting

### "Workflow failed with permission error"
**Fix:** Go to repo Settings → Actions → Workflow permissions → Select "Read and write permissions"

### "No changes to commit"
**Good!** This means no prices changed today. The workflow still ran successfully.

### "Python package not found"
**Fix:** Add the package to `requirements.txt` in your project root

### "Script timeout"
**Fix:** Current timeout is 30 min. Update in workflow file if needed:
```yaml
      - name: Run pricing automation
        timeout-minutes: 45  # Increase from 30 to 45
```

---

## 📊 Cost

**GitHub Actions Free Tier:**
- 2,000 minutes/month (free)
- Your automation: ~10 minutes/day × 30 days = 300 minutes/month
- **Cost: $0/month** ✅

**Paid if you exceed:**
- $0.008/minute = $2.40 for 300 minutes
- Still extremely cheap!

---

## 🎯 Next Steps

1. ✅ Push the workflow file to GitHub
2. ✅ Configure permissions (Step 2 above)
3. ✅ Test with manual run (Step 4 above)
4. ✅ Wait until tomorrow 6 AM for first automatic run
5. ✅ Disable local Task Scheduler (optional)

---

## 🚀 Future Enhancements

You can extend this workflow to:
- Send Slack/Discord notifications
- Run multiple times per day
- Generate daily reports
- Upload reports to S3/cloud storage
- Trigger only on weekdays (skip weekends)
- Run different scrapers on different schedules

Example - Run twice daily:
```yaml
  schedule:
    - cron: '0 11 * * *'  # 6 AM EST
    - cron: '0 23 * * *'  # 6 PM EST
```

---

## 📞 Support

**Check workflow logs:** https://github.com/cigarpricescout/cigar-price-scout/actions

**Workflow file location:** `.github/workflows/daily-pricing-update.yml`

**Questions?** Create an issue on GitHub or check the Actions documentation:
https://docs.github.com/en/actions
