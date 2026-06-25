@echo off
REM Full backup: DB dump + zip archive of the whole project (incl. .env) + git commit
REM of the current code state. Run from cmd (NOT PowerShell) on the local Windows
REM machine, same as the other deploy/rotate scripts in this folder.

set BACKUPDIR=F:\finance\backups
set LOG=%BACKUPDIR%\backup_all_log.txt
set DUMP=%BACKUPDIR%\backup_full_2026-06-25.sql
set ZIP=%BACKUPDIR%\backup_full_2026-06-25.zip

if not exist "%BACKUPDIR%" mkdir "%BACKUPDIR%"

echo ===== BACKUP START %DATE% %TIME% ===== > "%LOG%"

echo [1/4] Dumping database to %DUMP% ... >> "%LOG%"
docker exec -t finance_db pg_dump -U finance_user finance > "%DUMP%" 2>>"%LOG%"

echo [2/4] Compressing F:\finance (excluding backups folder) into %ZIP% ... >> "%LOG%"
powershell -NoProfile -Command "Get-ChildItem -Path 'F:\finance' -Exclude 'backups' | Compress-Archive -DestinationPath '%ZIP%' -Force" >> "%LOG%" 2>&1

echo [3/4] Committing current code state to git (secrets in .env stay out via .gitignore)... >> "%LOG%"
cd /d F:\finance
git add -A >> "%LOG%" 2>&1
git commit -m "Backup snapshot 2026-06-25" >> "%LOG%" 2>&1

echo [4/4] Verifying backups folder contents... >> "%LOG%"
dir "%BACKUPDIR%" >> "%LOG%" 2>&1

echo ===== BACKUP DONE %DATE% %TIME% ===== >> "%LOG%"
echo BACKUP_FINISHED_MARKER >> "%LOG%"

echo Done. Check %LOG% for details.
echo  - DB dump:  %DUMP%
echo  - Zip (includes .env with live secrets - store/share securely): %ZIP%
echo  - Git commit: run "git log -1" to confirm
pause
