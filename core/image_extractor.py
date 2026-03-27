"""
主图片提取器 - 三层架构
优先级: 第三方API(80%) → 本地爬虫(15%) → Selenium隐身(5%)
"""
import asyncio
import logging
from typing import Dict, Optional, List
from urllib.parse import urlparse, parse_qs

from core.third_party_api import ThirdPartyAPIGateway
from utils.image_validator import ImageValidator
from utils.variant_builder import VariantBuilder
from utils.url_parser import URLParser
from crawlers.tuguaishou_818ps import Tuguaishou818psCrawler
from crawlers.canva_crawler import CanvaCrawler
from crawlers.chuangkit_crawler import ChuangkitCrawler

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
            'Chuangkit': ChuangkitCrawler()
        }
        
    async def extract_image(self, url: str, platform: str) -> Dict:
        """
        主提取函数 - 完全对应Node.js版本的extractImage函数
        """
        logging.info(f"🚀 开始提取图片 - 平台: {platform}, URL: {url[:100]}")
        
        try:
            # ========== 阶段0: URL解析和清理 ==========
            logging.info("🔍 阶段0: 解析分享链接...")
            parse_result = self.url_parser.parse_share_url(url)
            
            if parse_result.get('success'):
                processed_url = parse_result['parsed_url']
                detected_platform = parse_result['platform']
                
                # 如果自动检测到平台，使用检测结果
                if platform == "auto" or platform == "Unknown":
                    platform = detected_platform
                
                logging.info(f"✅ URL解析成功: {processed_url}")
                logging.info(f"🎯 检测到平台: {platform}")
            else:
                processed_url = url
                logging.warning(f"⚠️ URL解析失败，使用原URL: {parse_result.get('error', '')}")
            
            # ========== 阶段1: 第三方API网关 (80%命中率) ==========
            logging.info("📡 阶段1: 尝试第三方API网关...")
            api_result = await self.third_party_api.extract_with_cache(processed_url, platform)
            
            if api_result and api_result.get('success') and api_result.get('imageUrl'):
                # 验证API返回的图片URL
                if await self.validator.validate_image_url(api_result['imageUrl']):
                    logging.info("✅ 【成功】第三方API网关返回结果")
                    return {
                        **api_result,
                        'source': 'api-gateway',
                        'platform': platform,
                        'original_url': url,
                        'processed_url': processed_url
                    }
            
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
            
            if local_result:
                # 检查是否是用户指导响应
                if local_result.get('status') == 'manual_guidance':
                    logging.info("🤝 【用户指导】本地提取返回用户指导")
                    return {
                        **local_result,
                        'original_url': url,
                        'processed_url': processed_url
                    }
                elif local_result.get('imageUrl'):
                    logging.info("✅ 【成功】本地提取返回结果")
                    return {
                        **local_result,
                        'original_url': url,
                        'processed_url': processed_url
                    }
                
            # ========== 阶段3: Selenium隐身抓取 ==========
            logging.info("🤖 阶段3: 尝试Selenium隐身抓取...")
            
            try:
                # 尝试导入和使用Selenium
                selenium_result = await self._selenium_extract(processed_url, platform)
                
                if selenium_result and selenium_result.get('imageUrl'):
                    logging.info("✅ 【成功】Selenium隐身抓取成功")
                    return {
                        **selenium_result,
                        'original_url': url,
                        'processed_url': processed_url
                    }
                    
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
        
        exclude_keywords = ['favicon', 'sprite', 'icon', 'avatar', 'tracking', 'ad']
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
        exclude_keys = ['favicon', 'sprite', 'icon', 'avatar', 'tracking', 'thumb', 'small', 'min', 'svg', 'watermark']
        
        if any(key in url_lower for key in prefer_keys):
            score += 200
        if any(key in url_lower for key in exclude_keys):
            score -= 150
        
        # 818ps特定规则
        if platform == '818ps' and 'tuguaishou.com' in url_lower:
            if any(pattern in url_lower for pattern in ['user_preview_ue', 'ips_user_preview_api', 'user_preview']):
                score += 400
            if any(pattern in url_lower for pattern in ['designer_upload_asset', 'element', 'asset']):
                score -= 350
            if url_lower.endswith('.jpg'):
                score += 80
            elif url_lower.endswith('.png'):
                score -= 60
        
        return score
    
    async def _cleanup(self):
        """清理资源"""
        try:
            if hasattr(self.third_party_api, 'session') and self.third_party_api.session:
                await self.third_party_api.session.close()
            if hasattr(self.validator, 'session') and self.validator.session:
                await self.validator.session.close()
            
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
            logging.info(f"🔍 本地提取调度器: 平台={platform}")
            
            if platform == '818ps':
                return await self._extract_818ps(url, parsed_params)
            elif platform == 'Canva':
                return await self._extract_canva(url, parsed_params)
            elif platform == 'Chuangkit':
                return await self._extract_chuangkit(url, parsed_params)
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
            logging.info(f"🎨 开始818ps本地提取: {url}")
            
            # 优先检查传入的 parsed_params
            if parsed_params and parsed_params.get('pic_id') and parsed_params.get('upic_id'):
                logging.info(f"🎯 使用预解析参数: picId={parsed_params['pic_id']}, upicId={parsed_params['upic_id']}")
                
                # 直接构建无水印URL列表（使用 img.818ps.com 等已知图床规则）
                result = await self._build_818ps_urls_from_params(
                    parsed_params['pic_id'], 
                    parsed_params['upic_id']
                )
                if result:
                    return result
            
            # 如果没有预解析参数或构建失败，使用爬虫进行网页抓取
            logging.info("🌐 使用818ps爬虫进行网页抓取...")
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
    
    async def close(self):
        """关闭资源"""
        await self._cleanup()
