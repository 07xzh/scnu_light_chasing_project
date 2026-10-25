@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem ============================================================
rem  Upload this project to GitHub
rem
rem  Usage:
rem    1. Copy this file into E:\ASL-Recognition\
rem    2. Double-click it
rem    3. Read the output, press any key when asked
rem
rem  It will:
rem    - make sure the two demo *.mp4 files are NOT uploaded
rem    - set your git identity if missing
rem    - git init / add / commit / remote / push
rem ============================================================

set "REPO=https://github.com/07xzh/scnu_light_chasing_project.git"
set "GITNAME=07xzh"
set "GITMAIL=07xzh@users.noreply.github.com"
set "BRANCH=main"

echo ============================================================
echo   GitHub upload helper
echo ============================================================
echo   Folder : %CD%
echo   Repo   : %REPO%
echo   Branch : %BRANCH%
echo ============================================================
echo.

rem ---------- 0. git installed? ----------
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git not found. Install Git for Windows first:
    echo         https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('git --version') do echo [OK] %%v
echo.

rem ---------- 1. keep the big videos out ----------
findstr /c:"*.mp4" .gitignore >nul 2>&1
if errorlevel 1 (
    echo.>> .gitignore
    echo # demo videos - too large for GitHub>> .gitignore
    echo *.mp4>> .gitignore
    echo [OK] added *.mp4 to .gitignore
) else (
    echo [OK] .gitignore already excludes *.mp4
)
echo.

rem ---------- 2. git identity ----------
set "GNAME="
for /f "delims=" %%n in ('git config user.name 2^>nul') do set "GNAME=%%n"
if not defined GNAME (
    git config --global user.name "%GITNAME%"
    echo [OK] set user.name = %GITNAME%
) else (
    echo [OK] user.name = !GNAME!
)

set "GMAIL="
for /f "delims=" %%m in ('git config user.email 2^>nul') do set "GMAIL=%%m"
if not defined GMAIL (
    git config --global user.email "%GITMAIL%"
    echo [OK] set user.email = %GITMAIL%
) else (
    echo [OK] user.email = !GMAIL!
)
echo.

rem ---------- 3. init repo ----------
if not exist ".git" (
    git init -b %BRANCH% || git init
    echo [OK] git repository initialized
) else (
    echo [OK] git repository already exists
)
echo.

rem ---------- 4. stage ----------
git add .
echo [INFO] staged files:
git status --short
echo.

git status --short | findstr /i ".mp4" >nul
if not errorlevel 1 (
    echo [WARN] mp4 files are still staged. Removing them from the index ...
    git rm --cached -q -- "*.mp4" 2>nul
    echo [OK] mp4 removed from index ^(files stay on disk^)
    echo.
)

echo Press any key to commit and push, or close this window to abort.
pause >nul
echo.

rem ---------- 5. commit ----------
git commit -m "feat: initial commit - ASL sign language recognition system"
if errorlevel 1 echo [INFO] nothing new to commit ^(or commit failed, see message above^)
echo.

rem ---------- 6. remote ----------
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    git remote add origin %REPO%
    echo [OK] remote origin added
) else (
    git remote set-url origin %REPO%
    echo [OK] remote origin updated
)
echo.

rem ---------- 7. push ----------
echo ============================================================
echo   Pushing to GitHub ...
echo   A login window may pop up. Sign in and allow access.
echo ============================================================
echo.
git push -u origin %BRANCH%

echo.
if errorlevel 1 (
    echo ============================================================
    echo [FAILED] push did not succeed.
    echo.
    echo   If the error mentions 403 / Authentication failed:
    echo     use a Personal Access Token as the password.
    echo     GitHub - Settings - Developer settings - Tokens ^(classic^)
    echo.
    echo   If it says "src refspec main does not match any":
    echo     run:  git branch -M main
    echo     then: git push -u origin main
    echo ============================================================
) else (
    echo ============================================================
    echo [DONE] Open your repo:
    echo        https://github.com/07xzh/scnu_light_chasing_project
    echo ============================================================
)
echo.
pause
