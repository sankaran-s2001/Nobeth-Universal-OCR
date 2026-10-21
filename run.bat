@echo off
:: Space-safe and drive-safe change directory to the folder containing this run.bat
cd /d "%~dp0"
setlocal enabledelayedexpansion

:: ============================================================
:: NOBETH UNIVERSAL OCR - ONE-CLICK WINDOWS LAUNCHER
:: ============================================================

set "PYTHON_CMD="

:: 1. Check if local .venv already exists and has a healthy Python (fastest startup)
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[0]==3 and 10<=sys.version_info[1]<=12 else 1)" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD="%~dp0.venv\Scripts\python.exe""
        goto :launch
    )
)

:: 2. Check Python 3.11 via Python Launcher (Recommended Version)
py -3.11 -c "import sys; sys.exit(0 if sys.version_info[0]==3 and sys.version_info[1]==11 else 1)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_CMD=py -3.11"
    goto :launch
)

:: 3. Check Python 3.10 via Python Launcher (Supported)
py -3.10 -c "import sys; sys.exit(0 if sys.version_info[0]==3 and sys.version_info[1]==10 else 1)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_CMD=py -3.10"
    goto :launch
)

:: 4. Check Python 3.12 via Python Launcher (Supported)
py -3.12 -c "import sys; sys.exit(0 if sys.version_info[0]==3 and sys.version_info[1]==12 else 1)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_CMD=py -3.12"
    goto :launch
)

:: 5. Check generic py -3 launcher for supported version (3.10 to 3.12)
py -3 -c "import sys; sys.exit(0 if sys.version_info[0]==3 and 10<=sys.version_info[1]<=12 else 1)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_CMD=py -3"
    goto :launch
)

:: 6. Check system python command for supported version (3.10 to 3.12)
python -c "import sys; sys.exit(0 if sys.version_info[0]==3 and 10<=sys.version_info[1]<=12 else 1)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_CMD=python"
    goto :launch
)

:: 7. Check system python3 command for supported version (3.10 to 3.12)
python3 -c "import sys; sys.exit(0 if sys.version_info[0]==3 and 10<=sys.version_info[1]<=12 else 1)" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PYTHON_CMD=python3"
    goto :launch
)

:: Python not found
goto :no_python

:launch
:: Launch the main Python-based launcher coordinator script
%PYTHON_CMD% "%~dp0launcher.py"
set "EXIT_CODE=%ERRORLEVEL%"

if %EXIT_CODE% neq 0 (
    echo.
    echo ============================================================
    echo  Launcher finished with exit code %EXIT_CODE%.
    echo ============================================================
    pause
)

exit /b %EXIT_CODE%

:no_python
echo ============================================================
echo  NOBETH UNIVERSAL OCR ^| PYTHON REQUIRED
echo ============================================================
echo.
echo  Python was not detected on your system, or an unsupported
echo  Python version was found.
echo.
echo  Why Python is required:
echo    Nobeth Universal OCR is an AI document intelligence application
echo    built with Python, Streamlit, and the Google Gemini SDK.
echo.
echo  How to install Python:
echo    1. Download Python 3.11 [Recommended] or 3.10 - 3.12 from:
echo       https://www.python.org/downloads/
echo.
echo    2. IMPORTANT STEP during installation:
echo       Check the box "Add python.exe to PATH" at the bottom
echo       of the first installer screen.
echo.
echo    3. Complete the installation, close the installer, and then
echo       double-click run.bat again.
echo.
echo ============================================================
echo  Opening python.org download page in your default browser...
echo ============================================================
start https://www.python.org/downloads/
pause
exit /b 1
