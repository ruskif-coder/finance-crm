@echo off
set LOG=backups\deploy_log.txt
for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value ^| find "="') do set DT=%%a
set TS=%DT:~0,4%-%DT:~4,2%-%DT:~6,2% %DT:~8,2%:%DT:~10,2%:%DT:~12,2%

echo [%TS%] === create_login_attempts.bat START === >> %LOG%
echo === Creating login_attempts table ===

docker exec -i finance_db psql -U finance_user -d finance -c "CREATE TABLE IF NOT EXISTS login_attempts (id SERIAL PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE, failed_count INTEGER NOT NULL DEFAULT 0, locked_until TIMESTAMP, updated_at TIMESTAMP DEFAULT NOW()); CREATE INDEX IF NOT EXISTS ix_login_attempts_email ON login_attempts (email);"
if errorlevel 1 (
    echo [%TS%] FAIL: create table >> %LOG%
    echo FAIL
    exit /b 1
)
echo [%TS%] OK: login_attempts table created/verified >> %LOG%
echo OK

echo.
echo === Verify ===
docker exec finance_db psql -U finance_user -d finance -c "\d login_attempts"
echo [%TS%] === create_login_attempts.bat END OK === >> %LOG%
echo.
echo Done. Try logging in now.
