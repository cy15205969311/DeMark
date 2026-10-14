@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "VENV_PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "PYTHON310=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
set "PYTHON_EXE=python"

if exist "%VENV_PYTHON%" (
    set "PYTHON_EXE=%VENV_PYTHON%"
) else if exist "%PYTHON310%" (
    set "PYTHON_EXE=%PYTHON310%"
)

echo ========================================
echo DeMark setup and launch
echo ========================================
echo.

"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 (
    echo Python is not available. Install Python 3.10 or create a .venv first.
    exit /b 1
)

echo Using interpreter:
"%PYTHON_EXE%" --version
echo.

"%PYTHON_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo pip is not available for the selected interpreter.
    exit /b 1
)

echo Upgrading pip...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

echo Installing project dependencies...
"%PYTHON_EXE%" -m pip install -r "%PROJECT_ROOT%requirements.txt"
if errorlevel 1 (
    echo Dependency installation failed.
    exit /b 1
)

echo Preparing runtime directories...
if not exist "%PROJECT_ROOT%downloads" mkdir "%PROJECT_ROOT%downloads"
if not exist "%PROJECT_ROOT%logs" mkdir "%PROJECT_ROOT%logs"
if not exist "%PROJECT_ROOT%cache" mkdir "%PROJECT_ROOT%cache"
echo.

echo Launching DeMark...
"%PYTHON_EXE%" "%PROJECT_ROOT%main.py"
exit /b %ERRORLEVEL%
