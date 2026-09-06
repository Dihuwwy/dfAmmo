@echo off
setlocal

cd /d "%~dp0"
title dfAmmo Assistant Launcher

set "UV_EXE="
where uv.exe >nul 2>&1
if not errorlevel 1 set "UV_EXE=uv.exe"

if not defined UV_EXE if exist "%USERPROFILE%\scoop\shims\uv.exe" (
    set "UV_EXE=%USERPROFILE%\scoop\shims\uv.exe"
)

if defined UV_EXE (
    echo Preparing the project environment...
    "%UV_EXE%" sync --frozen
    if errorlevel 1 goto :environment_error
    goto :launch
)

if not exist ".venv\Scripts\python.exe" goto :uv_missing

echo uv was not found. Trying the existing virtual environment...
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1
if errorlevel 1 goto :uv_missing

:launch
echo Starting dfAmmo Assistant...
".venv\Scripts\python.exe" "%~dp0main.py"
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" exit /b 0

echo.
echo The application exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

:environment_error
echo.
echo Failed to prepare the Python environment from uv.lock.
echo Check the network connection and the error message above.
pause
exit /b 1

:uv_missing
echo.
echo No usable project environment was found.
echo Install uv from https://docs.astral.sh/uv/ and run this file again.
pause
exit /b 1
