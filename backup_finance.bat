@echo off
REM ============================================================================
REM backup_finance.bat
REM
REM Scheduled backup for the Finance CRM Postgres database (finance_db).
REM Intended to be registered in Windows Task Scheduler (e.g. daily at 03:00).
REM
REM What it does:
REM   1. Runs pg_dump inside the running finance_db container.
REM   2. Saves the dump to backups\backup_<timestamp>.sql
REM   3. Verifies the dump file exists and is non-empty.
REM   4. Rotates old backups, keeping only the most recent 14.
REM   5. Appends a one-line result to backups\backup_log.txt
REM
REM Requirements: Docker Desktop / Rancher Desktop running, finance_db container up.
REM
REM NOTE: keep this file pure ASCII (no Cyrillic, no chcp) - see CLAUDE.md notes
REM about cmd/PowerShell mangling Cyrillic on redirect. This script only writes
REM ASCII timestamps/log lines, so it is safe to run from Task Scheduler either way.
REM ============================================================================

setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

if not exist "backups" mkdir "backups"

REM Sortable timestamp (yyyy-MM-dd_HHmmss) via PowerShell - ASCII only, no Cyrillic involved.
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

set "BACKUP_FILE=backups\backup_%TS%.sql"
set "LOG_FILE=backups\backup_log.txt"

docker exec -t finance_db pg_dump -U finance_user finance > "%BACKUP_FILE%"
set "DUMP_RESULT=%ERRORLEVEL%"

if not exist "%BACKUP_FILE%" (
    echo %DATE% %TIME% FAILED - dump file not created >> "%LOG_FILE%"
    endlocal
    exit /b 1
)

for %%A in ("%BACKUP_FILE%") do set "BACKUP_SIZE=%%~zA"

if "%DUMP_RESULT%"=="0" if not "%BACKUP_SIZE%"=="0" (
    echo %DATE% %TIME% OK %BACKUP_FILE% ^(%BACKUP_SIZE% bytes^) >> "%LOG_FILE%"
) else (
    echo %DATE% %TIME% FAILED dump_result=%DUMP_RESULT% size=%BACKUP_SIZE% >> "%LOG_FILE%"
    del "%BACKUP_FILE%" 2>nul
    endlocal
    exit /b 1
)

REM Rotation: keep the 14 most recent backup_*.sql files, delete the rest.
REM "dir /b /o-n" lists filenames sorted descending - newest timestamp first,
REM since the filename prefix is sortable (backup_yyyy-MM-dd_HHmmss.sql).
set "KEEP=14"
for /f "skip=%KEEP% delims=" %%f in ('dir /b /o-n "backups\backup_*.sql" 2^>nul') do (
    del "backups\%%f"
    echo %DATE% %TIME% ROTATED removed backups\%%f >> "%LOG_FILE%"
)

endlocal
exit /b 0
