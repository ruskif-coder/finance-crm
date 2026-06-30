@echo off
REM ============================================================================
REM deploy_finance.bat
REM
REM Deploy script for Finance CRM: backs up the database FIRST, then rebuilds
REM and recreates all Docker Compose services (db/backend/frontend/caddy) from
REM current source. If the backup fails, the build step is skipped and the
REM running containers are left untouched.
REM
REM Steps:
REM   1. pg_dump inside finance_db -> backups\deploy_<timestamp>.sql
REM   2. Verify the dump succeeded and is non-empty; abort if not (no build).
REM   3. Compress the dump into backups\deploy_<timestamp>.zip, delete raw .sql.
REM   4. Rotate old deploy_*.zip backups, keep the most recent 14.
REM   5. docker compose up -d --build (rebuilds backend/frontend images,
REM      recreates db/backend/frontend/caddy from current docker-compose.yml).
REM   6. Append a timestamped OK/FAILED result for each step to
REM      backups\deploy_log.txt.
REM
REM Run this from cmd, NOT PowerShell. Requires Docker Desktop running.
REM
REM NOTE: keep this file pure ASCII (no Cyrillic, no chcp) - see CLAUDE.md
REM notes about cmd/PowerShell mangling Cyrillic on redirect.
REM
REM NOTE on structure: this script deliberately avoids nesting an if/else
REM block inside another if/else's parenthesized block. cmd.exe's parser
REM frequently mismatches which "else" belongs to which "if" in that case,
REM aborting the whole compound statement (silently, or with "else was
REM unexpected at this time"). Flow control below uses goto/labels instead,
REM keeping every if/else single-level.
REM ============================================================================

setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

if not exist "backups" mkdir "backups"

REM Sortable timestamp (yyyy-MM-dd_HHmmss) via PowerShell - ASCII only, no Cyrillic involved.
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

set "LOG_FILE=backups\deploy_log.txt"
set "SQL_FILE=backups\deploy_%TS%.sql"
set "ZIP_FILE=backups\deploy_%TS%.zip"

echo ---------------------------------------------- >> "%LOG_FILE%"
echo %DATE% %TIME% DEPLOY START %TS% >> "%LOG_FILE%"

echo Step 1/3: backing up database...
docker exec -t finance_db pg_dump -U finance_user finance > "%SQL_FILE%"
set "DUMP_RESULT=%ERRORLEVEL%"

if not exist "%SQL_FILE%" goto :backup_failed

for %%A in ("%SQL_FILE%") do set "SQL_SIZE=%%~zA"

if not "%DUMP_RESULT%"=="0" goto :backup_failed
if "%SQL_SIZE%"=="0" goto :backup_failed
goto :backup_ok

:backup_failed
echo %DATE% %TIME% BACKUP FAILED dump_result=%DUMP_RESULT% size=%SQL_SIZE% >> "%LOG_FILE%"
echo Backup failed (dump_result=%DUMP_RESULT%, size=%SQL_SIZE%). Deploy aborted, containers untouched.
del "%SQL_FILE%" 2>nul
endlocal
exit /b 1

:backup_ok
powershell -NoProfile -Command "Compress-Archive -Path '%SQL_FILE%' -DestinationPath '%ZIP_FILE%' -Force"

if not exist "%ZIP_FILE%" goto :archive_failed

del "%SQL_FILE%"
for %%A in ("%ZIP_FILE%") do set "ZIP_SIZE=%%~zA"
echo %DATE% %TIME% BACKUP OK %ZIP_FILE% ^(%ZIP_SIZE% bytes^) >> "%LOG_FILE%"
echo Backup OK: %ZIP_FILE%
goto :rotate

:archive_failed
echo %DATE% %TIME% BACKUP OK but archive step failed, raw SQL kept: %SQL_FILE% >> "%LOG_FILE%"
echo Backup OK but zip step failed, kept raw file: %SQL_FILE%

:rotate
echo Step 2/3: rotating old deploy backups (keep last 14)...
set "KEEP=14"
for /f "skip=%KEEP% delims=" %%f in ('dir /b /o-n "backups\deploy_*.zip" 2^>nul') do (
    del "backups\%%f"
    echo %DATE% %TIME% ROTATED removed backups\%%f >> "%LOG_FILE%"
)

echo Step 3/3: docker compose up -d --build (this can take a few minutes)...
echo %DATE% %TIME% BUILD starting >> "%LOG_FILE%"
docker compose up -d --build >> "%LOG_FILE%" 2>&1
set "BUILD_RESULT=%ERRORLEVEL%"

if not "%BUILD_RESULT%"=="0" goto :build_failed

echo %DATE% %TIME% DEPLOY OK >> "%LOG_FILE%"
echo Deploy finished OK.
echo Backup: %ZIP_FILE%
echo Log:    %LOG_FILE%
endlocal
exit /b 0

:build_failed
echo %DATE% %TIME% DEPLOY FAILED build_result=%BUILD_RESULT% >> "%LOG_FILE%"
echo Deploy FAILED during build/up - exit code %BUILD_RESULT%. Check %LOG_FILE% and "docker compose logs".
endlocal
exit /b 1
