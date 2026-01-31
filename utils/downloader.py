"""
图片下载器 - 支持多种下载方式和进度跟踪
"""
import aiohttp
import asyncio
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Callable
from urllib.parse import urlparse
import hashlib
import time
from datetime import datetime

class ImageDownloader:
    """
    图片下载器 - 支持断点续传、进度回调、文件验证
    """
    
    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.session = None
        
    async def download_image(
        self, 
        image_url: str, 
        filename: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        platform: str = "Unknown"
    ) -> Dict:
        """
        下载图片
        
        Args:
            image_url: 图片URL
            filename: 自定义文件名（可选）
            progress_callback: 进度回调函数
            platform: 平台名称
        
        Returns:
            下载结果字典
        """
        try:
            logging.info(f"📥 开始下载图片: {image_url}")
            
            # 创建会话
            if not self.session:
                self.session = await self._create_session()
            
            # 生成文件名
            if not filename:
                filename = self._generate_filename(image_url, platform)
            
            file_path = self.download_dir / filename
            
            # 检查文件是否已存在
            if file_path.exists():
                logging.info(f"📁 文件已存在: {file_path}")
                return {
                    'success': True,
                    'file_path': str(file_path),
                    'filename': filename,
                    'size': file_path.stat().st_size,
                    'status': 'already_exists'
                }
            
            # 下载文件
            download_result = await self._download_with_progress(
                image_url, file_path, progress_callback
            )
            
            if download_result['success']:
                logging.info(f"✅ 下载完成: {file_path} ({download_result['size']} bytes)")
                return {
                    'success': True,
                    'file_path': str(file_path),
                    'filename': filename,
                    'size': download_result['size'],
                    'status': 'downloaded',
                    'download_time': download_result.get('download_time', 0)
                }
            else:
                logging.error(f"❌ 下载失败: {download_result.get('error', 'Unknown error')}")
                return {
                    'success': False,
                    'error': download_result.get('error', 'Download failed'),
                    'status': 'failed'
                }
                
        except Exception as e:
            logging.error(f"❌ 下载异常: {e}")
            return {
                'success': False,
                'error': str(e),
                'status': 'error'
            }
    
    async def _create_session(self) -> aiohttp.ClientSession:
        """创建下载会话"""
        import socket
        
        connector = aiohttp.TCPConnector(
            family=socket.AF_INET,
            ssl=False,
            limit=50,
            limit_per_host=10,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30
        )
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        }
        
        return aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60, connect=10),
            connector=connector,
            headers=headers
        )
    
    def _generate_filename(self, image_url: str, platform: str) -> str:
        """
        生成文件名
        格式: {platform}_{timestamp}_{hash}.{ext}
        """
        try:
            # 解析URL获取扩展名
            parsed_url = urlparse(image_url)
            path = parsed_url.path
            
            # 提取扩展名
            ext = Path(path).suffix.lower()
            if not ext or ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                ext = '.jpg'  # 默认扩展名
            
            # 生成时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 生成URL哈希（用于唯一性）
            url_hash = hashlib.md5(image_url.encode()).hexdigest()[:8]
            
            # 组合文件名
            filename = f"{platform}_{timestamp}_{url_hash}{ext}"
            
            # 确保文件名安全
            filename = self._sanitize_filename(filename)
            
            return filename
            
        except Exception as e:
            logging.warning(f"⚠️ 文件名生成失败，使用默认名称: {e}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"{platform}_{timestamp}.jpg"
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除非法字符"""
        import re
        
        # 移除或替换非法字符
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        # 限制文件名长度
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:190] + ext
        
        return filename
    
    async def _download_with_progress(
        self, 
        url: str, 
        file_path: Path, 
        progress_callback: Optional[Callable]
    ) -> Dict:
        """
        带进度的下载
        """
        start_time = time.time()
        
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    return {
                        'success': False,
                        'error': f'HTTP {response.status}: {response.reason}'
                    }
                
                # 获取文件大小
                total_size = int(response.headers.get('Content-Length', 0))
                
                # 检查内容类型
                content_type = response.headers.get('Content-Type', '').lower()
                if not any(img_type in content_type for img_type in ['image/', 'application/octet-stream']):
                    logging.warning(f"⚠️ 可能不是图片文件: {content_type}")
                
                downloaded_size = 0
                
                # 创建临时文件
                temp_file_path = file_path.with_suffix(file_path.suffix + '.tmp')
                
                try:
                    with open(temp_file_path, 'wb') as file:
                        async for chunk in response.content.iter_chunked(8192):
                            file.write(chunk)
                            downloaded_size += len(chunk)
                            
                            # 调用进度回调
                            if progress_callback and total_size > 0:
                                progress = (downloaded_size / total_size) * 100
                                progress_callback(progress, downloaded_size, total_size)
                    
                    # 验证下载完整性
                    if total_size > 0 and downloaded_size != total_size:
                        logging.warning(f"⚠️ 文件大小不匹配: 期望 {total_size}, 实际 {downloaded_size}")
                    
                    # 验证文件最小大小（避免下载到错误页面）
                    if downloaded_size < 1024:  # 小于1KB
                        return {
                            'success': False,
                            'error': f'文件过小 ({downloaded_size} bytes)，可能不是有效图片'
                        }
                    
                    # 重命名临时文件
                    temp_file_path.rename(file_path)
                    
                    download_time = time.time() - start_time
                    
                    return {
                        'success': True,
                        'size': downloaded_size,
                        'download_time': download_time
                    }
                    
                except Exception as e:
                    # 清理临时文件
                    if temp_file_path.exists():
                        temp_file_path.unlink()
                    raise e
                    
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def batch_download(
        self, 
        image_urls: list, 
        progress_callback: Optional[Callable] = None,
        platform: str = "Unknown",
        max_concurrent: int = 3
    ) -> Dict:
        """
        批量下载图片
        
        Args:
            image_urls: 图片URL列表
            progress_callback: 进度回调函数
            platform: 平台名称
            max_concurrent: 最大并发数
        
        Returns:
            批量下载结果
        """
        try:
            logging.info(f"📦 开始批量下载 {len(image_urls)} 张图片")
            
            if not self.session:
                self.session = await self._create_session()
            
            # 限制并发数
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def download_single(url, index):
                async with semaphore:
                    result = await self.download_image(url, platform=platform)
                    if progress_callback:
                        progress_callback(index + 1, len(image_urls), result)
                    return result
            
            # 并发下载
            tasks = [download_single(url, i) for i, url in enumerate(image_urls)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 统计结果
            successful = sum(1 for r in results if isinstance(r, dict) and r.get('success'))
            failed = len(results) - successful
            
            logging.info(f"📊 批量下载完成: 成功 {successful}, 失败 {failed}")
            
            return {
                'success': True,
                'total': len(image_urls),
                'successful': successful,
                'failed': failed,
                'results': results
            }
            
        except Exception as e:
            logging.error(f"❌ 批量下载异常: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def close(self):
        """关闭下载器"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def get_download_stats(self) -> Dict:
        """获取下载统计信息"""
        try:
            download_files = list(self.download_dir.glob('*'))
            total_files = len(download_files)
            total_size = sum(f.stat().st_size for f in download_files if f.is_file())
            
            return {
                'total_files': total_files,
                'total_size': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'download_dir': str(self.download_dir)
            }
            
        except Exception as e:
            logging.error(f"❌ 获取下载统计失败: {e}")
            return {
                'total_files': 0,
                'total_size': 0,
                'total_size_mb': 0,
                'download_dir': str(self.download_dir)
            }