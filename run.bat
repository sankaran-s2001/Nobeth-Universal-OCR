@echo off
:: Space-safe and drive-safe change directory to the folder containing this run.bat
cd /d "%~dp0"
setlocal enabledelayedexpansion

:: Attempt to locate the best compatible Python version in the prioritized order
set "PYTHON_EXE="

:: 1. Check Python 3.11 (Fully Supported version)
py -3.11 -c "import sys; sys.exit(0)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_EXE=py -3.11"
    goto :found
)

:: 2. Check Python 3.10 (Supported version)
py -3.10 -c "import sys; sys.exit(0)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_EXE=py -3.10"
    goto :found
)

:: 3. Check Python 3.12 (Supported version)
py -3.12 -c "import sys; sys.exit(0)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_EXE=py -3.12"
    goto :found
)

:: 4. Check Python 3.13 (Supported version)
py -3.13 -c "import sys; sys.exit(0)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_EXE=py -3.13"
    goto :found
)

:: 5. Check generic py -3 launcher
py -3 -c "import sys; sys.exit(0)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_EXE=py -3"
    goto :found
)

:: 6. Check system python command
python -c "import sys; sys.exit(0)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_EXE=python"
    goto :found
)

:found
if not defined PYTHON_EXE (
    echo ==================================================
    echo STARTUP FAILED
    echo ==============
    echo.
    echo Python was not found on your system.
    echo Nobeth Universal OCR requires Python 3.10 or newer.
    echo.
    echo Please install Python 3.10+ from:
    echo https://www.python.org/downloads/
    echo.
    echo Then run run.bat again.
    echo ==================================================
    pause
    exit /b 1
)

:: Launch the main Python-based launcher coordinator script
%PYTHON_EXE% "%~dp0launcher.py"

exit /b %ERRORLEVEL%
