@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "ALT_SITE_PACKAGES=%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.10_qbz5n2kfra8p0\LocalCache\local-packages\Python310\site-packages"
set "PYTHON_EXE="

if exist "%PROJECT_ROOT%.venv\Scripts\python.exe" set "PYTHON_EXE=%PROJECT_ROOT%.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if not defined PYTHON_EXE for /f "delims=" %%I in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%I"
    goto :python_found
)

:python_found

if not defined PYTHON_EXE (
    echo [ERROR] No usable Python was found.
    echo [TIP] Install Python 3.10 or create .venv in the project root.
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python does not exist: %PYTHON_EXE%
    exit /b 1
)

echo [1/4] Using Python: %PYTHON_EXE%

echo [2/4] Checking runtime dependencies...
"%PYTHON_EXE%" -c "import customtkinter, aiohttp, requests, selenium, PIL, bs4, lxml, undetected_chromedriver"
if errorlevel 1 (
    echo [ERROR] The selected Python environment is missing build/runtime dependencies.
    echo [TIP] Run:
    echo        "%PYTHON_EXE%" -m pip install -r requirements.txt
    exit /b 1
)

echo [3/4] Generating installer assets...
powershell -ExecutionPolicy Bypass -File "%PROJECT_ROOT%generate_installer_assets.ps1"
if errorlevel 1 (
    echo [ERROR] Failed to generate installer assets.
    exit /b 1
)

set "PYTHONPATH=%ALT_SITE_PACKAGES%;%PYTHONPATH%"

echo [4/4] Building EXE...
"%PYTHON_EXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller is not installed in the selected Python environment.
    echo [TIP] Run:
    echo        "%PYTHON_EXE%" -m pip install pyinstaller
    exit /b 1
)

pushd "%PROJECT_ROOT%"
"%PYTHON_EXE%" -m PyInstaller --clean --noconfirm DeMark.spec
set "BUILD_EXIT=%ERRORLEVEL%"
popd

if "%BUILD_EXIT%"=="0" (
    echo [DONE] EXE created: %PROJECT_ROOT%dist\DeMark\DeMark.exe
)

exit /b %BUILD_EXIT%
