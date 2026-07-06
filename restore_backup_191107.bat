@echo off
REM === Restore DB from deploy_2026-07-02_191107.zip ===
REM Run from cmd.exe, NOT PowerShell

set BACKUP_DIR=F:\finance\backups
set ZIP_FILE=%BACKUP_DIR%\deploy_2026-07-02_191107.zip
set SQL_FILE=%BACKUP_DIR%\deploy_2026-07-02_191107.sql
set LOG=%BACKUP_DIR%\deploy_log.txt

for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value ^| find "="') do set DT=%%a
set TS=%DT:~0,4%-%DT:~4,2%-%DT:~6,2% %DT:~8,2%:%DT:~10,2%:%DT:~12,2%

echo [%TS%] === restore_backup_191107.bat START === >> %LOG%
echo === Restoring DB from deploy_2026-07-02_191107.zip ===
echo.

REM Step 1: Save current state before overwriting
echo [1/4] Backing up current state first...
for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value ^| find "="') do set DT2=%%a
set TS2=%DT2:~0,4%-%DT2:~4,2%-%DT2:~6,2%_%DT2:~8,2%%DT2:~10,2%%DT2:~12,2%
docker exec -t finance_db pg_dump -U finance_user finance > "%BACKUP_DIR%\before_restore_%TS2%.sql"
if errorlevel 1 (
    echo FAIL: could not backup current state
    echo [%TS%] FAIL: pre-restore backup >> %LOG%
    exit /b 1
)
echo OK - saved before_restore_%TS2%.sql
echo [%TS%] OK: pre-restore backup saved >> %LOG%
echo.

REM Step 2: Extract SQL from zip
echo [2/4] Extracting SQL from zip...
powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%BACKUP_DIR%' -Force"
if errorlevel 1 (
    echo FAIL: could not unzip %ZIP_FILE%
    echo [%TS%] FAIL: unzip >> %LOG%
    exit /b 1
)
if not exist "%SQL_FILE%" (
    echo FAIL: SQL file not found after unzip: %SQL_FILE%
    echo [%TS%] FAIL: SQL file missing >> %LOG%
    exit /b 1
)
echo OK - %SQL_FILE%
echo [%TS%] OK: SQL extracted >> %LOG%
echo.

REM Step 3: Drop all tables and recreate schema
echo [3/4] Clearing database schema...
docker exec -i finance_db psql -U finance_user -d finance -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO finance_user; GRANT ALL ON SCHEMA public TO public;"
if errorlevel 1 (
    echo FAIL: could not drop schema
    echo [%TS%] FAIL: drop schema >> %LOG%
    exit /b 1
)
echo OK - schema cleared
echo [%TS%] OK: schema dropped and recreated >> %LOG%
echo.

REM Step 4: Restore from SQL dump
echo [4/4] Restoring from dump (may take a moment)...
docker exec -i finance_db psql -U finance_user -d finance < "%SQL_FILE%"
if errorlevel 1 (
    echo FAIL: restore failed
    echo [%TS%] FAIL: psql restore >> %LOG%
    exit /b 1
)
echo OK - restore complete
echo [%TS%] OK: restore from deploy_2026-07-02_191107.sql === >> %LOG%
echo.

echo === Restarting backend ===
docker restart finance_backend
if errorlevel 1 (echo WARNING: restart failed, do it manually)

echo.
echo ============================================================
echo  DONE. Database restored to 2026-07-02 19:11 state.
echo  Open http://localhost and verify the balance.
echo ============================================================
