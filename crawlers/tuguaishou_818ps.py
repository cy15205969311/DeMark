"""
图怪兽/818ps爬虫 - 增强版
支持短链接解析、源码正则回退机制、多重验证策略
"""
import re
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from typing import Dict, Optional, List, Tuple
import logging
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.image_validator import ImageValidator
from utils.variant_builder import VariantBuilder

class Tuguaishou818psCrawler:
    """
    图怪兽/818ps爬虫 - 增强版
    完全对应Node.js的extract818psImage函数，并增加鲁棒性
    """
    
    def __init__(self):
        self.validator = ImageValidator()
        self.variant_builder = VariantBuilder()
        self.session = None
        
        # 请求头配置 - 模拟真实浏览器
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://818ps.com/',
            'Origin': 'https://818ps.com',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Upgrade-Insecure-Requests': '1'
        }
    
    async def extract_image(self, url: str, extracted_params: Optional[Dict] = None) -> Optional[Dict]:
        """
        提取818ps图片 - 增强版主入口
        
        Args:
            url: 目标URL
            extracted_params: 从URL解析器预提取的参数 (pic_id, upic_id)
        
        Returns:
            包含图片信息的字典或None
        """
        try:
            logging.info(f"🎨 开始提取818ps图片: {url}")
            
            # 初始化会话
            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                )
            
            # 步骤1: 强制ID优先构建策略 - 关键优化
            upic_id = None
            pic_id = None
            
            # 优先使用预提取的参数
            if extracted_params and extracted_params.get('upic_id'):
                upic_id = extracted_params['upic_id']
                pic_id = extracted_params.get('pic_id')
                logging.info(f"🎯 使用预提取参数: upicId={upic_id}, picId={pic_id}")
            
            # 如果没有预提取参数，从URL中提取
            if not upic_id:
                parsed_url = urlparse(url)
                params = parse_qs(parsed_url.query)
                pic_id = params.get('picId', [None])[0]
                upic_id = params.get('upicId', [None])[0]
                if upic_id:
                    logging.info(f"🔍 从URL提取参数: picId={pic_id}, upicId={upic_id}")
            
            # 🆕 智能分流策略：检测用户分享链接，跳过无效的静态URL构建
            is_user_share = (('/u/' in url and ('818ps.com' in url or 'tuguaishou.com' in url)) or 
                           'ue.818ps.com' in url)
            
            if is_user_share:
                logging.info("🚀 检测到用户分享链接，跳过ID猜测，直接启动动态抓取...")
                # 直接跳转到网页抓取，避免浪费时间在静态URL构建上
            else:
                # 如果有upicId，优先执行ID构建策略（仅对非用户分享链接）
                if upic_id:
                    logging.info("🚀 执行ID优先构建策略...")
                    result = await self._extract_with_upic_id_priority(upic_id, pic_id)
                    if result:
                        logging.info("✅ ID优先构建成功，跳过网页抓取")
                        return result
                    else:
                        logging.warning("⚠️ ID优先构建失败，继续尝试网页抓取...")
                        # 不要直接返回None，继续执行后续的回退机制
            
            # 网页抓取 - 作为ID构建失败后的回退机制
            logging.info("🌐 启动网页抓取 + 源码分析...")
            result = await self._scrape_webpage_enhanced(url)
            if result:
                return result
            
            # 最后的尝试 - 直接从URL构造可能的图片链接
            logging.info("🔄 尝试URL模式匹配...")
            result = await self._extract_from_url_patterns(url)
            if result:
                return result
            
            logging.warning("❌ 所有818ps提取方法都失败了")
            return None
            
        except Exception as error:
            logging.error(f"❌ 提取818ps图片异常: {error}")
            return None
        finally:
            # 不在这里关闭session，让调用者管理
            pass
    
    async def _extract_with_upic_id_priority(self, upic_id: str, pic_id: Optional[str] = None) -> Optional[Dict]:
        """
        强制ID优先构建策略 - 用户路径扩展版
        针对用户分享页面的特殊存储路径
        
        Args:
            upic_id: 用户图片ID (必需)
            pic_id: 图片ID (可选)
        
        Returns:
            提取结果或None
        """
        try:
            logging.info(f"🚀 用户路径扩展构建: upicId={upic_id}, picId={pic_id}")
            
            # 用户作品路径 - 针对 /u/ 分享页面优化
            candidates = []
            
            # 方案1: 用户编辑器预览路径 (最高优先级)
            candidates.extend([
                f"https://img.818ps.com/user_preview_ue/{upic_id}.jpg",  # 用户编辑器预览
                f"https://img.818ps.com/user_preview_ue/{upic_id}.png",
                f"https://img.818ps.com/user_preview/{upic_id}.jpg",     # 用户预览
                f"https://img.818ps.com/user_preview/{upic_id}.png",
                f"https://cdn.818ps.com/user_preview_ue/{upic_id}.jpg",  # CDN版本
                f"https://cdn.818ps.com/user_preview/{upic_id}.jpg",
            ])
            
            # 方案2: 用户作品存储路径
            candidates.extend([
                f"https://img.818ps.com/user_work/{upic_id}.jpg",
                f"https://img.818ps.com/user_work/{upic_id}.png",
                f"https://img.818ps.com/user_upload/{upic_id}.jpg",
                f"https://img.818ps.com/user_upload/{upic_id}.png",
                f"https://img.818ps.com/works/{upic_id}.jpg",
                f"https://img.818ps.com/works/{upic_id}.png",
            ])
            
            # 方案3: 如果有完整的pic_id和upic_id (传统模板路径)
            if pic_id:
                candidates.extend([
                    f"https://img.818ps.com/pic/{upic_id}/{pic_id}.jpg",  # 传统模板路径
                    f"https://img.818ps.com/pic/{upic_id}/{pic_id}.png",
                    f"https://cdn.818ps.com/pic/{upic_id}/{pic_id}.jpg",
                    f"https://static.818ps.com/pic/{upic_id}/{pic_id}.jpg",
                    # 高清版本
                    f"https://img.818ps.com/pic/{upic_id}/{pic_id}_hd.jpg",
                    f"https://img.818ps.com/pic/{upic_id}/{pic_id}_origin.jpg",
                ])
            
            # 方案4: 只有upic_id的情况 (简化格式)
            candidates.extend([
                f"https://img.818ps.com/pic/{upic_id}.jpg",  # 简化格式
                f"https://img.818ps.com/pic/{upic_id}.png",
                f"https://cdn.818ps.com/pic/{upic_id}.jpg",
                f"https://static.818ps.com/pic/{upic_id}.jpg",
                # 可能的分段规则 (针对长ID如304074038)
                f"https://img.818ps.com/pic/{upic_id[:3]}/{upic_id[3:6]}/{upic_id[6:]}.jpg",
                f"https://img.818ps.com/pic/{upic_id[:3]}/{upic_id[3:]}.jpg",
            ])
            
            # 方案5: 图怪兽域名 (备用)
            if pic_id:
                candidates.extend([
                    f"https://tuguaishou.com/user_preview_ue/{upic_id}.jpg",
                    f"https://tuguaishou.com/user_preview/{upic_id}.jpg",
                    f"https://tuguaishou.com/pic/{upic_id}/{pic_id}.jpg",
                    f"https://tuguaishou.com/pic/{upic_id}/{pic_id}.png",
                ])
            candidates.extend([
                f"https://tuguaishou.com/user_preview_ue/{upic_id}.jpg",
                f"https://tuguaishou.com/user_preview/{upic_id}.jpg",
                f"https://tuguaishou.com/pic/{upic_id}.jpg",
                f"https://tuguaishou.com/pic/{upic_id}.png",
            ])
            
            logging.info(f"🔄 验证 {len(candidates)} 个用户路径候选URL...")
            
            # 并发验证所有候选URL - 快速模式
            validation_tasks = []
            for candidate_url in candidates:
                task = asyncio.create_task(self.validator.validate_image_url(candidate_url))
                validation_tasks.append((candidate_url, task))
            
            # 等待验证完成，返回第一个有效的URL
            for candidate_url, task in validation_tasks:
                try:
                    is_valid = await task
                    if is_valid:
                        logging.info(f"✅ 找到有效的用户路径URL: {candidate_url}")
                        return {
                            'imageUrl': candidate_url,
                            'picId': pic_id,
                            'upicId': upic_id,
                            'platform': '818ps',
                            'source': 'user_path_priority',
                            'method': 'user_work_construction'
                        }
                except Exception as e:
                    logging.debug(f"用户路径URL验证失败: {candidate_url} - {e}")
            
            logging.warning("❌ 所有用户路径URL都验证失败")
            return None
            
        except Exception as e:
            logging.error(f"❌ 用户路径构建失败: {e}")
            return None
    
    async def _extract_with_known_params(self, pic_id: str, upic_id: str) -> Optional[Dict]:
        """
        使用已知参数构建图片URL并验证
        这是最可靠的方法，对应Node.js的核心逻辑
        """
        try:
            logging.info(f"🔧 构建图片URL: picId={pic_id}, upicId={upic_id}")
            
            # 构建可能的图片URL - 基于成功的Node.js模式
            possible_urls = [
                # 主要CDN域名
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
            
            logging.info(f"🔄 验证 {len(possible_urls)} 个可能的图片URL...")
            
            # 并发验证所有URL (提高效率)
            validation_tasks = []
            for test_url in possible_urls:
                task = asyncio.create_task(self._validate_and_score_url(test_url))
                validation_tasks.append((test_url, task))
            
            # 等待所有验证完成
            best_url = None
            best_score = 0
            
            for test_url, task in validation_tasks:
                try:
                    is_valid, score = await task
                    if is_valid and score > best_score:
                        best_url = test_url
                        best_score = score
                        logging.info(f"✅ 找到更好的图片URL: {test_url} (评分: {score})")
                except Exception as e:
                    logging.debug(f"URL验证失败: {test_url} - {e}")
            
            if best_url:
                logging.info(f"🎯 最终选择: {best_url}")
                return {
                    'imageUrl': best_url,
                    'picId': pic_id,
                    'upicId': upic_id,
                    'platform': '818ps',
                    'source': 'constructed_validated',
                    'score': best_score
                }
            
            return None
            
        except Exception as e:
            logging.error(f"❌ 参数构建方法失败: {e}")
            return None
    
    async def _validate_and_score_url(self, url: str) -> Tuple[bool, int]:
        """
        验证URL并给出评分
        评分越高表示图片质量越好
        """
        try:
            is_valid = await self.validator.validate_image_url(url)
            if not is_valid:
                return False, 0
            
            # 根据URL特征评分
            score = 100  # 基础分
            
            # 文件格式加分
            if url.endswith('.jpg'):
                score += 20
            elif url.endswith('.png'):
                score += 10
            elif url.endswith('.webp'):
                score += 5
            
            # 域名加分
            if 'img.818ps.com' in url:
                score += 30
            elif 'cdn.818ps.com' in url:
                score += 20
            elif 'static.818ps.com' in url:
                score += 10
            
            # 高清版本加分
            if '_hd' in url or '_origin' in url:
                score += 50
            
            return True, score
            
        except Exception:
            return False, 0
    
    async def _scrape_webpage_enhanced(self, url: str) -> Optional[Dict]:
        """
        增强版网页抓取 - 核心改进
        增加JSON深度提取，支持动态渲染页面
        """
        try:
            logging.info(f"🌐 开始增强版网页抓取: {url}")
            
            # 检查是否为动态渲染页面
            if 'ue.818ps.com' in url or 'tuguaishou.com' in url:
                logging.info("🔍 检测到动态渲染页面，启用JSON深度提取...")
                return await self._extract_dynamic_page(url)
            
            # 获取页面内容 (静态页面)
            async with self.session.get(url, timeout=15) as response:
                if response.status != 200:
                    logging.warning(f"⚠️ 页面响应异常: {response.status}")
                    return None
                
                html_content = await response.text()
                logging.info(f"📄 获取页面内容: {len(html_content)} 字符")
            
            # 方法1: JSON深度提取 (新增)
            logging.info("🔍 尝试JSON深度提取...")
            result = await self._extract_json_data(html_content, url)
            if result:
                logging.info("✅ JSON深度提取成功")
                return result
            
            # 方法2: BeautifulSoup解析 (结构化方法)
            result = await self._extract_with_beautifulsoup(html_content, url)
            if result:
                logging.info("✅ BeautifulSoup解析成功")
                return result
            
            # 方法3: 源码正则回退机制 (核心增强)
            logging.info("🔍 启动源码正则回退机制...")
            result = await self._extract_with_regex_fallback(html_content, url)
            if result:
                logging.info("✅ 正则回退机制成功")
                return result
            
            # 方法4: JavaScript变量提取
            logging.info("🔍 尝试JavaScript变量提取...")
            result = await self._extract_from_js_variables(html_content, url)
            if result:
                logging.info("✅ JavaScript变量提取成功")
                return result
            
            return None
            
        except Exception as e:
            logging.error(f"❌ 增强版网页抓取失败: {e}")
            return None
    
    async def _extract_dynamic_page(self, url: str) -> Optional[Dict]:
        """
        提取动态渲染页面 - 使用浏览器服务
        """
        try:
            from core.browser_service import BrowserService
            browser_service = BrowserService()
            
            # 提取动态内容
            dynamic_data = await browser_service.extract_dynamic_content(url)
            
            if not dynamic_data:
                return None
            
            # 分析提取的数据
            result = await self._analyze_dynamic_data(dynamic_data, url)
            return result
            
        except Exception as e:
            logging.error(f"❌ 动态页面提取失败: {e}")
            return None
    
    async def _analyze_dynamic_data(self, dynamic_data: dict, url: str) -> Optional[Dict]:
        """
        分析动态提取的数据，查找图片URL
        """
        try:
            logging.info("🔍 分析动态数据...")
            
            best_image_url = None
            best_score = 0
            
            # 1. 分析window数据
            window_data = dynamic_data.get('windowData', {})
            for key, data in window_data.items():
                image_url = self._extract_image_from_data(data)
                if image_url:
                    score = self._score_dynamic_image(image_url, key)
                    if score > best_score:
                        best_image_url = image_url
                        best_score = score
                        logging.info(f"🎯 从window.{key}找到图片: {image_url} (评分: {score})")
            
            # 2. 分析JSON数据
            json_data_list = dynamic_data.get('jsonData', [])
            for i, json_data in enumerate(json_data_list):
                image_url = self._extract_image_from_data(json_data)
                if image_url:
                    score = self._score_dynamic_image(image_url, f'json_{i}')
                    if score > best_score:
                        best_image_url = image_url
                        best_score = score
                        logging.info(f"🎯 从JSON数据{i}找到图片: {image_url} (评分: {score})")
            
            # 3. 分析直接提取的图片URL
            image_urls = dynamic_data.get('imageUrls', [])
            for image_url in image_urls:
                if self._is_relevant_dynamic_image(image_url):
                    score = self._score_dynamic_image(image_url, 'direct')
                    if score > best_score:
                        best_image_url = image_url
                        best_score = score
                        logging.info(f"🎯 从直接提取找到图片: {image_url} (评分: {score})")
            
            if best_image_url:
                # 验证最佳图片URL
                if await self.validator.validate_image_url(best_image_url):
                    return {
                        'imageUrl': best_image_url,
                        'platform': '818ps',
                        'source': 'dynamic_json_extraction',
                        'score': best_score,
                        'original_url': url
                    }
            
            return None
            
        except Exception as e:
            logging.error(f"❌ 动态数据分析失败: {e}")
            return None
    
    def _extract_image_from_data(self, data) -> Optional[str]:
        """
        从数据结构中递归提取图片URL
        """
        try:
            if isinstance(data, dict):
                # 查找常见的图片字段
                image_fields = [
                    'imageUrl', 'image_url', 'imgUrl', 'img_url',
                    'previewUrl', 'preview_url', 'coverUrl', 'cover_url',
                    'thumbnailUrl', 'thumbnail_url', 'picUrl', 'pic_url',
                    'workUrl', 'work_url', 'designUrl', 'design_url',
                    'originalUrl', 'original_url', 'hdUrl', 'hd_url'
                ]
                
                for field in image_fields:
                    if field in data and isinstance(data[field], str):
                        url = data[field]
                        if url.startswith('http') and self._is_relevant_dynamic_image(url):
                            return url
                
                # 递归搜索嵌套对象
                for value in data.values():
                    result = self._extract_image_from_data(value)
                    if result:
                        return result
                        
            elif isinstance(data, list):
                # 搜索数组中的每个元素
                for item in data:
                    result = self._extract_image_from_data(item)
                    if result:
                        return result
            
            return None
            
        except Exception:
            return None
    
    def _is_relevant_dynamic_image(self, url: str) -> bool:
        """
        判断动态提取的图片URL是否相关
        """
        if not url or not url.startswith('http'):
            return False
        
        url_lower = url.lower()
        
        # 排除明显的无关图片
        exclude_keywords = [
            'favicon', 'icon', 'logo', 'avatar', 'sprite',
            'loading', 'placeholder', 'blank', 'ad', 'banner'
        ]
        
        for keyword in exclude_keywords:
            if keyword in url_lower:
                return False
        
        # 包含相关关键词
        include_keywords = [
            'img.818ps.com', 'cdn.818ps.com', 'tuguaishou.com',
            'pic/', 'work/', 'design/', 'preview/', 'cover/',
            'user_preview', 'user_work', 'template'
        ]
        
        return any(keyword in url_lower for keyword in include_keywords)
    
    def _score_dynamic_image(self, url: str, source: str) -> int:
        """
        为动态提取的图片URL评分
        """
        score = 100  # 基础分
        url_lower = url.lower()
        
        # 域名加分
        if 'img.818ps.com' in url_lower:
            score += 50
        elif 'cdn.818ps.com' in url_lower:
            score += 40
        elif 'tuguaishou.com' in url_lower:
            score += 30
        
        # 路径加分
        if 'user_preview' in url_lower:
            score += 40
        elif 'user_work' in url_lower:
            score += 35
        elif 'preview' in url_lower:
            score += 30
        elif 'work' in url_lower:
            score += 25
        
        # 文件格式加分
        if url_lower.endswith('.jpg'):
            score += 20
        elif url_lower.endswith('.png'):
            score += 15
        elif url_lower.endswith('.webp'):
            score += 10
        
        # 数据源加分
        if 'window' in source:
            score += 30
        elif 'json' in source:
            score += 25
        elif 'direct' in source:
            score += 15
        
        return score
    
    async def _extract_json_data(self, html_content: str, url: str) -> Optional[Dict]:
        """
        从HTML中提取JSON数据 - 新增方法
        """
        try:
            import json
            import re
            
            # 查找script标签中的JSON数据
            json_patterns = [
                r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
                r'<script[^>]*>(.*?window\.__INITIAL_STATE__\s*=\s*({.*?});.*?)</script>',
                r'<script[^>]*>(.*?window\.__APP_DATA__\s*=\s*({.*?});.*?)</script>',
                r'<script[^>]*>(.*?window\.pageData\s*=\s*({.*?});.*?)</script>',
                r'<script[^>]*>(.*?var\s+pageData\s*=\s*({.*?});.*?)</script>',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
                for match in matches:
                    try:
                        # 提取JSON部分
                        json_str = match if isinstance(match, str) else match[-1]
                        json_str = json_str.strip()
                        
                        if json_str.startswith('{') and json_str.endswith('}'):
                            data = json.loads(json_str)
                            
                            # 从JSON数据中提取图片
                            image_url = self._extract_image_from_data(data)
                            if image_url and await self.validator.validate_image_url(image_url):
                                logging.info(f"🎯 JSON提取找到图片: {image_url}")
                                return {
                                    'imageUrl': image_url,
                                    'platform': '818ps',
                                    'source': 'json_extraction',
                                    'original_url': url
                                }
                                
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logging.debug(f"JSON解析异常: {e}")
                        continue
            
            return None
            
        except Exception as e:
            logging.warning(f"⚠️ JSON数据提取失败: {e}")
            return None
    
    async def _extract_with_beautifulsoup(self, html_content: str, url: str) -> Optional[Dict]:
        """
        使用BeautifulSoup进行结构化解析
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # 尝试多种选择器
            selectors = [
                f'img[src*="pic/"]',  # 包含pic/的图片
                'img[src*="img.818ps.com"]',
                'img[data-src*="pic/"]',
                'img.preview-image',
                'img.main-image',
                '.image-preview img',
                '.work-image img',
                '#showImg',
                '[style*="background-image"]'
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                for elem in elements:
                    img_src = elem.get('src') or elem.get('data-src')
                    style = elem.get('style', '')
                    
                    image_url = None
                    
                    if img_src and self._is_valid_image_src(img_src):
                        image_url = img_src if img_src.startswith('http') else f'https:{img_src}'
                    elif style and 'url(' in style:
                        match = re.search(r'url\([\'"]?([^\'"]+)[\'"]?\)', style)
                        if match:
                            bg_url = match.group(1)
                            if self._is_valid_image_src(bg_url):
                                image_url = bg_url if bg_url.startswith('http') else f'https:{bg_url}'
                    
                    if image_url:
                        logging.info(f"🎯 BeautifulSoup找到图片: {image_url}")
                        
                        # 尝试生成无水印变体
                        final_url = await self._try_watermark_removal(image_url)
                        
                        return {
                            'imageUrl': final_url,
                            'platform': '818ps',
                            'source': 'beautifulsoup_parsed',
                            'original_url': url
                        }
            
            return None
            
        except Exception as e:
            logging.warning(f"⚠️ BeautifulSoup解析失败: {e}")
            return None
    
    async def _extract_with_regex_fallback(self, html_content: str, url: str) -> Optional[Dict]:
        """
        源码正则回退机制 - 核心增强功能
        即使URL中没有参数，也能从页面源码中提取关键信息
        """
        try:
            logging.info("🔍 执行源码正则回退机制...")
            
            # 定义多种正则模式来搜索picId和upicId
            id_patterns = [
                # JavaScript变量定义
                r'var\s+picId\s*=\s*["\']?(\d+)["\']?',
                r'var\s+upicId\s*=\s*["\']?(\d+)["\']?',
                r'let\s+picId\s*=\s*["\']?(\d+)["\']?',
                r'let\s+upicId\s*=\s*["\']?(\d+)["\']?',
                r'const\s+picId\s*=\s*["\']?(\d+)["\']?',
                r'const\s+upicId\s*=\s*["\']?(\d+)["\']?',
                
                # 对象属性
                r'picId\s*:\s*["\']?(\d+)["\']?',
                r'upicId\s*:\s*["\']?(\d+)["\']?',
                r'pic_id\s*:\s*["\']?(\d+)["\']?',
                r'upic_id\s*:\s*["\']?(\d+)["\']?',
                
                # JSON配置
                r'"picId"\s*:\s*["\']?(\d+)["\']?',
                r'"upicId"\s*:\s*["\']?(\d+)["\']?',
                r'"pic_id"\s*:\s*["\']?(\d+)["\']?',
                r'"upic_id"\s*:\s*["\']?(\d+)["\']?',
                
                # 数据属性
                r'data-pic-id\s*=\s*["\'](\d+)["\']',
                r'data-upic-id\s*=\s*["\'](\d+)["\']',
                
                # URL参数
                r'picId=(\d+)',
                r'upicId=(\d+)',
                
                # 可能的API调用
                r'/api/[^"\']*picId[=/](\d+)',
                r'/api/[^"\']*upicId[=/](\d+)',
            ]
            
            pic_id = None
            upic_id = None
            
            # 搜索picId
            for pattern in id_patterns:
                if 'pic' in pattern.lower() and 'upic' not in pattern.lower():
                    matches = re.findall(pattern, html_content, re.IGNORECASE | re.MULTILINE)
                    if matches:
                        pic_id = matches[0]
                        logging.info(f"🎯 正则找到picId: {pic_id}")
                        break
            
            # 搜索upicId
            for pattern in id_patterns:
                if 'upic' in pattern.lower():
                    matches = re.findall(pattern, html_content, re.IGNORECASE | re.MULTILINE)
                    if matches:
                        upic_id = matches[0]
                        logging.info(f"🎯 正则找到upicId: {upic_id}")
                        break
            
            # 如果找到了参数，使用已知参数方法
            if pic_id and upic_id:
                logging.info(f"✅ 正则提取成功: picId={pic_id}, upicId={upic_id}")
                result = await self._extract_with_known_params(pic_id, upic_id)
                if result:
                    result['source'] = 'regex_fallback'
                    return result
            
            # 即使没有完整参数，也尝试搜索图片URL
            logging.info("🔍 搜索页面中的图片URL...")
            image_urls = self._extract_image_urls_from_content(html_content)
            
            for img_url in image_urls:
                if await self.validator.validate_image_url(img_url):
                    logging.info(f"✅ 正则找到有效图片: {img_url}")
                    
                    # 尝试生成无水印变体
                    final_url = await self._try_watermark_removal(img_url)
                    
                    return {
                        'imageUrl': final_url,
                        'platform': '818ps',
                        'source': 'regex_image_search',
                        'original_url': url
                    }
            
            return None
            
        except Exception as e:
            logging.error(f"❌ 正则回退机制失败: {e}")
            return None
    
    def _extract_image_urls_from_content(self, html_content: str) -> List[str]:
        """
        从HTML内容中提取所有可能的图片URL
        增强版：添加黑名单过滤，避免提取统计图片
        """
        urls = set()
        
        # 图片URL的正则模式
        patterns = [
            # 完整HTTP URL
            r'https?://[^"\'\\s>]+\.(?:png|jpe?g|webp|gif)(?:\?[^"\'\\s>]*)?',
            # 协议相对URL
            r'//[^"\'\\s>]+\.(?:png|jpe?g|webp|gif)(?:\?[^"\'\\s>]*)?',
            # 相对路径
            r'/[^"\'\\s>]+\.(?:png|jpe?g|webp|gif)(?:\?[^"\'\\s>]*)?',
        ]
        
        # 黑名单关键词 - 过滤统计图片和小图标
        blacklist_keywords = [
            'p.gif',           # 统计图片 (如 818ps.com/p.gif)
            'favicon',         # 网站图标
            'icon',            # 各种图标
            'loading',         # 加载图片
            'track',           # 追踪图片
            'analytics',       # 分析图片
            'pixel',           # 像素图片
            'beacon',          # 信标图片
            'sprite',          # 精灵图
            'logo',            # Logo图片
            'avatar',          # 头像图片
            'thumb',           # 缩略图
            'small',           # 小图
            'mini',            # 迷你图
            'tiny',            # 微小图
            '1x1',             # 1x1像素图
            'blank',           # 空白图
            'placeholder',     # 占位图
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                # 清理和标准化URL
                clean_url = match.replace('\\', '/')
                if clean_url.startswith('//'):
                    clean_url = 'https:' + clean_url
                elif clean_url.startswith('/') and not clean_url.startswith('//'):
                    clean_url = 'https://818ps.com' + clean_url
                
                # 黑名单过滤 - 关键优化
                url_lower = clean_url.lower()
                is_blacklisted = any(keyword in url_lower for keyword in blacklist_keywords)
                
                if is_blacklisted:
                    logging.debug(f"🚫 黑名单过滤: {clean_url}")
                    continue
                
                # 进一步的相关性检查
                if self._is_relevant_image_url(clean_url):
                    urls.add(clean_url)
                    logging.debug(f"✅ 添加候选图片: {clean_url}")
        
        logging.info(f"🔍 从页面提取到 {len(urls)} 个候选图片URL (已过滤黑名单)")
        return list(urls)
    
    def _is_relevant_image_url(self, url: str) -> bool:
        """
        判断图片URL是否相关 - 增强版
        更严格的过滤规则，避免统计图片和小图标
        """
        url_lower = url.lower()
        
        # 严格的排除关键词 (扩展版)
        exclude_keywords = [
            'favicon', 'icon', 'logo', 'avatar', 'sprite', 
            'banner', 'ad', 'advertisement', 'tracking',
            'analytics', 'pixel', 'beacon', 'p.gif',
            'loading', 'placeholder', 'blank', '1x1',
            'thumb', 'small', 'mini', 'tiny', 'btn',
            'button', 'arrow', 'close', 'search'
        ]
        
        for keyword in exclude_keywords:
            if keyword in url_lower:
                return False
        
        # 包含的关键词 (提高相关性) - 更严格
        include_keywords = [
            'pic/', 'image/', 'img/', 'photo/', 'work/',
            'preview', 'show', 'display', 'main', 'content',
            'design', 'template', 'poster', 'cover'
        ]
        
        # 必须包含至少一个相关关键词
        has_relevant_keyword = any(keyword in url_lower for keyword in include_keywords)
        
        # 或者是818ps/tuguaishou的图片域名
        is_trusted_domain = any(domain in url_lower for domain in [
            'img.818ps.com', 'cdn.818ps.com', 'static.818ps.com',
            'tuguaishou.com'
        ])
        
        return has_relevant_keyword or is_trusted_domain
    
    def _is_valid_image_src(self, src: str) -> bool:
        """
        判断图片src是否有效
        """
        if not src:
            return False
        
        src_lower = src.lower()
        
        # 必须包含图片相关路径或域名
        valid_indicators = [
            'pic/', 'image/', 'img/', 'photo/',
            '818ps.com', 'tuguaishou.com',
            '.jpg', '.png', '.webp', '.jpeg'
        ]
        
        return any(indicator in src_lower for indicator in valid_indicators)
    
    async def _try_watermark_removal(self, image_url: str) -> str:
        """
        尝试生成无水印版本
        如果无水印版本无效，返回原URL
        """
        try:
            # 生成无水印变体
            variants = self.variant_builder.build_818ps_variants(image_url)
            
            # 验证变体
            for variant in variants:
                if await self.validator.validate_image_url(variant):
                    logging.info(f"✅ 找到无水印版本: {variant}")
                    return variant
            
            # 如果没有找到有效的无水印版本，返回原URL
            return image_url
            
        except Exception as e:
            logging.warning(f"⚠️ 无水印处理失败: {e}")
            return image_url
    
    async def _extract_from_js_variables(self, html_content: str, url: str) -> Optional[Dict]:
        """
        从JavaScript变量中提取配置信息
        """
        try:
            # 搜索常见的JS配置模式
            js_patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                r'window\.config\s*=\s*({.+?});',
                r'var\s+config\s*=\s*({.+?});',
                r'const\s+config\s*=\s*({.+?});',
            ]
            
            for pattern in js_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL)
                if matches:
                    try:
                        import json
                        config = json.loads(matches[0])
                        
                        # 尝试从配置中提取图片信息
                        pic_id = self._extract_from_config(config, ['picId', 'pic_id', 'id'])
                        upic_id = self._extract_from_config(config, ['upicId', 'upic_id', 'userId', 'user_id'])
                        
                        if pic_id and upic_id:
                            result = await self._extract_with_known_params(str(pic_id), str(upic_id))
                            if result:
                                result['source'] = 'js_config'
                                return result
                                
                    except json.JSONDecodeError:
                        continue
            
            return None
            
        except Exception as e:
            logging.warning(f"⚠️ JS变量提取失败: {e}")
            return None
    
    def _extract_from_config(self, config: dict, keys: List[str]) -> Optional[str]:
        """
        从配置对象中提取值
        支持嵌套查找
        """
        def recursive_search(obj, target_keys):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in target_keys:
                        return str(value)
                    if isinstance(value, (dict, list)):
                        result = recursive_search(value, target_keys)
                        if result:
                            return result
            elif isinstance(obj, list):
                for item in obj:
                    result = recursive_search(item, target_keys)
                    if result:
                        return result
            return None
        
        return recursive_search(config, keys)
    
    async def _extract_from_url_patterns(self, url: str) -> Optional[Dict]:
        """
        从URL模式中尝试提取信息
        最后的尝试方法
        """
        try:
            # 尝试从URL路径中提取可能的ID
            path_patterns = [
                r'/(\d+)/(\d+)',  # /123/456 格式
                r'id[=/](\d+)',   # id=123 或 id/123 格式
                r'pic[=/](\d+)',  # pic=123 格式
            ]
            
            for pattern in path_patterns:
                matches = re.findall(pattern, url)
                if matches:
                    if len(matches[0]) == 2:  # 两个ID
                        pic_id, upic_id = matches[0]
                        result = await self._extract_with_known_params(pic_id, upic_id)
                        if result:
                            result['source'] = 'url_pattern'
                            return result
            
            return None
            
        except Exception as e:
            logging.warning(f"⚠️ URL模式提取失败: {e}")
            return None
    
    async def close(self):
        """关闭资源"""
        if self.session:
            await self.session.close()
        await self.validator.close()