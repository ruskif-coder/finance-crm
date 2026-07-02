@echo off
REM deploy_contracts_documents.bat
REM Adds document_link + file attachment support to Dogovory directory.
REM Steps:
REM   1. Backup DB
REM   2. Run SQL migration (add columns)
REM   3. Push models.py + contracts.py -> restart backend
REM   4. Apply docker-compose.yml upload volume (down/up --build)
REM   5. Push directories.js -> rebuild frontend
REM
REM Zapuskat iz cmd (ne PowerShell)
REM -----------------------------------------------------------------------

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"
if not exist "uploads" mkdir "uploads"

set "LOG=backups\deploy_contracts_documents_log.txt"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo.
echo ============================================================
echo  deploy_contracts_documents.bat  [%TS%]
echo ============================================================
echo.
echo [%TS%] === START === >> "%LOG%"

REM ---------- 1. Backup DB ----------
echo [1/7] Backup DB ...
docker exec -t finance_db pg_dump -U finance_user finance > "backups\before_contracts_documents_%TS%.sql"
if errorlevel 1 (
    echo WARNING: backup failed, prodolzhaem...
    echo [%TS%] WARNING backup failed >> "%LOG%"
) else (
    echo       OK: backups\before_contracts_documents_%TS%.sql
    echo [%TS%] backup OK >> "%LOG%"
)
echo.

REM ---------- 2. SQL migration ----------
echo [2/7] SQL migration (add document_link + attached_filename) ...
docker exec -i finance_db psql -U finance_user -d finance < "F:\finance\add_contract_documents.sql"
if errorlevel 1 (
    echo OSHYBKA: SQL migration
    echo [%TS%] FAIL sql migration >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] sql migration OK >> "%LOG%"
echo.

REM ---------- 3. Push models.py ----------
echo [3/7] Push models.py ...
docker exec -i finance_backend sh -c "cat > /app/app/models.py" < "F:\finance\backend\app\models.py"
if errorlevel 1 (
    echo OSHYBKA: models.py
    echo [%TS%] FAIL models.py >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] models.py pushed >> "%LOG%"

REM ---------- 4. Push contracts.py + restart backend ----------
echo [4/7] Push contracts.py ...
docker exec -i finance_backend sh -c "cat > /app/app/routers/contracts.py" < "F:\finance\backend\app\routers\contracts.py"
if errorlevel 1 (
    echo OSHYBKA: contracts.py
    echo [%TS%] FAIL contracts.py >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] contracts.py pushed >> "%LOG%"

echo [5/7] Restart backend + apply upload volume via docker compose up ...
REM docker compose up -d re-reads docker-compose.yml and adds the new volume mount
REM without full rebuild (only backend config changed, not Dockerfile)
docker compose up -d
if errorlevel 1 (
    echo OSHYBKA: docker compose up
    echo [%TS%] FAIL compose up >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] compose up OK (uploads volume mounted) >> "%LOG%"
echo.
echo       Zhdyom 3 sekundy poka backend podnimetsya...
timeout /t 3 /nobreak > nul

REM ---------- 5. Push frontend ----------
echo [6/7] Push directories.js ...
docker exec -i finance_frontend sh -c "cat > /app/pages/directories.js" < "F:\finance\frontend\pages\directories.js"
if errorlevel 1 (
    echo OSHYBKA: directories.js
    echo [%TS%] FAIL directories.js >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] directories.js pushed >> "%LOG%"
echo.

REM ---------- 6. Rebuild frontend ----------
echo [7/7] Rebuild frontend (rm -rf .next && npm run build) ...
echo       Zanimaet 1-3 minuty...
echo.
docker exec finance_frontend sh -c "rm -rf .next && npm run build"
if errorlevel 1 (
    echo OSHYBKA: npm run build
    echo [%TS%] FAIL build >> "%LOG%"
    pause & exit /b 1
)
echo [%TS%] build OK >> "%LOG%"

docker restart finance_frontend
if errorlevel 1 (
    echo OSHYBKA: restart frontend
    echo [%TS%] FAIL frontend restart >> "%LOG%"
    pause & exit /b 1
)
echo [%TS%] frontend restarted >> "%LOG%"

echo.
echo ============================================================
echo  GOTOVO
echo  Prover: http://localhost/directories (vkladka Dogovory)
echo    - Kolonka "Deystviya": knopka 🔗 (ssylka), 📎 (zagruzit), 📥 (skachat)
echo    - Redaktirovanie: pole "Ssylka na dokument" + prikleplenie faylа
echo    - Forma novogo dogovora: pole ssylki + zagruzka faylа posle sozdaniya
echo  Fayly khranatsya v: F:\finance\uploads\contracts\
echo  Log: %LOG%
echo ============================================================
echo.
echo [%TS%] === DONE OK === >> "%LOG%"

pause
endlocal
