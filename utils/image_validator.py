"""
图片URL验证器 - 请求头伪装版
解决CDN防盗链问题，增加快速熔断机制
"""
import aiohttp
import asyncio
import logging
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
    
    def __init__(self):
        self.session = None
        self.sync_session = None
        
        # 初始化同步会话（回退机制）
        self.sync_session = requests.Session()
        self.sync_session.headers.update(self.DEFAULT_HEADERS)
        self.sync_session.verify = False  # 忽略SSL证书验证
        # 快速熔断 - 5秒超时
        self.sync_session.timeout = 5
    
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
                timeout = aiohttp.ClientTimeout(total=5, connect=3)
                
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
            sync_result = self._validate_sync_fast(image_url, headers)
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
                async with self.session.head(image_url, headers=headers, timeout=3) as resp:
                    if resp.status in [200, 206]:
                        # 快速大小检查
                        content_length = resp.headers.get('Content-Length')
                        if content_length:
                            file_size = int(content_length)
                            if file_size < 10240:  # 小于10KB视为无效图片
                                logging.warning(f"❌ 图片过小 ({file_size} bytes)，已丢弃: {image_url}")
                                return False
                            logging.info(f"✅ 快速HEAD验证成功 (大小: {file_size} bytes)")
                        else:
                            logging.info("✅ 快速HEAD验证成功 (大小未知)")
                        return True
                    elif resp.status == 403:
                        logging.warning(f"🚫 CDN拒绝访问 (403): {image_url}")
                        return False
                    elif resp.status == 404:
                        logging.warning(f"❌ 图片不存在 (404): {image_url}")
                        return False
            except asyncio.TimeoutError:
                logging.debug(f"⏰ 异步HEAD超时: {image_url}")
            except Exception as e:
                logging.debug(f"异步HEAD请求失败: {e}")
            
            return None  # 异步验证失败，需要回退
            
        except Exception as e:
            logging.debug(f"异步验证异常: {e}")
            return None
    
    def _validate_sync_fast(self, image_url: str, headers: dict) -> bool:
        """
        快速同步验证 - 5秒熔断
        """
        try:
            logging.info("🔄 执行快速同步验证...")
            
            # 快速HEAD请求 - 5秒超时
            try:
                resp = self.sync_session.head(image_url, headers=headers, timeout=5)
                if resp.status_code in [200, 206]:
                    # 快速大小检查
                    content_length = resp.headers.get('Content-Length')
                    if content_length:
                        file_size = int(content_length)
                        if file_size < 10240:
                            logging.warning(f"❌ 图片过小 ({file_size} bytes)，已丢弃: {image_url}")
                            return False
                        logging.info(f"✅ 快速同步验证成功 (大小: {file_size} bytes)")
                    else:
                        logging.info("✅ 快速同步验证成功 (大小未知)")
                    return True
                elif resp.status_code == 403:
                    logging.warning(f"🚫 CDN拒绝访问 (403): {image_url}")
                    return False
                elif resp.status_code == 404:
                    logging.warning(f"❌ 图片不存在 (404): {image_url}")
                    return False
            except requests.exceptions.Timeout:
                logging.debug(f"⏰ 同步HEAD超时: {image_url}")
            except Exception as e:
                logging.debug(f"同步HEAD请求失败: {e}")
            
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