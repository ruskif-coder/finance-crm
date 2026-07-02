@echo off
REM deploy_counterparty_card.bat
REM
REM Деплой карточки контрагента:
REM   1. SQL-миграция (новые колонки counterparties + таблица counterparty_bank_accounts)
REM   2. Push backend-файлов + перезапуск backend
REM   3. Push frontend-файлов + пересборка + перезапуск frontend
REM
REM Запускать из cmd (не PowerShell) — Cyrillic в источниках.
REM -----------------------------------------------------------------------

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"
set "LOG=backups\deploy_counterparty_card_log.txt"
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"
echo %DATE% %TIME% === START deploy_counterparty_card.bat === >> "%LOG%"

REM ---------- 1. Backup DB ----------
echo === [1/5] Backup DB ===
docker exec -t finance_db pg_dump -U finance_user finance > "backups\pre_cp_card_%TS%.sql"
echo %DATE% %TIME% backup done >> "%LOG%"
echo.

REM ---------- 2. SQL migration ----------
echo === [2/5] Run SQL migration ===
docker exec -i finance_db psql -U finance_user -d finance < add_counterparty_requisites.sql
if errorlevel 1 (
    echo ERROR: SQL migration failed
    echo %DATE% %TIME% SQL migration FAILED >> "%LOG%"
    pause & exit /b 1
)
echo %DATE% %TIME% SQL migration OK >> "%LOG%"
echo.

REM ---------- 3. Push backend ----------
echo === [3/5] Push backend files ===
docker exec -i finance_backend sh -c "cat > /app/app/models.py" < "F:\finance\backend\app\models.py"
docker exec -i finance_backend sh -c "cat > /app/app/routers/counterparties.py" < "F:\finance\backend\app\routers\counterparties.py"
docker restart finance_backend
echo %DATE% %TIME% backend pushed + restarted >> "%LOG%"
echo.

REM ---------- 4. Push frontend ----------
echo === [4/5] Push frontend files ===
docker exec -i finance_frontend sh -c "cat > /app/pages/directories.js" < "F:\finance\frontend\pages\directories.js"

REM Создать директорию counterparty в контейнере и скопировать страницу
docker exec finance_frontend mkdir -p /app/pages/counterparty
docker exec -i finance_frontend sh -c "cat > /app/pages/counterparty/[id].js" < "F:\finance\frontend\pages\counterparty\[id].js"

echo %DATE% %TIME% frontend files pushed >> "%LOG%"
echo.

REM ---------- 5. Rebuild + restart frontend ----------
echo === [5/5] Rebuild frontend (npm run build) ===
echo This takes 1-3 minutes...
docker exec finance_frontend sh -c "rm -rf .next && npm run build"
if errorlevel 1 (
    echo ERROR: frontend build failed
    echo %DATE% %TIME% frontend build FAILED >> "%LOG%"
    pause & exit /b 1
)
docker restart finance_frontend
echo %DATE% %TIME% frontend rebuilt + restarted >> "%LOG%"
echo.

echo %DATE% %TIME% === DONE OK === >> "%LOG%"
echo Done. Log: %LOG%
echo.
echo Test: http://localhost/directories -- click a counterparty name to open card
echo To fill PM requisites: fill_pm_requisites.bat
pause
endlocal
