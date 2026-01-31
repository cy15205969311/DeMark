"""
URL解析工具 - 处理各种分享链接格式
智能解析短链接并提取关键参数
"""
import re
import requests
from urllib.parse import urlparse, parse_qs, unquote
from typing import Dict, Optional, Tuple
import logging
import time

class URLParser:
    """
    URL解析器 - 将分享链接转换为可处理的URL
    支持短链接解析和参数提取
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        self.session.timeout = 10
    
    def parse_share_url(self, url: str) -> Dict:
        """
        解析分享链接，提取真实的图片页面URL
        优先处理短链接解析，确保获取完整参数
        """
        try:
            logging.info(f"🔍 开始解析分享链接: {url}")
            
            # 步骤1: 清理URL，移除多余文本
            clean_url = self._clean_url(url)
            logging.info(f"🧹 清理后URL: {clean_url}")
            
            # 步骤2: 检测平台类型
            platform = self._detect_platform(clean_url)
            logging.info(f"🎯 检测到平台: {platform}")
            
            # 步骤3: 智能短链接解析 (核心优化)
            if self._is_short_link(clean_url):
                logging.info("🔗 检测到短链接，开始解析...")
                resolved_result = self.resolve_short_link(clean_url)
                
                if resolved_result['success']:
                    logging.info(f"✅ 短链接解析成功: {resolved_result['final_url']}")
                    return {
                        'success': True,
                        'original_url': url,
                        'parsed_url': resolved_result['final_url'],
                        'platform': platform,
                        'type': 'short_link_resolved',
                        'pic_id': resolved_result.get('pic_id'),
                        'upic_id': resolved_result.get('upic_id'),
                        'redirect_chain': resolved_result.get('redirect_chain', [])
                    }
                else:
                    logging.warning(f"⚠️ 短链接解析失败: {resolved_result.get('error')}")
                    # 继续使用原URL，不中断流程
            
            # 步骤4: 平台特定解析
            if platform == "818ps":
                return self._parse_818ps_share_url(clean_url, url)
            elif platform == "Canva":
                return self._parse_canva_share_url(clean_url, url)
            elif platform == "Chuangkit":
                return self._parse_chuangkit_share_url(clean_url, url)
            elif platform == "抖音":
                return self._parse_douyin_share_url(clean_url, url)
            elif platform == "小红书":
                return self._parse_xiaohongshu_share_url(clean_url, url)
            else:
                # 尝试直接使用原URL
                return {
                    'success': True,
                    'original_url': url,
                    'parsed_url': clean_url,
                    'platform': 'Unknown',
                    'type': 'direct'
                }
                
        except Exception as e:
            logging.error(f"❌ URL解析失败: {e}")
            # 返回失败但不中断，让后续流程继续尝试
            return {
                'success': False,
                'error': str(e),
                'original_url': url,
                'fallback_url': url  # 提供回退URL
            }
    
    def resolve_short_link(self, url: str) -> Dict:
        """
        解析短链接，获取最终URL和关键参数
        这是核心的短链接解析逻辑
        """
        try:
            logging.info(f"🔗 开始解析短链接: {url}")
            redirect_chain = []
            
            # 方法1: 使用HEAD请求跟踪重定向 (更快，消耗更少带宽)
            try:
                response = self.session.head(url, allow_redirects=True, timeout=15)
                final_url = response.url
                redirect_chain = [resp.url for resp in response.history] + [final_url]
                
                logging.info(f"📍 HEAD重定向链: {' -> '.join(redirect_chain[-3:])}")  # 只显示最后3个
                
                # 从最终URL提取参数
                pic_id, upic_id = self._extract_ids_from_url(final_url)
                
                if pic_id and upic_id:
                    logging.info(f"✅ 从重定向URL提取到参数: picId={pic_id}, upicId={upic_id}")
                    return {
                        'success': True,
                        'final_url': final_url,
                        'pic_id': pic_id,
                        'upic_id': upic_id,
                        'redirect_chain': redirect_chain,
                        'method': 'head_redirect'
                    }
                
            except Exception as e:
                logging.warning(f"⚠️ HEAD请求失败: {e}")
            
            # 方法2: 使用GET请求获取页面内容 (回退方案)
            try:
                logging.info("🌐 尝试GET请求获取页面内容...")
                response = self.session.get(url, allow_redirects=True, timeout=15)
                final_url = response.url
                redirect_chain = [resp.url for resp in response.history] + [final_url]
                
                # 先尝试从URL提取参数
                pic_id, upic_id = self._extract_ids_from_url(final_url)
                
                if not (pic_id and upic_id):
                    # 从页面内容中提取参数
                    logging.info("🔍 从页面内容中搜索参数...")
                    pic_id, upic_id = self._extract_ids_from_content(response.text)
                
                if pic_id and upic_id:
                    logging.info(f"✅ 提取到参数: picId={pic_id}, upicId={upic_id}")
                    return {
                        'success': True,
                        'final_url': final_url,
                        'pic_id': pic_id,
                        'upic_id': upic_id,
                        'redirect_chain': redirect_chain,
                        'method': 'get_content'
                    }
                else:
                    # 即使没有提取到参数，也返回最终URL
                    logging.info("⚠️ 未提取到参数，但获得了最终URL")
                    return {
                        'success': True,
                        'final_url': final_url,
                        'pic_id': None,
                        'upic_id': None,
                        'redirect_chain': redirect_chain,
                        'method': 'get_no_params'
                    }
                    
            except Exception as e:
                logging.error(f"❌ GET请求也失败: {e}")
                return {
                    'success': False,
                    'error': f"所有解析方法都失败: {e}",
                    'original_url': url
                }
                
        except Exception as e:
            logging.error(f"❌ 短链接解析异常: {e}")
            return {
                'success': False,
                'error': str(e),
                'original_url': url
            }
    
    def _is_short_link(self, url: str) -> bool:
        """
        判断是否为短链接
        识别各种短链接格式
        """
        short_link_patterns = [
            r'818ps\.com/u/',           # 图怪兽用户分享链接
            r'tuguaishou\.com/u/',      # 图怪兽备用域名
            r'818ps\.com/s/',           # 可能的短链接格式
            r'bit\.ly/',                # 通用短链接
            r't\.cn/',                  # 微博短链接
            r'dwz\.cn/',                # 短网址
        ]
        
        url_lower = url.lower()
        for pattern in short_link_patterns:
            if re.search(pattern, url_lower):
                logging.info(f"🔗 匹配到短链接模式: {pattern}")
                return True
        
        return False
    
    def _extract_ids_from_url(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        从URL中提取picId和upicId
        支持多种URL格式
        """
        try:
            parsed_url = urlparse(url)
            params = parse_qs(parsed_url.query)
            
            # 方法1: 从查询参数中提取
            pic_id = params.get('picId', [None])[0]
            upic_id = params.get('upicId', [None])[0]
            
            if pic_id and upic_id:
                return pic_id, upic_id
            
            # 方法2: 从路径中提取 (如 /preview/123/456)
            path_match = re.search(r'/preview/(\d+)/(\d+)', parsed_url.path)
            if path_match:
                return path_match.group(1), path_match.group(2)
            
            # 方法3: 从fragment中提取
            if parsed_url.fragment:
                fragment_params = parse_qs(parsed_url.fragment)
                pic_id = fragment_params.get('picId', [None])[0]
                upic_id = fragment_params.get('upicId', [None])[0]
                if pic_id and upic_id:
                    return pic_id, upic_id
            
            return None, None
            
        except Exception as e:
            logging.warning(f"⚠️ URL参数提取失败: {e}")
            return None, None
    
    def _extract_ids_from_content(self, html_content: str) -> Tuple[Optional[str], Optional[str]]:
        """
        从HTML内容中提取picId和upicId
        使用多种正则表达式模式搜索
        """
        try:
            # 定义多种可能的参数模式
            patterns = [
                # JavaScript变量定义
                r'var\s+picId\s*=\s*["\'](\d+)["\']',
                r'var\s+upicId\s*=\s*["\'](\d+)["\']',
                r'picId\s*:\s*["\'](\d+)["\']',
                r'upicId\s*:\s*["\'](\d+)["\']',
                
                # JSON配置
                r'"picId"\s*:\s*["\']?(\d+)["\']?',
                r'"upicId"\s*:\s*["\']?(\d+)["\']?',
                
                # 数据属性
                r'data-pic-id\s*=\s*["\'](\d+)["\']',
                r'data-upic-id\s*=\s*["\'](\d+)["\']',
                
                # URL中的参数
                r'picId=(\d+)',
                r'upicId=(\d+)',
                
                # 其他可能的格式
                r'id\s*:\s*["\'](\d+)["\']',
                r'pic_id\s*:\s*["\'](\d+)["\']',
                r'upic_id\s*:\s*["\'](\d+)["\']',
            ]
            
            pic_id = None
            upic_id = None
            
            # 搜索picId
            for pattern in patterns:
                if 'pic' in pattern.lower() and 'upic' not in pattern.lower():
                    matches = re.findall(pattern, html_content, re.IGNORECASE)
                    if matches:
                        pic_id = matches[0]
                        logging.info(f"🎯 找到picId: {pic_id} (模式: {pattern})")
                        break
            
            # 搜索upicId
            for pattern in patterns:
                if 'upic' in pattern.lower():
                    matches = re.findall(pattern, html_content, re.IGNORECASE)
                    if matches:
                        upic_id = matches[0]
                        logging.info(f"🎯 找到upicId: {upic_id} (模式: {pattern})")
                        break
            
            # 如果还没找到upicId，尝试通用的id模式
            if pic_id and not upic_id:
                general_id_patterns = [
                    r'user_id["\']?\s*:\s*["\']?(\d+)["\']?',
                    r'userId["\']?\s*:\s*["\']?(\d+)["\']?',
                    r'"id"\s*:\s*["\']?(\d+)["\']?',
                ]
                
                for pattern in general_id_patterns:
                    matches = re.findall(pattern, html_content, re.IGNORECASE)
                    if matches:
                        upic_id = matches[0]
                        logging.info(f"🎯 找到upicId (通用模式): {upic_id}")
                        break
            
            return pic_id, upic_id
            
        except Exception as e:
            logging.warning(f"⚠️ 内容参数提取失败: {e}")
            return None, None
    
    def _clean_url(self, url: str) -> str:
        """清理URL，移除多余的文本"""
        # 移除中文描述文本
        url = re.sub(r'^[^http]*', '', url)
        
        # 提取第一个完整的HTTP URL
        http_match = re.search(r'https?://[^\s]+', url)
        if http_match:
            url = http_match.group(0)
        
        # URL解码
        url = unquote(url)
        
        return url.strip()
    
    def _detect_platform(self, url: str) -> str:
        """检测平台类型"""
        url_lower = url.lower()
        
        if '818ps.com' in url_lower or 'tuguaishou.com' in url_lower:
            return '818ps'
        elif 'canva.com' in url_lower or 'canva.cn' in url_lower:
            return 'Canva'
        elif 'chuangkit.com' in url_lower or 'chuangkit.cn' in url_lower:
            return 'Chuangkit'
        elif 'douyin.com' in url_lower or 'dy.com' in url_lower:
            return '抖音'
        elif 'xiaohongshu.com' in url_lower or 'xhs.com' in url_lower:
            return '小红书'
        else:
            return 'Unknown'
    
    def _parse_818ps_share_url(self, url: str, original_url: str) -> Dict:
        """解析818ps分享链接"""
        try:
            logging.info("🎨 解析图怪兽分享链接...")
            
            # 直接返回解析结果，让后续流程处理
            return {
                'success': True,
                'original_url': original_url,
                'parsed_url': url,
                'platform': '818ps',
                'type': 'direct'
            }
            
        except Exception as e:
            logging.error(f"❌ 818ps链接解析失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'original_url': original_url,
                'fallback_url': url
            }
    
    def _extract_preview_from_page(self, html_content: str) -> Optional[str]:
        """从页面内容中提取预览链接"""
        try:
            # 查找预览链接的模式
            patterns = [
                r'href="([^"]*preview[^"]*)"',
                r'"previewUrl":"([^"]*)"',
                r'preview\?[^"\']*picId=\d+[^"\']*',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html_content)
                if matches:
                    preview_url = matches[0]
                    if not preview_url.startswith('http'):
                        preview_url = 'https://818ps.com' + preview_url
                    return preview_url
            
            return None
            
        except Exception as e:
            logging.error(f"预览链接提取失败: {e}")
            return None
    
    def _parse_canva_share_url(self, url: str, original_url: str) -> Dict:
        """解析Canva分享链接"""
        return {
            'success': True,
            'original_url': original_url,
            'parsed_url': url,
            'platform': 'Canva',
            'type': 'direct'
        }
    
    def _parse_chuangkit_share_url(self, url: str, original_url: str) -> Dict:
        """解析创客贴分享链接"""
        return {
            'success': True,
            'original_url': original_url,
            'parsed_url': url,
            'platform': 'Chuangkit',
            'type': 'direct'
        }
    
    def _parse_douyin_share_url(self, url: str, original_url: str) -> Dict:
        """解析抖音分享链接"""
        return {
            'success': True,
            'original_url': original_url,
            'parsed_url': url,
            'platform': '抖音',
            'type': 'direct'
        }
    
    def _parse_xiaohongshu_share_url(self, url: str, original_url: str) -> Dict:
        """解析小红书分享链接"""
        return {
            'success': True,
            'original_url': original_url,
            'parsed_url': url,
            'platform': '小红书',
            'type': 'direct'
        }