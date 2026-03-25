@echo off 
cd /d "C:\Users\briah\cigar-price-scout\automation\.." 
python automation\run_weekly_discovery.py --top-cids 50 > automation\logs\discovery_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log 2>&1 
