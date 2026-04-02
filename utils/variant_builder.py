"""
无水印 URL 变体生成器
基于 Node.js 成功实践中的 buildNoWatermarkVariants 思路
"""
import re
from typing import List


class VariantBuilder:
    """
    无水印 URL 变体生成器
    基于 Node.js 成功实践中的 buildNoWatermarkVariants 思路
    """

    @staticmethod
    def _dedupe_keep_order(items: List[str]) -> List[str]:
        seen = set()
        ordered: List[str] = []

        for item in items or []:
            if not isinstance(item, str):
                continue
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)

        return ordered

    @staticmethod
    def build_818ps_variants(url: str) -> List[str]:
        """
        构建 818ps / 图怪兽无水印变体
        与 Node 侧 build818psVariants 的顺序保持一致
        """
        if not url or not isinstance(url, str):
            return []

        base_url = url.split('?', 1)[0]
        query = url[url.find('?'):] if '?' in url else ''

        variants = [
            re.sub(r'!l\d+(_b)?$', '', base_url, flags=re.IGNORECASE),
            re.sub(r'!\w+$', '', base_url, flags=re.IGNORECASE),
            base_url.replace('ips_user_preview_api/', 'pic/'),
            base_url.replace('user_preview_ue/', 'pic/'),
            base_url.replace('preview', 'origin'),
            base_url.replace('psd_import/', 'pic/'),
        ]

        base_no_ext = re.sub(r'\.(jpeg|jpg|png|webp)(!.*)?$', '', base_url, flags=re.IGNORECASE)
        for ext in ['.png', '.jpg', '.jpeg', '.webp']:
            variants.append(base_no_ext + ext)

        variants = VariantBuilder._dedupe_keep_order(variants)
        if query:
            variants = VariantBuilder._dedupe_keep_order(
                variants + [variant + query for variant in variants]
            )

        return variants

    @staticmethod
    def build_canva_variants(url: str) -> List[str]:
        """构建 Canva 无水印变体"""
        variants = set()
        if not url or not isinstance(url, str):
            return []

        base_url = url.split('?')[0]
        query = url[url.find('?'):] if '?' in url else ''

        variants.add(re.sub(r'-(?:\d+x\d+)|\?[^#]*$', '', base_url, flags=re.IGNORECASE))
        variants.add(base_url.replace('thumbnail', 'original'))
        variants.add(base_url.replace('thumb', 'original'))
        variants.add(base_url.replace('small', 'original'))
        variants.add(base_url.replace('preview', 'original'))

        base_no_ext = re.sub(r'\.(jpeg|jpg|png|webp)(?:\?.*)?$', '', base_url, flags=re.IGNORECASE)
        for ext in ['.png', '.jpg', '.jpeg', '.webp']:
            variants.add(base_no_ext + ext)

        result = list(variants)
        if query:
            result.extend([v + query for v in variants])

        return list(set(result))

    @staticmethod
    def build_chuangkit_variants(url: str) -> List[str]:
        """构建创客贴无水印变体"""
        variants = set()
        if not url or not isinstance(url, str):
            return []

        base_url = url.split('?')[0]
        query = url[url.find('?'):] if '?' in url else ''

        variants.add(re.sub(r'_\d+x\d+', '', base_url))
        variants.add(re.sub(r'@\d+w_\d+h', '', base_url))
        variants.add(base_url.replace('thumb', 'origin'))
        variants.add(base_url.replace('preview', 'origin'))

        result = list(variants)
        if query:
            result.extend([v + query for v in variants])

        return list(set(result))
