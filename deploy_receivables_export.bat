@echo off
REM deploy_receivables_export.bat
REM Fix: export Excel uchityvaet aktivnye filtry
REM Push reports.py (backend) + receivables.js (frontend), rebuild
REM Zapuskat iz cmd (ne PowerShell)
REM -----------------------------------------------------------------------

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"
set "LOG=backups\deploy_receivables_export_log.txt"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo.
echo ============================================================
echo  deploy_receivables_export.bat  [%TS%]
echo ============================================================
echo.

echo [%TS%] === START === >> "%LOG%"

REM ---------- 1. Push backend ----------
echo [1/4] Push backend reports.py ...
docker exec -i finance_backend sh -c "cat > /app/app/routers/reports.py" < "F:\finance\backend\app\routers\reports.py"
if errorlevel 1 (
    echo OSHYBKA: reports.py
    echo [%TS%] FAIL reports.py >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] reports.py pushed >> "%LOG%"
echo.

REM ---------- 2. Restart backend ----------
echo [2/4] Restart backend ...
docker restart finance_backend
if errorlevel 1 (
    echo OSHYBKA: docker restart finance_backend
    echo [%TS%] FAIL backend restart >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] backend restarted >> "%LOG%"
echo.

REM ---------- 3. Push frontend ----------
echo [3/4] Push frontend receivables.js ...
docker exec -i finance_frontend sh -c "cat > /app/pages/receivables.js" < "F:\finance\frontend\pages\receivables.js"
if errorlevel 1 (
    echo OSHYBKA: receivables.js
    echo [%TS%] FAIL receivables.js >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] receivables.js pushed >> "%LOG%"
echo.

REM ---------- 4. Rebuild frontend ----------
echo [4/4] Rebuild frontend (rm -rf .next && npm run build) ...
echo       Zanimaet 1-3 minuty, ne zakryvayte okno...
echo.
docker exec finance_frontend sh -c "rm -rf .next && npm run build"
if errorlevel 1 (
    echo.
    echo OSHYBKA: npm run build
    echo Smotri vyvod vyshe.
    echo [%TS%] FAIL build >> "%LOG%"
    pause & exit /b 1
)
echo [%TS%] build OK >> "%LOG%"

docker restart finance_frontend
if errorlevel 1 (
    echo OSHYBKA: docker restart finance_frontend
    echo [%TS%] FAIL frontend restart >> "%LOG%"
    pause & exit /b 1
)
echo [%TS%] frontend restarted >> "%LOG%"

echo.
echo ============================================================
echo  GOTOVO
echo  Log: %LOG%
echo ============================================================
echo  Prover: http://localhost/receivables
echo    Ustanovi filtry, zhmi eksport -- dolzhen uchistyvat' filtry
echo ============================================================
echo.
echo [%TS%] === DONE OK === >> "%LOG%"

pause
endlocal
