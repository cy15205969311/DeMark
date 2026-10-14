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
echo Running project tests
echo ========================================
echo.

"%PYTHON_EXE%" --version
if errorlevel 1 (
    echo Python is not available.
    exit /b 1
)

"%PYTHON_EXE%" -m pip show pytest >nul 2>&1
if errorlevel 1 (
    echo Installing test dependencies...
    "%PYTHON_EXE%" -m pip install pytest pytest-asyncio
    if errorlevel 1 exit /b 1
)

echo Running baseline tests...
"%PYTHON_EXE%" -m pytest tests/test_basic.py -v
if errorlevel 1 (
    echo Tests failed.
    exit /b 1
)

echo Tests passed.
exit /b 0
