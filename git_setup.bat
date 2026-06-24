@echo off
REM Initializes git in F:\finance and creates the first baseline commit.
REM Run this from cmd (NOT PowerShell) on the local Windows machine.
REM Git on the cowork sandbox cannot write to this mounted drive reliably -
REM this step has to run locally.

cd /d F:\finance

git init

git config user.name >nul 2>&1
if errorlevel 1 git config user.name "Finance Admin"
git config user.email >nul 2>&1
if errorlevel 1 git config user.email "admin@finance.local"

git add .
git commit -m "Initial baseline commit"

echo.
echo Done. Repository initialized at F:\finance
git log --oneline -1
git status
pause
