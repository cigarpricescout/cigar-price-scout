@echo off
REM Simplified Windows Task Scheduler Setup for Automated Cigar Price Updates
REM Run this from the automation folder
REM Author: Bri's Assistant
REM Date: November 24, 2025

echo.
echo ==================================================================
echo    CIGAR PRICE SCOUT - AUTOMATED SCHEDULING SETUP
echo ==================================================================
echo.

REM Set paths based on current directory being automation folder
set AUTOMATION_DIR=%cd%
set PROJECT_ROOT=%cd%\..

echo Current automation directory: %AUTOMATION_DIR%
echo Project root: %PROJECT_ROOT%

REM Check if we can find the required files
if not exist "%AUTOMATION_DIR%\automated_cigar_price_system.py" (
    echo ERROR: automated_cigar_price_system.py not found in current directory
    echo Make sure you're running this from the automation folder
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\app" (
    echo ERROR: Cannot find app folder at %PROJECT_ROOT%\app
    echo Make sure you're running this from inside the automation folder
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\static\data" (
    echo ERROR: Cannot find static\data folder at %PROJECT_ROOT%\static\data
    echo Make sure you're running this from inside the automation folder
    pause
    exit /b 1
)

echo ✓ Found automation script
echo ✓ Found app folder with update scripts
echo ✓ Found static\data folder with CSV files
echo.

REM Create logs directory if it doesn't exist
if not exist "%AUTOMATION_DIR%\logs" mkdir "%AUTOMATION_DIR%\logs"

REM Prompt for schedule time
echo Please choose your preferred automation time:
echo.
echo 1. 6:00 AM daily (recommended for morning updates)
echo 2. 2:00 PM daily (afternoon updates)  
echo 3. 10:00 PM daily (evening updates)
echo 4. Custom time
echo.
set /p choice="Enter choice (1-4): "

if "%choice%"=="1" (
    set SCHEDULE_TIME=06:00
    set SCHEDULE_NAME=Morning
) else if "%choice%"=="2" (
    set SCHEDULE_TIME=14:00
    set SCHEDULE_NAME=Afternoon
) else if "%choice%"=="3" (
    set SCHEDULE_TIME=22:00
    set SCHEDULE_NAME=Evening
) else if "%choice%"=="4" (
    set /p SCHEDULE_TIME="Enter time in HH:MM format (24-hour): "
    set SCHEDULE_NAME=Custom
) else (
    echo Invalid choice. Using default 6:00 AM
    set SCHEDULE_TIME=06:00
    set SCHEDULE_NAME=Morning
)

echo.
echo Setting up automation to run daily at %SCHEDULE_TIME% (%SCHEDULE_NAME%)...
echo.

REM Create a batch file that will be executed by Task Scheduler
set TASK_SCRIPT=%AUTOMATION_DIR%\run_automation.bat

echo @echo off > "%TASK_SCRIPT%"
echo REM Automated execution script created by setup >> "%TASK_SCRIPT%"
echo cd /d "%AUTOMATION_DIR%" >> "%TASK_SCRIPT%"
echo python automated_cigar_price_system.py ^> logs\automation_output_%%date:~-4,4%%%%date:~-10,2%%%%date:~-7,2%%.log 2^>^&1 >> "%TASK_SCRIPT%"

echo ✓ Task script created: %TASK_SCRIPT%
echo.

REM Create the Windows scheduled task
echo Creating Windows scheduled task...

schtasks /create ^
    /tn "CigarPriceScout_DailyAutomation" ^
    /tr "\"%TASK_SCRIPT%\"" ^
    /sc daily ^
    /st %SCHEDULE_TIME% ^
    /ru %USERNAME% ^
    /f

if %errorlevel%==0 (
    echo.
    echo ✓ SUCCESS: Scheduled task created successfully!
    echo.
    echo Task Details:
    echo   Name: CigarPriceScout_DailyAutomation
    echo   Schedule: Daily at %SCHEDULE_TIME% 
    echo   User: %USERNAME%
    echo   Script: %TASK_SCRIPT%
    echo   Working Directory: %AUTOMATION_DIR%
    echo.
    echo The automation will now run automatically every day at %SCHEDULE_TIME%
    echo.
    echo You can:
    echo   - View/modify the task in Windows Task Scheduler
    echo   - Check logs in: %AUTOMATION_DIR%\logs\
    echo   - Test immediately with: schtasks /run /tn "CigarPriceScout_DailyAutomation"
    echo.
) else (
    echo.
    echo ✗ ERROR: Failed to create scheduled task
    echo.
    echo Common solutions:
    echo   1. Run this script as Administrator
    echo   2. Check if task name already exists
    echo   3. Verify your Windows user permissions
    echo.
)

REM Ask if user wants to test the automation now
echo.
set /p test_now="Would you like to test the automation now? (y/n): "
if /i "%test_now%"=="y" (
    echo.
    echo Running test automation...
    echo.
    python automated_cigar_price_system.py
)

echo.
echo Setup complete! Check the automation\logs directory for execution results.
echo.
pause
