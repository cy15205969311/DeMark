"""
浏览器服务 - 驱动配置清洗版
解决Chrome驱动兼容性问题，移除冲突配置
"""
import logging
import os
import sys
import re
import subprocess
from typing import Optional
import time

class BrowserService:
    """
    浏览器服务 - 增强版
    解决Chrome驱动配置冲突，支持多种Chrome安装路径
    """
    
    def __init__(self):
        self.driver = None
        self.chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(os.getenv('USERNAME', '')),
            r"C:\Program Files\Chromium\Application\chrome.exe",
        ]
    
    def _find_chrome_executable(self) -> Optional[str]:
        """
        查找Chrome可执行文件路径
        """
        for path in self.chrome_paths:
            if os.path.exists(path):
                logging.info(f"✅ 找到Chrome浏览器: {path}")
                return path
        
        logging.warning("⚠️ 未找到Chrome浏览器")
        return None
    
    def _get_chrome_version(self) -> Optional[int]:
        """
        获取本地Chrome浏览器的主版本号
        """
        chrome_path = self._find_chrome_executable()
        if not chrome_path:
            return None

        version_sources = [
            self._get_windows_file_version,
            self._get_version_from_command,
        ]

        for getter in version_sources:
            try:
                major_version = getter(chrome_path)
                if major_version:
                    logging.info(f"🔍 检测到Chrome版本: {major_version}")
                    return major_version
            except Exception as e:
                logging.debug(f"Chrome版本探测方法失败: {getter.__name__} - {e}")

        logging.warning("⚠️ 未能自动检测到Chrome版本，将交给驱动自动匹配")
        return None

    def _parse_chrome_major_version(self, version_text: str) -> Optional[int]:
        """
        从任意版本字符串中提取Chrome主版本号
        """
        if not version_text:
            return None

        version_match = re.search(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', version_text)
        if version_match:
            return int(version_match.group(1))

        version_match = re.search(r'(\d+)\.', version_text)
        if version_match:
            return int(version_match.group(1))

        return None

    def _get_windows_file_version(self, chrome_path: str) -> Optional[int]:
        """
        Windows 下优先通过文件元数据读取版本，避免直接执行 chrome.exe --version 卡住
        """
        if os.name != 'nt':
            return None

        try:
            escaped_path = chrome_path.replace("'", "''")
            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Item -LiteralPath '{escaped_path}').VersionInfo.ProductVersion"
            ]
            version_output = subprocess.check_output(
                command,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=5,
                encoding='utf-8',
                errors='ignore'
            )
            return self._parse_chrome_major_version(version_output.strip())
        except subprocess.TimeoutExpired:
            logging.debug("Windows 文件版本检测超时")
            return None

    def _get_version_from_command(self, chrome_path: str) -> Optional[int]:
        """
        通过 chrome.exe --version 获取版本，作为通用回退方案
        """
        try:
            version_output = subprocess.check_output(
                [chrome_path, '--version'],
                stderr=subprocess.STDOUT,
                text=True,
                timeout=5,
                encoding='utf-8',
                errors='ignore'
            )
            return self._parse_chrome_major_version(version_output.strip())
        except subprocess.TimeoutExpired:
            logging.warning("⚠️ Chrome版本命令检测超时")
            return None

    def _extract_browser_version_from_error(self, error: Exception) -> Optional[int]:
        """
        从驱动异常里反推出真实浏览器版本
        """
        error_text = str(error)
        patterns = [
            r'Current browser version is (\d+)\.',
            r'Current browser version is (\d+)',
            r'browser version is (\d+)\.',
        ]

        for pattern in patterns:
            version_match = re.search(pattern, error_text, re.IGNORECASE)
            if version_match:
                return int(version_match.group(1))

        return None

    def _build_driver_kwargs(self, options, version_main: Optional[int] = None) -> dict:
        """
        构建 undetected-chromedriver 参数
        """
        kwargs = {
            'options': options,
            'driver_executable_path': None,
        }
        if version_main is not None:
            kwargs['version_main'] = version_main
        return kwargs
    
    def _get_stealth_driver(self, headless: bool = True):
        """
        获取隐身Chrome驱动 - 清洗版配置
        移除所有冲突的实验性选项
        """
        try:
            # 动态导入以避免依赖问题
            import undetected_chromedriver as uc
            
            logging.info("🤖 启动隐身Chrome驱动...")
            
            # 查找Chrome可执行文件
            chrome_path = self._find_chrome_executable()
            if not chrome_path:
                raise Exception("未找到Chrome浏览器，请安装Chrome: https://www.google.com/chrome/")
            
            # 基础Chrome选项 - 仅保留兼容性好的配置
            options = uc.ChromeOptions()
            
            # 基础性能优化选项
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            # 注意: 为了支持动态渲染，不禁用JavaScript
            # options.add_argument('--disable-javascript')  # 移除此选项
            
            # 网络优化
            options.add_argument('--aggressive-cache-discard')
            options.add_argument('--disable-background-networking')
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-renderer-backgrounding')
            
            # 动态渲染支持
            options.add_argument('--enable-javascript')  # 明确启用JavaScript
            options.add_argument('--allow-running-insecure-content')
            options.add_argument('--disable-web-security')  # 允许跨域请求
            
            # 隐身模式
            if headless:
                options.add_argument('--headless=new')
                logging.info("🔇 启用无头模式")
            
            # 窗口大小
            options.add_argument('--window-size=1920,1080')
            
            # 指定Chrome可执行文件路径
            options.binary_location = chrome_path
            
            # ❌ 绝对不要添加这些冲突配置 (会导致新版Chrome崩溃):
            # options.add_experimental_option("excludeSwitches", [...])
            # options.add_experimental_option('useAutomationExtension', False)
            
            logging.info("🔧 Chrome选项配置完成")
            
            # 创建驱动实例 - 版本锁定策略
            try:
                # 获取本地Chrome版本
                chrome_version = self._get_chrome_version()
                version_candidates = []
                attempted_versions = set()

                def enqueue_version(version_candidate):
                    key = 'auto' if version_candidate is None else int(version_candidate)
                    if key in attempted_versions:
                        return
                    attempted_versions.add(key)
                    version_candidates.append(version_candidate)

                enqueue_version(chrome_version)
                enqueue_version(None)

                driver = None
                last_error = None

                while version_candidates:
                    version_main = version_candidates.pop(0)
                    try:
                        if version_main is None:
                            logging.info("🔄 尝试让驱动自动匹配当前Chrome版本")
                        else:
                            logging.info(f"🔒 尝试使用 Chrome {version_main} 对应驱动")

                        driver = uc.Chrome(**self._build_driver_kwargs(options, version_main))
                        break
                    except Exception as e:
                        last_error = e
                        logging.error(f"❌ Chrome驱动创建失败: {e}")

                        inferred_version = self._extract_browser_version_from_error(e)
                        if inferred_version and inferred_version != version_main:
                            logging.info(f"🔁 从异常中识别到真实浏览器版本 {inferred_version}，加入重试")
                            enqueue_version(inferred_version)

                if driver is None:
                    raise last_error or RuntimeError("Chrome驱动初始化失败")
                
                # 设置超时
                driver.set_page_load_timeout(30)
                driver.implicitly_wait(10)
                
                # 执行增强隐身脚本 - 支持动态渲染页面
                driver.execute_script("""
                    // 基础反检测
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5],
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['zh-CN', 'zh', 'en'],
                    });
                    
                    // 增强脚本 - 支持动态渲染
                    window.chrome = {
                        runtime: {}
                    };
                    Object.defineProperty(navigator, 'permissions', {
                        get: () => ({
                            query: () => Promise.resolve({state: 'granted'})
                        })
                    });
                """)
                
                logging.info("✅ 版本锁定Chrome驱动启动成功")
                return driver
                
            except Exception as e:
                logging.error(f"❌ Chrome驱动创建失败: {e}")
                
                # 提供详细的错误诊断
                if 'version' in str(e).lower():
                    actual_version = self._extract_browser_version_from_error(e)
                    logging.info("💡 解决方案: Chrome版本不匹配")
                    if actual_version:
                        logging.info(f"   1. 当前浏览器主版本是 {actual_version}，请确认驱动已匹配该版本")
                    else:
                        logging.info("   1. 请确认浏览器与驱动主版本一致")
                    logging.info("   2. 运行: pip install --upgrade undetected-chromedriver")
                elif 'permission' in str(e).lower():
                    logging.info("💡 解决方案: 权限问题")
                    logging.info("   1. 以管理员权限运行程序")
                    logging.info("   2. 关闭所有Chrome进程后重试")
                elif 'path' in str(e).lower():
                    logging.info("💡 解决方案: 路径问题")
                    logging.info(f"   1. 确认Chrome安装路径: {chrome_path}")
                    logging.info("   2. 重新安装Chrome浏览器")
                else:
                    logging.info("💡 通用解决方案:")
                    logging.info("   1. 重启计算机")
                    logging.info("   2. 清理Chrome用户数据")
                    logging.info("   3. 重新安装Chrome和驱动")
                
                raise e
                
        except ImportError as e:
            logging.error("❌ undetected-chromedriver模块未安装")
            logging.info("💡 解决方案: pip install undetected-chromedriver")
            raise e
        except Exception as e:
            logging.error(f"❌ 浏览器服务启动失败: {e}")
            raise e
    
    async def get_page_content(self, url: str, headless: bool = True) -> Optional[str]:
        """
        获取页面内容
        """
        driver = None
        try:
            logging.info(f"🌐 获取页面内容: {url}")
            
            # 获取驱动
            driver = self._get_stealth_driver(headless=headless)
            
            # 访问页面
            driver.get(url)
            
            # 等待页面加载
            time.sleep(3)
            
            # 模拟滚动触发懒加载
            driver.execute_script("window.scrollBy(0, window.innerHeight);")
            time.sleep(2)
            
            # 获取页面源码
            page_source = driver.page_source
            
            logging.info(f"✅ 页面内容获取成功 ({len(page_source)} 字符)")
            return page_source
            
        except Exception as e:
            logging.error(f"❌ 页面内容获取失败: {e}")
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                    logging.info("✅ Chrome驱动已关闭")
                except:
                    pass
    
    async def extract_dynamic_content(self, url: str, headless: bool = True) -> dict:
        """
        提取动态渲染页面的内容 - 支持JSON深度提取
        专门用于处理ue.818ps.com等动态渲染页面
        """
        driver = None
        try:
            logging.info(f"🌐 提取动态渲染内容: {url}")
            
            # 获取驱动
            driver = self._get_stealth_driver(headless=headless)
            
            # 访问页面
            driver.get(url)
            
            # 等待动态内容加载
            time.sleep(5)  # 增加等待时间
            
            # 执行JavaScript获取页面数据
            page_data = driver.execute_script("""
                // 尝试获取各种可能的数据源
                var result = {
                    pageSource: document.documentElement.outerHTML,
                    windowData: {},
                    jsonData: [],
                    apiData: {},
                    imageUrls: []
                };
                
                // 1. 获取window对象中的数据
                try {
                    if (window.__INITIAL_STATE__) result.windowData.initialState = window.__INITIAL_STATE__;
                    if (window.__APP_DATA__) result.windowData.appData = window.__APP_DATA__;
                    if (window.pageData) result.windowData.pageData = window.pageData;
                    if (window.workData) result.windowData.workData = window.workData;
                    if (window.imageData) result.windowData.imageData = window.imageData;
                } catch(e) {}
                
                // 2. 查找页面中的JSON数据
                try {
                    var scripts = document.querySelectorAll('script[type="application/json"], script:not([src])');
                    scripts.forEach(function(script) {
                        try {
                            var content = script.textContent || script.innerHTML;
                            if (content.trim().startsWith('{') || content.trim().startsWith('[')) {
                                result.jsonData.push(JSON.parse(content));
                            }
                        } catch(e) {}
                    });
                } catch(e) {}
                
                // 3. 查找所有图片URL
                try {
                    var images = document.querySelectorAll('img, [style*="background-image"]');
                    images.forEach(function(img) {
                        var src = img.src || img.getAttribute('data-src') || img.getAttribute('data-original');
                        if (src && src.startsWith('http')) {
                            result.imageUrls.push(src);
                        }
                        
                        // 检查背景图片
                        var style = img.style.backgroundImage || getComputedStyle(img).backgroundImage;
                        if (style && style !== 'none') {
                            var match = style.match(/url\\(['"]?([^'"\\)]+)['"]?\\)/);
                            if (match && match[1]) {
                                result.imageUrls.push(match[1]);
                            }
                        }
                    });
                } catch(e) {}
                
                // 4. 尝试获取API响应数据
                try {
                    if (window.fetch) {
                        // 这里可以添加特定的API调用逻辑
                    }
                } catch(e) {}
                
                return result;
            """)
            
            logging.info(f"✅ 动态内容提取完成")
            logging.info(f"   JSON数据块: {len(page_data.get('jsonData', []))} 个")
            logging.info(f"   图片URL: {len(page_data.get('imageUrls', []))} 个")
            logging.info(f"   Window数据: {len(page_data.get('windowData', {}))} 个属性")
            
            return page_data
            
        except Exception as e:
            logging.error(f"❌ 动态内容提取失败: {e}")
            return {}
        finally:
            if driver:
                try:
                    driver.quit()
                    logging.info("✅ Chrome驱动已关闭")
                except:
                    pass
    
    async def extract_images_from_page(self, url: str, headless: bool = True) -> list:
        """
        从页面提取图片元素 - 增强版 (支持背景图提取)
        专门处理 SPA 应用的背景图和 Canvas 渲染图片
        """
        driver = None
        try:
            logging.info(f"🖼️ 从页面提取图片 (增强版): {url}")
            
            # 获取驱动
            driver = self._get_stealth_driver(headless=headless)
            
            # 访问页面
            driver.get(url)
            
            # 等待页面加载
            time.sleep(5)  # 增加等待时间，确保 SPA 完全加载
            
            # 模拟滚动触发懒加载
            driver.execute_script("window.scrollBy(0, window.innerHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollBy(0, -window.innerHeight);")
            time.sleep(1)
            
            # 执行增强的图片提取脚本
            image_data = driver.execute_script("""
                var result = {
                    images: [],
                    backgroundImages: [],
                    canvasImages: [],
                    allImages: []
                };
                
                // 1. 提取传统 <img> 标签
                try {
                    var images = document.querySelectorAll('img');
                    images.forEach(function(img) {
                        var src = img.src || img.getAttribute('data-src') || img.getAttribute('data-original');
                        if (src && src.startsWith('http')) {
                            var imgData = {
                                src: src,
                                width: img.naturalWidth || img.width || 0,
                                height: img.naturalHeight || img.height || 0,
                                alt: img.alt || '',
                                className: img.className || '',
                                type: 'img'
                            };
                            imgData.size = imgData.width * imgData.height;
                            result.images.push(imgData);
                            result.allImages.push(imgData);
                        }
                    });
                } catch(e) {
                    console.log('Error extracting img tags:', e);
                }
                
                // 2. 提取背景图片 - 核心增强功能
                try {
                    var allElements = document.querySelectorAll('*');
                    allElements.forEach(function(el) {
                        try {
                            var computedStyle = window.getComputedStyle(el);
                            var backgroundImage = computedStyle.backgroundImage;
                            
                            if (backgroundImage && backgroundImage !== 'none' && backgroundImage.includes('url(')) {
                                // 提取 url("...") 中的链接
                                var matches = backgroundImage.match(/url\\(['"]?([^'"\\)]+)['"]?\\)/g);
                                if (matches) {
                                    matches.forEach(function(match) {
                                        var urlMatch = match.match(/url\\(['"]?([^'"\\)]+)['"]?\\)/);
                                        if (urlMatch && urlMatch[1]) {
                                            var bgUrl = urlMatch[1];
                                            
                                            // 过滤掉小图标和非 HTTP 链接
                                            if (bgUrl.startsWith('http') && 
                                                !bgUrl.includes('favicon') && 
                                                !bgUrl.includes('icon') &&
                                                !bgUrl.includes('sprite') &&
                                                !bgUrl.includes('cursor') &&
                                                (bgUrl.includes('.jpg') || bgUrl.includes('.png') || 
                                                 bgUrl.includes('.webp') || bgUrl.includes('.jpeg'))) {
                                                
                                                var bgData = {
                                                    src: bgUrl,
                                                    width: el.offsetWidth || 0,
                                                    height: el.offsetHeight || 0,
                                                    className: el.className || '',
                                                    tagName: el.tagName || '',
                                                    type: 'background'
                                                };
                                                bgData.size = bgData.width * bgData.height;
                                                result.backgroundImages.push(bgData);
                                                result.allImages.push(bgData);
                                            }
                                        }
                                    });
                                }
                            }
                        } catch(e) {
                            // 忽略单个元素的错误
                        }
                    });
                } catch(e) {
                    console.log('Error extracting background images:', e);
                }
                
                // 3. 提取 Canvas 元素 (如果有的话)
                try {
                    var canvases = document.querySelectorAll('canvas');
                    canvases.forEach(function(canvas) {
                        try {
                            if (canvas.width > 100 && canvas.height > 100) {
                                // 尝试将 Canvas 转换为 Data URL
                                var dataUrl = canvas.toDataURL('image/png');
                                if (dataUrl && dataUrl.startsWith('data:image')) {
                                    var canvasData = {
                                        src: dataUrl,
                                        width: canvas.width,
                                        height: canvas.height,
                                        className: canvas.className || '',
                                        type: 'canvas'
                                    };
                                    canvasData.size = canvasData.width * canvasData.height;
                                    result.canvasImages.push(canvasData);
                                    result.allImages.push(canvasData);
                                }
                            }
                        } catch(e) {
                            // Canvas 可能有跨域限制，忽略错误
                        }
                    });
                } catch(e) {
                    console.log('Error extracting canvas images:', e);
                }
                
                // 4. 查找可能的图片容器元素
                try {
                    var containers = document.querySelectorAll('[class*="image"], [class*="photo"], [class*="picture"], [class*="preview"], [class*="thumbnail"]');
                    containers.forEach(function(container) {
                        try {
                            var computedStyle = window.getComputedStyle(container);
                            var backgroundImage = computedStyle.backgroundImage;
                            
                            if (backgroundImage && backgroundImage !== 'none' && backgroundImage.includes('url(')) {
                                var urlMatch = backgroundImage.match(/url\\(['"]?([^'"\\)]+)['"]?\\)/);
                                if (urlMatch && urlMatch[1]) {
                                    var containerUrl = urlMatch[1];
                                    if (containerUrl.startsWith('http')) {
                                        var containerData = {
                                            src: containerUrl,
                                            width: container.offsetWidth || 0,
                                            height: container.offsetHeight || 0,
                                            className: container.className || '',
                                            type: 'container_background'
                                        };
                                        containerData.size = containerData.width * containerData.height;
                                        result.backgroundImages.push(containerData);
                                        result.allImages.push(containerData);
                                    }
                                }
                            }
                        } catch(e) {
                            // 忽略单个容器的错误
                        }
                    });
                } catch(e) {
                    console.log('Error extracting container images:', e);
                }
                
                return result;
            """)
            
            # 处理提取结果
            all_images = image_data.get('allImages', [])
            
            logging.info(f"✅ 图片提取完成:")
            logging.info(f"   传统 <img> 标签: {len(image_data.get('images', []))} 个")
            logging.info(f"   背景图片: {len(image_data.get('backgroundImages', []))} 个")
            logging.info(f"   Canvas 图片: {len(image_data.get('canvasImages', []))} 个")
            logging.info(f"   总计: {len(all_images)} 个")
            
            return all_images
            
        except Exception as e:
            logging.error(f"❌ 增强图片提取失败: {e}")
            return []
        finally:
            if driver:
                try:
                    driver.quit()
                    logging.info("✅ Chrome驱动已关闭")
                except:
                    pass
    
    def check_chrome_installation(self) -> dict:
        """
        检查Chrome安装状态
        """
        result = {
            'installed': False,
            'path': None,
            'version': None,
            'message': ''
        }
        
        chrome_path = self._find_chrome_executable()
        if chrome_path:
            result['installed'] = True
            result['path'] = chrome_path
            result['message'] = f"✅ Chrome已安装: {chrome_path}"
            
            chrome_version = self._get_chrome_version()
            if chrome_version:
                result['version'] = f"{chrome_version}.x"
            else:
                result['version'] = "版本获取失败"
        else:
            result['message'] = "❌ 未检测到Chrome浏览器，建议安装: https://www.google.com/chrome/"
        
        return result
    
    async def extract_meta_images(self, url: str, headless: bool = True) -> dict:
        """
        提取页面中的 Meta 标签图片 - 专门用于 Canva 等平台
        增强 og:image 和 twitter:image 的提取能力
        """
        driver = None
        try:
            logging.info(f"🔍 提取Meta标签图片: {url}")
            
            # 获取驱动
            driver = self._get_stealth_driver(headless=headless)
            
            # 访问页面
            driver.get(url)
            
            # 等待页面加载
            time.sleep(3)
            
            # 执行JavaScript提取Meta标签
            meta_data = driver.execute_script("""
                var result = {
                    ogImage: null,
                    twitterImage: null,
                    otherMetaImages: [],
                    allImages: []
                };
                
                // 1. 提取 og:image
                var ogImageMeta = document.querySelector('meta[property="og:image"]');
                if (ogImageMeta && ogImageMeta.content) {
                    result.ogImage = ogImageMeta.content;
                }
                
                // 2. 提取 twitter:image
                var twitterImageMeta = document.querySelector('meta[name="twitter:image"]');
                if (twitterImageMeta && twitterImageMeta.content) {
                    result.twitterImage = twitterImageMeta.content;
                }
                
                // 3. 提取其他可能的Meta图片标签
                var otherMetaSelectors = [
                    'meta[property="og:image:url"]',
                    'meta[name="twitter:image:src"]',
                    'meta[property="image"]',
                    'meta[name="image"]',
                    'meta[property="og:image:secure_url"]'
                ];
                
                otherMetaSelectors.forEach(function(selector) {
                    var meta = document.querySelector(selector);
                    if (meta && meta.content) {
                        result.otherMetaImages.push({
                            selector: selector,
                            content: meta.content
                        });
                    }
                });
                
                // 4. 提取所有图片URL作为备用
                var images = document.querySelectorAll('img[src], img[data-src]');
                images.forEach(function(img) {
                    var src = img.src || img.getAttribute('data-src');
                    if (src && src.startsWith('http')) {
                        result.allImages.push({
                            src: src,
                            alt: img.alt || '',
                            width: img.naturalWidth || img.width || 0,
                            height: img.naturalHeight || img.height || 0
                        });
                    }
                });
                
                return result;
            """)
            
            logging.info(f"✅ Meta标签提取完成")
            logging.info(f"   og:image: {'✅' if meta_data.get('ogImage') else '❌'}")
            logging.info(f"   twitter:image: {'✅' if meta_data.get('twitterImage') else '❌'}")
            logging.info(f"   其他Meta图片: {len(meta_data.get('otherMetaImages', []))} 个")
            logging.info(f"   所有图片: {len(meta_data.get('allImages', []))} 个")
            
            return meta_data
            
        except Exception as e:
            logging.error(f"❌ Meta标签提取失败: {e}")
            return {}
        finally:
            if driver:
                try:
                    driver.quit()
                    logging.info("✅ Chrome驱动已关闭")
                except:
                    pass

    async def close(self):
        """关闭浏览器服务"""
        if self.driver:
            try:
                self.driver.quit()
                logging.info("✅ 浏览器服务已关闭")
            except:
                pass
            finally:
                self.driver = None
