@echo off
REM apply_security_patches.bat
REM Zakryvayet tri "nemедленно" pункта iz tekhnicheskogo audita:
REM   1. Убраn hardcoded fallback SECRET_KEY iz auth.py
REM   2. Zakryt Swagger UI v production (main.py)
REM   3. Dobavleny DB-indeksy (CONCURRENTLY, bez blokirovki)
REM Zapuskat iz cmd (ne PowerShell)

setlocal enabledelayedexpansion
cd /d F:\finance

if not exist "backups" mkdir "backups"
set "LOG=backups\security_patches_log.txt"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmmss"') do set "TS=%%i"

echo.
echo ============================================================
echo  apply_security_patches.bat  [%TS%]
echo  Audit patches: SECRET_KEY + Swagger + DB indexes
echo ============================================================
echo [%TS%] === START === >> "%LOG%"

REM ---------- 1. Backup BD ----------
echo [1/4] Backup BD ...
docker exec -t finance_db pg_dump -U finance_user finance > "backups\before_security_%TS%.sql"
if errorlevel 1 (
    echo WARNING: backup ne udalsya, prodolzhaem
    echo [%TS%] WARNING backup failed >> "%LOG%"
) else (
    echo       OK
    echo [%TS%] backup OK >> "%LOG%"
)

REM ---------- 2. Patch auth.py (SECRET_KEY) ----------
echo [2/4] Push auth.py (ubrali hardcoded fallback SECRET_KEY) ...
docker exec -i finance_backend sh -c "cat > /app/app/routers/auth.py" < "F:\finance\backend\app\routers\auth.py"
if errorlevel 1 (
    echo OSHYBKA: auth.py
    echo [%TS%] FAIL auth.py >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] auth.py OK >> "%LOG%"

REM ---------- 3. Patch main.py (Swagger) ----------
echo [3/4] Push main.py (zakryli /docs v production) ...
docker exec -i finance_backend sh -c "cat > /app/app/main.py" < "F:\finance\backend\app\main.py"
if errorlevel 1 (
    echo OSHYBKA: main.py
    echo [%TS%] FAIL main.py >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] main.py OK >> "%LOG%"

REM ---------- 4. Restart backend (uvicorn --reload podkhvatit izmeneniya) ----------
echo       Restart finance_backend ...
docker restart finance_backend
if errorlevel 1 (
    echo OSHYBKA: restart
    echo [%TS%] FAIL restart >> "%LOG%"
    pause & exit /b 1
)
echo       OK — zhdyom 5 sek...
timeout /t 5 /nobreak > nul

REM ---------- 5. DB indexes (CONCURRENTLY — bez blokirovki) ----------
echo [4/4] Dobavlyaem DB-indeksy (CONCURRENTLY) ...
docker exec -i finance_db psql -U finance_user -d finance < "F:\finance\add_db_indexes.sql"
if errorlevel 1 (
    echo OSHYBKA: indeksy
    echo [%TS%] FAIL indexes >> "%LOG%"
    pause & exit /b 1
)
echo       OK
echo [%TS%] indexes OK >> "%LOG%"

REM ---------- Verifikatsiya ----------
echo.
echo --- Proverka: backend otvechayet ---
docker exec finance_backend curl -s -o /dev/null -w "HTTP status: %%{http_code}" http://localhost:8000/
echo.
echo --- /docs dolzhen vernut 404 ---
docker exec finance_backend curl -s -o /dev/null -w "/docs: %%{http_code}" http://localhost:8000/docs
echo.
echo --- Indeksy v BD ---
docker exec finance_db psql -U finance_user -d finance -c "SELECT tablename, indexname FROM pg_indexes WHERE tablename IN ('operations','contracts','audit_log') AND schemaname='public' ORDER BY tablename, indexname;"

echo [%TS%] DONE OK >> "%LOG%"
echo.
echo ============================================================
echo  GOTOVO. Vse tri patcha primeneny.
echo  Prover: http://localhost/docs dolzhen dat 404.
echo ============================================================
echo.
pause
endlocal
