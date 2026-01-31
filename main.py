"""
多平台图片爬取工具 v2.0 - 基于成功Node.js逻辑
主程序入口
"""
import sys
import os
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from gui.main_window import MainWindow
from config.settings import Settings

def setup_logging():
    """设置日志系统"""
    logging.basicConfig(
        level=getattr(logging, Settings.LOG_LEVEL),
        format=Settings.LOG_FORMAT,
        handlers=[
            logging.FileHandler(Settings.LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def create_directories():
    """创建必要的目录"""
    directories = [
        Settings.DOWNLOAD_PATH,
        'logs',
        'cache'
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)

def main():
    """主函数"""
    try:
        # 设置日志
        setup_logging()
        
        # 创建必要目录
        create_directories()
        
        logging.info("🚀 启动多平台图片爬取工具 v2.0")
        logging.info("📋 基于成功Node.js逻辑的Python实现")
        
        # 启动GUI应用
        app = MainWindow()
        app.run()
        
    except Exception as e:
        logging.error(f"❌ 应用启动失败: {e}")
        print(f"启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()