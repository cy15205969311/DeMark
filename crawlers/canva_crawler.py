"""
Canva (可画) 爬虫 - OEmbed 接口优先策略
专门处理 SPA 单页应用的复杂抓取场景
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
    Canva (可画) 爬虫 - OEmbed 接口优先策略
    专门处理 SPA 单页应用，使用 OEmbed API + 背景图提取
    """
    
    def __init__(self):
        self.validator = ImageValidator()
        
        # OEmbed API 专用请求头
        self.api_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.canva.com/',
            'Origin': 'https://www.canva.com',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        }
        
        # HTML 抓取备用请求头
        self.html_headers = {
            'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0'
        }
    
    async def extract_image(self, url: str, extracted_params: Optional[Dict] = None) -> Optional[Dict]:
        """
        提取 Canva 图片 - OEmbed 接口优先策略
        增强版：支持URL转换和更强的反检测
        
        Args:
            url: Canva 模板URL
            extracted_params: 预提取的参数 (对Canva不使用)
        
        Returns:
            包含图片信息的字典或None
        """
        session = None
        try:
            logging.info(f"🎨 开始提取Canva图片 (增强反检测模式): {url}")
            
            # URL预处理：转换编辑链接为查看链接
            processed_url = self._preprocess_canva_url(url)
            if processed_url != url:
                logging.info(f"🔄 URL转换: {url} -> {processed_url}")
                url = processed_url
            
            # 创建会话，强制 IPv4 连接
            import socket
            connector = aiohttp.TCPConnector(
                family=socket.AF_INET,
                ssl=False,
                limit=50,
                limit_per_host=20,
                ttl_dns_cache=300,
                use_dns_cache=True
            )
            
            session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                connector=connector
            )
            
            # 方法1: OEmbed API 优先 (最高成功率)
            logging.info("� 尝试 OEmbed API 接口...")
            result = await self._fetch_oembed_data(session, url)
            if result:
                logging.info("✅ OEmbed API 提取成功")
                return result
            
            # 方法2: HTML 正则补救
            logging.info("� OEmbed API 失败，尝试 HTML 正则补救...")
            result = await self._extract_from_html_regex(session, url)
            if result:
                logging.info("✅ HTML 正则补救成功")
                return result
            
            # 方法3: 传统 Meta 标签提取 (兜底)
            logging.info("🔄 正则补救失败，尝试传统 Meta 标签提取...")
            result = await self._extract_meta_tags(session, url)
            if result:
                logging.info("✅ Meta 标签提取成功")
                return result
            
            # 方法4: 尝试公开分享链接
            if '/edit' in url:
                logging.info("🔗 尝试转换为公开分享链接...")
                share_url = self._convert_to_share_url(url)
                if share_url != url:
                    logging.info(f"🔄 分享链接转换: {share_url}")
                    result = await self._extract_from_html_regex(session, share_url)
                    if result:
                        logging.info("✅ 分享链接提取成功")
                        return result
            
            logging.warning("❌ 所有 Canva 提取方法都失败了")
            return None
            
        except Exception as error:
            logging.error(f"❌ 提取Canva图片异常: {error}")
            return None
        finally:
            if session:
                await session.close()
    
    def _preprocess_canva_url(self, url: str) -> str:
        """
        预处理Canva URL，转换编辑链接为更容易访问的格式
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
            logging.debug(f"❌ URL预处理失败: {e}")
            return url
    
    def _convert_to_share_url(self, url: str) -> str:
        """
        尝试转换为公开分享URL格式
        """
        try:
            import re
            
            # 提取设计ID
            design_id_match = re.search(r'/design/([^/]+)', url)
            if design_id_match:
                design_id = design_id_match.group(1)
                
                # 构建不同的分享URL格式
                if 'canva.cn' in url:
                    return f"https://www.canva.cn/design/{design_id}/view"
                else:
                    return f"https://www.canva.com/design/{design_id}/view"
            
            return url
            
        except Exception as e:
            logging.debug(f"❌ 分享URL转换失败: {e}")
            return url
    
    async def _fetch_oembed_data(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """
        获取 OEmbed 数据 - 核心方法
        注意：Canva 可能没有公开的 OEmbed API，此方法主要用于测试
        """
        try:
            # 确定 OEmbed API 端点
            oembed_url = self._build_oembed_url(url)
            logging.info(f"🔗 构建 OEmbed URL: {oembed_url}")
            
            # 发送 API 请求
            async with session.get(oembed_url, headers=self.api_headers) as response:
                logging.debug(f"🌐 OEmbed API 响应状态: {response.status}")
                
                if response.status == 404:
                    logging.debug("❌ OEmbed API 端点不存在 (404)")
                    return None
                elif response.status == 403:
                    logging.debug("❌ OEmbed API 访问被拒绝 (403)")
                    return None
                elif response.status != 200:
                    logging.debug(f"⚠️ OEmbed API 响应异常: {response.status}")
                    return None
                
                # 检查响应内容类型
                content_type = response.headers.get('Content-Type', '').lower()
                if 'application/json' not in content_type:
                    logging.debug(f"❌ OEmbed API 返回非JSON内容: {content_type}")
                    return None
                
                # 解析 JSON 响应
                try:
                    data = await response.json()
                    logging.info(f"📄 获取 OEmbed 数据: {len(str(data))} 字符")
                except Exception as e:
                    logging.debug(f"❌ OEmbed JSON 解析失败: {e}")
                    return None
            
            # 提取 thumbnail_url
            thumbnail_url = data.get('thumbnail_url')
            if not thumbnail_url:
                logging.debug("❌ OEmbed 数据中未找到 thumbnail_url")
                return None
            
            logging.info(f"🎯 找到 OEmbed thumbnail_url: {thumbnail_url}")
            
            # 验证图片URL
            if await self._validate_image_with_session(session, thumbnail_url):
                logging.info("✅ OEmbed thumbnail_url 验证成功")
                return {
                    'imageUrl': thumbnail_url,
                    'platform': 'Canva',
                    'source': 'oembed_api',
                    'original_url': url,
                    'method': 'oembed_extraction',
                    'title': data.get('title', ''),
                    'author_name': data.get('author_name', ''),
                    'width': data.get('thumbnail_width'),
                    'height': data.get('thumbnail_height')
                }
            else:
                logging.debug("❌ OEmbed thumbnail_url 验证失败")
                return None
                
        except Exception as e:
            logging.debug(f"❌ OEmbed 数据获取失败: {e}")
            return None
    
    def _build_oembed_url(self, target_url: str) -> str:
        """
        构建 OEmbed API URL
        """
        try:
            parsed = urlparse(target_url)
            domain = parsed.netloc.lower()
            
            # 根据域名选择对应的 OEmbed 端点
            if 'canva.cn' in domain:
                oembed_base = 'https://www.canva.cn/_oembed'
            else:
                oembed_base = 'https://www.canva.com/_oembed'
            
            # 构建完整的 OEmbed URL
            encoded_url = quote(target_url, safe='')
            oembed_url = f"{oembed_base}?url={encoded_url}&format=json"
            
            return oembed_url
            
        except Exception as e:
            logging.error(f"❌ OEmbed URL 构建失败: {e}")
            # 默认使用 .com 端点
            encoded_url = quote(target_url, safe='')
            return f"https://www.canva.com/_oembed?url={encoded_url}&format=json"
    
    async def _extract_from_html_regex(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """
        HTML 正则补救 - 在源码中搜索图片URL
        增强版：支持多种User-Agent和更全面的正则模式
        """
        try:
            logging.info("🔍 开始 HTML 正则补救...")
            
            # 尝试多种User-Agent策略 - 增强反检测
            user_agents = [
                # 搜索引擎爬虫 (通常不被拦截)
                'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
                'Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)',
                'Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)',
                
                # 社交媒体爬虫 (通常能获得更好的Meta数据)
                'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
                'Twitterbot/1.0',
                'LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +https://www.linkedin.com/)',
                'WhatsApp/2.19.81 A',
                
                # 移动设备User-Agent (有时限制较少)
                'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
                'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36',
                
                # 标准浏览器 (最后尝试)
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
            ]
            
            html_content = None
            successful_ua = None
            
            # 尝试不同的User-Agent
            for ua in user_agents:
                try:
                    # 构建更完整的请求头，模拟真实浏览器
                    headers = {
                        'User-Agent': ua,
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
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
                    
                    # 为不同类型的User-Agent添加特定头部
                    if 'Googlebot' in ua or 'Bingbot' in ua or 'YandexBot' in ua:
                        # 搜索引擎爬虫
                        headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                        headers.pop('Sec-Fetch-Dest', None)
                        headers.pop('Sec-Fetch-Mode', None)
                        headers.pop('Sec-Fetch-Site', None)
                        headers.pop('Sec-Fetch-User', None)
                    elif 'facebook' in ua.lower() or 'twitter' in ua.lower() or 'linkedin' in ua.lower():
                        # 社交媒体爬虫
                        headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                        headers['Accept-Language'] = 'en-US,en;q=0.5'
                    elif 'Mobile' in ua or 'iPhone' in ua or 'Android' in ua:
                        # 移动设备
                        headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'
                        headers['Sec-CH-UA-Mobile'] = '?1'
                    
                    # 添加随机延迟，避免被识别为机器人
                    import random
                    await asyncio.sleep(random.uniform(0.5, 2.0))
                    
                    async with session.get(url, headers=headers) as response:
                        logging.debug(f"🌐 User-Agent测试: {ua[:30]}... -> {response.status}")
                        
                        if response.status == 200:
                            html_content = await response.text()
                            successful_ua = ua
                            logging.info(f"✅ 成功获取HTML ({len(html_content)} 字符) - UA: {ua[:50]}...")
                            break
                        elif response.status == 403:
                            logging.debug(f"❌ 403 Forbidden: {ua[:50]}...")
                        elif response.status == 429:
                            logging.debug(f"❌ 429 Too Many Requests: {ua[:50]}...")
                            # 遇到429时增加延迟
                            await asyncio.sleep(random.uniform(3.0, 6.0))
                        else:
                            logging.debug(f"❌ User-Agent失败 ({response.status}): {ua[:50]}...")
                except Exception as e:
                    logging.debug(f"❌ User-Agent异常: {ua[:30]}... - {e}")
                    continue
            
            if not html_content:
                logging.debug("❌ 所有User-Agent都失败了")
                return None
            
            # 增强的正则搜索模式
            regex_patterns = [
                # 主要模式：JSON 中的各种图片字段
                r'"thumbnail_url"\s*:\s*"(https?:[^"]+)"',
                r'\"thumbnail_url\"\s*:\s*\"(https?:[^\"]+)\"',
                r'"thumbnailUrl"\s*:\s*"(https?:[^"]+)"',
                r'"preview_url"\s*:\s*"(https?:[^"]+)"',
                r'"previewUrl"\s*:\s*"(https?:[^"]+)"',
                r'"image_url"\s*:\s*"(https?:[^"]+)"',
                r'"imageUrl"\s*:\s*"(https?:[^"]+)"',
                r'"cover_url"\s*:\s*"(https?:[^"]+)"',
                r'"coverUrl"\s*:\s*"(https?:[^"]+)"',
                
                # Canvas 和设计相关模式
                r'"previewImageUrl"\s*:\s*"(https?:[^"]+)"',
                r'"thumbnailImageUrl"\s*:\s*"(https?:[^"]+)"',
                r'"designPreviewUrl"\s*:\s*"(https?:[^"]+)"',
                r'"templatePreviewUrl"\s*:\s*"(https?:[^"]+)"',
                
                # Meta 标签模式
                r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
                r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']',
                r'<meta\s+property=["\']og:image:url["\']\s+content=["\']([^"\']+)["\']',
                
                # 通用图片 URL 模式 (更精确)
                r'https://[^"\s]+\.canva\.com/[^"\s]*\.(jpg|jpeg|png|webp|gif)',
                r'https://[^"\s]+\.canva\.cn/[^"\s]*\.(jpg|jpeg|png|webp|gif)',
                
                # CDN 和媒体服务器模式
                r'https://[^"\s]*canva[^"\s]*\.(jpg|jpeg|png|webp|gif)',
                r'https://media\.canva\.com/[^"\s]+',
                r'https://media\.canva\.cn/[^"\s]+',
                
                # 数据URL模式 (base64图片)
                r'data:image/(jpeg|jpg|png|webp|gif);base64,[A-Za-z0-9+/=]+',
                
                # JavaScript变量中的图片URL
                r'var\s+\w*[Ii]mage\w*\s*=\s*["\']([^"\']+)["\']',
                r'const\s+\w*[Ii]mage\w*\s*=\s*["\']([^"\']+)["\']',
                r'let\s+\w*[Ii]mage\w*\s*=\s*["\']([^"\']+)["\']'
            ]
            
            found_urls = set()
            
            for pattern in regex_patterns:
                try:
                    matches = re.findall(pattern, html_content, re.IGNORECASE | re.MULTILINE)
                    for match in matches:
                        if isinstance(match, tuple):
                            # 处理带分组的匹配
                            image_url = match[0]
                        else:
                            image_url = match
                        
                        if self._is_valid_canva_image_url(image_url):
                            found_urls.add(image_url)
                            logging.info(f"🎯 正则找到图片URL: {image_url[:80]}...")
                except Exception as e:
                    logging.debug(f"❌ 正则模式失败: {pattern[:30]}... - {e}")
                    continue
            
            logging.info(f"📊 正则搜索结果: 找到 {len(found_urls)} 个候选URL")
            
            # 按优先级排序验证找到的 URL
            sorted_urls = sorted(found_urls, key=lambda x: self._get_url_priority(x), reverse=True)
            
            for i, image_url in enumerate(sorted_urls[:10]):  # 最多验证前10个
                logging.info(f"🔍 验证候选URL {i+1}/{min(len(sorted_urls), 10)}: {image_url[:60]}...")
                if await self._validate_image_with_session(session, image_url):
                    logging.info(f"✅ 正则提取验证成功: {image_url}")
                    return {
                        'imageUrl': image_url,
                        'platform': 'Canva',
                        'source': 'html_regex',
                        'original_url': url,
                        'method': 'regex_extraction',
                        'successful_user_agent': successful_ua,
                        'total_candidates': len(found_urls)
                    }
            
            logging.debug(f"❌ 正则补救未找到有效图片 (测试了{len(sorted_urls)}个候选)")
            return None
            
        except Exception as e:
            logging.debug(f"❌ HTML 正则补救失败: {e}")
            return None
    
    async def _extract_meta_tags(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """
        传统 Meta 标签提取 - 兜底方案
        """
        try:
            logging.info("� 开始传统 Meta 标签提取...")
            
            # 获取页面 HTML
            async with session.get(url, headers=self.html_headers) as response:
                if response.status != 200:
                    logging.debug(f"⚠️ Meta 页面响应异常: {response.status}")
                    return None
                
                html_content = await response.text()
                logging.info(f"📄 获取 Meta HTML 内容: {len(html_content)} 字符")
            
            # 使用 BeautifulSoup 解析
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Meta 标签提取优先级
            meta_selectors = [
                ('meta[property="og:image"]', 'content'),
                ('meta[name="twitter:image"]', 'content'),
                ('link[rel="image_src"]', 'href'),
                ('meta[property="og:image:url"]', 'content'),
                ('meta[name="twitter:image:src"]', 'content'),
                ('meta[property="image"]', 'content'),
                ('meta[name="image"]', 'content')
            ]
            
            for selector, attr in meta_selectors:
                element = soup.select_one(selector)
                if element and element.get(attr):
                    image_url = element[attr]
                    logging.info(f"🎯 找到 Meta 标签图片: {image_url} (来源: {selector})")
                    
                    # 验证图片URL
                    if await self._validate_image_with_session(session, image_url):
                        logging.info(f"✅ Meta 标签验证成功: {image_url}")
                        return {
                            'imageUrl': image_url,
                            'platform': 'Canva',
                            'source': 'meta_tag',
                            'original_url': url,
                            'method': 'meta_extraction',
                            'meta_selector': selector
                        }
            
            logging.debug("❌ Meta 标签提取未找到有效图片")
            return None
            
        except Exception as e:
            logging.debug(f"❌ Meta 标签提取失败: {e}")
            return None
    
    def _get_url_priority(self, image_url: str) -> int:
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