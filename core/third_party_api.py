"""
第三方API网关 - 统一接入多个去水印API
支持多API fallback、缓存、速率限制
"""
import aiohttp
import asyncio
from typing import Dict, Optional, List
import json
import time
import logging
from config.settings import Settings

class ThirdPartyAPIGateway:
    """
    第三方API网关 - 统一接入多个去水印API
    支持多API fallback、缓存、速率限制
    """
    
    def __init__(self):
        self.apis = [
            {
                'name': 'TSGPT',
                'base_url': 'https://kk.tsgpt.top/tgs/info/',
                'token': 'OflDpfIKZrH8',  # 从Node.js配置复制
                'enabled': True,
                'priority': 1
            },
            # 可添加更多API
        ]
        self.cache = {}
        self.session = None
    
    async def extract_with_cache(self, target_url: str, platform: str) -> Optional[Dict]:
        """带缓存的提取函数"""
        cache_key = f"{platform}:{target_url}"
        
        # 检查缓存
        if cache_key in self.cache:
            cache_data = self.cache[cache_key]
            if time.time() - cache_data['timestamp'] < Settings.CACHE_TTL:
                logging.info("📦 从缓存返回结果")
                return cache_data['data']
        
        # 调用API
        result = await self._call_apis(target_url, platform)
        
        # 缓存成功结果
        if result and result.get('success'):
            self.cache[cache_key] = {
                'data': result,
                'timestamp': time.time()
            }
        
        return result
    
    async def _call_apis(self, target_url: str, platform: str) -> Optional[Dict]:
        """依次调用API直到成功"""
        logging.info(f"🌐 启动第三方API网关，平台: {platform}")
        
        # 按优先级排序
        sorted_apis = sorted(self.apis, key=lambda x: x['priority'])
        
        for api in sorted_apis:
            if not api['enabled']:
                continue
                
            try:
                result = await self._call_tsgpt_api(target_url, api)
                if result and result.get('success'):
                    logging.info(f"✅ {api['name']} API成功")
                    return result
            except Exception as e:
                logging.warning(f"❌ {api['name']} API失败: {e}")
        
        logging.info("❌ 所有第三方API都失败了")
        return None
    
    async def _call_tsgpt_api(self, target_url: str, api_config: Dict) -> Optional[Dict]:
        """
        调用TSGPT API - 完全对应Node.js版本
        增加Content-Type检查，防止HTML响应导致JSON解析错误
        """
        if self.session and self.session.closed:
            self.session = None

        if not self.session:
            self.session = aiohttp.ClientSession()
        
        # 先尝试GET请求
        try:
            get_url = f"{api_config['base_url']}?token={api_config['token']}&url={target_url}"
            logging.info(f"🌐 调用TSGPT API (GET): {get_url}")
            
            async with self.session.get(get_url, timeout=10) as resp:
                if resp.status == 200:
                    # 关键修复: 检查Content-Type
                    content_type = resp.headers.get('Content-Type', '').lower()
                    logging.info(f"📋 响应Content-Type: {content_type}")
                    
                    if 'text/html' in content_type:
                        logging.warning("⚠️ API返回HTML而非JSON，可能是错误页面或重定向")
                        return None  # 不抛出异常，让流程继续
                    
                    if 'application/json' in content_type or 'json' in content_type:
                        try:
                            data = await resp.json()
                            image_url = data.get('image') or data.get('imageUrl') or data.get('url')
                            if image_url:
                                logging.info(f"✅ TSGPT API (GET) 成功返回: {image_url}")
                                return {
                                    'success': True,
                                    'imageUrl': image_url,
                                    'provider': api_config['name'],
                                    'source': 'thirdparty-get'
                                }
                        except Exception as json_error:
                            logging.warning(f"⚠️ JSON解析失败: {json_error}")
                            return None
                    else:
                        logging.warning(f"⚠️ 不支持的Content-Type: {content_type}")
                        return None
                else:
                    logging.warning(f"⚠️ API响应状态异常: {resp.status}")
                    
        except Exception as e:
            logging.warning(f"⚠️ GET请求失败: {e}")
        
        # 再尝试POST请求
        try:
            post_data = {
                'token': api_config['token'],
                'url': target_url
            }
            logging.info(f"🌐 调用TSGPT API (POST): {api_config['base_url']}")
            
            async with self.session.post(api_config['base_url'], json=post_data, timeout=10) as resp:
                if resp.status == 200:
                    # 同样检查Content-Type
                    content_type = resp.headers.get('Content-Type', '').lower()
                    logging.info(f"📋 响应Content-Type: {content_type}")
                    
                    if 'text/html' in content_type:
                        logging.warning("⚠️ API返回HTML而非JSON，可能是错误页面或重定向")
                        return None
                    
                    if 'application/json' in content_type or 'json' in content_type:
                        try:
                            data = await resp.json()
                            image_url = data.get('image') or data.get('imageUrl') or data.get('url')
                            if image_url:
                                logging.info(f"✅ TSGPT API (POST) 成功返回: {image_url}")
                                return {
                                    'success': True,
                                    'imageUrl': image_url,
                                    'provider': api_config['name'],
                                    'source': 'thirdparty-post'
                                }
                        except Exception as json_error:
                            logging.warning(f"⚠️ JSON解析失败: {json_error}")
                            return None
                    else:
                        logging.warning(f"⚠️ 不支持的Content-Type: {content_type}")
                        return None
                else:
                    logging.warning(f"⚠️ API响应状态异常: {resp.status}")
                    
        except Exception as e:
            logging.warning(f"⚠️ POST请求失败: {e}")
        
        logging.info("❌ TSGPT API所有方法都失败")
        return None
    
    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.close()
            self.session = None
