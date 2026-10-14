@echo off
setlocal

set "PROJECT_ROOT=%~dp0"

echo [1/2] Building desktop EXE...
call "%PROJECT_ROOT%build_exe.bat"
if errorlevel 1 exit /b %ERRORLEVEL%

echo [2/2] Building the Chinese installer...
call "%PROJECT_ROOT%build_installer.bat"
if errorlevel 1 exit /b %ERRORLEVEL%

echo [DONE] Shareable installer created in:
echo        %PROJECT_ROOT%dist\installer
exit /b 0
