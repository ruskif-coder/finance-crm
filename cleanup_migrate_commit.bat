@echo off
REM cleanup_migrate_commit.bat
REM Polnyy pereezd: ubiraem musor, gitignore, git add+commit vsego nakoplennogo.
REM Zapuskat iz cmd (ne PowerShell) iz lyuboy papki.
setlocal enabledelayedexpansion
cd /d F:\finance

echo.
echo ============================================================
echo  cleanup_migrate_commit.bat
echo  1. Udalyaem musor iz kornya F:\finance
echo  2. Snimaem zависshie git locks
echo  3. Git add + commit nakoplennykh izmeneniy
echo  4. Ubiraem osirotevshie Docker-toma
echo ============================================================
echo.

REM ---------- 1. Musor-fayly (pusto/dubli) ----------
echo [1/4] Udalyaem musor...
if exist "2025-01-01"       del /f /q "2025-01-01"
if exist "Dogovory\"        rmdir /s /q "Dogovory"
if exist "kartochka\"       rmdir /s /q "kartochka"
if exist "otkroy\"          rmdir /s /q "otkroy"
if exist "deploy_cp_card.bat" del /f /q "deploy_cp_card.bat"
echo       OK

REM ---------- 2. Git locks ----------
echo [2/4] Snimaem git locks...
if exist ".git\index.lock"  del /f /q ".git\index.lock"
if exist ".git\HEAD.lock"   del /f /q ".git\HEAD.lock"
echo       OK

REM ---------- 3. Git commit ----------
echo [3/4] Git: staging + commit...

git config user.email "suhum1966@gmail.com"
git config user.name "SimbAD"

REM -- Commit A: security + block1 patches (modified tracked files)
git add CLAUDE.md
git add Caddyfile
git add docker-compose.yml
git add backend/app/main.py
git add backend/app/models.py
git add backend/app/permissions.py
git add "backend/app/routers/auth.py"
git add "backend/app/routers/contracts.py"
git add "backend/app/routers/counterparties.py"
git add "backend/app/routers/reports.py"
git add "frontend/pages/directories.js"
git add "frontend/pages/operations.js"
git add "frontend/pages/receivables.js"

git commit -m "security: SECRET_KEY hard-fail, Swagger closed, DB indexes, Block 1 patches"
if errorlevel 1 (
    echo WARNING: commit A ne udalos ili nechego komitit
) else (
    echo       Commit A OK
)

REM -- Commit B: new scripts and SQL (untracked operational files)
git add add_contract_documents.sql
git add add_counterparty_requisites.sql
git add add_db_indexes.sql
git add backfill_contracts_from_csv.sql
git add check_missing_contracts_query.sql
git add insert_missing_contracts.sql
git add migrate_add_term_days.sql
git add sync_edo_contracts.sql
git add update_counterparty_requisites.sql
git add update_director_names.sql

git add apply_block1_patches.bat
git add apply_counterparty_requisites.bat
git add apply_director_names.bat
git add apply_missing_contracts.bat
git add apply_security_patches.bat
git add check_missing_contracts.bat
git add cleanup_and_commit.bat
git add cleanup_migrate_commit.bat
git add deploy_contracts_documents.bat
git add deploy_contracts_excel.bat
git add deploy_counterparty_card.bat
git add deploy_ops_receivables.bat
git add deploy_receivables_export.bat
git add fill_pm_requisites.bat
git add make_contracts_xlsx.bat
git add sync_edo_contracts.bat
git add sync_edo_data.bat

git add make_contracts_xlsx.py
git add "backend/app/fill_pm_requisites.py"
git add "backend/app/sync_edo_data.py"

git add "frontend/pages/counterparty/"

git commit -m "ops: SQL migrations, deploy scripts, EDO sync, counterparty card"
if errorlevel 1 (
    echo WARNING: commit B ne udalos ili nechego komitit
) else (
    echo       Commit B OK
)

REM -- Commit C: docs folder
git add docs/
git commit -m "docs: technical audit, Excel analyses, cashflow reference"
if errorlevel 1 (
    echo WARNING: commit C ne udalos ili nechego komitit
) else (
    echo       Commit C OK
)

REM ---------- 4. Osirotevshie Docker-toma ----------
echo [4/4] Ubiraem osirotevshie financecrm-toma...
docker volume rm financecrm_postgres_data financecrm_caddy_data financecrm_caddy_config 2>nul
echo       (esli oshibka "no such volume" — uzhe udaleny, vsyo OK)

echo.
echo --- Git log (poslednie 5) ---
git log --oneline -5
echo.
echo --- Git status ---
git status --short
echo.
echo ============================================================
echo  GOTOVO. Papka F:\finance privedena v poryadok.
echo  D:\Dropbox\Finance CRM mozhno udalit ili ostavit kak arxiv.
echo ============================================================
echo.
pause
endlocal
