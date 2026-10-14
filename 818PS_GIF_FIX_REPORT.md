# 图怪兽 GIF 提取修复记录（2026-10-14）

## 真实复现与证据

用户提供了“愚人节优惠活动动图GIF动图模板手机海报”公开分享链接。本文不保存分享 ID、Cookie 或签名 URL；需要复现时通过环境变量提供原链接。

修改前实跑：静态和公开数据均为 0 页，浏览器发现 1 个标记，7 个候选全部被整页图片路径过滤器排除；缺页补采仍为 0 页，总耗时 7218 ms。

同一编辑器会话的网络 JSON 显示：

- 分享页跳转到 `gif.818ps.com`。
- `doc.pageAttr.pageInfo` 是画板列表，`gifInfo[].imagePath` 是背景 GIF 素材；它不能代替含文字、SVG 等叠加层的整稿。
- `preview[]` 中 `.gif!l1000_b` 实际响应为 JPEG。移除处理后缀并复用该签名返回 403，不能据此构造原始 GIF 地址。
- 公开分享响应另有独立签名的完整 GIF，页面数据另有动态 WebP。全部按响应字节识别，优先保留完整 GIF。
- 编辑器脚本使用 `template_type=2` 请求分享数据；代码只在 GIF 编辑器 URL 上添加此参数。预览按钮最多触发一次，复用现有页面。

修改后真实链接独立测试：`pageCount=1`、`expectedPageCount=1`、`frameCount=12`、`mediaType=image/gif`、`animationStatus=animated`、`completenessStatus=complete`、`missingPages=[]`；572×900，483062 字节，提取 860 ms。本次公开数据足够，未启动 Chrome。Pillow 解码至最后一帧，下载文件与验证缓存逐字节相同。

## 修改文件及关键差异

| Python 文件 | 修改 |
| --- | --- |
| `crawlers/tuguaishou_818ps.py` | 公开请求共享任务上下文、GIF 编辑器请求参数、Referer、GIF 页码、幂等关闭 |
| `crawlers/tuguaishou_pipeline.py` | 动画发现/验证先于补采；画板与帧数分开；仅补缺页；动画缺失禁止完整成功 |
| `crawlers/tuguaishou_animation.py`（新增） | 分开整稿和素材来源，按 URL/请求上下文缓存验证，保留每个画板身份，选择原始 GIF，失败统计 |
| `core/browser_service.py` | 记录媒体响应、状态、类型、最终 URL、原始请求上下文与完整 body；复用会话预览 |
| `core/tuguaishou_media_capture.py`（新增） | DOM/source/poster/CSS/performance/data/Blob 收集；Blob 在当前页面限量读取 |
| `utils/media_inspector.py`（新增） | 有界 GET、真实文件签名、完整图片解码和帧数，原字节缓存 |
| `utils/image_validator.py` | 818ps 启用字节校验，其他平台保持原接口；先转移关闭所有权，再执行清理；成功关闭为 DEBUG |
| `utils/downloader.py` | 818ps 从 URL 索引取验证后的原始字节，保留真实扩展名，支持浏览器关闭后的 Blob/data 资源 |
| `core/image_extractor.py` | 归一化结果时保留动画缺失状态，不能重新升级为 complete |
| `tests/test_818ps_animation.py`（新增） | 本地 HTTP 和 Pillow 夹具、真假 GIF、动态 WebP、视频、静态首帧、签名、超时、去重、补采、关闭所有权 |
| `tests/test_818ps_browser_integration.py` | 真 Chrome 的媒体/Blob/DOM 采集和可选择运行的真实分享链接测试 |
| `tests/test_basic.py`、`tests/test_818ps_pipeline.py` | 原有测试替身适配共享任务及请求头参数，保留其行为断言 |

## 运行命令

PowerShell：

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:DEMARK_818PS_BROWSER_TEST='1'
$env:DEMARK_818PS_LIVE_URL='<用户提供的完整公开分享链接>'
python -m pytest tests -k "not test_extract_818ps_basic and not test_platform_detection and not test_validate_valid_image and not test_validate_invalid_image" -q
```

这四个未运行的旧用例依赖外部网络或示例链接，不能列为通过。真实 GIF 链接测试为独立新增用例，不属于排除项。

最终实际结果：**129 passed，4 deselected，2 warnings，33.60 s**。包含原静态/多页回归、其他平台回归、2 个本地真实 Chrome 用例及用户分享 GIF 用例。`git diff --check` 与修改 Python 文件的 `compileall` 均通过。

独立真实链接验证（包含保存原字节）：

```powershell
python -m pytest tests/test_818ps_browser_integration.py::test_live_shared_animation_preserves_original_bytes -q -s
```

实际结果：1 passed，2.04 s；提取内部计时 860 ms。

## 边界

单资源上限 32 MiB，请求总超时 6 秒；图片解码另有限制，超过限制明确拒绝。视频只确认容器类型，帧数和动画状态保持 unknown，不放入 GIF 图片结果。若没有公开整稿动画，只提供素材、静态首帧或 Canvas，最多尝试一次公开预览，不自动登录、付费或调用下载生成接口；返回动画未提取成功。总画板数无可靠证据时仍为 unknown，页面标记不作为总数证据。

原字节与 URL 哈希索引保存在忽略提交的 `cache/818ps_media`。目前无自动缓存淘汰，需沿用项目缓存清理方式；签名链接可能过期，已验证资源的下载使用保存的原字节。

真实分享 GIF 已验证；真实动态 WebP/视频分享页和需登录导出场景尚未逐个平台样本验证，这些分支已由本地夹具覆盖。环境仍有 pytest-asyncio 默认循环范围和 UC 的 locale 弃用提示。
