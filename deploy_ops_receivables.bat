@echo off
REM deploy_ops_receivables.bat
REM Push operations.js + receivables.js, rebuild frontend
REM Zapuskat iz cmd (ne PowerShell)
REM -----------------------------------------------------------------------

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"
set "LOG=backups\deploy_ops_receivables_log.txt"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo.
echo ============================================================
echo  deploy_ops_receivables.bat  [%TS%]
echo ============================================================
echo.

echo [%TS%] === START === >> "%LOG%"

REM ---------- 1. Push frontend files ----------
echo [1/3] Push frontend files ...
docker exec -i finance_frontend sh -c "cat > /app/pages/operations.js" < "F:\finance\frontend\pages\operations.js"
if errorlevel 1 (
    echo OSHYBKA: operations.js
    echo [%TS%] FAIL operations.js >> "%LOG%"
    pause & exit /b 1
)
docker exec -i finance_frontend sh -c "cat > /app/pages/receivables.js" < "F:\finance\frontend\pages\receivables.js"
if errorlevel 1 (
    echo OSHYBKA: receivables.js
    echo [%TS%] FAIL receivables.js >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] frontend files pushed >> "%LOG%"
echo.

REM ---------- 2. Rebuild ----------
echo [2/3] Rebuild frontend (rm -rf .next && npm run build) ...
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
echo.

REM ---------- 3. Restart ----------
echo [3/3] Restart frontend ...
docker restart finance_frontend
if errorlevel 1 (
    echo OSHYBKA: docker restart
    echo [%TS%] FAIL restart >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] frontend restarted >> "%LOG%"

echo.
echo ============================================================
echo  GOTOVO
echo  Log: %LOG%
echo ============================================================
echo  Prover: http://localhost/operations
echo           Eksport -- imya fayla dolzhno soderzhat datu/vremya
echo ============================================================
echo.
echo [%TS%] === DONE OK === >> "%LOG%"

pause
endlocal
