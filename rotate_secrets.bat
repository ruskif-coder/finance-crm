@echo off
REM Rotates POSTGRES_PASSWORD and SECRET_KEY using the new values already
REM generated into F:\finance\.env. Run this from cmd (NOT PowerShell).
REM
REM Effects:
REM  - Backs up the database BEFORE touching anything.
REM  - Changes the Postgres password for finance_user (ALTER USER - this is
REM    required because POSTGRES_PASSWORD in docker-compose.yml only applies
REM    on first init of an empty volume, not to an existing database).
REM  - Recreates containers so they pick up the new SECRET_KEY/POSTGRES_PASSWORD
REM    from .env via docker compose.
REM  - Logs everyone out: changing SECRET_KEY invalidates all existing JWTs.
REM
REM Pick a moment when nobody is actively using the system.

cd /d F:\finance

set ENVFILE=F:\finance\.env
for /f "tokens=1,2 delims==" %%A in ("%ENVFILE%") do (
    if "%%A"=="POSTGRES_PASSWORD" set NEWPASS=%%B
    if "%%A"=="SECRET_KEY" set NEWKEY=%%B
)

if "%NEWPASS%"=="" (
    echo ERROR: POSTGRES_PASSWORD not found in %ENVFILE%
    pause
    exit /b 1
)
if "%NEWKEY%"=="" (
    echo ERROR: SECRET_KEY not found in %ENVFILE%
    pause
    exit /b 1
)

set BACKUPDIR=F:\finance\backups
if not exist "%BACKUPDIR%" mkdir "%BACKUPDIR%"
set DUMP=%BACKUPDIR%\backup_before_secret_rotation.sql

echo [1/3] Backing up database to %DUMP% ...
docker exec -t finance_db pg_dump -U finance_user finance > "%DUMP%"
if errorlevel 1 (
    echo ERROR: backup failed. Aborting rotation - nothing was changed.
    pause
    exit /b 1
)

echo [2/3] Changing Postgres password for finance_user ...
docker exec -i finance_db psql -U finance_user -d finance -c "ALTER USER finance_user WITH PASSWORD '%NEWPASS%';"
if errorlevel 1 (
    echo ERROR: ALTER USER failed. Aborting before container recreation.
    echo Database backup is saved at %DUMP% if you need it.
    pause
    exit /b 1
)

echo [3/3] Recreating containers with the new secrets from .env ...
docker compose up -d

echo.
echo Done.
echo  - Postgres password for finance_user has been changed.
echo  - SECRET_KEY has been rotated - everyone currently logged in has been
echo    logged out and will need to log in again.
echo  - Pre-rotation backup saved at %DUMP%
pause
