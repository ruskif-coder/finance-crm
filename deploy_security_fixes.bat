@echo off
REM Deploy Etap 2 security fixes: counterparties.py, users.py, auth.py, operations.py
REM Run this from cmd (NOT PowerShell) - PowerShell mangles Cyrillic strings on redirect.

set LOG=F:\finance\deploy_security_fixes_log.txt
echo ===== DEPLOY SECURITY FIXES START %DATE% %TIME% ===== > "%LOG%"

echo [1/5] Copying counterparties.py into container... >> "%LOG%"
docker exec -i finance_backend sh -c "cat > /app/app/routers/counterparties.py" < "F:\finance\backend\app\routers\counterparties.py"

echo [2/5] Copying users.py into container... >> "%LOG%"
docker exec -i finance_backend sh -c "cat > /app/app/routers/users.py" < "F:\finance\backend\app\routers\users.py"

echo [3/5] Copying auth.py into container... >> "%LOG%"
docker exec -i finance_backend sh -c "cat > /app/app/routers/auth.py" < "F:\finance\backend\app\routers\auth.py"

echo [4/5] Copying operations.py into container... >> "%LOG%"
docker exec -i finance_backend sh -c "cat > /app/app/routers/operations.py" < "F:\finance\backend\app\routers\operations.py"

echo [5/5] Restarting finance_backend (uvicorn --reload picks up the files, restart clears state)... >> "%LOG%"
docker restart finance_backend >> "%LOG%" 2>&1

echo ===== DEPLOY DONE %DATE% %TIME% ===== >> "%LOG%"
echo DEPLOY_FINISHED_MARKER >> "%LOG%"

echo Done. Check %LOG% for details.
echo After this, verify manually:
echo  1. Try deleting a counterparty as a non-admin user without counterparties-delete permission - should be refused (403).
echo  2. Try creating a user with a 1-character password - should be refused (400).
echo  3. Try logging in with a wrong password 5 times in a row - 6th attempt should be refused (429) for 15 minutes.
echo  4. Try uploading a non-xlsx file to /operations import - should be refused (400).
pause
