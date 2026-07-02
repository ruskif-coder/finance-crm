@echo off
REM apply_director_names.bat
REM Zapisyvaet FIO gendirektorov iz 1S v tablitsu counterparties.director_name
REM 33 UPDATE, tolko esli director_name IS NULL (ne perepisyvaet)
REM Zapuskat iz cmd (ne PowerShell)
REM -----------------------------------------------------------------------

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"
set "LOG=backups\apply_directors_log.txt"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo.
echo ============================================================
echo  apply_director_names.bat  [%TS%]
echo ============================================================
echo [%TS%] === START === >> "%LOG%"

REM ---------- 1. Backup ----------
echo [1/3] Backup BD ...
docker exec -t finance_db pg_dump -U finance_user finance > "backups\before_directors_%TS%.sql"
if errorlevel 1 (
    echo WARNING: backup ne udalsya
    echo [%TS%] WARNING backup failed >> "%LOG%"
) else (
    echo       OK
    echo [%TS%] backup OK >> "%LOG%"
)

REM ---------- 2. Apply ----------
echo [2/3] Primenyaem SQL (33 UPDATE director_name) ...
docker exec -i finance_db psql -U finance_user -d finance < "F:\finance\update_director_names.sql"
if errorlevel 1 (
    echo OSHYBKA: SQL
    echo [%TS%] FAIL sql >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] sql OK >> "%LOG%"

REM ---------- 3. Verify ----------
echo [3/3] Proverka ...
docker exec finance_db psql -U finance_user -d finance -c "SELECT COUNT(*) AS zapolneno FROM counterparties WHERE director_name IS NOT NULL;"
echo [%TS%] DONE OK >> "%LOG%"

echo.
echo ============================================================
echo  GOTOVO — FIO gendirektorov zapisany
echo  Prover: Spravochniki -> Kontragenty -> kartochka kontragenta
echo ============================================================
echo.
pause
endlocal
