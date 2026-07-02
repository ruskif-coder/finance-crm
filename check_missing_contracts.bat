@echo off
REM check_missing_contracts.bat
REM Kontragenty s operatsiyami posle 01.01.2025 bez dogovora v BD
REM Zapuskat iz cmd (ne PowerShell)

cd /d F:\finance

echo.
echo ============================================================
echo  Kontragenty s operatsiyami 2025+ bez dogovora v BD
echo ============================================================
echo.

docker exec -i finance_db psql -U finance_user -d finance < "F:\finance\check_missing_contracts_query.sql"

echo.
echo ---- ITOG: kolichestvo kontragentov bez dogovora ----
docker exec -i finance_db psql -U finance_user -d finance -c "SELECT COUNT(DISTINCT o.counterparty_id) AS bez_dogovora FROM operations o WHERE o.date >= '2025-01-01' AND o.counterparty_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM contracts c WHERE c.counterparty_id = o.counterparty_id);"

echo.
pause
