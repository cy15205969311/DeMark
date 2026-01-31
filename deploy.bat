@echo off
chcp 65001 >nul
echo ========================================
echo 多平台图片爬取工具 v2.0 - 一键部署脚本
echo 基于成功Node.js逻辑的Python实现
echo ========================================
echo.

:: 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: 未检测到Python，请先安装Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ 检测到Python环境
python --version

:: 检查pip是否可用
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: pip不可用，请检查Python安装
    pause
    exit /b 1
)

echo ✅ pip可用
echo.

:: 升级pip
echo 📦 升级pip到最新版本...
python -m pip install --upgrade pip

:: 安装依赖
echo 📦 安装项目依赖...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo ❌ 依赖安装失败，请检查网络连接或手动安装
    pause
    exit /b 1
)

echo ✅ 依赖安装完成
echo.

:: 创建必要目录
echo 📁 创建项目目录...
if not exist "downloads" mkdir downloads
if not exist "logs" mkdir logs
if not exist "cache" mkdir cache

echo ✅ 目录创建完成
echo.

:: 检查Chrome浏览器
echo 🌐 检查Chrome浏览器...
reg query "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️  警告: 未检测到Chrome浏览器
    echo    Selenium功能可能无法正常工作
    echo    建议安装Chrome浏览器: https://www.google.com/chrome/
) else (
    echo ✅ 检测到Chrome浏览器
)
echo.

:: 运行应用
echo 🚀 启动应用程序...
echo ========================================
python main.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ 应用程序运行出错
    echo 请检查日志文件: crawler.log
    pause
    exit /b 1
)

echo.
echo ✅ 应用程序正常退出
pause