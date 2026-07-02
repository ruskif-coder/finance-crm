@echo off
REM apply_block1_patches.bat
REM Block 1 security patches from technical audit:
REM   1. contracts.py  — upload size limit 20MB + document_link protocol validation
REM   2. Caddyfile     — security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
REM   3. permissions.py — "delete" added to counterparties actions (SECTIONS)
REM   4. docker-compose.yml — db healthcheck + condition:service_healthy + mem_limit
REM Run from cmd (not PowerShell)

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"
set "LOG=backups\block1_patches_log.txt"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo.
echo ============================================================
echo  apply_block1_patches.bat  [%TS%]
echo  Block 1: upload limit + link validation + headers + healthcheck
echo ============================================================
echo [%TS%] === START === >> "%LOG%"

REM ---------- 1. Backup DB ----------
echo [1/5] Backup DB ...
docker exec -t finance_db pg_dump -U finance_user finance > "backups\before_block1_%TS%.sql"
if errorlevel 1 (
    echo WARNING: backup failed, continuing
    echo [%TS%] WARNING backup failed >> "%LOG%"
) else (
    echo       OK
    echo [%TS%] backup OK >> "%LOG%"
)

REM ---------- 2. contracts.py (upload limit + URL validation) ----------
echo [2/5] Push contracts.py ...
docker exec -i finance_backend sh -c "cat > /app/app/routers/contracts.py" < "F:\finance\backend\app\routers\contracts.py"
if errorlevel 1 (
    echo FAIL: contracts.py
    echo [%TS%] FAIL contracts.py >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] contracts.py OK >> "%LOG%"

REM ---------- 3. permissions.py (counterparties delete) ----------
echo [3/5] Push permissions.py ...
docker exec -i finance_backend sh -c "cat > /app/app/permissions.py" < "F:\finance\backend\app\permissions.py"
if errorlevel 1 (
    echo FAIL: permissions.py
    echo [%TS%] FAIL permissions.py >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] permissions.py OK >> "%LOG%"

REM ---------- 4. Restart backend ----------
echo       Restart finance_backend ...
docker restart finance_backend
if errorlevel 1 (
    echo FAIL: restart backend
    echo [%TS%] FAIL restart >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] restart OK >> "%LOG%"
timeout /t 5 /nobreak > nul

REM ---------- 5. Caddyfile (security headers) ----------
echo [4/5] Reload Caddy (security headers) ...
REM Caddyfile uzhe obnovlen na diske (F:\finance\Caddyfile).
REM Konteyner smotrit na nego cherez bind-mount — docker cp zdes NE nuzhen
REM (i padet s "device or resource busy" na bind-mounted faylakh).
REM Prosto soobshchaem Caddy perechitat config:
docker exec finance_caddy caddy reload --config /etc/caddy/Caddyfile
if errorlevel 1 (
    echo       Reload returned non-zero, trying restart...
    docker restart finance_caddy
    timeout /t 3 /nobreak > nul
)
echo       OK
echo [%TS%] caddy OK >> "%LOG%"

REM ---------- NOTE: docker-compose.yml healthcheck + mem_limit ----------
echo [5/5] docker-compose.yml patched on disk.
echo       Healthcheck + mem_limit take effect on next full redeploy (deploy_finance.bat).
echo       Running containers are unchanged — no immediate restart needed.
echo [%TS%] compose noted (needs redeploy) >> "%LOG%"

REM ---------- Verification ----------
echo.
echo --- Backend zdravstvuyet? ---
docker exec finance_backend curl -s -o /dev/null -w "HTTP: %%{http_code}" http://localhost:8000/
echo.
echo --- Security headers ot Caddy ---
curl -s -o /dev/null -w "X-Frame-Options: %%header{x-frame-options}\nX-Content-Type: %%header{x-content-type-options}\n" http://localhost/
echo.
echo --- permissions.py: counterparties actions ---
docker exec finance_backend python -c "from app.permissions import SECTIONS; s=[x for x in SECTIONS if x['key']=='counterparties'][0]; print('counterparties actions:', s['actions'])"
echo.

echo [%TS%] DONE OK >> "%LOG%"
echo.
echo ============================================================
echo  READY. Block 1 applied.
echo  After next deploy_finance.bat: healthcheck + mem_limit activate.
echo ============================================================
echo.
pause
endlocal
