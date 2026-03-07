@echo off
REM Setup Weekly URL Discovery Scheduled Task
REM Runs the URL Discovery Agent every Monday at 7:00 AM
REM Run this from the automation folder

echo.
echo ==================================================================
echo    CIGAR PRICE SCOUT - WEEKLY DISCOVERY SETUP
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

REM Create the weekly scheduled task (Monday at 7 AM)
echo Creating weekly scheduled task (Monday at 7:00 AM)...

schtasks /create ^
    /tn "CigarPriceScout_WeeklyDiscovery" ^
    /tr "\"%TASK_SCRIPT%\"" ^
    /sc weekly ^
    /d MON ^
    /st 07:00 ^
    /ru %USERNAME% ^
    /f

if %errorlevel%==0 (
    echo.
    echo SUCCESS: Weekly discovery task created!
    echo   Name: CigarPriceScout_WeeklyDiscovery
    echo   Schedule: Monday at 7:00 AM
    echo   Logs: %AUTOMATION_DIR%\logs\
    echo.
) else (
    echo.
    echo ERROR: Failed to create scheduled task
    echo Try running as Administrator
    echo.
)

pause
