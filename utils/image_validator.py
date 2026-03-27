"""
图片URL验证器 - 请求头伪装版
解决CDN防盗链问题，增加快速熔断机制
"""
import aiohttp
import asyncio
import logging
import re
import socket
import requests
from typing import Optional, Dict
from urllib.parse import urlparse

class ImageValidator:
    """
    图片URL验证器 - 防盗链绕过版
    解决CDN拒绝访问和超时问题
    """
    
    # 标准请求头 - 绕过防盗链的关键
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://818ps.com/',  # 关键：绕过防盗链
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Fetch-Dest': 'image',
        'Sec-Fetch-Mode': 'no-cors',
        'Sec-Fetch-Site': 'cross-site',
    }
    
    ASYNC_HEAD_TIMEOUT = 2
    ASYNC_RANGE_TIMEOUT = 2
    SYNC_TIMEOUT = 2
    SYNC_FALLBACK_CONCURRENCY = 4

    def __init__(self):
        self.session = None
        self.sync_session = None
        self.sync_fallback_semaphore = asyncio.Semaphore(self.SYNC_FALLBACK_CONCURRENCY)
        
        # 初始化同步会话（回退机制）
        self.sync_session = requests.Session()
        self.sync_session.headers.update(self.DEFAULT_HEADERS)
        self.sync_session.verify = False  # 忽略SSL证书验证
        # 快速熔断
        self.sync_session.timeout = self.SYNC_TIMEOUT
    
    async def _init_async_session(self):
        """初始化异步会话 - 强制IPv4 + 快速熔断"""
        if not self.session:
            try:
                # 强制IPv4连接器 - 解决IPv6解析问题
                connector = aiohttp.TCPConnector(
                    family=socket.AF_INET,  # 强制IPv4
                    ssl=False,              # 禁用SSL验证
                    limit=50,               # 减少连接池大小
                    limit_per_host=10,      # 减少每个主机的连接数
                    ttl_dns_cache=300,      # DNS缓存时间
                    use_dns_cache=True,     # 启用DNS缓存
                )
                
                # 快速熔断 - 5秒总超时
                timeout = aiohttp.ClientTimeout(total=self.ASYNC_HEAD_TIMEOUT + self.ASYNC_RANGE_TIMEOUT, connect=2)
                
                self.session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers=self.DEFAULT_HEADERS  # 使用标准防盗链头
                )
                
                logging.info("✅ 异步会话初始化成功 (快速熔断模式)")
                
            except Exception as e:
                logging.warning(f"⚠️ 异步会话初始化失败: {e}")
                self.session = None
    
    async def validate_image_url(self, image_url: str) -> bool:
        """
        验证图片URL - 快速验证模式
        使用防盗链头和快速熔断机制
        """
        try:
            logging.info(f"🔍 快速验证图片URL: {image_url}")
            
            # 使用统一的防盗链头
            headers = self._get_anti_hotlink_headers(image_url)
            
            # 方法1: 异步验证 (优先) - 快速模式
            async_result = await self._validate_async_fast(image_url, headers)
            if async_result is not None:
                return async_result
            
            # 方法2: 同步验证 (回退) - 快速模式
            logging.info("🔄 异步验证失败，快速同步验证...")
            sync_result = await self._validate_sync_fast_async(image_url, headers)
            return sync_result
            
        except Exception as error:
            logging.warning(f"⚠️ 图片URL验证异常: {error}")
            return False
    
    def _get_anti_hotlink_headers(self, image_url: str) -> dict:
        """
        获取防盗链绕过头 - 根据域名优化
        """
        try:
            parsed = urlparse(image_url)
            hostname = parsed.hostname.lower() if parsed.hostname else ''
            
            # 基础防盗链头
            headers = self.DEFAULT_HEADERS.copy()
            
            # 根据域名优化Referer
            if 'tuguaishou.com' in hostname:
                headers['Referer'] = 'https://tuguaishou.com/'
                headers['Origin'] = 'https://tuguaishou.com'
            elif 'chuangkit.com' in hostname:
                headers['Referer'] = 'https://www.chuangkit.com/'
                headers['Origin'] = 'https://www.chuangkit.com'
            elif '818ps.com' in hostname:
                headers['Referer'] = 'https://818ps.com/'
                headers['Origin'] = 'https://818ps.com'
            else:
                # 默认使用818ps作为Referer
                headers['Referer'] = 'https://818ps.com/'
                headers['Origin'] = 'https://818ps.com'
            
            return headers
            
        except Exception:
            return self.DEFAULT_HEADERS.copy()

    def _extract_reported_size(self, headers: Dict[str, str]) -> Optional[int]:
        """
        从响应头中提取资源大小
        优先使用 Content-Range 中的总大小，兼容 Range GET 回退
        """
        content_range = headers.get('Content-Range') or headers.get('content-range')
        if content_range:
            match = re.search(r'/(\d+)$', content_range)
            if match:
                return int(match.group(1))

        content_length = headers.get('Content-Length') or headers.get('content-length')
        if content_length and content_length.isdigit():
            return int(content_length)

        return None

    def _is_image_content_type(self, headers: Dict[str, str]) -> bool:
        """
        判断响应头是否像图片资源
        """
        content_type = (headers.get('Content-Type') or headers.get('content-type') or '').lower()
        if not content_type:
            return True
        return content_type.startswith('image/') or 'application/octet-stream' in content_type

    def _is_valid_image_response(self, status: int, headers: Dict[str, str], image_url: str, method: str) -> bool:
        """
        校验单次响应是否足够证明URL可用
        """
        if status not in [200, 206]:
            return False

        if not self._is_image_content_type(headers):
            logging.debug(f"{method} 返回的 Content-Type 不是图片: {image_url}")
            return False

        file_size = self._extract_reported_size(headers)
        if file_size is not None:
            if file_size < 10240:
                logging.warning(f"❌ 图片过小 ({file_size} bytes)，已丢弃: {image_url}")
                return False
            logging.info(f"✅ {method} 验证成功 (大小: {file_size} bytes)")
            return True

        logging.info(f"✅ {method} 验证成功 (大小未知)")
        return True
    
    async def _validate_async_fast(self, image_url: str, headers: dict) -> Optional[bool]:
        """
        快速异步验证 - 5秒熔断
        """
        try:
            await self._init_async_session()
            
            if not self.session:
                return None
            
            # 快速HEAD请求 - 3秒超时
            try:
                async with self.session.head(
                    image_url,
                    headers=headers,
                    timeout=self.ASYNC_HEAD_TIMEOUT,
                    allow_redirects=True
                ) as resp:
                    if self._is_valid_image_response(resp.status, resp.headers, image_url, "异步HEAD"):
                        return True
                    if resp.status == 404:
                        logging.warning(f"❌ 图片不存在 (404): {image_url}")
                        return False
            except asyncio.TimeoutError:
                logging.debug(f"⏰ 异步HEAD超时: {image_url}")
            except Exception as e:
                logging.debug(f"异步HEAD请求失败: {e}")

            # 部分CDN不支持HEAD，回退到轻量GET + Range
            try:
                range_headers = headers.copy()
                range_headers['Range'] = 'bytes=0-0'
                async with self.session.get(
                    image_url,
                    headers=range_headers,
                    timeout=self.ASYNC_RANGE_TIMEOUT,
                    allow_redirects=True
                ) as resp:
                    if self._is_valid_image_response(resp.status, resp.headers, image_url, "异步GET"):
                        return True
                    if resp.status == 404:
                        logging.warning(f"❌ 图片不存在 (404): {image_url}")
                        return False
            except asyncio.TimeoutError:
                logging.debug(f"⏰ 异步GET超时: {image_url}")
            except Exception as e:
                logging.debug(f"异步GET请求失败: {e}")
            
            return None  # 异步验证失败，需要回退
            
        except Exception as e:
            logging.debug(f"异步验证异常: {e}")
            return None

    async def _validate_sync_fast_async(self, image_url: str, headers: dict) -> bool:
        """
        在线程池中执行同步回退，避免阻塞事件循环
        """
        async with self.sync_fallback_semaphore:
            return await asyncio.to_thread(self._validate_sync_fast, image_url, headers)
    
    def _validate_sync_fast(self, image_url: str, headers: dict) -> bool:
        """
        快速同步验证 - 5秒熔断
        """
        try:
            logging.info("🔄 执行快速同步验证...")
            
            # 快速HEAD请求 - 5秒超时
            try:
                resp = self.sync_session.head(
                    image_url,
                    headers=headers,
                    timeout=self.SYNC_TIMEOUT,
                    allow_redirects=True
                )
                if self._is_valid_image_response(resp.status_code, resp.headers, image_url, "同步HEAD"):
                    return True
                if resp.status_code == 404:
                    logging.warning(f"❌ 图片不存在 (404): {image_url}")
                    return False
            except requests.exceptions.Timeout:
                logging.debug(f"⏰ 同步HEAD超时: {image_url}")
            except Exception as e:
                logging.debug(f"同步HEAD请求失败: {e}")

            try:
                range_headers = headers.copy()
                range_headers['Range'] = 'bytes=0-0'
                resp = self.sync_session.get(
                    image_url,
                    headers=range_headers,
                    timeout=self.SYNC_TIMEOUT,
                    allow_redirects=True,
                    stream=True
                )
                try:
                    if self._is_valid_image_response(resp.status_code, resp.headers, image_url, "同步GET"):
                        return True
                    if resp.status_code == 404:
                        logging.warning(f"❌ 图片不存在 (404): {image_url}")
                        return False
                finally:
                    resp.close()
            except requests.exceptions.Timeout:
                logging.debug(f"⏰ 同步GET超时: {image_url}")
            except Exception as e:
                logging.debug(f"同步GET请求失败: {e}")
            
            logging.warning("❌ 快速同步验证失败")
            return False
            
        except Exception as e:
            logging.warning(f"⚠️ 快速同步验证异常: {e}")
            return False
    
    async def close(self):
        """关闭会话"""
        try:
            if self.session:
                await self.session.close()
                logging.info("✅ 异步会话已关闭")
            
            if self.sync_session:
                self.sync_session.close()
                logging.info("✅ 同步会话已关闭")
        except Exception as e:
            logging.warning(f"⚠️ 会话关闭异常: {e}")
