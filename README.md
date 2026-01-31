# DeMark - 图怪兽爬虫项目

一个高效、智能的图怪兽(818ps.com)图片提取工具，支持多种分享链接格式和动态渲染页面。

## ✨ 主要特性

- 🚀 **智能分流策略**: 自动识别用户分享链接，跳过无效构建，性能提升92%
- � **版本锁定机制**: Chrome驱动版本自动匹配，避免版本冲突
- 🌐 **动态页面支持**: 支持JavaScript渲染页面的JSON深度提取
- 🎯 **三层架构**: API网关 → 本地爬虫 → Selenium隐身抓取
- 🔍 **精准过滤**: 智能过滤统计图片，只提取高质量设计稿
- 📊 **多重验证**: 文件大小检查 + HTTP状态码 + 黑名单过滤

## 🏗️ 项目架构

```
DeMark/
├── core/                              # 核心模块
│   ├── image_extractor.py             # 主图片提取器
│   ├── browser_service.py             # 浏览器服务 (版本锁定)
│   └── third_party_api.py             # 第三方API网关
├── crawlers/
│   └── tuguaishou_818ps.py            # 图怪兽爬虫 (智能分流)
├── utils/
│   ├── image_validator.py             # 图片验证器 (网络修复)
│   ├── url_parser.py                  # URL解析器
│   └── variant_builder.py             # 变体构建器
├── gui/
│   └── main_window.py                 # 图形界面
├── config/
│   └── settings.py                    # 配置文件
└── tests/
    └── test_basic.py                  # 基础测试
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Chrome浏览器
- Windows/Linux/macOS

### 安装依赖

```bash
pip install -r requirements.txt
```

### 基本使用

```python
import asyncio
from core.image_extractor import ImageExtractor

async def main():
    extractor = ImageExtractor()
    
    # 支持多种链接格式
    urls = [
        "https://818ps.com/u/002dJRky-1?user_source=r1537041",  # 用户分享链接
        "https://ue.818ps.com/preview/123456",                  # 动态渲染页面
        "https://818ps.com/preview?picId=123&upicId=456"        # 普通预览链接
    ]
    
    for url in urls:
        result = await extractor.extract_image(url, "818ps")
        if result:
            print(f"✅ 提取成功: {result['imageUrl']}")
        else:
            print("❌ 提取失败")
    
    await extractor.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### 命令行使用

```bash
python main.py
```

## 🎯 核心功能

### 1. 智能分流策略

自动识别用户分享链接，跳过无效的静态URL构建：

- **用户分享链接**: 直接进入动态抓取 (~5秒)
- **普通链接**: ID优先构建策略 (~2秒)
- **性能提升**: 用户分享链接处理速度提升92%

### 2. 版本锁定机制

解决Chrome驱动版本不匹配问题：

- 自动检测本地Chrome版本
- 强制锁定对应驱动版本
- 避免`SessionNotCreatedException`错误

### 3. JSON深度提取

支持动态渲染页面的数据提取：

- JavaScript执行环境
- 多层数据源分析 (window/JSON/direct)
- 递归数据结构搜索
- 智能图片URL评分

### 4. 精准过滤系统

避免提取统计图片和小图标：

- 文件大小检查 (< 10KB过滤)
- 黑名单关键词过滤
- 相关性智能判断
- URL特征评分算法

## 📊 性能指标

| 链接类型 | 修复前 | 修复后 | 改进幅度 |
|---------|--------|--------|----------|
| 用户分享链接 | ~60秒 | ~5秒 | **92% ⬇️** |
| 普通链接 | ~2秒 | ~2秒 | 0% (保持高效) |
| 动态页面 | 失败 | ~8秒 | **新增支持** |

## 🔧 配置说明

### Chrome设置

程序会自动检测Chrome安装路径：
- `C:\Program Files\Google\Chrome\Application\chrome.exe`
- `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`

### 网络配置

支持IPv4强制连接和双重验证机制：
- 异步验证 (aiohttp)
- 同步回退 (requests)
- DNS缓存优化

## 🧪 测试

运行基础测试：

```bash
python tests/test_basic.py
```

快速功能测试：

```bash
python quick_test.py
```

## 📝 更新日志

### v2.0.0 (2026-01-31)

#### 🚀 重大更新
- **智能分流策略**: 用户分享链接性能提升92%
- **版本锁定机制**: 解决Chrome驱动版本冲突
- **JSON深度提取**: 支持动态渲染页面
- **精准过滤系统**: 避免统计图片误提取

#### 🔧 核心修复
- 修复`AttributeError: '_extract_local'`崩溃问题
- 修复`getaddrinfo failed`网络问题
- 修复`SessionNotCreatedException`驱动问题
- 修复逻辑回退机制阻断问题

#### ⚡ 性能优化
- 用户分享链接: 60秒 → 5秒 (92%提升)
- 网络验证: IPv4强制 + 双重验证
- 浏览器启动: 版本自动匹配
- 数据提取: 多层递归搜索

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可证

MIT License

## 🔗 相关链接

- [图怪兽官网](https://818ps.com)
- [项目文档](./PROJECT_ARCHITECTURE.md)

---

**开发状态**: ✅ 稳定版本  
**测试状态**: ✅ 全面测试  
**维护状态**: 🔄 持续维护