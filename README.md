# DeMark

DeMark 是一个面向设计稿分享链接提取与下载的 Python 桌面工具，提供 GUI 界面和可复用的提取核心。项目的目标不是通用网页爬虫，而是围绕设计平台分享页、预览页和公开接口，尽可能稳定地提取设计稿主画布结果，并把结果整理成统一的可下载结构。

当前仓库重点支持以下平台：

- 818ps / 图怪兽
- Canva / 可画
- Chuangkit / 创客贴
- Gaoding / 稿定设计
- Huaban / 花瓣

项目的核心价值在于：

- 把混杂在分享文案中的 URL 清洗成可处理链接
- 按平台走更合适的提取路径，而不是只靠一种通用抓取方式
- 对单图、多页设计稿、公开预览图、受限结果给出不同语义
- 统一输出 `imageUrl / imageUrls / pages / pageCount` 结构，便于 GUI 和脚本复用

## 目录

- [适用场景](#适用场景)
- [当前能力](#当前能力)
- [整体架构](#整体架构)
- [提取流程](#提取流程)
- [平台支持说明](#平台支持说明)
- [结果结构](#结果结构)
- [运行环境](#运行环境)
- [快速开始](#快速开始)
- [脚本调用示例](#脚本调用示例)
- [项目结构](#项目结构)
- [核心模块说明](#核心模块说明)
- [配置说明](#配置说明)
- [测试与验证](#测试与验证)
- [开发指南](#开发指南)
- [调试与排障](#调试与排障)
- [限制与注意事项](#限制与注意事项)
- [相关文档](#相关文档)
- [License](#license)

## 适用场景

这个项目更适合下面几类场景：

- 你拿到的是图怪兽、创客贴、稿定等平台的分享链接，希望提取设计稿预览图
- 你需要识别多页设计稿，并按页输出整套图片结果
- 你需要一个可嵌入自己脚本或业务流程的统一提取入口
- 你希望在桌面 GUI 中直接粘贴链接、查看结果、预览和下载
- 你需要区分“公开可下载结果”和“仅公开预览图结果”，避免把受限素材误判成无水印成功

它不适合：

- 作为任意网站的通用大规模爬虫
- 获取平台未公开暴露的受限原素材
- 绕过平台权限、登录态或授权限制

## 当前能力

### 已实现能力

- 支持分享文本中的 URL 清洗、平台识别和部分短链解析
- 支持单图和多页设计稿结果的统一输出
- 支持 818ps / 图怪兽多页设计稿提取与整套下载
- 支持创客贴多页设计稿提取与推荐模板干扰过滤
- 支持 Canva 基础提取流程
- 支持稿定设计分享链接识别、候选原图优选、套图提取和 URL 清洗
- 支持花瓣 `pin / board / discovery` 公开接口提取
- 支持花瓣公开预览图下载与 `preview_image / preview_only` 状态区分
- 支持图片 URL 有效性校验和跨平台防盗链请求头
- 支持 GUI 结果卡片展示、复制链接、预览、单图下载和批量下载

### 当前重点边界

- 结果“成功”并不等于拿到了平台无水印原素材
- 某些平台返回的是公开预览图，系统会以警告态而不是普通成功呈现
- 动态抓取依赖本机 Chrome 浏览器和页面可访问性
- 平台改版、资源过期、防盗链策略变化都可能影响提取成功率

## 整体架构

DeMark 采用“统一调度 + 平台专用提取器 + 公共能力模块”的结构：

```text
用户输入 URL
  ↓
utils/url_parser.py
  ↓
core/image_extractor.py
  ↓
第三方网关 / 平台专用提取器 / 浏览器动态抓取
  ↓
utils/image_validator.py
  ↓
统一结果结构
  ↓
gui/main_window.py 或脚本调用
  ↓
utils/downloader.py
```

### 架构分层

#### 1. 入口层

- `main.py`
- `gui/main_window.py`

负责应用启动、运行时检查、GUI 初始化、结果展示和用户交互。

#### 2. 调度层

- `core/image_extractor.py`

负责串联 URL 解析、第三方网关、本地平台提取器、动态浏览器抓取，以及最终结果归一化。

#### 3. 平台层

- `crawlers/tuguaishou_818ps.py`
- `crawlers/canva_crawler.py`
- `crawlers/chuangkit_crawler.py`
- `crawlers/gaoding_crawler.py`
- `crawlers/huaban_crawler.py`

每个平台尽量把“链接结构、页面结构、候选图筛选、分页策略、预览图边界”封装在自己的爬虫里。

#### 4. 公共能力层

- `utils/url_parser.py`
- `utils/image_validator.py`
- `utils/downloader.py`
- `utils/variant_builder.py`

这些模块对所有平台共享，负责 URL 清洗、图片校验、防盗链下载和结果变体构造。

#### 5. 测试层

- `tests/test_basic.py`
- `tests/test_chuangkit.py`
- `tests/test_gaoding.py`
- `tests/test_huaban.py`

用于验证 URL 解析、平台提取器核心逻辑和回归行为。

## 提取流程

主调度入口位于 [core/image_extractor.py](./core/image_extractor.py)。整体流程可以概括为三阶段：

### 阶段 0：URL 清洗与平台识别

由 [utils/url_parser.py](./utils/url_parser.py) 负责：

- 从整段分享文案中抽出第一个有效 URL
- 移除 fragment 和无关文本
- 识别目标平台
- 为部分平台预提取关键参数

### 阶段 1：第三方 API 或轻量入口

由 [core/image_extractor.py](./core/image_extractor.py) 调度：

- 对大多数平台优先尝试第三方 API 网关
- 对花瓣显式跳过第三方网关，直接走官方公开接口
- 若接口结果存在 `imageUrl`，先经过图片有效性校验，再返回

### 阶段 2：本地平台专用提取器

由 `core/image_extractor.py -> crawlers/*.py` 调度：

- 对应平台走自己的静态提取和结果组装逻辑
- 对候选图进行排序、去重、过滤和分页补齐
- 输出标准结构或警告态结构

### 阶段 3：动态浏览器抓取

当静态提取失败时，会尝试 [core/browser_service.py](./core/browser_service.py) 提供的 Selenium 路径：

- 采集页面中的候选图片资源
- 结合 URL 规则、资源大小和关键词做评分
- 选择更可能是主画布结果的图片

### 结果归一化

无论结果来自哪条路径，最终都会尽可能归一化为：

- `imageUrl`
- `imageUrls`
- `pages`
- `pageCount`
- `isMultiPage`
- `platform`
- `source`

这样 GUI 和脚本层可以不关心底层是 API、静态提取还是 Selenium 抓取。

## 平台支持说明

### 818ps / 图怪兽

当前策略：

- 优先利用分享页参数和官方分享 API 构建结果
- 遇到 `818ps.com/u/...` 分享壳页时，先保留壳页入口，再用本地浏览器解析最终编辑器地址
- 分享 API 返回预览图后，会优先尝试 818ps URL 变体，尽量升级到无 `!l1000_b` 的去水印版本
- 当分享预览只返回 `_1/_2/_3` 这类后缀页图、但接口元数据表明还有首页时，会自动补齐无后缀第一页
- 失败后回退到动态页抓取、滚动采样与逐页激活
- 对水印图、元素素材、SVG、小图标和装饰资源做过滤

适合处理：

- 单页设计稿
- 多页设计稿
- 预览页或带参数的分享链接

详细设计说明见 [818ps套图提取逻辑说明.md](./818ps套图提取逻辑说明.md)。

### Canva / 可画

当前策略：

- 保留已有多源融合提取路径
- 作为统一调度体系中的一个平台分支

当前仓库中，Canva 相关逻辑已经接入，但文档深度和专项测试覆盖不如图怪兽、稿定和花瓣完整。

### Chuangkit / 创客贴

当前策略：

- 优先提取页面预加载的设计稿结果
- 对推荐模板和非主画布资源降权
- 如果只拿到首图，再结合资源快照和分页逻辑补齐套图

适合处理：

- `sharedesign` 分享链接
- 创客贴公开预览页链接

### Gaoding / 稿定设计

当前策略：

- 支持 `gaoding.com` / `gaoding.cn` 链接识别
- 自动清理 `#我分享了...` 这类 fragment
- 从静态 HTML、内嵌 JSON、动态快照中提取候选图
- 优先识别 `preview_info`、`source_preview_info`、`extends_previews`
- 对候选图做排序并尽量靠近主画布原图
- 清理 `x-oss-process` 之类可能导致资源访问失败的 URL 参数

适合处理：

- 稿定分享页
- 部分模板页
- 多页设计稿结果

详细设计说明见 [稿定设计提取逻辑说明.md](./稿定设计提取逻辑说明.md)。

### Huaban / 花瓣

当前策略：

- 支持 `huaban.com` / `api.huaban.com` / `huabanimg.com` 识别
- 优先使用花瓣公开 JSON 接口
- 支持 `pin / board / discovery`
- 将 `file.key` 统一规范到 `https://hbimg.huabanimg.com/{key}`
- 对公开预览图结果返回 `preview_image`
- 对更受限结果返回 `preview_only`

这部分逻辑的重点不是“获取无水印原素材”，而是：

- 稳定提取公开可访问结果
- 清楚区分普通成功、公开预览图和受限结果
- 在 GUI 中向用户明确告知风险

详细设计说明见 [花瓣素材提取逻辑说明.md](./花瓣素材提取逻辑说明.md)。

## 结果结构

提取结果会尽量统一为如下结构：

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
  "source": "dynamic-resource-pages",
  "original_url": "https://example.com/share-link",
  "processed_url": "https://example.com/share-link"
}
```

### 常见字段说明

- `imageUrl`：首张图片 URL，兼容旧逻辑
- `imageUrls`：完整图片 URL 列表
- `pages`：按页组织的结果
- `pageCount`：识别到的页数
- `isMultiPage`：是否为多页设计稿
- `platform`：当前平台
- `source`：结果命中的提取来源
- `original_url`：用户输入的原始链接
- `processed_url`：经过 URL 解析器清洗后的链接

### 花瓣警告态结果

花瓣相关结果还可能返回：

```json
{
  "status": "preview_image",
  "warningText": "已提取公开预览图，可直接下载，但可能包含平台水印，未获取到无水印原素材",
  "imageUrl": "https://hbimg.huabanimg.com/xxx",
  "platform": "Huaban"
}
```

或：

```json
{
  "status": "preview_only",
  "warningText": "公开接口仅提供带水印预览图，未返回无水印原素材下载地址",
  "platform": "Huaban"
}
```

这两种状态不应被理解为“彻底失败”，而应理解为“公开访问能力受限”。

## 运行环境

### Python 版本

当前项目：

- 最低支持 `Python 3.8`
- `Python 3.8 ~ 3.11` 为当前主代码明确测试区间

[main.py](./main.py) 中带有运行时检查逻辑：

- 如果当前 Python 版本不在测试范围内，或缺少关键依赖
- 程序会尝试寻找更合适的解释器并重启
- 如果找不到可用运行时，会给出明确错误提示

### 操作系统

- Windows 环境下验证更多
- 其他系统理论上可运行，但动态抓取、打包与浏览器行为仍需自行验证

### 浏览器要求

- 动态抓取路径依赖本机 Chrome 浏览器
- 如果完全不触发 Selenium 回退，部分静态接口提取路径可独立工作

### 依赖概览

核心依赖见 [requirements.txt](./requirements.txt)，主要包括：

- `customtkinter`
- `aiohttp`
- `requests`
- `beautifulsoup4`
- `lxml`
- `selenium`
- `undetected-chromedriver`
- `Pillow`
- `diskcache`
- `sqlalchemy`
- `pytest`
- `pytest-asyncio`

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/cy15205969311/DeMark.git
cd DeMark
```

### 2. 安装依赖

推荐：

```bash
python -m pip install -r requirements.txt
```

如果你使用虚拟环境，也可以：

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

### 3. 启动 GUI

```bash
python main.py
```

### 4. 首次运行时会自动创建的目录

应用启动时会自动创建：

- `downloads/`
- `logs/`
- `cache/`

日志默认写入：

- `crawler.log`

## 脚本调用示例

### 异步调用主提取器

```python
import asyncio
from core.image_extractor import ImageExtractor


async def main():
    extractor = ImageExtractor()
    try:
        result = await extractor.extract_image(
            "https://www.chuangkit.com/sharedesign?d=26205704-ac51-4516-94ee-104ac29b6c96",
            "Chuangkit",
        )

        print("platform:", result.get("platform"))
        print("source:", result.get("source"))
        print("pageCount:", result.get("pageCount"))
        print("imageUrl:", result.get("imageUrl"))

        for page in result.get("pages", []):
            print(page["page"], page["imageUrl"])
    finally:
        await extractor.close()


if __name__ == "__main__":
    asyncio.run(main())
```

### 平台参数说明

`extract_image(url, platform)` 中：

- `platform="auto"` 表示自动识别
- 也可以显式传：
  - `818ps`
  - `Canva`
  - `Chuangkit`
  - `Gaoding`
  - `Huaban`

### 可编辑安装

如果你希望作为开发模式使用，也可以：

```bash
python -m pip install -e .
```

根据 [setup.py](./setup.py)，这会注册控制台入口：

```bash
watermark-remover
```

## 项目结构

```text
DeMark/
├── config/
│   └── settings.py                    全局配置
├── core/
│   ├── browser_service.py             浏览器动态抓取服务
│   ├── image_extractor.py             主调度入口
│   └── third_party_api.py             第三方 API 网关
├── crawlers/
│   ├── tuguaishou_818ps.py            图怪兽 / 818ps 提取器
│   ├── canva_crawler.py               Canva 提取器
│   ├── chuangkit_crawler.py           创客贴提取器
│   ├── gaoding_crawler.py             稿定设计提取器
│   └── huaban_crawler.py              花瓣提取器
├── gui/
│   └── main_window.py                 桌面 GUI 主窗口
├── tests/
│   ├── test_basic.py                  基础与公共行为测试
│   ├── test_chuangkit.py              创客贴测试
│   ├── test_gaoding.py                稿定测试
│   └── test_huaban.py                 花瓣测试
├── utils/
│   ├── downloader.py                  下载器
│   ├── image_validator.py             图片有效性校验
│   ├── url_parser.py                  分享链接解析
│   └── variant_builder.py             结果变体构建
├── 818ps套图提取逻辑说明.md          图怪兽专项说明
├── 稿定设计提取逻辑说明.md            稿定专项说明
├── 花瓣素材提取逻辑说明.md            花瓣专项说明
├── main.py                            GUI 启动入口
├── requirements.txt                   依赖列表
├── setup.py                           包安装入口
├── deploy.bat                         Windows 部署脚本
├── deploy.sh                          Linux/macOS 部署脚本
└── README.md
```

## 核心模块说明

### `main.py`

职责：

- 检查 Python 运行时和关键依赖
- 在必要时尝试切换到更合适的解释器
- 初始化日志和运行目录
- 启动 GUI 主窗口

### `core/image_extractor.py`

职责：

- 统一提取入口
- 协调 URL 解析、第三方网关、本地提取器和动态抓取
- 对结果做归一化

这是你理解整个项目的第一优先级入口文件。

### `core/browser_service.py`

职责：

- 承担 Selenium / 浏览器隐身抓取路径
- 处理浏览器检查、页面图片采集和资源评分

### `core/third_party_api.py`

职责：

- 管理第三方 API 调用与缓存命中
- 作为“更轻量的优先路径”参与调度

### `utils/url_parser.py`

职责：

- 清理分享文案中的 URL
- 识别平台
- 为部分平台做专用 URL 清洗

### `utils/image_validator.py`

职责：

- 验证图片 URL 是否真实可访问
- 对不同平台补充 `Referer / Origin` 等防盗链请求头
- 用快速 HEAD / Range GET 策略提高验证效率

### `utils/downloader.py`

职责：

- 下载单图或批量图片
- 根据平台补充下载请求头
- 在 URL 不带扩展名时按 `Content-Type` 修正文件后缀

### `gui/main_window.py`

职责：

- 提供桌面端交互界面
- 管理输入框、平台切换、日志面板、结果卡片、下载操作和状态栏

## 配置说明

配置集中在 [config/settings.py](./config/settings.py)。

### 网络与超时

- `REQUEST_TIMEOUT`
- `MAX_RETRIES`
- `CONCURRENT_REQUESTS`

### 下载相关

- `DOWNLOAD_PATH`
- `THUMBNAIL_SIZE`
- `MAX_FILE_SIZE`

### 缓存相关

- `CACHE_TTL`
- `CACHE_MAX_SIZE`

### Selenium 相关

- `SELENIUM_TIMEOUT`
- `SELENIUM_IMPLICIT_WAIT`
- `SELENIUM_PAGE_LOAD_TIMEOUT`
- `CHROME_OPTIONS`

### 日志相关

- `LOG_LEVEL`
- `LOG_FORMAT`
- `LOG_FILE`

### 第三方 API 相关环境变量

当前配置文件中保留了第三方 API 网关配置位，建议用环境变量注入敏感配置：

- `TSGPT_TOKEN`
- `RAPIDAPI_KEY`

如果你要切换网关、禁用某个第三方服务，优先修改 [config/settings.py](./config/settings.py)。

## 测试与验证

### 推荐运行方式

```bash
python -m pytest tests/test_basic.py
python -m pytest tests/test_chuangkit.py
python -m pytest tests/test_gaoding.py -q
python -m pytest tests/test_huaban.py -q
```

### 当前测试重点

- URL 解析与平台识别
- 创客贴多页结果构建
- 稿定 URL 清洗、候选排序与多页提取
- 花瓣 `pin / board / discovery` 分类
- 花瓣公开预览图状态与防盗链请求头
- 下载器扩展名修正行为

### GUI 验证建议

除了跑 pytest，建议实际做一轮 GUI 冒烟测试：

1. 启动 `python main.py`
2. 分别输入图怪兽、创客贴、稿定、花瓣链接
3. 检查结果卡片是否正确区分：
   - 普通成功
   - 多页结果
   - 警告态结果
   - 失败态结果
4. 检查单图下载、整套下载和原页跳转是否正常

## 开发指南

### 本地开发建议流程

1. 先用真实链接复现问题。
2. 查看 `crawler.log` 和 GUI 日志区域。
3. 定位到对应平台爬虫。
4. 优先修平台专用逻辑，不要轻易污染公共模块。
5. 为修复补上 pytest 回归。
6. 再用 GUI 做一轮实际验证。

### 修改原则

- 平台特有逻辑尽量留在 `crawlers/*.py`
- 公共能力问题再修改 `utils/*`
- 不要把“平台预览图”误写成“无水印原图”
- 不要把 GUI 文案写得比实际能力更激进
- 修改结果结构时，先确认不会破坏 GUI 和下载器的兼容字段

### 818ps / 图怪兽开发建议

- 优先区分 `818ps.com/u/...` 分享壳页和已经带 `share_id` 的编辑器地址，这两条链路不要混在一起处理
- `/u/` 壳页拿不到 `share_id` 时，优先用浏览器解析最终地址，再走 `_extract_from_share_api()`，不要先把它当短链跳转页处理
- 官方分享 API 返回的 `user_preview_ue` 结果要继续走 818ps 变体校验，避免直接把 `!l1000_b` 预览图当成最终结果
- 如果 `page_map` / `pageInfo` 表示是 4 页，但预览只拿到 `_1/_2/_3`，优先检查是否需要补无后缀首页
- 分享 API 命中部分页时，不要立刻判死；先比较 `share_template`、`get_template_page_data`、`team_share_get_templ` 哪组更完整
- 修改 818ps 逻辑后，至少回归真实 `/u/` 分享页、带 `share_id` 的编辑器地址，以及多页缺首页预览这三类样例

### 新增平台时的建议步骤

1. 在 `utils/url_parser.py` 增加平台识别和必要的 URL 清洗。
2. 在 `crawlers/` 下新增平台提取器。
3. 在 `core/image_extractor.py` 注册并接入调度。
4. 在 `utils/image_validator.py` / `utils/downloader.py` 补充目标域名的请求头。
5. 在 GUI 平台选择与自动识别中加入新平台。
6. 增加对应测试文件和至少一个真实边界案例。

### 代码阅读顺序建议

如果你第一次接手这个项目，推荐按下面顺序阅读：

1. [main.py](./main.py)
2. [core/image_extractor.py](./core/image_extractor.py)
3. [utils/url_parser.py](./utils/url_parser.py)
4. [utils/image_validator.py](./utils/image_validator.py)
5. 对应平台的 `crawlers/*.py`
6. [gui/main_window.py](./gui/main_window.py)
7. 对应平台测试

## 调试与排障

### 通用排障思路

1. 先确认输入 URL 是否已经被 `URLParser` 清洗正确。
2. 再确认平台识别是否正确。
3. 查看是卡在第三方网关、本地提取器还是 Selenium 回退。
4. 检查图片 URL 是否通过 `ImageValidator`。
5. 最后再检查下载阶段和 GUI 呈现阶段。

### 稿定问题排查建议

- 如果提取结果通过校验，但浏览器打开时报 OSS 参数错误，优先检查是否带了残缺的 `x-oss-process`
- 如果返回的是带分享文案的链接，优先检查 `utils/url_parser.py` 是否去掉了 `#我分享了...`
- 如果稿定分享页仍然只返回单图，优先检查 `extends_previews` 和相关 HTML 提取逻辑
- 如果命中了错误封面图或疑似水印图，优先检查 `GaodingCrawler` 的候选评分逻辑
- 如果图片请求 403 或 404，优先检查防盗链请求头和签名 URL 是否过期

### 818ps / 图怪兽问题排查建议

- 如果日志显示能提取但仍然有水印，优先检查 `_extract_from_share_api()` 后是否继续走了 818ps 变体校验，而不是直接返回 `!l1000_b` 预览图
- 如果日志显示 `expected=4` 但只下载到 3 张，优先检查 `team_share_get_templ.preview` 是否只给了 `_1/_2/_3`，以及首页补全逻辑是否生效
- 如果 `/u/` 分享页没有进入官方分享 API，优先检查浏览器解析最终地址阶段是否拿到了 `share_id / share_uid / upicId`
- 如果动态抓取拿到很多图但页图不对，优先检查 818ps 的候选过滤是否把 `ips_svg / ips_group_word / editor/` 等素材资源排掉了
- 如果分享 API 在多个 payload 都有结果，优先比较 `share_template` 与 `team_share_get_templ` 的页数完整性，而不是只看谁先返回

### 花瓣问题排查建议

- 如果日志里显示 `preview_image`，说明当前拿到的是公开预览图，而不是无水印原素材
- 如果日志里显示 `preview_only`，说明连公开预览图都没有稳定通过校验
- 如果花瓣图片校验失败，优先检查 `utils/image_validator.py` 和 `utils/downloader.py` 中的花瓣请求头
- 如果 `board` 或 `discovery` 结果数量异常，优先检查 `limit` 转发和 pin 列表筛选逻辑

### GUI 无结果但没有报错

优先检查：

- URL 是否为空或格式不完整
- 平台自动识别是否误判
- 本地 Chrome 是否可用
- 页面是否要求登录才能渲染主画布

### 下载失败

优先检查：

- 下载目录是否可写
- 图片 URL 是否仍然有效
- URL 是否没有后缀且 `Content-Type` 异常
- 对应平台的 `Referer / Origin` 是否正确

## 限制与注意事项

- 动态抓取依赖本机 Chrome 浏览器
- 某些分享页是 SPA 或强动态渲染页面，静态 HTML 中拿不到设计稿属于正常情况
- 多页提取的关键不是“抓到所有图片”，而是“筛出真正的主画布结果”
- 平台登录态、资源过期时间、前端改版和防盗链策略都会影响成功率
- 花瓣公开预览图、稿定候选预览图等结果不应自动等同于无水印原图
- 请仅在合法、合规且符合平台条款的前提下使用本项目

## 相关文档

- [818ps套图提取逻辑说明.md](./818ps套图提取逻辑说明.md)
- [稿定设计提取逻辑说明.md](./稿定设计提取逻辑说明.md)
- [花瓣素材提取逻辑说明.md](./花瓣素材提取逻辑说明.md)

如果你正在排查某个平台的专项问题，优先阅读对应平台的逻辑说明文档，而不是只看 README。

## License

MIT License
