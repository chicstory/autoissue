@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ===================================================
echo [ThePathLab] Auto Issue Daily Briefing & Deploy
echo ===================================================

cd /d "%~dp0"

echo [1/3] Fetching domestic and global auto issues...
python auto_issue_collector.py
if errorlevel 1 (
    echo [ERROR] Collector script failed. Please check internet connection.
    pause
    exit /b 1
)

echo.
echo [2/3] Staging updated data and files...
git add index.html data/issues.json data/latest_stats.json auto_issue_collector.py run_autoissue.bat README.md 2>nul

echo.
echo [3/3] Committing and deploying to GitHub...
for /f "tokens=1-3 delims=- " %%a in ('date /t') do (
    set TODAY=%%a-%%b-%%c
)
git commit -m "Auto update daily issues: %TODAY%"
git push origin main

echo.
echo ===================================================
echo [COMPLETE] Auto Issue daily briefing deployed successfully!
echo URL: https://chicstory.github.io/autoissue/
echo ===================================================
echo.
timeout /t 5
