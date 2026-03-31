# DeMark

DeMark 是一个面向设计稿分享链接提取与下载的 Python 工具，提供 GUI 界面和可复用的提取核心，当前仓库重点支持以下平台：

- 818ps / 图怪兽
- Canva / 可画
- Chuangkit / 创客贴
- Gaoding / 稿定设计

项目目标是尽可能稳定地从分享链接中提取真实设计稿预览图，并在识别到多页设计稿时输出整套图片结果，便于本地下载、二次开发和后续自动化处理。

## 当前能力

- 支持分享文本中的 URL 清洗、短链解析与平台识别
- 支持 818ps / 图怪兽多页设计稿提取与批量下载
- 支持创客贴多页设计稿提取
- 支持 Canva 基础提取流程
- 支持稿定设计分享链接识别、候选原图优选与无水印直链清洗
- 支持静态源码提取、动态浏览器抓取、资源监听与结果归一化
- 统一输出单图 / 套图结构，方便 GUI 和脚本复用

## 提取流程概览

主调度入口在 [core/image_extractor.py](./core/image_extractor.py)，整体流程如下：

1. 解析分享链接，清理输入文本中的 URL，并识别平台。
2. 优先尝试第三方网关或平台可用的轻量接口。
3. 回退到平台专用提取器，执行静态源码分析、候选图筛选与本地构造。
4. 必要时启动浏览器动态抓取，采集页面资源、主画布快照与逐页结果。
5. 将结果统一归一化为 `imageUrl`、`imageUrls`、`pages`、`pageCount` 等字段。

## 多页提取说明

### 818ps / 图怪兽

- 优先使用分享接口与页面参数直连
- 失败后回退到动态页抓取、滚动采样和逐页激活
- 对水印图、素材图、SVG 小图、文字贴纸等干扰资源进行过滤

详细说明见 [818ps套图提取逻辑说明.md](./818ps套图提取逻辑说明.md)。

### 创客贴

- 优先提取页面预加载的 `render_result` 设计稿资源
- 如果仅拿到首张结果，再结合浏览器内资源快照和分页激活补齐整套设计稿
- 对左侧推荐模板、装饰资源和非主画布图片进行降权过滤

创客贴套图逻辑核心位于 [crawlers/chuangkit_crawler.py](./crawlers/chuangkit_crawler.py)。

### Canva

- 维持现有多源融合提取逻辑
- 当前本次更新未改动 Canva 专用提取代码

### Gaoding / 稿定设计

- 支持 `gaoding.com` / `gaoding.cn` 分享链接识别，并自动清理 `#我分享了...` 这类分享文案 fragment
- 优先从静态 HTML、内嵌 JSON 和浏览器动态快照中提取设计稿候选图
- 单图候选评分优先 `source_preview_info`、`original_url`、`export_url`、`download_url` 等更接近原图的字段
- 自动过滤图标、推荐位、侧边栏资源以及明显疑似带水印的预览图
- 对稿定 / `dancf.com` 图片链接自动移除 `x-oss-process`，避免残缺 OSS 处理参数导致打开失败
- 统一补充稿定图片校验所需的 `Referer` / `Origin` 防盗链请求头

## 输出结构

提取结果会统一规范为如下结构：

```json
{
  "imageUrl": "https://example.com/page1.jpg",
  "imageUrls": [
    "https://example.com/page1.jpg",
    "https://example.com/page2.jpg"
  ],
  "pages": [
    { "page": 1, "imageUrl": "https://example.com/page1.jpg" },
    { "page": 2, "imageUrl": "https://example.com/page2.jpg" }
  ],
  "pageCount": 2,
  "isMultiPage": true,
  "platform": "Chuangkit",
  "source": "dynamic-resource-pages"
}
```

字段含义：

- `imageUrl`：兼容旧逻辑的首张图
- `imageUrls`：完整套图 URL 列表
- `pages`：页码与图片 URL 的对应关系
- `pageCount`：识别到的页面数量
- `isMultiPage`：是否为多页设计稿
- `source`：当前结果命中的提取来源

## 快速开始

### 环境要求

- Python 3.8+
- 已安装 Chrome 浏览器
- Windows 环境下已做更多实际验证

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动图形界面

```bash
python main.py
```

### 脚本调用示例

```python
import asyncio
from core.image_extractor import ImageExtractor


async def main():
    extractor = ImageExtractor()
    result = await extractor.extract_image(
        "https://www.chuangkit.com/sharedesign?d=26205704-ac51-4516-94ee-104ac29b6c96",
        "Chuangkit",
    )

    print("platform:", result.get("platform"))
    print("source:", result.get("source"))
    print("pageCount:", result.get("pageCount"))

    for item in result.get("pages", []):
        print(item["page"], item["imageUrl"])

    await extractor.close()


if __name__ == "__main__":
    asyncio.run(main())
```

## 项目结构

```text
DeMark/
├── core/                        核心调度、浏览器服务、结果归一化
├── crawlers/                    平台专用提取器
├── gui/                         图形界面
├── tests/                       测试用例
├── utils/                       URL 解析、验证、下载等公共能力
├── 818ps套图提取逻辑说明.md      818ps / 图怪兽套图实现说明
├── main.py                      GUI 启动入口
└── README.md
```

## 关键模块

- [core/image_extractor.py](./core/image_extractor.py)：总入口与多阶段调度
- [core/browser_service.py](./core/browser_service.py)：浏览器抓取、动态资源采样与驱动管理
- [crawlers/tuguaishou_818ps.py](./crawlers/tuguaishou_818ps.py)：818ps / 图怪兽提取逻辑
- [crawlers/chuangkit_crawler.py](./crawlers/chuangkit_crawler.py)：创客贴提取与套图识别逻辑
- [crawlers/canva_crawler.py](./crawlers/canva_crawler.py)：Canva 提取逻辑
- [crawlers/gaoding_crawler.py](./crawlers/gaoding_crawler.py)：稿定设计候选图提取、排序与 URL 清洗逻辑
- [utils/url_parser.py](./utils/url_parser.py)：分享链接清洗、平台识别与稿定 fragment 清理
- [utils/image_validator.py](./utils/image_validator.py)：图片有效性校验与跨平台防盗链请求头
- [utils/downloader.py](./utils/downloader.py)：单图与整套下载

## 测试

建议优先运行以下测试：

```bash
pytest tests/test_basic.py
pytest tests/test_chuangkit.py
pytest tests/test_gaoding.py -q
```

如果本机没有安装 `pytest`，也可以先使用：

```bash
pip install pytest
```

如果本机有多个 Python 版本，建议显式使用当前项目依赖所在的解释器，例如：

```bash
python -m pytest tests/test_gaoding.py -q
```

## 开发与调试

### 稿定相关文件

- [core/image_extractor.py](./core/image_extractor.py)：把稿定接入统一调度入口
- [crawlers/gaoding_crawler.py](./crawlers/gaoding_crawler.py)：稿定静态 / 动态提取主逻辑
- [tests/test_gaoding.py](./tests/test_gaoding.py)：稿定 URL 清洗、候选排序和多页结果回归测试

### 稿定问题排查建议

- 如果提取结果能通过校验但浏览器打开报 OSS 参数错误，优先检查是否带有残缺的 `x-oss-process`
- 如果返回的是带分享文案的链接，优先检查 `utils/url_parser.py` 是否已去掉 `#我分享了...` 这类 fragment
- 如果命中了错误封面图或带水印图，优先查看 `crawlers/gaoding_crawler.py` 中 `_score_candidate()` 的字段权重
- 如果图片请求 403 或 404，优先检查 `utils/image_validator.py` 的防盗链请求头与 `auth_key` 是否过期

### 推荐验证流程

1. 先运行 `python -m pytest tests/test_gaoding.py -q`，确认 URL 清洗和候选排序没有回退。
2. 再用 GUI 或脚本输入真实稿定分享链接，检查 `processed_url`、最终 `imageUrl` 和下载结果。
3. 如果日志出现 `preview_info.url`、`source_preview_info.url`、`export_url` 等字段，可结合日志判断当前命中的候选来源是否合理。

## 注意事项

- 动态抓取依赖本机 Chrome 浏览器。
- 某些平台分享页是 SPA 或强动态渲染页面，静态 HTML 中拿不到设计稿属于正常情况。
- 多页提取的关键不是“抓到所有图片”，而是“筛出真正的设计稿主画布结果”。
- 浏览器抓取结果会受到页面登录态、资源过期时间和平台前端改版影响。

## License

MIT License
