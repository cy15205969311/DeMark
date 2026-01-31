#!/bin/bash

# 多平台图片爬取工具 v2.0 - 一键部署脚本 (Linux/macOS)
# 基于成功Node.js逻辑的Python实现

echo "========================================"
echo "多平台图片爬取工具 v2.0 - 一键部署脚本"
echo "基于成功Node.js逻辑的Python实现"
echo "========================================"
echo

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未检测到Python3，请先安装Python 3.8+"
    echo "Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "CentOS/RHEL: sudo yum install python3 python3-pip"
    echo "macOS: brew install python3"
    exit 1
fi

echo "✅ 检测到Python环境"
python3 --version

# 检查pip是否可用
if ! command -v pip3 &> /dev/null; then
    echo "❌ 错误: pip3不可用，请检查Python安装"
    exit 1
fi

echo "✅ pip3可用"
echo

# 升级pip
echo "📦 升级pip到最新版本..."
python3 -m pip install --upgrade pip

# 安装依赖
echo "📦 安装项目依赖..."
pip3 install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ 依赖安装失败，请检查网络连接或手动安装"
    exit 1
fi

echo "✅ 依赖安装完成"
echo

# 创建必要目录
echo "📁 创建项目目录..."
mkdir -p downloads logs cache

echo "✅ 目录创建完成"
echo

# 检查Chrome浏览器
echo "🌐 检查Chrome浏览器..."
if command -v google-chrome &> /dev/null || command -v chromium-browser &> /dev/null; then
    echo "✅ 检测到Chrome浏览器"
else
    echo "⚠️  警告: 未检测到Chrome浏览器"
    echo "   Selenium功能可能无法正常工作"
    echo "   Ubuntu/Debian: sudo apt install google-chrome-stable"
    echo "   CentOS/RHEL: sudo yum install google-chrome-stable"
    echo "   macOS: brew install --cask google-chrome"
fi
echo

# 设置权限
chmod +x deploy.sh

# 运行应用
echo "🚀 启动应用程序..."
echo "========================================"
python3 main.py

if [ $? -ne 0 ]; then
    echo
    echo "❌ 应用程序运行出错"
    echo "请检查日志文件: crawler.log"
    exit 1
fi

echo
echo "✅ 应用程序正常退出"