@echo off 
REM Automated execution script created by setup 
cd /d "C:\Users\briah\cigar-price-scout\automation" 
python automated_cigar_price_system.py > logs\automation_output_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log 2>&1 
