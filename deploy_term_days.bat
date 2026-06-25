@echo off
REM Deploys the "term_days" (payment deferral, in days) feature for the counterparty
REM registry: DB migration, backend code (models/reports/operations/counterparties),
REM frontend code (settings.js), rebuild frontend, restart backend.
REM Run from cmd (NOT PowerShell) on the local Windows machine.

cd /d F:\finance
set LOG=F:\finance\deploy_term_days_log.txt

echo ===== %DATE% %TIME% ===== > "%LOG%"

echo [1/6] Backing up database before migration... >> "%LOG%"
docker exec -t finance_db pg_dump -U finance_user finance > "F:\finance\backups\backup_before_term_days_2026-06-24.sql" 2>>"%LOG%"

echo [2/6] Running migration (add term_days column + backfill)... >> "%LOG%"
docker exec -i finance_db psql -U finance_user -d finance < "F:\finance\migrate_add_term_days.sql" >> "%LOG%" 2>&1

echo [3/6] Copying backend code into finance_backend... >> "%LOG%"
docker cp "F:\finance\backend\app\models.py" finance_backend:/app/app/models.py >> "%LOG%" 2>&1
docker cp "F:\finance\backend\app\routers\reports.py" finance_backend:/app/app/routers/reports.py >> "%LOG%" 2>&1
docker cp "F:\finance\backend\app\routers\operations.py" finance_backend:/app/app/routers/operations.py >> "%LOG%" 2>&1
docker cp "F:\finance\backend\app\routers\counterparties.py" finance_backend:/app/app/routers/counterparties.py >> "%LOG%" 2>&1

echo [4/6] Restarting finance_backend... >> "%LOG%"
docker restart finance_backend >> "%LOG%" 2>&1

echo [5/6] Copying settings.js into finance_frontend and rebuilding... >> "%LOG%"
docker cp "F:\finance\frontend\pages\settings.js" finance_frontend:/app/pages/settings.js >> "%LOG%" 2>&1
docker exec finance_frontend sh -c "rm -rf .next && npm run build" >> "%LOG%" 2>&1

echo [6/6] Restarting finance_frontend... >> "%LOG%"
docker restart finance_frontend >> "%LOG%" 2>&1

echo ===== DONE ===== >> "%LOG%"
echo Done. Log saved to %LOG%
echo Wait ~10-15 seconds for frontend to come back up, then check /settings - Kontragenty and /receivables.
pause
