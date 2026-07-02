@echo off
REM sync_edo_data.bat
REM Sync KPP + EDO identifiers from CSV into counterparties table
REM Zapuskat iz cmd (ne PowerShell)
REM -----------------------------------------------------------------------
REM Usage: drag-and-drop CSV onto this bat, or run:
REM   sync_edo_data.bat "C:\path\to\counteragents.csv"
REM If no argument given, looks for counteragents.csv next to this bat.
REM -----------------------------------------------------------------------

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"
set "LOG=backups\sync_edo_data_log.txt"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo.
echo ============================================================
echo  sync_edo_data.bat  [%TS%]
echo ============================================================
echo.

echo [%TS%] === START === >> "%LOG%"

REM --- Determine CSV path ---
if "%~1"=="" (
    set "CSV_SRC=%~dp0counteragents.csv"
) else (
    set "CSV_SRC=%~1"
)

if not exist "!CSV_SRC!" (
    echo ERROR: CSV not found: !CSV_SRC!
    echo Ukazi put k faylu kak argument: sync_edo_data.bat "C:\...\counteragents.csv"
    echo [%TS%] FAIL csv not found >> "%LOG%"
    pause & exit /b 1
)

echo CSV: !CSV_SRC!
echo.

REM --- Backup DB before changes ---
echo [1/3] Backup DB ...
docker exec -t finance_db pg_dump -U finance_user finance > "backups\before_sync_edo_%TS%.sql"
if errorlevel 1 (
    echo WARNING: backup failed, prodolzhaem...
    echo [%TS%] WARNING backup failed >> "%LOG%"
) else (
    echo       OK: backups\before_sync_edo_%TS%.sql
    echo [%TS%] backup OK >> "%LOG%"
)
echo.

REM --- Copy CSV into container ---
echo [2/3] Copy CSV into container ...
docker exec finance_backend sh -c "mkdir -p /app/app/tmp"
docker cp "!CSV_SRC!" finance_backend:/app/app/tmp/counteragents_sync.csv
if errorlevel 1 (
    echo OSHYBKA: docker cp
    echo [%TS%] FAIL docker cp >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo.

REM --- Push script and run ---
echo [3/3] Push script + run sync ...
docker exec -i finance_backend sh -c "cat > /app/app/sync_edo_data.py" < "F:\finance\backend\app\sync_edo_data.py"
if errorlevel 1 (
    echo OSHYBKA: push script
    echo [%TS%] FAIL push script >> "%LOG%"
    pause & exit /b 1
)

echo.
echo --- Vyvod skrypta ---
docker exec finance_backend python /app/app/sync_edo_data.py /app/app/tmp/counteragents_sync.csv
if errorlevel 1 (
    echo.
    echo OSHYBKA: script exited with error
    echo [%TS%] FAIL script >> "%LOG%"
    pause & exit /b 1
)
echo --- Konets vyvoda ---

echo.
echo [%TS%] sync OK >> "%LOG%"

echo.
echo ============================================================
echo  GOTOVO
echo  Prover: http://localhost/directories (vkladka Kontragenty)
echo  Log: %LOG%
echo ============================================================
echo.
echo [%TS%] === DONE OK === >> "%LOG%"

pause
endlocal
