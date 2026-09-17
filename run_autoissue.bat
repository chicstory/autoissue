@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ===================================================
echo [ThePathLab] Auto Issue Daily Briefing ^& Deploy
echo  13 Brand Groups: KR10 + BYD + Rivian + Lucid
echo ===================================================

cd /d "%~dp0"

echo [1/4] Fetching domestic and global auto issues...
python auto_issue_collector.py
if errorlevel 1 (
    echo [ERROR] Collector script failed. Please check internet connection.
    pause
    exit /b 1
)

echo.
echo [2/4] Updating unified network SEO & RSS feeds...
python "%~dp0..\thepathlab\generate_network_seo.py"

echo.
echo [3/4] Staging updated data and files...
git add index.html safepick.html sitemap.xml rss.xml robots.txt data/issues.json data/safepick.json data/latest_stats.json auto_issue_collector.py run_autoissue.bat README.md 2>nul

for /f "tokens=1-3 delims=- " %%a in ('date /t') do (
    set TODAY=%%a-%%b-%%c
)
git commit -m "Auto update daily issues & RSS: %TODAY%"
git push origin main

echo.
echo [4/4] Deploying master RSS feed & fuel price to Portal...
set "PORTAL_DIR=%~dp0..\chicstory.github.io"
if exist "%PORTAL_DIR%\index.html" (
    pushd "%PORTAL_DIR%"
    python "%PORTAL_DIR%\autocost\fuel_collector.py" > nul 2>&1
    git add rss.xml sitemap.xml robots.txt autocost/
    git commit -m "Auto sync portal master RSS & fuel prices: %TODAY%" > nul 2>&1
    git push origin main
    popd
)

echo.
echo ===================================================
echo [COMPLETE] Auto Issue daily briefing deployed successfully!
echo URL: https://chicstory.github.io/autoissue/
echo ===================================================
echo.
timeout /t 5
