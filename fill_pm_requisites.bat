@echo off
REM fill_pm_requisites.bat
REM Заполняет реквизиты OOO Programmatic Media из файла реквизитов.
REM Запускать из cmd (не PowerShell).

cd /d F:\finance

echo === Push script to container ===
docker exec -i finance_backend sh -c "cat > /app/app/fill_pm_requisites.py" < "F:\finance\backend\app\fill_pm_requisites.py"

echo.
echo === DRY RUN ===
docker exec finance_backend python app/fill_pm_requisites.py

echo.
set /p CONFIRM=Apply? (y/n):
if /i "%CONFIRM%"=="y" (
    docker exec finance_backend python app/fill_pm_requisites.py --apply
    echo Done.
) else (
    echo Cancelled.
)
pause
