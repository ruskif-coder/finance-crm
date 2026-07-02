@echo off
REM Создать Excel-сравнение CSV vs БД (запускать из cmd из F:\finance)
cd /d F:\finance

echo [1/3] Копируем скрипт в контейнер...
docker exec -i finance_backend sh -c "cat > /tmp/make_xlsx.py" < "F:\finance\make_contracts_xlsx.py"
if errorlevel 1 ( echo ОШИБКА: копирование & pause & exit /b 1 )

echo [2/3] Запускаем (pip install openpyxl если нужно)...
docker exec finance_backend sh -c "pip install openpyxl -q 2>/dev/null; python /tmp/make_xlsx.py"
if errorlevel 1 ( echo ОШИБКА: скрипт & pause & exit /b 1 )

echo [3/3] Копируем xlsx обратно...
docker cp finance_backend:/tmp/contracts_comparison.xlsx "F:\finance\contracts_comparison.xlsx"
if errorlevel 1 ( echo ОШИБКА: docker cp & pause & exit /b 1 )

echo.
echo ГОТОВО: F:\finance\contracts_comparison.xlsx
pause
