@echo off
REM Restores finance_backend's live code to match what's on disk in F:\finance\backend.
REM Needed because "docker compose up -d --force-recreate" rebuilt the container from
REM the original image, discarding code that had been pushed in live over time via
REM "docker exec ... cat > file.py" (this project never rebuilds the image on deploy).
REM Uses docker cp - a direct byte copy, not a text pipe, so Cyrillic content is safe.

cd /d F:\finance

echo [1/2] Copying current backend/app code into finance_backend container...
docker cp "F:\finance\backend\app\." finance_backend:/app/app
if errorlevel 1 (
    echo ERROR: docker cp failed.
    pause
    exit /b 1
)

echo [2/2] Restarting finance_backend...
docker restart finance_backend

echo.
echo Done. Wait a few seconds, then try logging in again.
echo If it still fails, run: docker logs --tail 50 finance_backend
pause
