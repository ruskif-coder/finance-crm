@echo off
echo === Block 2: Deploy login lockout (DB-backed) ===

echo [1/3] Push models.py (adds LoginAttempt table)
docker exec -i finance_backend sh -c "cat > /app/app/models.py" < "F:\finance\backend\app\models.py"
if errorlevel 1 (echo FAIL models.py && goto :err)
echo OK

echo [2/3] Push auth.py (DB-based lockout functions)
docker exec -i finance_backend sh -c "cat > /app/app/routers/auth.py" < "F:\finance\backend\app\routers\auth.py"
if errorlevel 1 (echo FAIL auth.py && goto :err)
echo OK

echo [3/3] Restart backend (create_all creates login_attempts table on startup)
docker restart finance_backend
if errorlevel 1 (echo FAIL restart && goto :err)

echo.
echo === Done. Verify: docker logs finance_backend --tail 30 ===
echo Login attempts now survive docker restart (stored in PostgreSQL).
goto :end

:err
echo FAILED - check error above
exit /b 1

:end
