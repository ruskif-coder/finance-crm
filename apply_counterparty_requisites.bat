@echo off
REM apply_counterparty_requisites.bat
REM Zapisyvaet v BD: KPP + EDO ID (counterparties) + bank accounts (counterparty_bank_accounts)
REM 153 UPDATE counterparties, do 148 INSERT counterparty_bank_accounts
REM Zapuskat iz cmd (ne PowerShell)
REM -----------------------------------------------------------------------

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"

set "LOG=backups\apply_cp_requisites_log.txt"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo.
echo ============================================================
echo  apply_counterparty_requisites.bat  [%TS%]
echo ============================================================
echo.
echo [%TS%] === START === >> "%LOG%"

REM ---------- 1. Backup ----------
echo [1/3] Backup BD ...
docker exec -t finance_db pg_dump -U finance_user finance > "backups\before_cp_requisites_%TS%.sql"
if errorlevel 1 (
    echo WARNING: backup ne udalsya, prodolzhaem...
    echo [%TS%] WARNING backup failed >> "%LOG%"
) else (
    echo       OK: backups\before_cp_requisites_%TS%.sql
    echo [%TS%] backup OK >> "%LOG%"
)
echo.

REM ---------- 2. Apply SQL ----------
echo [2/3] Primenyaem SQL-migratsiyu ...
echo       153 UPDATE counterparties  ^(kpp + edo_id^)
echo       do 148 INSERT counterparty_bank_accounts
echo.
docker exec -i finance_db psql -U finance_user -d finance < "F:\finance\update_counterparty_requisites.sql"
if errorlevel 1 (
    echo OSHYBKA: SQL zavershilsya s oshibkoy
    echo [%TS%] FAIL sql >> "%LOG%"
    pause & exit /b 1
)
echo.
echo       OK
echo [%TS%] sql applied OK >> "%LOG%"
echo.

REM ---------- 3. Verify ----------
echo [3/3] Proverka ...
docker exec finance_db psql -U finance_user -d finance -c "SELECT COUNT(*) AS \"KPP zapolnen\" FROM counterparties WHERE kpp IS NOT NULL;"
docker exec finance_db psql -U finance_user -d finance -c "SELECT COUNT(*) AS \"Bankovskikh schetov\" FROM counterparty_bank_accounts;"
echo [%TS%] verify OK >> "%LOG%"

echo.
echo ============================================================
echo  GOTOVO
echo  Prover v sisteme: Spravochniki -> Kontragenty -> otkroy kartochku lyubogo
echo  dolzhny poyavitsya KPP i bankovskie rekvizity
echo  Log: %LOG%
echo ============================================================
echo.
echo [%TS%] === DONE OK === >> "%LOG%"

pause
endlocal
