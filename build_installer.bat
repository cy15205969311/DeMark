@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "ISCC_EXE=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if exist "%ISCC_EXE%" goto iscc_ok
echo [ERROR] Inno Setup compiler not found: %ISCC_EXE%
exit /b 1

:iscc_ok
if exist "%PROJECT_ROOT%dist\DeMark\DeMark.exe" goto exe_ok
echo [ERROR] dist\DeMark\DeMark.exe was not found. Run build_exe.bat first.
exit /b 1

:exe_ok
if exist "%PROJECT_ROOT%installer_assets\ChineseSimplified.isl" goto lang_ok
echo [ERROR] Missing Chinese language file: %PROJECT_ROOT%installer_assets\ChineseSimplified.isl
exit /b 1

:lang_ok
if exist "%PROJECT_ROOT%installer_assets\install_guide.txt" goto install_guide_ok
echo [ERROR] Missing install guide file.
exit /b 1

:install_guide_ok
if exist "%PROJECT_ROOT%installer_assets\quick_start_guide.txt" goto quick_start_ok
echo [ERROR] Missing quick start guide file.
exit /b 1

:quick_start_ok

echo [1/3] Generating installer assets...
powershell -ExecutionPolicy Bypass -File "%PROJECT_ROOT%generate_installer_assets.ps1"
if not errorlevel 1 goto assets_ok
echo [ERROR] Failed to generate installer assets.
exit /b 1

:assets_ok
echo [2/3] Compiling the Chinese installer...
pushd "%PROJECT_ROOT%"
"%ISCC_EXE%" "DeMarkInstaller.iss"
set "BUILD_EXIT=%ERRORLEVEL%"
popd

if not "%BUILD_EXIT%"=="0" goto done
echo [3/3] Installer created in: %PROJECT_ROOT%dist\installer

:done
exit /b %BUILD_EXIT%
