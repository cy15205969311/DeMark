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

"%PYTHON_EXE%" "%PROJECT_ROOT%main.py" %*
exit /b %ERRORLEVEL%
