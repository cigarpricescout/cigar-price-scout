@echo off
REM Setup Daily URL Discovery Scheduled Task
REM Runs the URL Discovery Agent every day at 5:00 AM (before the 6 AM price run)
REM Run this from the automation folder

echo.
echo ==================================================================
echo    CIGAR PRICE SCOUT - DAILY DISCOVERY SETUP
echo ==================================================================
echo.

set AUTOMATION_DIR=%cd%
set PROJECT_ROOT=%cd%\..

if not exist "%AUTOMATION_DIR%\run_weekly_discovery.py" (
    echo ERROR: run_weekly_discovery.py not found
    echo Make sure you're running this from the automation folder
    pause
    exit /b 1
)

REM Create the runner batch file
set TASK_SCRIPT=%AUTOMATION_DIR%\run_discovery.bat

echo @echo off > "%TASK_SCRIPT%"
echo cd /d "%PROJECT_ROOT%" >> "%TASK_SCRIPT%"
echo python automation\run_weekly_discovery.py --top-cids 50 ^> automation\logs\discovery_%%date:~-4,4%%%%date:~-10,2%%%%date:~-7,2%%.log 2^>^&1 >> "%TASK_SCRIPT%"

echo Created: %TASK_SCRIPT%
echo.

REM Remove old weekly task if it exists
schtasks /delete /tn "CigarPriceScout_WeeklyDiscovery" /f >nul 2>&1

REM Create the daily scheduled task (every day at 5 AM)
echo Creating daily scheduled task (every day at 5:00 AM)...

schtasks /create ^
    /tn "CigarPriceScout_DailyDiscovery" ^
    /tr "\"%TASK_SCRIPT%\"" ^
    /sc daily ^
    /st 05:00 ^
    /ru %USERNAME% ^
    /f

if %errorlevel%==0 (
    echo.
    echo SUCCESS: Daily discovery task created!
    echo   Name: CigarPriceScout_DailyDiscovery
    echo   Schedule: Every day at 5:00 AM
    echo   Logs: %AUTOMATION_DIR%\logs\
    echo.
) else (
    echo.
    echo ERROR: Failed to create scheduled task
    echo Try running as Administrator
    echo.
)

pause
