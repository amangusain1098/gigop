@echo off
echo =========================================
echo  GigOptimizer Pro - Push to GitHub
echo =========================================
cd /d "%~dp0"

echo.
echo [1/4] Removing stale git lock if present...
if exist ".git\index.lock" (
    del /f ".git\index.lock"
    echo     Removed index.lock
) else (
    echo     No lock file found
)

echo.
echo [2/4] Staging all changes...
git add gigoptimizer\connectors\fiverr_marketplace.py
git add gigoptimizer\services\health_score_service.py
git add gigoptimizer\services\tag_gap_analyzer.py
git add gigoptimizer\services\price_alert_service.py
git add gigoptimizer\services\__init__.py
git add gigoptimizer\api\main.py
git add gigoptimizer\config.py
git add tests\test_new_services.py
git add CODEX_ROUND3_BRIEF.md
git add push_to_github.bat

echo.
echo [3/4] Committing...
git commit -m "feat(intelligence): health score, tag gap analyzer, price alert service + scraper fix" --allow-empty

echo.
echo [4/4] Pushing to origin/main...
git push origin main

echo.
echo =========================================
echo  Done\! Check above for any errors.
echo =========================================
pause
