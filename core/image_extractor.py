"""
主图片提取器 - 三层架构
优先级: 第三方API(80%) → 本地爬虫(15%) → Selenium隐身(5%)
"""
import asyncio
import logging
import time
from typing import Dict, Optional, List
from urllib.parse import urlparse, parse_qs

from core.third_party_api import ThirdPartyAPIGateway
from utils.image_validator import ImageValidator
from utils.variant_builder import VariantBuilder
from utils.url_parser import URLParser
from crawlers.tuguaishou_818ps import Tuguaishou818psCrawler
from crawlers.canva_crawler import CanvaCrawler
from crawlers.chuangkit_crawler import ChuangkitCrawler
from crawlers.gaoding_crawler import GaodingCrawler
from crawlers.huaban_crawler import HuabanCrawler

class ImageExtractor:
    """
    主图片提取器 - 三层架构
    优先级: 第三方API(80%) → 本地爬虫(15%) → Selenium隐身(5%)
    """
    
    def __init__(self):
        self.third_party_api = ThirdPartyAPIGateway()
        self.validator = ImageValidator()
        self.variant_builder = VariantBuilder()
        self.url_parser = URLParser()
        
        # 平台特定爬虫
        self.crawlers = {
            '818ps': Tuguaishou818psCrawler(),
            'Canva': CanvaCrawler(),
            'Chuangkit': ChuangkitCrawler(),
            'Gaoding': GaodingCrawler(),
            'Huaban': HuabanCrawler()
        }

    async def _extract_huaban(self, url: str, parsed_params: dict = None) -> Optional[Dict]:
        """Extract Huaban images with the dedicated crawler."""
        try:
            logging.info(f"Start Huaban local extraction: {url}")
            del parsed_params

            if 'Huaban' in self.crawlers:
                crawler = self.crawlers['Huaban']
                return await crawler.extract_image(url)

            logging.warning("Huaban crawler not initialized")
            return None

        except Exception as e:
            logging.error(f"Huaban extraction failed: {e}")
            return None

    def _normalize_result_images(self, result: Optional[Dict]) -> Optional[Dict]:
        """Unify single-image and multi-image results into one structure."""
        if not result or result.get('status') == 'manual_guidance':
            return result

        if result.get('platform') == '818ps':
            # 818ps pages carry identity, including gaps and equal URLs on distinct pages.
            normalized = dict(result)
            pages = [dict(page) for page in result.get('pages', [])
                     if isinstance(page, dict) and page.get('imageUrl')]
            if not pages:
                urls = result.get('imageUrls') or result.get('images') or [result.get('imageUrl')]
                pages = [{'page': index, 'imageUrl': url}
                         for index, url in enumerate(urls, 1) if isinstance(url, str) and url]
            pages.sort(key=lambda page: int(page['page']))
            urls = [page['imageUrl'] for page in pages]
            expected = result.get('expectedPageCount')
            missing = [page for page in range(1, (expected or 0) + 1)
                       if page not in {int(item['page']) for item in pages if item.get('identityConfirmed', True)}]
            status = ('complete' if not missing and len(pages) == expected else 'partial') if expected else 'unknown'
            normalized.update(pages=pages, imageUrls=urls, images=list(urls),
                              imageUrl=urls[0] if urls else None, pageCount=len(pages),
                              isMultiPage=len(pages) > 1, completenessStatus=status,
                              expectedPageCount=expected, missingPages=missing)
            normalized.setdefault('thumbnailUrl', urls[0] if urls else None)
            return normalized

        normalized_result = dict(result)
        image_urls: List[str] = []
        seen = set()

        def add_image_url(candidate_url: object) -> None:
            if not isinstance(candidate_url, str):
                return

            normalized_url = candidate_url.strip()
            if not normalized_url or normalized_url in seen:
                return

            image_urls.append(normalized_url)
            seen.add(normalized_url)

        def extract_item_url(item: object) -> Optional[str]:
            if isinstance(item, str):
                return item.strip()
            if not isinstance(item, dict):
                return None

            for key in ('imageUrl', 'url', 'src'):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            return None

        page_entries = []
        for page in normalized_result.get('pages', []) or []:
            if not isinstance(page, dict):
                continue

            page_url = extract_item_url(page)
            if not page_url:
                continue

            page_number = page.get('page')
            try:
                parsed_page_number = int(page_number)
            except (TypeError, ValueError):
                parsed_page_number = None

            page_entries.append((parsed_page_number, page_url))

        numbered_pages = [
            (page_number, page_url)
            for page_number, page_url in page_entries
            if page_number is not None
        ]
        if page_entries and len(numbered_pages) == len(page_entries):
            page_entries = sorted(page_entries, key=lambda item: item[0])

        for _, page_url in page_entries:
            add_image_url(page_url)

        for field_name in ('imageUrls', 'images'):
            for item in normalized_result.get(field_name, []) or []:
                add_image_url(extract_item_url(item))

        if not image_urls:
            add_image_url(extract_item_url(normalized_result.get('imageUrl')))

        thumbnail_url = normalized_result.get('thumbnailUrl')
        if not image_urls:
            add_image_url(extract_item_url(thumbnail_url))

        if not image_urls:
            return normalized_result

        normalized_pages = []
        for index, image_url in enumerate(image_urls):
            normalized_pages.append({
                'page': index + 1,
                'imageUrl': image_url
            })

        normalized_result['imageUrl'] = image_urls[0]
        normalized_result['imageUrls'] = image_urls
        normalized_result['images'] = list(image_urls)
        normalized_result['pages'] = normalized_pages
        normalized_result['pageCount'] = len(image_urls)
        normalized_result['isMultiPage'] = len(image_urls) > 1
        if not isinstance(thumbnail_url, str) or not thumbnail_url.strip():
            normalized_result['thumbnailUrl'] = image_urls[0]
        return normalized_result
        
    async def extract_image(self, url: str, platform: str) -> Dict:
        """
        主提取函数 - 完全对应Node.js版本的extractImage函数
        """
        started = time.monotonic()
        log = logging.debug if platform == '818ps' or any(
            host in url.lower() for host in ('818ps.com', 'tuguaishou.com')) else logging.info
        log(f"🚀 开始提取图片 - 平台: {platform}, URL: {url[:100]}")
        
        try:
            # ========== 阶段0: URL解析和清理 ==========
            log("🔍 阶段0: 解析分享链接...")
            parse_result = self.url_parser.parse_share_url(url)
            
            if parse_result.get('success'):
                processed_url = parse_result['parsed_url']
                detected_platform = parse_result['platform']
                
                # 如果自动检测到平台，使用检测结果
                if platform == "auto" or platform == "Unknown":
                    platform = detected_platform
                
                log(f"✅ URL解析成功: {processed_url}")
                log(f"🎯 检测到平台: {platform}")
            else:
                processed_url = url
                logging.warning(f"⚠️ URL解析失败，使用原URL: {parse_result.get('error', '')}")
            
            if platform == '818ps':
                # A gateway or generic Selenium single image cannot establish page completeness.
                local_result = await self._extract_local(processed_url, platform, parse_result)
                if local_result:
                    local_result.setdefault('metadata', {})['totalMs'] = round((time.monotonic() - started) * 1000)
                    return self._normalize_result_images({
                        **local_result, 'platform': platform,
                        'original_url': url, 'processed_url': processed_url
                    })
                return {'platform': platform, 'success': False, 'error': '818ps提取失败',
                        'completenessStatus': 'unknown', 'expectedPageCount': None,
                        'missingPages': [], 'pages': [], 'imageUrls': [], 'images': [],
                        'imageUrl': None, 'thumbnailUrl': None, 'pageCount': 0, 'isMultiPage': False}

            # ========== 阶段1: 第三方API网关 (80%命中率) ==========
            if platform == 'Huaban':
                logging.info("📡 阶段1: Huaban使用官方公开接口，跳过第三方API网关")
                api_result = None
            elif platform == '818ps' and parse_result.get('type') == 'share_shell':
                logging.info("📡 阶段1: 818ps /u/ 分享壳页优先走本地渲染提取，跳过第三方API网关")
                api_result = None
            else:
                logging.info("📡 阶段1: 尝试第三方API网关...")
                api_result = await self.third_party_api.extract_with_cache(processed_url, platform)
            
            deferred_api_result = None
            if api_result and api_result.get('success'):
                normalized_api_result = self._normalize_result_images({
                    **api_result,
                    'source': 'api-gateway',
                    'platform': platform,
                    'original_url': url,
                    'processed_url': processed_url
                })

                api_image_url = normalized_api_result.get('imageUrl') if normalized_api_result else None
                if api_image_url and await self.validator.validate_image_url(api_image_url):
                    if platform == 'Chuangkit' and not normalized_api_result.get('isMultiPage'):
                        logging.info("Chuangkit API returned a single image; defer it until local multi-page extraction completes")
                        deferred_api_result = normalized_api_result
                    else:
                        logging.info("✅ 【成功】第三方API网关返回结果")
                        return normalized_api_result
            
            # ========== 阶段2: 本地平台特定提取 ==========
            logging.info("🔍 阶段2: 尝试本地平台特定提取...")
            
            # 传递URL解析器提取的参数给本地爬虫
            extracted_params = None
            if parse_result.get('success'):
                extracted_params = {
                    'pic_id': parse_result.get('pic_id'),
                    'upic_id': parse_result.get('upic_id')
                }
            
            local_result = await self._extract_local(processed_url, platform, extracted_params)

            if not local_result and deferred_api_result:
                logging.info("Chuangkit local extraction did not yield a multi-page result; use deferred API fallback")
                return deferred_api_result
            
            if local_result:
                normalized_local_result = self._normalize_result_images({
                    **local_result,
                    'original_url': url,
                    'processed_url': processed_url
                })

                if local_result.get('status') == 'preview_only':
                    logging.info("Huaban preview-only result returned")
                    return normalized_local_result
                if local_result.get('status') == 'preview_image':
                    logging.info("Huaban preview-image result returned")
                    return normalized_local_result
                # 检查是否是用户指导响应
                if local_result.get('status') == 'manual_guidance':
                    logging.info("🤝 【用户指导】本地提取返回用户指导")
                    return self._normalize_result_images({
                        **local_result,
                        'original_url': url,
                        'processed_url': processed_url
                    })
                elif normalized_local_result and normalized_local_result.get('imageUrl'):
                    if platform == 'Chuangkit' and deferred_api_result and not normalized_local_result.get('isMultiPage'):
                        logging.info("Chuangkit local extraction stayed single-page; use deferred API fallback")
                        return deferred_api_result

                    logging.info("✅ 【成功】本地提取返回结果")
                    return self._normalize_result_images({
                        **local_result,
                        'original_url': url,
                        'processed_url': processed_url
                    })
                
            # ========== 阶段3: Selenium隐身抓取 ==========
            logging.info("🤖 阶段3: 尝试Selenium隐身抓取...")
            
            try:
                # 尝试导入和使用Selenium
                selenium_result = await self._selenium_extract(processed_url, platform)
                
                if selenium_result and selenium_result.get('imageUrl'):
                    logging.info("✅ 【成功】Selenium隐身抓取成功")
                    return self._normalize_result_images({
                        **selenium_result,
                        'original_url': url,
                        'processed_url': processed_url
                    })
                    
            except ImportError as e:
                logging.warning(f"⚠️ Selenium模块未安装: {e}")
                logging.info("💡 提示: 运行 'pip install selenium undetected-chromedriver' 安装Selenium支持")
                
            except Exception as selenium_error:
                # 详细的Selenium错误处理
                error_msg = str(selenium_error).lower()
                
                if 'chrome' in error_msg and ('not found' in error_msg or 'no such file' in error_msg):
                    logging.error("❌ Selenium失败: 未找到Chrome浏览器")
                    logging.info("💡 解决方案: 请安装Chrome浏览器 https://www.google.com/chrome/")
                    
                elif 'driver' in error_msg and ('version' in error_msg or 'mismatch' in error_msg):
                    logging.error("❌ Selenium失败: Chrome驱动版本不匹配")
                    logging.info("💡 解决方案: 运行 'pip install --upgrade undetected-chromedriver' 更新驱动")
                    
                elif 'permission' in error_msg or 'access' in error_msg:
                    logging.error("❌ Selenium失败: 权限不足")
                    logging.info("💡 解决方案: 尝试以管理员权限运行程序")
                    
                elif 'timeout' in error_msg:
                    logging.error("❌ Selenium失败: 页面加载超时")
                    logging.info("💡 解决方案: 检查网络连接或增加超时时间")
                    
                else:
                    logging.error(f"❌ Selenium失败: {selenium_error}")
                    logging.info("💡 提示: 这可能是网络问题或页面结构变化导致的")
            
            # 所有方法都失败
            raise Exception(f"[{platform}] 无法提取图片: 三层架构所有方法都失败了")
            
        except Exception as error:
            logging.error(f"❌ 【最终失败】{error}")
            raise error
        finally:
            # 确保资源正确关闭
            await self._cleanup()
    
    async def _selenium_extract(self, url: str, platform: str) -> Optional[Dict]:
        """
        Selenium隐身抓取 - 使用新的浏览器服务
        """
        try:
            logging.info(f"🤖 启动Selenium隐身抓取: {url}")
            
            # 使用新的浏览器服务
            from core.browser_service import BrowserService
            browser_service = BrowserService()
            
            # 检查Chrome安装状态
            chrome_status = browser_service.check_chrome_installation()
            logging.info(chrome_status['message'])
            
            if not chrome_status['installed']:
                raise Exception("Chrome浏览器未安装")
            
            # 提取图片
            image_data = await browser_service.extract_images_from_page(url, headless=True)
            
            if not image_data:
                logging.warning("❌ Selenium未找到图片元素")
                return None
            
            # 评分和选择最佳图片
            best_image_url = None
            max_score = 0
            
            for img_data in image_data:
                src = img_data['src']
                size = img_data['size']
                
                if self._should_consider_selenium_image(src):
                    # 评分
                    score = self._score_selenium_image(src, size, platform)
                    
                    if score > max_score and size > 30000:
                        logging.info(f"🔍 Selenium发现候选图片: {score}分 -> {src}")
                        max_score = score
                        best_image_url = src
            
            if best_image_url:
                logging.info(f"✅ Selenium最终选择: {best_image_url}")
                return {
                    'imageUrl': best_image_url,
                    'platform': platform,
                    'source': 'selenium-stealth',
                    'score': max_score
                }
            
            logging.warning("❌ Selenium未找到有效图片")
            return None
            
        except ImportError as e:
            logging.warning(f"⚠️ 浏览器服务模块导入失败: {e}")
            raise e
        except Exception as e:
            logging.error(f"❌ Selenium执行失败: {e}")
            raise e
    
    def _should_consider_selenium_image(self, src: str) -> bool:
        """判断Selenium是否应该考虑这个图片"""
        if not src or not src.startswith('http'):
            return False
        
        exclude_keywords = [
            'favicon', 'sprite', 'icon', 'avatar', 'tracking', 'ad',
            'qrcode', 'wechat_qrcode', 'vx-code', 'xcx-code',
            'index_hot_day', 'new-index/', 'editor/image/',
            'topcard', 'blur', 'label_lg_'
        ]
        return not any(keyword in src.lower() for keyword in exclude_keywords)
    
    def _score_selenium_image(self, url: str, size: int, platform: str) -> int:
        """
        Selenium图片评分算法
        对应Node.js的scoreUrl函数
        """
        score = min(size // 1024, 500)  # 基于大小的基础分
        url_lower = url.lower()
        
        # 通用加权
        prefer_keys = ['preview', 'cover', 'main', 'banner', 'poster', 'detail', 'work', 'showimg', 'l2000', 'l3000', 'origin', 'big']
        exclude_keys = [
            'favicon', 'sprite', 'icon', 'avatar', 'tracking',
            'thumb', 'small', 'min', 'svg', 'watermark',
            'qrcode', 'wechat_qrcode', 'vx-code', 'xcx-code',
            'index_hot_day', 'new-index/'
        ]
        
        if any(key in url_lower for key in prefer_keys):
            score += 200
        if any(key in url_lower for key in exclude_keys):
            score -= 150
        
        # 818ps特定规则
        if platform == '818ps' and 'tuguaishou.com' in url_lower:
            if any(pattern in url_lower for pattern in ['user_preview_ue', 'user_preview']):
                score += 400
            if 'ips_user_preview_api' in url_lower:
                score -= 320
            if any(pattern in url_lower for pattern in ['designer_upload_asset', 'element', 'asset']):
                score -= 350
            if any(pattern in url_lower for pattern in ['editor/image/', 'new-index/', 'topcard', 'blur', 'label_lg_']):
                score -= 500
            if not any(
                pattern in url_lower
                for pattern in ['img.tuguaishou.com', 'img.818ps.com', 'cdn.818ps.com', 'static.818ps.com',
                                'user_preview_ue', 'user_preview', 'user_work', '/works/']
            ):
                score -= 450
            if url_lower.endswith('.jpg'):
                score += 80
            elif url_lower.endswith('.png'):
                score -= 60
        
        return score
    
    async def _cleanup(self):
        """清理资源"""
        try:
            if hasattr(self.third_party_api, 'close'):
                await self.third_party_api.close()
            if hasattr(self.validator, 'close'):
                await self.validator.close()
            
            # 清理爬虫资源
            for crawler in self.crawlers.values():
                if hasattr(crawler, 'close'):
                    await crawler.close()
                    
        except Exception as e:
            logging.warning(f"资源清理警告: {e}")
    
    async def _extract_local(self, url: str, platform: str, parsed_params: dict = None) -> Optional[Dict]:
        """
        本地提取调度器
        
        Args:
            url: 目标URL
            platform: 平台名称
            parsed_params: Stage 0 解析出来的参数字典(包含 pic_id, upic_id 等)，必须透传给具体爬虫
        
        Returns:
            提取结果字典或None
        """
        try:
            (logging.debug if platform == '818ps' else logging.info)(f"🔍 本地提取调度器: 平台={platform}")
            
            if platform == '818ps':
                return await self._extract_818ps(url, parsed_params)
            elif platform == 'Canva':
                return await self._extract_canva(url, parsed_params)
            elif platform == 'Chuangkit':
                return await self._extract_chuangkit(url, parsed_params)
            elif platform == 'Gaoding':
                return await self._extract_gaoding(url, parsed_params)
            elif platform == 'Huaban':
                return await self._extract_huaban(url, parsed_params)
            else:
                logging.warning(f"⚠️ 不支持的平台: {platform}")
                return None
                
        except Exception as e:
            logging.error(f"❌ 本地提取调度失败: {e}")
            return None
    
    async def _extract_818ps(self, url: str, parsed_params: dict = None) -> Optional[Dict]:
        """
        提取818ps图片 - 优化版
        
        Args:
            url: 目标URL
            parsed_params: 从URL解析器预提取的参数 (pic_id, upic_id)
        
        Returns:
            包含图片信息的字典或None
        """
        try:
            logging.debug(f"开始818ps本地提取: {url}")
            
            if '818ps' in self.crawlers:
                crawler = self.crawlers['818ps']
                return await crawler.extract_image(url, parsed_params)
            
            logging.warning("❌ 818ps爬虫未初始化")
            return None
            
        except Exception as e:
            logging.error(f"❌ 818ps提取失败: {e}")
            return None
    
    async def _build_818ps_urls_from_params(self, pic_id: str, upic_id: str) -> Optional[Dict]:
        """
        使用已知参数直接构建818ps图片URL
        这是最高效的方法，充分利用URL解析的成果
        """
        try:
            logging.info(f"🔧 构建818ps图片URL: picId={pic_id}, upicId={upic_id}")
            
            # 构建可能的无水印图片URL - 基于已知的图床规则
            possible_urls = [
                # 主要CDN域名 - 最常用的格式
                f"https://img.818ps.com/pic/{upic_id}/{pic_id}.jpg",
                f"https://img.818ps.com/pic/{upic_id}/{pic_id}.png",
                f"https://img.818ps.com/pic/{upic_id}/{pic_id}.webp",
                
                # 备用CDN域名
                f"https://cdn.818ps.com/pic/{upic_id}/{pic_id}.jpg",
                f"https://static.818ps.com/pic/{upic_id}/{pic_id}.jpg",
                
                # 可能的高清版本
                f"https://img.818ps.com/pic/{upic_id}/{pic_id}_hd.jpg",
                f"https://img.818ps.com/pic/{upic_id}/{pic_id}_origin.jpg",
                
                # 图怪兽域名
                f"https://tuguaishou.com/pic/{upic_id}/{pic_id}.jpg",
                f"https://tuguaishou.com/pic/{upic_id}/{pic_id}.png",
            ]
            
            logging.info(f"🔄 验证 {len(possible_urls)} 个构建的图片URL...")

            async def validate_candidate(test_url: str):
                return test_url, await self.validator.validate_image_url(test_url)

            tasks = [asyncio.create_task(validate_candidate(test_url)) for test_url in possible_urls]

            try:
                for future in asyncio.as_completed(tasks):
                    test_url, is_valid = await future
                    if is_valid:
                        logging.info(f"✅ 找到有效的构建URL: {test_url}")
                        return {
                            'imageUrl': test_url,
                            'picId': pic_id,
                            'upicId': upic_id,
                            'platform': '818ps',
                            'source': 'params_constructed',
                            'method': 'direct_build'
                        }
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            
            logging.warning("❌ 所有构建的URL都无效")
            return None
            
        except Exception as e:
            logging.error(f"❌ URL构建失败: {e}")
            return None
    
    # 移除旧的单独提取方法，现在使用统一的爬虫架构
    async def _extract_canva(self, url: str, parsed_params: dict = None) -> Optional[Dict]:
        """
        提取Canva图片 - 使用专用爬虫
        
        Args:
            url: Canva模板URL
            parsed_params: 预提取的参数 (对Canva暂时不使用)
        
        Returns:
            提取结果字典或None
        """
        try:
            logging.info(f"🎨 开始Canva本地提取: {url}")
            
            # 使用Canva专用爬虫
            if 'Canva' in self.crawlers:
                crawler = self.crawlers['Canva']
                return await crawler.extract_image(url, parsed_params)
            
            logging.warning("❌ Canva爬虫未初始化")
            return None
            
        except Exception as e:
            logging.error(f"❌ Canva提取失败: {e}")
            return None
    
    async def _extract_chuangkit(self, url: str, parsed_params: dict = None) -> Optional[Dict]:
        """
        提取创客贴图片 - 使用专用爬虫
        
        Args:
            url: 创客贴设计稿URL
            parsed_params: 预提取的参数 (对创客贴暂时不使用)
        
        Returns:
            提取结果字典或None
        """
        try:
            logging.info(f"🧩 开始创客贴本地提取: {url}")
            
            # 使用创客贴专用爬虫
            if 'Chuangkit' in self.crawlers:
                crawler = self.crawlers['Chuangkit']
                return await crawler.extract_image(url, parsed_params)
            
            logging.warning("❌ 创客贴爬虫未初始化")
            return None
            
        except Exception as e:
            logging.error(f"❌ 创客贴提取失败: {e}")
            return None

    async def _extract_gaoding(self, url: str, parsed_params: dict = None) -> Optional[Dict]:
        """
        提取稿定设计图片 - 使用专用爬虫

        Args:
            url: 稿定设计分享页 / 模板页 / 编辑页 URL
            parsed_params: 预提取参数 (当前暂不使用)

        Returns:
            提取结果字典或 None
        """
        try:
            logging.info(f"🎯 开始稿定设计本地提取: {url}")
            del parsed_params

            if 'Gaoding' in self.crawlers:
                crawler = self.crawlers['Gaoding']
                return await crawler.extract_image(url)

            logging.warning("❌ 稿定设计爬虫未初始化")
            return None

        except Exception as e:
            logging.error(f"❌ 稿定设计提取失败: {e}")
            return None

    async def close(self):
        """关闭资源"""
        await self._cleanup()
