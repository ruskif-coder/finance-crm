@echo off
REM Reverts the interface font: pushes the restored globals.css (no @font-face,
REM back to the original -apple-system/Segoe UI stack) into finance_frontend,
REM rebuilds (CSS goes through next build) and restarts the container.
REM Run from cmd (NOT PowerShell) on the local Windows machine.

cd /d F:\finance
set LOG=F:\finance\deploy_revert_font_log.txt

echo ===== %DATE% %TIME% ===== > "%LOG%"

echo [1/3] Copying reverted globals.css into finance_frontend... >> "%LOG%"
docker cp "F:\finance\frontend\styles\globals.css" finance_frontend:/app/styles/globals.css >> "%LOG%" 2>&1

echo [2/3] Rebuilding frontend (rm -rf .next && npm run build)... >> "%LOG%"
docker exec finance_frontend sh -c "rm -rf .next && npm run build" >> "%LOG%" 2>&1

echo [3/3] Restarting finance_frontend... >> "%LOG%"
docker restart finance_frontend >> "%LOG%" 2>&1

echo ===== DONE ===== >> "%LOG%"
echo Done. Log saved to %LOG%
echo Wait ~10-15 seconds for frontend to come back up, then refresh any page in the browser.
pause
