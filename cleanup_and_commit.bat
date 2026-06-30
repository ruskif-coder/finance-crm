@echo off
setlocal enabledelayedexpansion

cd /d F:\finance
if not exist "backups" mkdir "backups"

set "LOG_FILE=backups\cleanup_commit_log.txt"
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo %DATE% %TIME% === START cleanup_and_commit.bat === >> "%LOG_FILE%"

echo === Removing orphaned Docker volumes (if any) ===
docker volume rm financecrm_postgres_data financecrm_caddy_data financecrm_caddy_config 2>nul
echo %DATE% %TIME% docker volume rm done >> "%LOG_FILE%"
echo.

echo === Clearing stale git locks (if any) ===
if exist ".git\index.lock" (
    del /f /q ".git\index.lock"
    echo %DATE% %TIME% deleted stale .git\index.lock >> "%LOG_FILE%"
    echo Deleted stale .git\index.lock
)
if exist ".git\HEAD.lock" (
    del /f /q ".git\HEAD.lock"
    echo %DATE% %TIME% deleted stale .git\HEAD.lock >> "%LOG_FILE%"
    echo Deleted stale .git\HEAD.lock
)

echo === Git commit ===
git add -A
if errorlevel 1 (
    echo %DATE% %TIME% git add FAILED >> "%LOG_FILE%"
    echo ERROR: git add failed
    pause
    exit /b 1
)
git status
echo.
set /p MSG=Commit message (Enter for default):
if "%MSG%"=="" set MSG=bulk delete counterparties with password, cp status filter on operations, virtual cp description migration, contracts module, directories page, font self-hosting
git commit -m "%MSG%"
set "GIT_RESULT=%ERRORLEVEL%"
echo %DATE% %TIME% git commit result=%GIT_RESULT% msg=%MSG% >> "%LOG_FILE%"

if "%GIT_RESULT%"=="0" (
    echo %DATE% %TIME% === DONE OK === >> "%LOG_FILE%"
) else (
    echo %DATE% %TIME% === DONE with errors === >> "%LOG_FILE%"
)

echo.
echo Done. Log: %LOG_FILE%
pause
endlocal
