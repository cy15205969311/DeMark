"""
无水印URL变体生成器
基于Node.js成功实践的buildNoWatermarkVariants函数
"""
import re
from typing import List, Set
from urllib.parse import urlparse, parse_qs

class VariantBuilder:
    """
    无水印URL变体生成器
    基于Node.js成功实践的buildNoWatermarkVariants函数
    """
    
    @staticmethod
    def build_818ps_variants(url: str) -> List[str]:
        """
        构建818ps/图怪兽无水印变体
        完全对应Node.js的buildNoWatermarkVariants函数
        """
        variants = set()
        if not url or not isinstance(url, str):
            return []
        
        # 分离URL和查询参数
        base_url = url.split('?')[0]
        query = url[url.find('?'):] if '?' in url else ''
        
        # 去除尾部强制尺寸/样式后缀
        variants.add(re.sub(r'!l\d+(_b)?$', '', base_url, flags=re.IGNORECASE))
        variants.add(re.sub(r'!\w+$', '', base_url, flags=re.IGNORECASE))
        
        # 替换预览路径到可能的原图路径
        variants.add(base_url.replace('ips_user_preview_api/', 'pic/'))
        variants.add(base_url.replace('user_preview_ue/', 'pic/'))
        variants.add(base_url.replace('preview', 'origin'))
        variants.add(base_url.replace('psd_import/', 'pic/'))
        
        # 统一扩展名尝试
        base_no_ext = re.sub(r'\.(jpeg|jpg|png|webp)(!.*)?$', '', base_url, flags=re.IGNORECASE)
        for ext in ['.png', '.jpg', '.jpeg', '.webp']:
            variants.add(base_no_ext + ext)
        
        # 恢复查询参数
        result = list(variants)
        if query:
            result.extend([v + query for v in variants])
        
        return list(set(result))  # 去重
    
    @staticmethod
    def build_canva_variants(url: str) -> List[str]:
        """构建Canva无水印变体"""
        variants = set()
        if not url or not isinstance(url, str):
            return []
        
        base_url = url.split('?')[0]
        query = url[url.find('?'):] if '?' in url else ''
        
        # 去除裁剪/尺寸参数
        variants.add(re.sub(r'-(?:\d+x\d+)|\?[^#]*$', '', base_url, flags=re.IGNORECASE))
        
        # 缩略图到原图替换
        variants.add(base_url.replace('thumbnail', 'original'))
        variants.add(base_url.replace('thumb', 'original'))
        variants.add(base_url.replace('small', 'original'))
        variants.add(base_url.replace('preview', 'original'))
        
        # 扩展名尝试
        base_no_ext = re.sub(r'\.(jpeg|jpg|png|webp)(?:\?.*)?$', '', base_url, flags=re.IGNORECASE)
        for ext in ['.png', '.jpg', '.jpeg', '.webp']:
            variants.add(base_no_ext + ext)
        
        result = list(variants)
        if query:
            result.extend([v + query for v in variants])
        
        return list(set(result))
    
    @staticmethod
    def build_chuangkit_variants(url: str) -> List[str]:
        """构建创可贴无水印变体"""
        variants = set()
        if not url or not isinstance(url, str):
            return []
        
        base_url = url.split('?')[0]
        query = url[url.find('?'):] if '?' in url else ''
        
        # 去除尺寸参数
        variants.add(re.sub(r'_\d+x\d+', '', base_url))
        variants.add(re.sub(r'@\d+w_\d+h', '', base_url))
        
        # 替换预览到原图
        variants.add(base_url.replace('thumb', 'origin'))
        variants.add(base_url.replace('preview', 'origin'))
        
        result = list(variants)
        if query:
            result.extend([v + query for v in variants])
        
        return list(set(result))