@echo off
REM ============================================================
REM Deploy: visual redesign (Onest font + design tokens)
REM Run from cmd.exe in F:\finance  (NOT PowerShell - mangles Cyrillic on redirect)
REM ============================================================

echo.
echo === STEP 0: DB backup reminder ===
echo This deploy only changes frontend code and one backend file
echo (read-only field additions). No schema/data changes.
echo If you want a safety net anyway, run in another window first:
echo   docker exec -t finance_db pg_dump -U finance_user finance ^> backups\backup_before_redesign.sql
echo.
pause

echo.
echo === STEP 1: Push backend file ===
docker exec -i finance_backend sh -c "cat > /app/app/routers/reports.py" < "F:\finance\backend\app\routers\reports.py"
if errorlevel 1 goto :error

echo === STEP 2: Restart backend (uvicorn --reload, no rebuild needed) ===
docker restart finance_backend
if errorlevel 1 goto :error

echo.
echo === STEP 3: Push frontend files ===
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

echo.
echo === STEP 4: Rebuild frontend (production mode - needs internet access ===
echo === for next/font/google to fetch Onest on first build) ===
docker exec finance_frontend sh -c "rm -rf .next && npm run build"
if errorlevel 1 goto :error

echo === STEP 5: Restart frontend ===
docker restart finance_frontend
if errorlevel 1 goto :error

echo.
echo === DONE. Open http://localhost:3000 and check all pages. ===
goto :eof

:error
echo.
echo *** STEP FAILED - stopped. Check the error above before retrying. ***
exit /b 1
