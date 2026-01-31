"""
Canva (可画) 爬虫 - 简化高效策略
专门处理 SPA 单页应用，使用智能URL转换 + 快速Meta提取
"""
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Dict, Optional
import logging
import sys
import os
import json
import re
from urllib.parse import urlparse, quote

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.image_validator import ImageValidator

class CanvaCrawler:
    """
    Canva (可画) 爬虫 - 简化高效策略
    专门处理 SPA 单页应用，使用智能URL转换 + 快速Meta提取
    """
    
    def __init__(self):
        self.validator = ImageValidator()
        
        # 高效请求头 - 只使用最有效的User-Agent
        self.headers = {
            'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0'
        }
    
    async def extract_image(self, url: str, extracted_params: Optional[Dict] = None) -> Optional[Dict]:
        """
        提取 Canva 图片 - 多源融合策略
        智能URL构造 + 深度页面分析 + 增强反检测
        
        Args:
            url: Canva 模板URL
            extracted_params: 预提取的参数 (对Canva不使用)
        
        Returns:
            包含图片信息的字典或None
        """
        session = None
        try:
            logging.info(f"🎨 开始提取Canva图片 (多源融合策略): {url}")
            
            # 步骤1: 智能URL构造 - 直接构造预览图片URL
            logging.info("🔧 智能URL构造...")
            result = await self._smart_url_construction(url)
            if result:
                logging.info("✅ 智能URL构造成功")
                return result
            
            # 创建增强会话，强化反检测
            session = await self._create_enhanced_session()
            
            # 步骤2: 增强Meta标签提取 - 使用多User-Agent策略
            logging.info("🚀 增强Meta标签提取...")
            result = await self._enhanced_meta_extraction(session, url)
            if result:
                logging.info("✅ 增强Meta提取成功")
                return result
            
            # 步骤3: 深度HTML分析 - 使用更全面的正则和解析
            logging.info("🔍 深度HTML分析...")
            result = await self._deep_html_analysis(session, url)
            if result:
                logging.info("✅ 深度HTML分析成功")
                return result
            
            # 步骤4: 智能分享链接变体 - 更多变体组合
            logging.info("🔗 智能分享链接变体...")
            result = await self._smart_share_variants(session, url)
            if result:
                logging.info("✅ 分享链接变体成功")
                return result
            
            # 步骤5: 动态内容提取 - 模拟浏览器行为
            logging.info("🤖 动态内容提取...")
            result = await self._dynamic_content_extraction(session, url)
            if result:
                logging.info("✅ 动态内容提取成功")
                return result
            
            logging.warning("❌ 所有 Canva 多源融合方法都失败了")
            return None
            
        except Exception as error:
            logging.error(f"❌ 提取Canva图片异常: {error}")
            return None
        finally:
            if session:
                await session.close()
    
    async def _smart_url_construction(self, url: str) -> Optional[Dict]:
        """
        智能URL构造 - 基于Canva URL规律直接构造预览图片URL
        """
        try:
            logging.info("🔧 开始智能URL构造...")
            
            # 提取设计ID
            import re
            design_id_match = re.search(r'/design/([^/]+)', url)
            if not design_id_match:
                logging.debug("❌ 无法提取设计ID")
                return None
            
            design_id = design_id_match.group(1)
            logging.info(f"🎯 提取到设计ID: {design_id}")
            
            # 构造可能的预览图片URL - 基于Canva CDN规律
            possible_urls = []
            
            # 确定域名
            if 'canva.cn' in url:
                domain_variants = ['canva.cn', 'www.canva.cn']
            else:
                domain_variants = ['canva.com', 'www.canva.com']
            
            # 构造多种可能的图片URL格式
            for domain in domain_variants:
                # 主要预览格式
                possible_urls.extend([
                    f"https://{domain}/design/{design_id}/0_1/preview.png",
                    f"https://{domain}/design/{design_id}/0_1/preview.jpg",
                    f"https://{domain}/design/{design_id}/preview.png",
                    f"https://{domain}/design/{design_id}/preview.jpg",
                    f"https://{domain}/design/{design_id}/thumbnail.png",
                    f"https://{domain}/design/{design_id}/thumbnail.jpg",
                ])
                
                # CDN格式
                possible_urls.extend([
                    f"https://marketplace-canva-{domain.split('.')[0]}.s3.amazonaws.com/{design_id}/preview.png",
                    f"https://marketplace-canva-{domain.split('.')[0]}.s3.amazonaws.com/{design_id}/preview.jpg",
                    f"https://d2k1ftgv7pobq7.cloudfront.net/{design_id}/preview.png",
                    f"https://d2k1ftgv7pobq7.cloudfront.net/{design_id}/preview.jpg",
                ])
            
            logging.info(f"🔄 构造了 {len(possible_urls)} 个候选URL")
            
            # 并发验证所有URL
            import asyncio
            session = None
            try:
                session = await self._create_enhanced_session()
                
                # 限制并发数，避免过度请求
                semaphore = asyncio.Semaphore(5)
                
                async def validate_url(test_url):
                    async with semaphore:
                        return await self._validate_image_with_session(session, test_url)
                
                validation_tasks = [validate_url(test_url) for test_url in possible_urls[:10]]  # 只测试前10个
                results = await asyncio.gather(*validation_tasks, return_exceptions=True)
                
                for i, (test_url, is_valid) in enumerate(zip(possible_urls[:10], results)):
                    if isinstance(is_valid, bool) and is_valid:
                        logging.info(f"✅ 找到有效的构造URL: {test_url}")
                        return {
                            'imageUrl': test_url,
                            'platform': 'Canva',
                            'source': 'smart_construction',
                            'original_url': url,
                            'method': 'url_construction',
                            'design_id': design_id
                        }
                
                logging.debug("❌ 所有构造的URL都无效")
                return None
                
            finally:
                if session:
                    await session.close()
                    
        except Exception as e:
            logging.debug(f"❌ 智能URL构造失败: {e}")
            return None
    
    async def _create_enhanced_session(self) -> aiohttp.ClientSession:
        """
        创建增强会话 - 强化反检测机制
        """
        import socket
        
        # 增强的连接器配置
        connector = aiohttp.TCPConnector(
            family=socket.AF_INET,
            ssl=False,
            limit=30,
            limit_per_host=10,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        # 增强的请求头 - 模拟真实浏览器
        enhanced_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }
        
        return aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
            connector=connector,
            headers=enhanced_headers
        )
    
    async def _enhanced_meta_extraction(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """
        增强Meta标签提取 - 使用多User-Agent策略
        """
        try:
            logging.info("🚀 开始增强Meta标签提取...")
            
            # 智能URL预处理
            processed_url = self._smart_url_conversion(url)
            
            # 多User-Agent策略 - 选择最有效的几个
            user_agents = [
                'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
                'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
                'Twitterbot/1.0',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ]
            
            for ua in user_agents:
                try:
                    headers = self.headers.copy()
                    headers['User-Agent'] = ua
                    
                    # 添加随机延迟
                    import random
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    
                    async with session.get(processed_url, headers=headers) as response:
                        if response.status == 200:
                            html_content = await response.text()
                            logging.info(f"📄 获取HTML内容: {len(html_content)} 字符 (UA: {ua[:30]}...)")
                            
                            # 解析Meta标签
                            result = await self._parse_meta_tags(html_content, processed_url)
                            if result:
                                return result
                        else:
                            logging.debug(f"❌ 响应失败 ({response.status}): {ua[:30]}...")
                            
                except Exception as e:
                    logging.debug(f"❌ User-Agent失败: {ua[:30]}... - {e}")
                    continue
            
            logging.debug("❌ 增强Meta提取失败")
            return None
            
        except Exception as e:
            logging.debug(f"❌ 增强Meta提取异常: {e}")
            return None
    
    async def _parse_meta_tags(self, html_content: str, url: str) -> Optional[Dict]:
        """
        解析Meta标签 - 增强版
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # 扩展的Meta标签选择器
            meta_selectors = [
                ('meta[property="og:image"]', 'content'),
                ('meta[name="twitter:image"]', 'content'),
                ('meta[property="og:image:url"]', 'content'),
                ('meta[name="twitter:image:src"]', 'content'),
                ('link[rel="image_src"]', 'href'),
                ('meta[property="image"]', 'content'),
                ('meta[name="image"]', 'content'),
                ('meta[property="og:image:secure_url"]', 'content'),
                ('meta[name="thumbnail"]', 'content'),
                ('link[rel="apple-touch-icon"]', 'href'),
            ]
            
            for selector, attr in meta_selectors:
                element = soup.select_one(selector)
                if element and element.get(attr):
                    image_url = element[attr]
                    
                    # URL标准化
                    image_url = self._normalize_image_url(image_url, url)
                    
                    if self._is_valid_canva_image_url(image_url):
                        logging.info(f"🎯 找到Meta标签图片: {image_url} (来源: {selector})")
                        
                        # 验证图片URL
                        if await self._validate_image_with_session_quick(image_url):
                            return {
                                'imageUrl': image_url,
                                'platform': 'Canva',
                                'source': 'enhanced_meta',
                                'original_url': url,
                                'method': 'enhanced_meta_extraction',
                                'meta_selector': selector
                            }
            
            return None
            
        except Exception as e:
            logging.debug(f"❌ Meta标签解析失败: {e}")
            return None
    
    def _normalize_image_url(self, image_url: str, base_url: str) -> str:
        """
        标准化图片URL
        """
        if image_url.startswith('//'):
            return 'https:' + image_url
        elif image_url.startswith('/'):
            parsed_url = urlparse(base_url)
            return f"{parsed_url.scheme}://{parsed_url.netloc}{image_url}"
        return image_url
    
    async def _validate_image_with_session_quick(self, image_url: str) -> bool:
        """
        快速验证图片URL - 独立会话
        """
        try:
            session = await self._create_enhanced_session()
            try:
                async with session.head(image_url, timeout=8) as response:
                    if response.status == 200:
                        content_length = response.headers.get('Content-Length')
                        if content_length and int(content_length) > 10240:  # 大于10KB
                            return True
                return False
            finally:
                await session.close()
        except:
            return False
    
    async def _deep_html_analysis(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """
        深度HTML分析 - 使用更全面的正则和解析
        """
        try:
            logging.info("🔍 开始深度HTML分析...")
            
            processed_url = self._smart_url_conversion(url)
            
            async with session.get(processed_url, headers=self.headers) as response:
                if response.status != 200:
                    logging.debug(f"⚠️ 深度分析页面响应异常: {response.status}")
                    return None
                
                html_content = await response.text()
                logging.info(f"📄 获取深度分析HTML内容: {len(html_content)} 字符")
            
            # 深度正则搜索模式 - 更全面的模式
            deep_patterns = [
                # JSON数据中的图片字段
                r'"thumbnail_url"\s*:\s*"(https?:[^"]+)"',
                r'"preview_url"\s*:\s*"(https?:[^"]+)"',
                r'"image_url"\s*:\s*"(https?:[^"]+)"',
                r'"cover_url"\s*:\s*"(https?:[^"]+)"',
                r'"previewImageUrl"\s*:\s*"(https?:[^"]+)"',
                r'"thumbnailImageUrl"\s*:\s*"(https?:[^"]+)"',
                
                # JavaScript变量
                r'var\s+\w*[Ii]mage\w*\s*=\s*["\']([^"\']+)["\']',
                r'const\s+\w*[Ii]mage\w*\s*=\s*["\']([^"\']+)["\']',
                r'let\s+\w*[Ii]mage\w*\s*=\s*["\']([^"\']+)["\']',
                
                # 数据属性
                r'data-image\s*=\s*["\']([^"\']+)["\']',
                r'data-preview\s*=\s*["\']([^"\']+)["\']',
                r'data-thumbnail\s*=\s*["\']([^"\']+)["\']',
                
                # CSS背景图片
                r'background-image\s*:\s*url\(["\']?([^"\']+)["\']?\)',
                
                # Canva特定URL模式
                r'https://[^"\s]*canva[^"\s]*\.(jpg|jpeg|png|webp|gif)',
                r'https://[^"\s]*\.canva\.[^"\s]*\.(jpg|jpeg|png|webp|gif)',
                
                # CDN模式
                r'https://d[0-9a-z]+\.cloudfront\.net/[^"\s]*\.(jpg|jpeg|png|webp)',
                r'https://[^"\s]*amazonaws\.com/[^"\s]*canva[^"\s]*\.(jpg|jpeg|png|webp)',
            ]
            
            found_urls = set()
            
            for pattern in deep_patterns:
                try:
                    matches = re.findall(pattern, html_content, re.IGNORECASE | re.MULTILINE)
                    for match in matches:
                        if isinstance(match, tuple):
                            image_url = match[0]
                        else:
                            image_url = match
                        
                        # 标准化URL
                        image_url = self._normalize_image_url(image_url, processed_url)
                        
                        if self._is_valid_canva_image_url(image_url):
                            found_urls.add(image_url)
                            logging.info(f"🎯 深度分析找到图片URL: {image_url[:80]}...")
                except Exception as e:
                    logging.debug(f"❌ 深度模式失败: {pattern[:30]}... - {e}")
                    continue
            
            logging.info(f"📊 深度分析结果: 找到 {len(found_urls)} 个候选URL")
            
            # 按优先级排序验证
            sorted_urls = sorted(found_urls, key=lambda x: self._get_url_priority(x), reverse=True)
            
            for i, image_url in enumerate(sorted_urls[:8]):  # 最多验证前8个
                logging.info(f"🔍 验证深度候选URL {i+1}/{min(len(sorted_urls), 8)}: {image_url[:60]}...")
                if await self._validate_image_with_session(session, image_url):
                    logging.info(f"✅ 深度分析验证成功: {image_url}")
                    return {
                        'imageUrl': image_url,
                        'platform': 'Canva',
                        'source': 'deep_analysis',
                        'original_url': url,
                        'method': 'deep_html_analysis',
                        'total_candidates': len(found_urls)
                    }
            
            logging.debug(f"❌ 深度分析未找到有效图片 (测试了{len(sorted_urls)}个候选)")
            return None
            
        except Exception as e:
            logging.debug(f"❌ 深度HTML分析失败: {e}")
            return None
    
    async def _smart_share_variants(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """
        智能分享链接变体 - 更多变体组合
        """
        try:
            logging.info("🔗 开始智能分享链接变体...")
            
            import re
            design_id_match = re.search(r'/design/([^/]+)', url)
            if not design_id_match:
                return None
            
            design_id = design_id_match.group(1)
            
            # 生成更多变体
            variants = []
            
            if 'canva.cn' in url:
                variants.extend([
                    f"https://www.canva.cn/design/{design_id}/view",
                    f"https://www.canva.cn/design/{design_id}",
                    f"https://canva.cn/design/{design_id}/view",
                    f"https://canva.cn/design/{design_id}",
                    f"https://www.canva.cn/design/{design_id}/preview",
                    f"https://www.canva.cn/templates/{design_id}",
                ])
            else:
                variants.extend([
                    f"https://www.canva.com/design/{design_id}/view",
                    f"https://www.canva.com/design/{design_id}",
                    f"https://canva.com/design/{design_id}/view",
                    f"https://canva.com/design/{design_id}",
                    f"https://www.canva.com/design/{design_id}/preview",
                    f"https://www.canva.com/templates/{design_id}",
                ])
            
            # 测试每个变体
            for variant_url in variants[:6]:  # 限制测试数量
                try:
                    logging.info(f"🔄 测试分享变体: {variant_url}")
                    
                    # 添加随机延迟
                    import random
                    await asyncio.sleep(random.uniform(0.3, 1.0))
                    
                    result = await self._enhanced_meta_extraction(session, variant_url)
                    if result:
                        logging.info("✅ 分享变体成功")
                        return result
                        
                except Exception as e:
                    logging.debug(f"❌ 分享变体失败: {variant_url} - {e}")
                    continue
            
            logging.debug("❌ 所有分享变体都失败了")
            return None
            
        except Exception as e:
            logging.debug(f"❌ 智能分享变体失败: {e}")
            return None
    
    async def _dynamic_content_extraction(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """
        动态内容提取 - 模拟浏览器行为
        """
        try:
            logging.info("🤖 开始动态内容提取...")
            
            processed_url = self._smart_url_conversion(url)
            
            # 模拟浏览器行为的请求头
            browser_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.google.com/',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'cross-site',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }
            
            # 模拟真实用户访问流程
            async with session.get(processed_url, headers=browser_headers) as response:
                if response.status != 200:
                    logging.debug(f"⚠️ 动态内容页面响应异常: {response.status}")
                    return None
                
                html_content = await response.text()
                logging.info(f"📄 获取动态内容HTML: {len(html_content)} 字符")
            
            # 寻找动态加载的图片数据
            dynamic_patterns = [
                # React/Vue组件数据
                r'window\.__INITIAL_STATE__\s*=\s*({[^}]+})',
                r'window\.__PRELOADED_STATE__\s*=\s*({[^}]+})',
                r'window\.__DATA__\s*=\s*({[^}]+})',
                
                # JSON-LD结构化数据
                r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([^<]+)</script>',
                
                # 内联JSON数据
                r'data-react-props\s*=\s*["\']([^"\']+)["\']',
                r'data-props\s*=\s*["\']([^"\']+)["\']',
                
                # API调用URL
                r'api/[^"\s]*image[^"\s]*',
                r'api/[^"\s]*preview[^"\s]*',
                r'api/[^"\s]*thumbnail[^"\s]*',
            ]
            
            for pattern in dynamic_patterns:
                try:
                    matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
                    for match in matches:
                        # 尝试解析JSON数据
                        if match.startswith('{'):
                            try:
                                import json
                                data = json.loads(match)
                                image_url = self._extract_image_from_json(data)
                                if image_url and self._is_valid_canva_image_url(image_url):
                                    if await self._validate_image_with_session(session, image_url):
                                        logging.info(f"✅ 动态内容提取成功: {image_url}")
                                        return {
                                            'imageUrl': image_url,
                                            'platform': 'Canva',
                                            'source': 'dynamic_content',
                                            'original_url': url,
                                            'method': 'dynamic_content_extraction'
                                        }
                            except:
                                continue
                except Exception as e:
                    logging.debug(f"❌ 动态模式失败: {pattern[:30]}... - {e}")
                    continue
            
            logging.debug("❌ 动态内容提取未找到有效图片")
            return None
            
        except Exception as e:
            logging.debug(f"❌ 动态内容提取失败: {e}")
            return None
    
    def _extract_image_from_json(self, data: dict) -> Optional[str]:
        """
        从JSON数据中提取图片URL
        """
        try:
            # 递归搜索图片URL
            def search_image_url(obj):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if isinstance(key, str) and any(keyword in key.lower() for keyword in ['image', 'preview', 'thumbnail', 'cover']):
                            if isinstance(value, str) and value.startswith('http'):
                                return value
                        result = search_image_url(value)
                        if result:
                            return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = search_image_url(item)
                        if result:
                            return result
                return None
            
            return search_image_url(data)
            
        except Exception as e:
            logging.debug(f"❌ JSON图片提取失败: {e}")
            return None
    
    def _smart_url_conversion(self, url: str) -> str:
        """
        智能URL转换 - 编辑链接转查看链接，提高访问成功率
        """
        try:
            # 移除UTM参数，简化URL
            if '?' in url:
                base_url = url.split('?')[0]
            else:
                base_url = url
            
            # 转换编辑链接为查看链接
            if '/edit' in base_url:
                base_url = base_url.replace('/edit', '/view')
                logging.info(f"🔄 转换编辑链接为查看链接")
            
            return base_url
            
        except Exception as e:
            logging.debug(f"❌ URL转换失败: {e}")
            return url
        """
        获取图片URL的优先级分数 (分数越高优先级越高)
        """
        if not image_url:
            return 0
        
        url_lower = image_url.lower()
        score = 0
        
        # 基础分数
        score += 10
        
        # 域名优先级
        if 'canva.com' in url_lower or 'canva.cn' in url_lower:
            score += 50
        
        # 关键词优先级
        high_priority_keywords = ['thumbnail', 'preview', 'template', 'design']
        for keyword in high_priority_keywords:
            if keyword in url_lower:
                score += 20
                break
        
        # 图片格式优先级
        if url_lower.endswith('.png'):
            score += 15
        elif url_lower.endswith('.jpg') or url_lower.endswith('.jpeg'):
            score += 10
        elif url_lower.endswith('.webp'):
            score += 8
        
        # 路径特征优先级
        if '/media/' in url_lower or '/images/' in url_lower:
            score += 15
        if '/thumb' in url_lower or '/preview' in url_lower:
            score += 20
        
        # 避免小图标
        avoid_keywords = ['icon', 'favicon', 'logo', 'sprite', 'avatar']
        for keyword in avoid_keywords:
            if keyword in url_lower:
                score -= 30
                break
        
        # 避免数据URL (base64)
        if url_lower.startswith('data:'):
            score -= 10
        
        return score
    
    def _is_valid_canva_image_url(self, image_url: str) -> bool:
        """
        判断是否为有效的 Canva 图片URL
        """
        if not image_url or not isinstance(image_url, str):
            return False
        
        url_lower = image_url.lower()
        
        # 必须是 HTTP/HTTPS 链接
        if not url_lower.startswith(('http://', 'https://')):
            return False
        
        # 排除明显无关的图片
        exclude_keywords = [
            'favicon', 'icon', 'logo', 'sprite', 'avatar',
            'loading', 'placeholder', 'blank', 'ad', 'banner',
            'button', 'arrow', 'close', 'search', 'menu',
            'cursor', 'pointer', 'tooltip', 'emoji'
        ]
        
        for keyword in exclude_keywords:
            if keyword in url_lower:
                return False
        
        # 包含相关关键词或域名
        include_indicators = [
            'canva.com', 'canva.cn', 'template', 'design', 
            'preview', 'thumbnail', 'media', 'image', 
            '.jpg', '.png', '.webp', '.jpeg'
        ]
        
        return any(indicator in url_lower for indicator in include_indicators)
    
    async def _validate_image_with_session(self, session: aiohttp.ClientSession, image_url: str) -> bool:
        """
        使用指定会话验证图片URL
        """
        try:
            async with session.head(image_url, timeout=10) as response:
                if response.status == 200:
                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) < 10240:  # 小于10KB
                        logging.debug(f"❌ 图片过小 ({content_length} bytes): {image_url}")
                        return False
                    logging.debug(f"✅ 图片验证成功: {image_url} ({content_length} bytes)")
                    return True
                else:
                    logging.debug(f"❌ 图片验证失败: {image_url} (状态码: {response.status})")
                    return False
        except Exception as e:
            logging.debug(f"❌ 图片验证异常: {image_url} - {e}")
            return False
    
    async def close(self):
        """关闭资源"""
        if self.validator:
            await self.validator.close()