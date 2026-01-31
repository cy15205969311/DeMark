@echo off
chcp 65001 >nul
echo ========================================
echo 运行项目测试
echo ========================================
echo.

:: 检查pytest是否安装
pip show pytest >nul 2>&1
if %errorlevel% neq 0 (
    echo 📦 安装测试依赖...
    pip install pytest pytest-asyncio
)

:: 运行测试
echo 🧪 运行基础功能测试...
python -m pytest tests/test_basic.py -v

if %errorlevel% neq 0 (
    echo ❌ 测试失败
    pause
    exit /b 1
)

echo ✅ 测试通过
pause