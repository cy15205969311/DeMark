"""
创客贴 (Chuangkit) 爬虫 - 优化版
解决平台名称不匹配和评分过严问题
"""
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Dict, Optional, List
import logging
import sys
import os
import re
from urllib.parse import urlparse, urljoin

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.image_validator import ImageValidator

class ChuangkitCrawler:
    """创客贴爬虫 - 优化版"""
    
    def __init__(self):
        self.validator = ImageValidator()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.chuangkit.com/',
            'Cache-Control': 'no-cache'
        }
    
    async def extract_image(self, url: str, extracted_params: Optional[Dict] = None) -> Optional[Dict]:
        """提取创客贴图片 - 优化版"""
        session = None
        try:
            logging.info(f"🧩 开始创客贴抓取: {url}")
            
            # 识别链接类型
            link_type = 'share' if '/sharedesign' in url else 'design' if '/designs/' in url else 'template' if '/templates/' in url else 'other'
            logging.info(f"📋 链接类型: {link_type}")
            
            # 创建会话
            import socket
            connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=False)
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), connector=connector)
            
            # 静态抓取
            result = await self._static_scraping(session, url)
            if result:
                result['linkType'] = link_type
                return result
            
            # 动态抓取
            result = await self._dynamic_scraping(url, link_type)
            if result:
                return result
            
            return None
            
        except Exception as error:
            logging.error(f"❌ 创客贴抓取异常: {error}")
            return None
        finally:
            if session:
                await session.close()
    
    async def _static_scraping(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """静态抓取"""
        try:
            async with session.get(url, headers=self.headers) as response:
                if response.status != 200:
                    return None
                html_content = await response.text()
            
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Meta标签提取
            meta_selectors = [
                ('meta[property="og:image"]', 'content'),
                ('meta[name="twitter:image"]', 'content'),
                ('link[rel="image_src"]', 'href')
            ]
            
            for selector, attr in meta_selectors:
                element = soup.select_one(selector)
                if element and element.get(attr):
                    meta_img = element[attr]
                    if meta_img and meta_img.startswith('http'):
                        return {
                            'imageUrl': meta_img,
                            'platform': 'Chuangkit',
                            'source': 'meta',
                            'method': 'meta_extraction',
                            'original_url': url
                        }
            
            # DOM选择器提取
            selectors = [
                'img[src*="chuangkit"]',
                '.design-preview img',
                '.template-preview img',
                '.share-preview img'
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    img_src = element.get('src') or element.get('data-src')
                    if img_src:
                        image_url = img_src if img_src.startswith('http') else urljoin(url, img_src)
                        if 'chuangkit' in image_url.lower():
                            return {
                                'imageUrl': image_url,
                                'platform': 'Chuangkit',
                                'source': 'dom',
                                'method': 'dom_extraction',
                                'original_url': url
                            }
            
            return None
            
        except Exception as e:
            logging.debug(f"静态抓取失败: {e}")
            return None
    
    async def _dynamic_scraping(self, url: str, link_type: str) -> Optional[Dict]:
        """动态抓取 - 降低评分阈值"""
        try:
            from core.browser_service import BrowserService
            browser_service = BrowserService()
            
            images = await browser_service.extract_images_from_page(url, headless=True)
            
            if images:
                logging.info(f"📊 找到 {len(images)} 个图片")
                
                # 评分所有图片
                scored_images = []
                for img in images:
                    if img.get('src'):
                        score = self._calculate_score(img)
                        scored_images.append({'data': img, 'score': score})
                        logging.info(f"🎯 图片评分: {img.get('src', '')[:50]}... → {score}分")
                
                # 按评分排序
                scored_images.sort(key=lambda x: x['score'], reverse=True)
                
                # 使用更宽松的阈值
                for candidate in scored_images:
                    if candidate['score'] > 100:  # 大幅降低阈值
                        best_image = candidate
                        logging.info(f"✅ 选择图片 (评分: {best_image['score']})")
                        
                        return {
                            'imageUrl': best_image['data']['src'],
                            'platform': 'Chuangkit',
                            'source': 'selenium-extraction',
                            'method': 'dynamic_extraction',
                            'score': best_image['score'],
                            'linkType': link_type,
                            'original_url': url
                        }
                
                logging.info(f"📊 所有图片评分都低于100分，最高分: {scored_images[0]['score'] if scored_images else 0}")
            
            await browser_service.close()
            return None
            
        except Exception as e:
            logging.debug(f"动态抓取失败: {e}")
            return None
    
    def _calculate_score(self, img_data: Dict) -> int:
        """计算图片评分 - 宽松版"""
        score = 100  # 基础分数
        
        # 尺寸评分
        width = img_data.get('width', 0)
        height = img_data.get('height', 0)
        
        if width > 100 and height > 100:
            score += 200
        if width > 200 and height > 200:
            score += 300
        
        # URL评分
        src = img_data.get('src', '').lower()
        if 'chuangkit' in src:
            score += 500
        if any(keyword in src for keyword in ['design', 'template', 'work', 'preview']):
            score += 300
        if any(keyword in src for keyword in ['main', 'primary']):
            score += 200
        
        # 图片类型加分
        img_type = img_data.get('type', '')
        if img_type == 'background':
            score += 150
        elif img_type == 'canvas':
            score += 200
        
        return score
    
    async def close(self):
        """关闭资源"""
        if self.validator:
            await self.validator.close()