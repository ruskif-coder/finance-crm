@echo off
REM sync_edo_contracts.bat
REM Sinkhronizatsiya dannykh iz Diadoc CSV s tablitsey contracts.
REM - Dobavlyaet kolonki edo_status, edo_signed_at (esli ikh net)
REM - UPDATE po INN + nomer dogovora (tochnoe sovpadenie)
REM - UPDATE pustykh zapisey po INN (tolko esli unikalnaya v BD)
REM - document_link ne pereterayet uzhe zapolnennuyu ssylku
REM Zapuskat iz cmd (ne PowerShell)

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"
set "LOG=backups\sync_edo_contracts_log.txt"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo.
echo ============================================================
echo  sync_edo_contracts.bat  [%TS%]
echo  Diadoc EDO sync: nomera + daty + ssylki + edo_status
echo ============================================================
echo [%TS%] === START === >> "%LOG%"

REM ---------- 1. Backup ----------
echo [1/3] Backup BD ...
docker exec -t finance_db pg_dump -U finance_user finance > "backups\before_edo_sync_%TS%.sql"
if errorlevel 1 (
    echo WARNING: backup ne udalsya
    echo [%TS%] WARNING backup failed >> "%LOG%"
) else (
    echo       OK
    echo [%TS%] backup OK >> "%LOG%"
)

REM ---------- 2. Apply ----------
echo [2/3] Primenenie sync_edo_contracts.sql ...
docker exec -i finance_db psql -U finance_user -d finance < "F:\finance\sync_edo_contracts.sql"
if errorlevel 1 (
    echo OSHYBKA: SQL
    echo [%TS%] FAIL sql >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] sql OK >> "%LOG%"

REM ---------- 3. Verify ----------
echo [3/3] Proverka ...
echo --- kontrakty s edo_status ---
docker exec finance_db psql -U finance_user -d finance -c "SELECT COUNT(*) AS edo_zapolneno FROM contracts WHERE edo_status IS NOT NULL;"
echo --- kontrakty s ssylkoy na diadoc ---
docker exec finance_db psql -U finance_user -d finance -c "SELECT COUNT(*) AS diadoc_link FROM contracts WHERE document_link LIKE '%%diadoc%%';"
echo --- trebuyut annulirovaniya ---
docker exec finance_db psql -U finance_user -d finance -c "SELECT inn, contract_number, counterparty_name, edo_status FROM contracts WHERE edo_status = 'Требует заполнения';"
echo --- poslednie obnovlennye ---
docker exec finance_db psql -U finance_user -d finance -c "SELECT inn, contract_number, LEFT(counterparty_name,30) AS kontragent, TO_CHAR(contract_date,'DD.MM.YYYY') AS data, edo_status, TO_CHAR(edo_signed_at,'DD.MM.YYYY') AS podpisan FROM contracts WHERE edo_signed_at IS NOT NULL ORDER BY edo_signed_at DESC LIMIT 10;"

echo [%TS%] DONE OK >> "%LOG%"
echo.
echo ============================================================
echo  GOTOVO. Prover: http://localhost -> Spravochniki -> Dogovory
echo ============================================================
echo.
pause
endlocal
