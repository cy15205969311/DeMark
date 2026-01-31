"""
配置管理类 - 基于Node.js成功配置
"""
import os
from typing import Dict, List

class Settings:
    """
    配置管理类 - 基于Node.js成功配置
    """
    
    # ========== 网络配置 ==========
    REQUEST_TIMEOUT = 10
    MAX_RETRIES = 3
    CONCURRENT_REQUESTS = 5
    
    # 通用请求头 (对应Node.js COMMON_HEADERS)
    COMMON_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    
    # ========== 第三方API配置 ==========
    # 对应Node.js的thirdPartyApiGateway.js配置
    THIRD_PARTY_APIS = {
        'tsgpt': {
            'name': 'TSGPT',
            'base_url': 'https://kk.tsgpt.top/tgs/info/',
            'token': os.getenv('TSGPT_TOKEN', 'OflDpfIKZrH8'),
            'enabled': True,
            'priority': 1,
            'timeout': 10
        },
        'rapidapi': {
            'name': 'RapidAPI',
            'base_url': 'https://api.rapidapi.com/watermark-remover',
            'key': os.getenv('RAPIDAPI_KEY', ''),
            'enabled': False,
            'priority': 2,
            'timeout': 15
        }
    }
    
    # ========== 下载配置 ==========
    DOWNLOAD_PATH = "./downloads"
    THUMBNAIL_SIZE = (200, 150)
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    
    # ========== 缓存配置 ==========
    CACHE_TTL = 3600  # 1小时 (对应Node.js的CACHE_TTL)
    CACHE_MAX_SIZE = 1000  # 最大缓存条目数
    
    # ========== Selenium配置 ==========
    SELENIUM_TIMEOUT = 30
    SELENIUM_IMPLICIT_WAIT = 10
    SELENIUM_PAGE_LOAD_TIMEOUT = 30
    
    # Chrome选项 (对应Node.js puppeteer配置)
    CHROME_OPTIONS = [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--disable-extensions',
        '--disable-plugins',
        '--disable-images',  # 性能优化
        '--disable-blink-features=AutomationControlled',
    ]
    
    # ========== 反爬虫配置 ==========
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    
    # 请求间隔配置
    REQUEST_DELAY_RANGE = (1, 3)  # 随机延迟1-3秒
    BATCH_DELAY_RANGE = (2, 5)   # 批量处理延迟2-5秒
    
    # ========== 平台特定配置 ==========
    PLATFORM_CONFIGS = {
        '818ps': {
            'base_domains': ['818ps.com', 'tuguaishou.com'],
            'image_domains': ['img.818ps.com', 'cdn.818ps.com', 'static.818ps.com'],
            'referer': 'https://818ps.com/',
            'origin': 'https://818ps.com',
            'selectors': [
                '.detail-img-box',
                '.work-image', 
                '.preview-image',
                '#showImg',
                '.image-preview'
            ]
        },
        'Canva': {
            'base_domains': ['canva.com'],
            'referer': 'https://www.canva.com/',
            'origin': 'https://www.canva.com',
            'selectors': [
                '.page-view',
                '.design',
                '.page',
                '.canvas-container'
            ]
        },
        '创可贴': {
            'base_domains': ['chuangkit.com'],
            'referer': 'https://www.chuangkit.com/',
            'origin': 'https://www.chuangkit.com',
            'selectors': [
                '.canvas',
                '.main-canvas',
                '.design-canvas',
                '.preview-image'
            ]
        }
    }
    
    # ========== 图片评分配置 ==========
    # 对应Node.js的scoreUrl函数配置
    IMAGE_SCORE_CONFIG = {
        'prefer_keywords': [
            'preview', 'cover', 'main', 'banner', 'poster', 
            'detail', 'work', 'showimg', 'l2000', 'l3000', 
            'origin', 'big'
        ],
        'exclude_keywords': [
            'favicon', 'sprite', 'icon', 'avatar', 'tracking',
            'thumb', 'small', 'min', 'svg', 'watermark'
        ],
        'tuguaishou_prefer': [
            'user_preview_ue', 'ips_user_preview_api', 'user_preview'
        ],
        'tuguaishou_exclude': [
            'designer_upload_asset', 'element', 'asset'
        ]
    }
    
    # ========== 日志配置 ==========
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FILE = 'crawler.log'
    
    @classmethod
    def get_platform_config(cls, platform: str) -> Dict:
        """获取平台特定配置"""
        return cls.PLATFORM_CONFIGS.get(platform, {})
    
    @classmethod
    def get_api_config(cls, api_name: str) -> Dict:
        """获取API配置"""
        return cls.THIRD_PARTY_APIS.get(api_name, {})
    
    @classmethod
    def is_api_enabled(cls, api_name: str) -> bool:
        """检查API是否启用"""
        config = cls.get_api_config(api_name)
        return config.get('enabled', False)