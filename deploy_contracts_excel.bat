@echo off
REM deploy_contracts_excel.bat
REM Add Excel export + import (preview/apply) to contracts directory
REM Backend: contracts.py restart; Frontend: directories.js rebuild
REM Zapuskat iz cmd (ne PowerShell)
REM -----------------------------------------------------------------------

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"
set "LOG=backups\deploy_contracts_excel_log.txt"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo.
echo ============================================================
echo  deploy_contracts_excel.bat  [%TS%]
echo ============================================================
echo.
echo [%TS%] === START === >> "%LOG%"

REM ---------- 1. Push + restart backend ----------
echo [1/4] Push contracts.py ...
docker exec -i finance_backend sh -c "cat > /app/app/routers/contracts.py" < "F:\finance\backend\app\routers\contracts.py"
if errorlevel 1 (
    echo OSHYBKA: contracts.py
    echo [%TS%] FAIL contracts.py >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] contracts.py pushed >> "%LOG%"

echo [2/4] Restart backend ...
docker restart finance_backend
if errorlevel 1 (
    echo OSHYBKA: restart backend
    echo [%TS%] FAIL backend restart >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] backend restarted >> "%LOG%"
echo.

REM ---------- 2. Push frontend ----------
echo [3/4] Push directories.js ...
docker exec -i finance_frontend sh -c "cat > /app/pages/directories.js" < "F:\finance\frontend\pages\directories.js"
if errorlevel 1 (
    echo OSHYBKA: directories.js
    echo [%TS%] FAIL directories.js >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] directories.js pushed >> "%LOG%"
echo.

REM ---------- 3. Rebuild ----------
echo [4/4] Rebuild frontend (rm -rf .next && npm run build) ...
echo       Zanimaet 1-3 minuty...
echo.
docker exec finance_frontend sh -c "rm -rf .next && npm run build"
if errorlevel 1 (
    echo OSHYBKA: npm run build — smotri vyvod vyshe
    echo [%TS%] FAIL build >> "%LOG%"
    pause & exit /b 1
)
echo [%TS%] build OK >> "%LOG%"

docker restart finance_frontend
if errorlevel 1 (
    echo OSHYBKA: restart frontend
    echo [%TS%] FAIL frontend restart >> "%LOG%"
    pause & exit /b 1
)
echo [%TS%] frontend restarted >> "%LOG%"

echo.
echo ============================================================
echo  GOTOVO
echo  Prover: http://localhost/directories (vkladka Dogovory)
echo    - knopka skhemy (eksport)
echo    - knopka zagruzki (import s preview)
echo  Log: %LOG%
echo ============================================================
echo.
echo [%TS%] === DONE OK === >> "%LOG%"

pause
endlocal
