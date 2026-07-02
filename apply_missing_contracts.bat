@echo off
REM apply_missing_contracts.bat
REM Sozdayet pustyye zapisi v contracts dlya 68 kontragentov bez dogovora.
REM Kazhday INSERT idet cherez NOT EXISTS — dubli ne sozdayutsya.
REM Zapuskat iz cmd (ne PowerShell)

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"
set "LOG=backups\apply_missing_contracts_log.txt"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo.
echo ============================================================
echo  apply_missing_contracts.bat  [%TS%]
echo  Sozdayot 68 pustykh zapisey v contracts
echo ============================================================
echo [%TS%] === START === >> "%LOG%"

REM ---------- 1. Backup ----------
echo [1/3] Backup BD ...
docker exec -t finance_db pg_dump -U finance_user finance > "backups\before_missing_contracts_%TS%.sql"
if errorlevel 1 (
    echo WARNING: backup ne udalsya
    echo [%TS%] WARNING backup failed >> "%LOG%"
) else (
    echo       OK
    echo [%TS%] backup OK >> "%LOG%"
)

REM ---------- 2. Apply ----------
echo [2/3] INSERT 68 kontragentov ...
docker exec -i finance_db psql -U finance_user -d finance < "F:\finance\insert_missing_contracts.sql"
if errorlevel 1 (
    echo OSHYBKA: SQL
    echo [%TS%] FAIL sql >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] sql OK >> "%LOG%"

REM ---------- 3. Verify ----------
echo [3/3] Proverka ...
docker exec finance_db psql -U finance_user -d finance -c "SELECT COUNT(*) AS vsego_dogovorov FROM contracts;"
docker exec finance_db psql -U finance_user -d finance -c "SELECT COUNT(*) AS trebuyut_zapolneniya FROM contracts WHERE note = 'Требует заполнения';"

echo [%TS%] DONE OK >> "%LOG%"
echo.
echo ============================================================
echo  GOTOVO
echo  Prover: http://localhost -> Spravochniki -> Dogovory
echo  Novyye zapisi budut s pometkey "Trebuyet zapolneniya"
echo ============================================================
echo.
pause
endlocal
