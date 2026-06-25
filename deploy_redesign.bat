@echo off
REM ============================================================
REM Deploy ALL pending changes: term_days feature (#179-183) +
REM visual redesign (Onest font + design tokens, #204-211).
REM These share backend/app/routers/reports.py, so they must be
REM deployed together in this order, or reports.py will reference
REM Counterparty.term_days before the column/model exist.
REM Run from cmd.exe in F:\finance  (NOT PowerShell - mangles Cyrillic on redirect)
REM ============================================================

echo.
echo === STEP 0: DB backup ===
if not exist "F:\finance\backups" mkdir "F:\finance\backups"
docker exec -t finance_db pg_dump -U finance_user finance > "F:\finance\backups\backup_before_deploy_2026-06-25.sql"
if errorlevel 1 goto :error
echo Backup saved to F:\finance\backups\backup_before_deploy_2026-06-25.sql
echo.
pause

echo.
echo === STEP 1: DB migration (add term_days column - safe to re-run) ===
docker exec -i finance_db psql -U finance_user -d finance < "F:\finance\migrate_add_term_days.sql"
if errorlevel 1 goto :error

echo.
echo === STEP 2: Push backend files ===
docker exec -i finance_backend sh -c "cat > /app/app/models.py" < "F:\finance\backend\app\models.py"
if errorlevel 1 goto :error
docker exec -i finance_backend sh -c "cat > /app/app/routers/reports.py" < "F:\finance\backend\app\routers\reports.py"
if errorlevel 1 goto :error
docker exec -i finance_backend sh -c "cat > /app/app/routers/operations.py" < "F:\finance\backend\app\routers\operations.py"
if errorlevel 1 goto :error
docker exec -i finance_backend sh -c "cat > /app/app/routers/counterparties.py" < "F:\finance\backend\app\routers\counterparties.py"
if errorlevel 1 goto :error

echo === STEP 3: Restart backend (uvicorn --reload, no rebuild needed) ===
docker restart finance_backend
if errorlevel 1 goto :error

echo.
echo === STEP 4: Push frontend files ===
docker exec finance_frontend mkdir -p /app/helpers
if errorlevel 1 goto :error

docker exec -i finance_frontend sh -c "cat > /app/styles/globals.css" < "F:\finance\frontend\styles\globals.css"
if errorlevel 1 goto :error
docker exec -i finance_frontend sh -c "cat > /app/pages/_app.js" < "F:\finance\frontend\pages\_app.js"
if errorlevel 1 goto :error
docker exec -i finance_frontend sh -c "cat > /app/components/Navbar.js" < "F:\finance\frontend\components\Navbar.js"
if errorlevel 1 goto :error
docker exec -i finance_frontend sh -c "cat > /app/helpers/ribbonChart.js" < "F:\finance\frontend\helpers\ribbonChart.js"
if errorlevel 1 goto :error
docker exec -i finance_frontend sh -c "cat > /app/pages/dashboard.js" < "F:\finance\frontend\pages\dashboard.js"
if errorlevel 1 goto :error
docker exec -i finance_frontend sh -c "cat > /app/pages/operations.js" < "F:\finance\frontend\pages\operations.js"
if errorlevel 1 goto :error
docker exec -i finance_frontend sh -c "cat > /app/pages/receivables.js" < "F:\finance\frontend\pages\receivables.js"
if errorlevel 1 goto :error
docker exec -i finance_frontend sh -c "cat > /app/pages/pl.js" < "F:\finance\frontend\pages\pl.js"
if errorlevel 1 goto :error
docker exec -i finance_frontend sh -c "cat > /app/pages/balance.js" < "F:\finance\frontend\pages\balance.js"
if errorlevel 1 goto :error
docker exec -i finance_frontend sh -c "cat > /app/pages/planfact.js" < "F:\finance\frontend\pages\planfact.js"
if errorlevel 1 goto :error
docker exec -i finance_frontend sh -c "cat > /app/pages/settings.js" < "F:\finance\frontend\pages\settings.js"
if errorlevel 1 goto :error

echo.
echo === STEP 5: Rebuild frontend (production mode - needs internet access ===
echo === for next/font/google to fetch Onest on first build) ===
docker exec finance_frontend sh -c "rm -rf .next && npm run build"
if errorlevel 1 goto :error

echo === STEP 6: Restart frontend ===
docker restart finance_frontend
if errorlevel 1 goto :error

echo.
echo === DONE. Open http://localhost:3000 and check: ===
echo   - all pages for the new look (Onest font, colors)
echo   - Settings - Kontragenty: Otsrochka column editable
echo   - Debitorka page: aging uses per-counterparty term
goto :eof

:error
echo.
echo *** STEP FAILED - stopped. Check the error above before retrying. ***
exit /b 1
