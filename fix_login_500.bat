@echo off
REM Diagnoses and fixes the 500 error on login that appeared after rotate_secrets.bat.
REM Likely cause: finance_backend's DB connection still uses the old password,
REM while finance_user's Postgres password was already changed via ALTER USER.
REM Run from cmd (NOT PowerShell) on the local Windows machine.

cd /d F:\finance
set LOG=F:\finance\fix_login_500_log.txt

echo ===== %DATE% %TIME% ===== > "%LOG%"

echo [1/3] Recent finance_backend logs (before fix): >> "%LOG%"
docker logs --tail 80 finance_backend >> "%LOG%" 2>&1

echo [2/3] Recreating db and backend containers from current docker-compose.yml + .env ... >> "%LOG%"
docker compose up -d --force-recreate db backend >> "%LOG%" 2>&1

echo Waiting 10 seconds for Postgres to finish starting... >> "%LOG%"
timeout /t 10 /nobreak >> "%LOG%" 2>&1

echo [3/3] finance_backend logs after recreate: >> "%LOG%"
docker logs --tail 40 finance_backend >> "%LOG%" 2>&1

echo ===== DONE ===== >> "%LOG%"

echo Done. Log saved to %LOG% - showing it below:
echo.
type "%LOG%"
echo.
echo Try logging in again now.
pause
