"""
图怪兽/818ps爬虫 - 增强版
支持短链接解析、源码正则回退机制、多重验证策略
"""
import re
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from typing import Dict, Optional, List, Tuple
import logging
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.image_validator import ImageValidator
from utils.variant_builder import VariantBuilder

class Tuguaishou818psCrawler:
    """
    图怪兽/818ps爬虫 - 增强版
    完全对应Node.js的extract818psImage函数，并增加鲁棒性
    """
    
    def __init__(self):
        self.validator = ImageValidator()
        self.variant_builder = VariantBuilder()
        self.session = None
        
        # 请求头配置 - 模拟真实浏览器
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://818ps.com/',
            'Origin': 'https://818ps.com',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Upgrade-Insecure-Requests': '1'
        }

    async def _ensure_session(self):
        """确保 aiohttp 会话可用"""
        if self.session and not self.session.closed:
            return

        if self.session and self.session.closed:
            self.session = None

        if not self.session:
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=30)
            )

    def _extract_share_query_params(self, url: str) -> Dict[str, Optional[str]]:
        """从分享链接中提取常用查询参数。"""
        parsed_url = urlparse(url)
        params = parse_qs(parsed_url.query)
        return {
            'pic_id': params.get('picId', [None])[0],
            'upic_id': params.get('upicId', [None])[0],
            'share_id': params.get('share_id', [None])[0],
            'share_uid': params.get('share_uid', [None])[0],
            'save_type': params.get('save_type', [''])[0],
            'user_source': params.get('user_source', [''])[0],
        }

    async def _fetch_json(self, url: str, referer: Optional[str] = None) -> Optional[Dict]:
        """统一发起 JSON 请求。"""
        await self._ensure_session()

        request_headers = {
            'Accept': 'application/json, text/plain, */*',
            'Referer': referer or 'https://ue.818ps.com/',
            'Origin': 'https://818ps.com',
        }

        try:
            async with self.session.get(url, headers=request_headers, timeout=15) as response:
                if response.status != 200:
                    logging.warning(f"⚠️ 分享API响应异常 ({response.status}): {url}")
                    return None

                return await response.json(content_type=None)
        except Exception as error:
            logging.warning(f"⚠️ 分享API请求失败: {url} ({error})")
            return None

    def _extract_expected_page_count_from_share_api_payloads(self, payloads: Dict[str, Dict]) -> int:
        """根据多个分享 API 响应推断设计稿页数。"""
        counts: List[int] = []

        share_template = payloads.get('share_template') or {}
        share_template_data = share_template.get('data') if isinstance(share_template, dict) else None
        if isinstance(share_template_data, dict):
            preview_urls = share_template_data.get('preview')
            if isinstance(preview_urls, list):
                counts.append(len(preview_urls))

        team_share_payload = payloads.get('team_share_get_templ') or {}
        if isinstance(team_share_payload, dict):
            page_map = team_share_payload.get('page_map')
            if isinstance(page_map, dict):
                counts.append(len(page_map))

            preview_urls = team_share_payload.get('preview')
            if isinstance(preview_urls, list):
                counts.append(len(preview_urls))

            doc = team_share_payload.get('doc')
            if isinstance(doc, dict):
                page_attr = doc.get('pageAttr')
                if isinstance(page_attr, dict):
                    page_info = page_attr.get('pageInfo')
                    if isinstance(page_info, list):
                        counts.append(len(page_info))

        page_data_payload = payloads.get('get_template_page_data') or {}
        if isinstance(page_data_payload, dict):
            preview_wrapper = page_data_payload.get('url')
            if isinstance(preview_wrapper, dict):
                preview_items = preview_wrapper.get('preview')
                if isinstance(preview_items, list):
                    counts.append(len(preview_items))

        counts = [count for count in counts if count > 0]
        return max(counts, default=0)

    def _build_share_preview_first_page_candidate(self, url: str) -> Optional[str]:
        normalized_url = self._normalize_dynamic_candidate_url(url)
        if not normalized_url:
            return None

        match = re.match(
            r'^(.*?_\d+)_1(\.(?:jpg|jpeg|png|webp))(.*)$',
            normalized_url,
            re.IGNORECASE
        )
        if not match:
            return None

        return f"{match.group(1)}{match.group(2)}{match.group(3)}"

    def _augment_share_preview_group(self, urls: List[str], expected_page_count: int) -> List[str]:
        normalized_urls = self._normalize_share_preview_group(urls)
        if not normalized_urls:
            return []

        if expected_page_count != len(normalized_urls) + 1:
            return normalized_urls

        inferred_pages: List[int] = []
        for preview_url in normalized_urls:
            page_number = self._extract_url_page_number(preview_url) or self._extract_818ps_preview_page_number(preview_url)
            if page_number is None:
                return normalized_urls
            inferred_pages.append(page_number)

        if inferred_pages != list(range(2, len(normalized_urls) + 2)):
            return normalized_urls

        first_page_candidate = self._build_share_preview_first_page_candidate(normalized_urls[0])
        if not first_page_candidate:
            return normalized_urls

        return self._sort_urls_by_page_token(
            self._dedupe_keep_order([first_page_candidate] + normalized_urls)
        )

    def _build_818ps_variant_candidates(self, image_url: str, prefer_variants: bool = False) -> List[str]:
        normalized_url = self._normalize_dynamic_candidate_url(image_url)
        if not normalized_url:
            return []

        variants = [
            self._normalize_dynamic_candidate_url(variant)
            for variant in self.variant_builder.build_818ps_variants(normalized_url)
        ]
        variants = [variant for variant in variants if variant]

        ordered_candidates = variants + [normalized_url] if prefer_variants else [normalized_url] + variants
        return self._dedupe_keep_order(ordered_candidates)

    async def _resolve_818ps_entry_url(self, image_url: str, prefer_variants: bool = False) -> Optional[str]:
        normalized_url = self._normalize_dynamic_candidate_url(image_url)
        if not normalized_url:
            return None

        for candidate_url in self._build_818ps_variant_candidates(normalized_url, prefer_variants=prefer_variants):
            if await self.validator.validate_image_url(candidate_url):
                if candidate_url != normalized_url:
                    logging.info(f"✅ 818ps 分享页已命中去水印候选: {candidate_url}")
                return candidate_url

        return None

    async def _resolve_818ps_image_entry_urls(self, entries: List[Dict], prefer_variants: bool = False) -> List[str]:
        if not entries:
            return []

        results = await asyncio.gather(
            *(
                self._resolve_818ps_entry_url(entry.get('url'), prefer_variants=prefer_variants)
                for entry in entries
            ),
            return_exceptions=True
        )

        valid_urls: List[str] = []
        seen = set()
        for resolved_url in results:
            if isinstance(resolved_url, Exception):
                continue

            normalized_url = self._normalize_dynamic_candidate_url(resolved_url)
            if normalized_url and normalized_url not in seen:
                valid_urls.append(normalized_url)
                seen.add(normalized_url)

        return self._sort_urls_by_page_token(valid_urls)

    def _share_api_source_priority(self, source_name: str) -> int:
        priorities = {
            'share_template': 3,
            'get_template_page_data': 2,
            'team_share_get_templ': 1,
        }
        return priorities.get(source_name, 0)

    def _normalize_share_preview_group(self, urls: List[str]) -> List[str]:
        """规范化并过滤分享 API 返回的设计稿预览。"""
        normalized_urls: List[str] = []
        seen = set()

        for raw_url in urls:
            candidate_url = self._normalize_dynamic_candidate_url(raw_url)
            if not candidate_url or candidate_url in seen:
                continue
            if not self._is_design_page_candidate(candidate_url):
                continue

            normalized_urls.append(candidate_url)
            seen.add(candidate_url)

        return self._sort_urls_by_page_token(normalized_urls)

    def _extract_share_api_preview_groups(self, payloads: Dict[str, Dict]) -> Tuple[List[Tuple[str, List[str]]], int]:
        """按优先级抽取分享 API 中的多页设计稿 URL。"""
        groups: List[Tuple[str, List[str]]] = []
        expected_page_count = self._extract_expected_page_count_from_share_api_payloads(payloads)

        def add_group(source: str, raw_urls: List[str]) -> None:
            normalized_urls = self._augment_share_preview_group(raw_urls, expected_page_count)
            if normalized_urls:
                groups.append((source, normalized_urls))

        share_template = payloads.get('share_template') or {}
        share_template_data = share_template.get('data') if isinstance(share_template, dict) else None
        if isinstance(share_template_data, dict):
            preview_urls = share_template_data.get('preview')
            if isinstance(preview_urls, list):
                add_group('share_template', preview_urls)

        team_share_payload = payloads.get('team_share_get_templ') or {}
        if isinstance(team_share_payload, dict):
            preview_urls = team_share_payload.get('preview')
            if isinstance(preview_urls, list):
                add_group('team_share_get_templ', preview_urls)

        page_data_payload = payloads.get('get_template_page_data') or {}
        if isinstance(page_data_payload, dict):
            preview_wrapper = page_data_payload.get('url')
            if isinstance(preview_wrapper, dict):
                preview_items = preview_wrapper.get('preview')
                if isinstance(preview_items, list):
                    extracted_urls: List[str] = []
                    for preview_item in preview_items:
                        if isinstance(preview_item, dict):
                            for key in ['origin_img', 'big_img', 'img', 'url', 'preview']:
                                preview_url = preview_item.get(key)
                                if isinstance(preview_url, str):
                                    extracted_urls.append(preview_url)
                                    break
                        elif isinstance(preview_item, str):
                            extracted_urls.append(preview_item)
                    add_group('get_template_page_data', extracted_urls)

        return groups, expected_page_count

    async def _extract_from_share_api(self, url: str) -> Optional[Dict]:
        """优先调用 818ps 官方分享 API，直接拿到多页设计稿。"""
        query_params = self._extract_share_query_params(url)
        share_id = query_params.get('share_id')
        upic_id = query_params.get('upic_id')
        share_uid = query_params.get('share_uid')
        save_type = query_params.get('save_type') or ''
        user_source = query_params.get('user_source') or ''

        if not share_id:
            return None

        payloads: Dict[str, Dict] = {}
        endpoints = [
            ('share_template', f'https://818ps.com/apiV1/template/index/share-template?share_id={share_id}'),
        ]

        if upic_id and share_uid:
            endpoints.extend([
                (
                    'team_share_get_templ',
                    'https://818ps.com/api/team-share-get-templ'
                    f'?upicId={upic_id}&share_uid={share_uid}&share_id={share_id}'
                    f'&save_type={save_type}&user_source={user_source}'
                ),
                (
                    'get_template_page_data',
                    'https://818ps.com/apiv2/get-template-page-data'
                    f'?picId=0&upicId={upic_id}&version_id=0&user_template_team_id=0'
                    f'&paperId=0&share_uid={share_uid}'
                ),
                (
                    'get_template_info',
                    'https://818ps.com/apiv2/get-template-info'
                    f'?picId=0&paperId=0&upicId={upic_id}&version_id=0'
                    f'&user_template_team_id=0&share_uid={share_uid}'
                ),
            ])

        for endpoint_name, endpoint_url in endpoints:
            payload = await self._fetch_json(endpoint_url, referer=url)
            if isinstance(payload, dict):
                payloads[endpoint_name] = payload

        preview_groups, expected_page_count = self._extract_share_api_preview_groups(payloads)
        if not preview_groups:
            return None

        best_result: Optional[Dict] = None
        best_result_rank = (-1, -1, -1)

        for source_name, candidate_urls in preview_groups:
            entries = [
                {
                    'url': candidate_url,
                    'source': f'share_api_{source_name}',
                    'score': self._score_dynamic_image(candidate_url, f'share_api_{source_name}')
                }
                for candidate_url in candidate_urls
            ]
            valid_urls = await self._resolve_818ps_image_entry_urls(entries, prefer_variants=True)
            if not valid_urls:
                continue

            result = self._build_multi_image_result(
                valid_urls,
                url,
                f'share_api_{source_name}',
                max((entry['score'] for entry in entries), default=0)
            )
            result_rank = (
                1 if expected_page_count <= 1 or len(valid_urls) >= expected_page_count else 0,
                len(valid_urls),
                self._share_api_source_priority(source_name),
            )

            if result_rank > best_result_rank:
                best_result = result
                best_result_rank = result_rank

            if result_rank[0]:
                logging.info(
                    f"✅ 官方分享API提取成功: source={source_name}, "
                    f"pages={len(valid_urls)}, expected={expected_page_count or len(valid_urls)}"
                )
                return result

        if best_result:
            if expected_page_count > 1 and best_result.get('pageCount', 0) < expected_page_count:
                logging.warning(
                    f"⚠️ 官方分享API仅拿到部分页面: source={best_result.get('source')}, "
                    f"pages={best_result.get('pageCount', 0)}, expected={expected_page_count}"
                )
            return best_result

        if expected_page_count > 1:
            logging.warning(
                f"⚠️ 官方分享API已拿到候选结果，但有效页数不足: expected={expected_page_count}, "
                f"groups={[name for name, _ in preview_groups]}"
            )

        return None

    async def _find_first_valid_candidate(self, candidate_urls: List[str]) -> Optional[str]:
        """
        并发验证候选URL，返回最先验证成功的结果
        一旦命中立即取消剩余任务，避免被慢超时拖住
        """
        async def validate(candidate_url: str):
            return candidate_url, await self.validator.validate_image_url(candidate_url)

        tasks = [asyncio.create_task(validate(candidate_url)) for candidate_url in candidate_urls]

        try:
            for future in asyncio.as_completed(tasks):
                candidate_url, is_valid = await future
                if is_valid:
                    logging.info(f"✅ 找到有效候选URL: {candidate_url}")
                    return candidate_url
            return None
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _find_best_scored_candidate(self, candidate_urls: List[str]) -> Tuple[Optional[str], int]:
        """
        并发验证并评分所有候选URL
        """
        async def validate(candidate_url: str):
            is_valid, score = await self._validate_and_score_url(candidate_url)
            return candidate_url, is_valid, score

        tasks = [asyncio.create_task(validate(candidate_url)) for candidate_url in candidate_urls]
        best_url = None
        best_score = 0

        try:
            for future in asyncio.as_completed(tasks):
                candidate_url, is_valid, score = await future
                if is_valid and score > best_score:
                    best_url = candidate_url
                    best_score = score
                    logging.info(f"✅ 找到更好的图片URL: {candidate_url} (评分: {score})")
            return best_url, best_score
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def extract_image(self, url: str, extracted_params: Optional[Dict] = None) -> Optional[Dict]:
        """
        提取818ps图片 - 增强版主入口
        
        Args:
            url: 目标URL
            extracted_params: 从URL解析器预提取的参数 (pic_id, upic_id)
        
        Returns:
            包含图片信息的字典或None
        """
        try:
            logging.info(f"🎨 开始提取818ps图片: {url}")
            
            # 初始化会话
            await self._ensure_session()
            
            # 步骤1: 强制ID优先构建策略 - 关键优化
            upic_id = None
            pic_id = None
            share_id = None
            
            # 优先使用预提取的参数
            if extracted_params and extracted_params.get('upic_id'):
                upic_id = extracted_params['upic_id']
                pic_id = extracted_params.get('pic_id')
                logging.info(f"🎯 使用预提取参数: upicId={upic_id}, picId={pic_id}")
            
            # 如果没有预提取参数，从URL中提取
            query_params = self._extract_share_query_params(url)
            share_id = query_params.get('share_id')
            if not upic_id:
                pic_id = query_params.get('pic_id')
                upic_id = query_params.get('upic_id')
                if upic_id:
                    logging.info(f"🔍 从URL提取参数: picId={pic_id}, upicId={upic_id}")
            
            # 🆕 智能分流策略：检测用户分享链接，跳过无效的静态URL构建
            is_user_share = (('/u/' in url and ('818ps.com' in url or 'tuguaishou.com' in url)) or 
                           'ue.818ps.com' in url)

            if share_id:
                logging.info("馃摙 妫€娴嬪埌鍒嗕韩鍙傛暟锛屼紭鍏堝皾璇曞畼鏂瑰垎浜玂PI...")
                result = await self._extract_from_share_api(url)
                if result:
                    logging.info("鉁?瀹樻柟鍒嗕韩API鎻愬彇鎴愬姛锛岃烦杩囧悗缁姩鎬佸洖閫€")
                    return result
                logging.warning("鈿狅笍 瀹樻柟鍒嗕韩API鏈懡涓紝缁х画鎵ц鏈湴鍥為€€閾捐矾...")
            
            if is_user_share:
                if upic_id:
                    logging.info("🚀 检测到用户分享链接且已拿到upicId，先尝试轻量直连构造...")
                    result = await self._extract_with_upic_id_priority(upic_id, pic_id)
                    if result:
                        logging.info("✅ 用户分享链接直连构造成功，跳过动态抓取")
                        return result
                    logging.warning("⚠️ 用户分享链接直连构造未命中，回退到动态抓取...")
                else:
                    logging.info("🚀 检测到用户分享链接，但未拿到upicId，直接启动动态抓取...")
            else:
                # 如果有upicId，优先执行ID构建策略（仅对非用户分享链接）
                if upic_id:
                    logging.info("🚀 执行ID优先构建策略...")
                    result = await self._extract_with_upic_id_priority(upic_id, pic_id)
                    if result:
                        logging.info("✅ ID优先构建成功，跳过网页抓取")
                        return result
                    else:
                        logging.warning("⚠️ ID优先构建失败，继续尝试网页抓取...")
                        # 不要直接返回None，继续执行后续的回退机制
            
            # 网页抓取 - 作为ID构建失败后的回退机制
            logging.info("🌐 启动网页抓取 + 源码分析...")
            result = await self._scrape_webpage_enhanced(url)
            if result:
                return result
            
            # 最后的尝试 - 直接从URL构造可能的图片链接
            logging.info("🔄 尝试URL模式匹配...")
            result = await self._extract_from_url_patterns(url)
            if result:
                return result
            
            logging.warning("❌ 所有818ps提取方法都失败了")
            return None
            
        except Exception as error:
            logging.error(f"❌ 提取818ps图片异常: {error}")
            return None
        finally:
            # 不在这里关闭session，让调用者管理
            pass
    
    async def _extract_with_upic_id_priority(self, upic_id: str, pic_id: Optional[str] = None) -> Optional[Dict]:
        """
        强制ID优先构建策略 - 用户路径扩展版
        针对用户分享页面的特殊存储路径
        
        Args:
            upic_id: 用户图片ID (必需)
            pic_id: 图片ID (可选)
        
        Returns:
            提取结果或None
        """
        try:
            logging.info(f"🚀 用户路径扩展构建: upicId={upic_id}, picId={pic_id}")
            
            # 用户作品路径 - 针对 /u/ 分享页面优化
            candidates = []
            
            # 方案1: 用户编辑器预览路径 (最高优先级)
            candidates.extend([
                f"https://img.818ps.com/user_preview_ue/{upic_id}.jpg",  # 用户编辑器预览
                f"https://img.818ps.com/user_preview_ue/{upic_id}.png",
                f"https://img.818ps.com/user_preview/{upic_id}.jpg",     # 用户预览
                f"https://img.818ps.com/user_preview/{upic_id}.png",
                f"https://cdn.818ps.com/user_preview_ue/{upic_id}.jpg",  # CDN版本
                f"https://cdn.818ps.com/user_preview/{upic_id}.jpg",
            ])
            
            # 方案2: 用户作品存储路径
            candidates.extend([
                f"https://img.818ps.com/user_work/{upic_id}.jpg",
                f"https://img.818ps.com/user_work/{upic_id}.png",
                f"https://img.818ps.com/user_upload/{upic_id}.jpg",
                f"https://img.818ps.com/user_upload/{upic_id}.png",
                f"https://img.818ps.com/works/{upic_id}.jpg",
                f"https://img.818ps.com/works/{upic_id}.png",
            ])
            
            # 方案3: 如果有完整的pic_id和upic_id (传统模板路径)
            if pic_id:
                candidates.extend([
                    f"https://img.818ps.com/pic/{upic_id}/{pic_id}.jpg",  # 传统模板路径
                    f"https://img.818ps.com/pic/{upic_id}/{pic_id}.png",
                    f"https://cdn.818ps.com/pic/{upic_id}/{pic_id}.jpg",
                    f"https://static.818ps.com/pic/{upic_id}/{pic_id}.jpg",
                    # 高清版本
                    f"https://img.818ps.com/pic/{upic_id}/{pic_id}_hd.jpg",
                    f"https://img.818ps.com/pic/{upic_id}/{pic_id}_origin.jpg",
                ])
            
            # 方案4: 只有upic_id的情况 (简化格式)
            candidates.extend([
                f"https://img.818ps.com/pic/{upic_id}.jpg",  # 简化格式
                f"https://img.818ps.com/pic/{upic_id}.png",
                f"https://cdn.818ps.com/pic/{upic_id}.jpg",
                f"https://static.818ps.com/pic/{upic_id}.jpg",
                # 可能的分段规则 (针对长ID如304074038)
                f"https://img.818ps.com/pic/{upic_id[:3]}/{upic_id[3:6]}/{upic_id[6:]}.jpg",
                f"https://img.818ps.com/pic/{upic_id[:3]}/{upic_id[3:]}.jpg",
            ])
            
            # 方案5: 图怪兽域名 (备用)
            if pic_id:
                candidates.extend([
                    f"https://tuguaishou.com/user_preview_ue/{upic_id}.jpg",
                    f"https://tuguaishou.com/user_preview/{upic_id}.jpg",
                    f"https://tuguaishou.com/pic/{upic_id}/{pic_id}.jpg",
                    f"https://tuguaishou.com/pic/{upic_id}/{pic_id}.png",
                ])
            candidates.extend([
                f"https://tuguaishou.com/user_preview_ue/{upic_id}.jpg",
                f"https://tuguaishou.com/user_preview/{upic_id}.jpg",
                f"https://tuguaishou.com/pic/{upic_id}.jpg",
                f"https://tuguaishou.com/pic/{upic_id}.png",
            ])

            candidates = list(dict.fromkeys(candidates))
            
            logging.info(f"🔄 验证 {len(candidates)} 个用户路径候选URL...")

            candidate_url = await self._find_first_valid_candidate(candidates)
            if candidate_url:
                return {
                    'imageUrl': candidate_url,
                    'picId': pic_id,
                    'upicId': upic_id,
                    'platform': '818ps',
                    'source': 'user_path_priority',
                    'method': 'user_work_construction'
                }
            
            logging.warning("❌ 所有用户路径URL都验证失败")
            return None
            
        except Exception as e:
            logging.error(f"❌ 用户路径构建失败: {e}")
            return None
    
    async def _extract_with_known_params(self, pic_id: str, upic_id: str) -> Optional[Dict]:
        """
        使用已知参数构建图片URL并验证
        这是最可靠的方法，对应Node.js的核心逻辑
        """
        try:
            logging.info(f"🔧 构建图片URL: picId={pic_id}, upicId={upic_id}")
            
            # 构建可能的图片URL - 基于成功的Node.js模式
            possible_urls = [
                # 主要CDN域名
                f"https://img.818ps.com/pic/{upic_id}/{pic_id}.jpg",
                f"https://img.818ps.com/pic/{upic_id}/{pic_id}.png",
                f"https://img.818ps.com/pic/{upic_id}/{pic_id}.webp",
                
                # 备用CDN域名
                f"https://cdn.818ps.com/pic/{upic_id}/{pic_id}.jpg",
                f"https://static.818ps.com/pic/{upic_id}/{pic_id}.jpg",
                
                # 可能的高清版本
                f"https://img.818ps.com/pic/{upic_id}/{pic_id}_hd.jpg",
                f"https://img.818ps.com/pic/{upic_id}/{pic_id}_origin.jpg",
                
                # 图怪兽域名
                f"https://tuguaishou.com/pic/{upic_id}/{pic_id}.jpg",
                f"https://tuguaishou.com/pic/{upic_id}/{pic_id}.png",
            ]
            
            logging.info(f"🔄 验证 {len(possible_urls)} 个可能的图片URL...")
            best_url, best_score = await self._find_best_scored_candidate(possible_urls)
            
            if best_url:
                logging.info(f"🎯 最终选择: {best_url}")
                return {
                    'imageUrl': best_url,
                    'picId': pic_id,
                    'upicId': upic_id,
                    'platform': '818ps',
                    'source': 'constructed_validated',
                    'score': best_score
                }
            
            return None
            
        except Exception as e:
            logging.error(f"❌ 参数构建方法失败: {e}")
            return None
    
    async def _validate_and_score_url(self, url: str) -> Tuple[bool, int]:
        """
        验证URL并给出评分
        评分越高表示图片质量越好
        """
        try:
            is_valid = await self.validator.validate_image_url(url)
            if not is_valid:
                return False, 0
            
            # 根据URL特征评分
            score = 100  # 基础分
            
            # 文件格式加分
            if url.endswith('.jpg'):
                score += 20
            elif url.endswith('.png'):
                score += 10
            elif url.endswith('.webp'):
                score += 5
            
            # 域名加分
            if 'img.818ps.com' in url:
                score += 30
            elif 'cdn.818ps.com' in url:
                score += 20
            elif 'static.818ps.com' in url:
                score += 10
            
            # 高清版本加分
            if '_hd' in url or '_origin' in url:
                score += 50
            
            return True, score
            
        except Exception:
            return False, 0

    def _is_dynamic_like_page(self, url: str) -> bool:
        """
        判断当前 URL 是否更像需要渲染后的分享/编辑器页面。
        """
        url_lower = (url or '').lower()
        return (
            'ue.818ps.com' in url_lower or
            'tuguaishou.com' in url_lower or
            '818ps.com/u/' in url_lower
        )

    async def _extract_from_html_content(
        self,
        html_content: str,
        url: str,
        source_label: str
    ) -> Optional[Dict]:
        """
        统一执行 HTML 内容提取链路，便于静态源码和渲染后 DOM 复用同一套解析逻辑。
        """
        if not html_content:
            return None

        logging.info(f"📄 {source_label}: 获取页面内容 {len(html_content)} 字符")

        extractors = [
            ("Meta标签提取", self._extract_meta_image_from_html),
            ("JSON深度提取", self._extract_json_data),
            ("源码正则回退", self._extract_with_regex_fallback),
            ("JavaScript变量提取", self._extract_from_js_variables),
            ("BeautifulSoup解析", self._extract_with_beautifulsoup),
        ]

        for extractor_name, extractor in extractors:
            logging.info(f"🔍 {source_label}: 尝试{extractor_name}...")
            result = await extractor(html_content, url)
            if result:
                logging.info(f"✅ {source_label}: {extractor_name}成功")
                return result

        return None

    async def _render_page_with_local_chrome_legacy(self, url: str) -> Optional[str]:
        """
        使用本机 Chrome 渲染页面并导出 DOM。

        这条路径不依赖 chromedriver，适合作为动态页的轻量回退。
        """
        try:
            from core.browser_service import BrowserService

            browser_service = BrowserService()

            initial_share_params = self._extract_share_query_params(url)
            needs_share_resolution = (
                '818ps.com/u/' in (url or '').lower()
                and not initial_share_params.get('share_id')
            )

            if needs_share_resolution:
                resolved_url = await asyncio.to_thread(
                    browser_service.resolve_url_with_browser,
                    url
                )
                if resolved_url:
                    resolved_share_params = self._extract_share_query_params(resolved_url)
                    if resolved_share_params.get('share_id'):
                        logging.info(
                            "🔗 818ps 分享壳页已解析到编辑器地址，优先回退官方分享 API: "
                            f"{resolved_url}"
                        )
                        share_api_result = await self._extract_from_share_api(resolved_url)
                        if share_api_result:
                            logging.info("✅ 浏览器解析后的编辑器地址命中官方分享 API")
                            return share_api_result
            return await asyncio.to_thread(
                browser_service.dump_dom_with_local_chrome,
                url
            )
        except Exception as error:
            logging.warning(f"⚠️ 本地Chrome渲染DOM失败: {error}")
            return None

    async def _scrape_webpage_enhanced(self, url: str) -> Optional[Dict]:
        """
        增强版网页抓取 - 核心改进
        增加JSON深度提取，支持动态渲染页面
        """
        try:
            logging.info(f"🌐 开始增强版网页抓取: {url}")
            await self._ensure_session()
            
            # 检查是否为动态渲染页面
            if self._is_dynamic_like_page(url):
                logging.info("🔍 检测到动态/分享壳页面，启用静态HTML + 渲染DOM回退...")
                return await self._extract_dynamic_page(url)
            
            # 获取页面内容 (静态页面)
            async with self.session.get(url, timeout=15) as response:
                if response.status != 200:
                    logging.warning(f"⚠️ 页面响应异常: {response.status}")
                    return None
                
                html_content = await response.text()

            return await self._extract_from_html_content(
                html_content,
                url,
                '静态HTML'
            )
            
        except Exception as e:
            logging.error(f"❌ 增强版网页抓取失败: {e}")
            return None
    
    async def _extract_dynamic_page_legacy(self, url: str) -> Optional[Dict]:
        """
        提取动态渲染页面 - 使用浏览器服务
        """
        logging.info("🧩 动态页先尝试静态HTML/JSON回退...")
        static_result = await self._extract_dynamic_page_without_browser(url)
        if static_result:
            return static_result

        try:
            from core.browser_service import BrowserService
            browser_service = BrowserService()
            
            # 提取动态内容
            dynamic_data = await browser_service.extract_dynamic_content(url)
            
            if not dynamic_data:
                return None
            
            # 分析提取的数据
            result = await self._analyze_dynamic_data(dynamic_data, url)
            return result
            
        except Exception as e:
            logging.warning(f"⚠️ 浏览器动态抓取失败，动态页回退结束: {e}")
            return None

    async def _extract_dynamic_page_without_browser(self, url: str) -> Optional[Dict]:
        """
        动态页的轻量回退方案
        浏览器启动失败时，仍然尝试用静态HTML提取可用信息
        """
        html_content: Optional[str] = None

        try:
            await self._ensure_session()
            async with self.session.get(url, timeout=15) as response:
                if response.status != 200:
                    logging.warning(f"⚠️ 动态页静态抓取失败，响应码: {response.status}")
                else:
                    html_content = await response.text()
                    logging.info(f"📄 动态页静态源码获取成功 ({len(html_content)} 字符)")
        except Exception as e:
            logging.warning(f"⚠️ 动态页静态回退失败: {e}")

        if html_content:
            result = await self._extract_from_html_content(
                html_content,
                url,
                '动态页静态源码'
            )
            if result:
                return result

        rendered_dom = await self._render_page_with_local_chrome(url)
        if rendered_dom:
            result = await self._extract_from_html_content(
                rendered_dom,
                url,
                '本地Chrome渲染DOM'
            )
            if result:
                return result

        return None
    
    async def _analyze_dynamic_data(self, dynamic_data: dict, url: str) -> Optional[Dict]:
        """
        分析动态提取的数据，查找图片URL
        """
        try:
            logging.info("🔍 分析动态数据...")

            detected_page_markers = dynamic_data.get('pageMarkers', []) or []
            if detected_page_markers:
                logging.info(f"📑 浏览器识别到页面标记: {detected_page_markers}")

            page_specific_urls = await self._extract_page_specific_image_urls(dynamic_data)
            if page_specific_urls:
                logging.info(f"📄 逐页激活提取到设计稿页面: {len(page_specific_urls)}")
                if len(page_specific_urls) > 1:
                    return self._build_multi_image_result(
                        page_specific_urls,
                        url,
                        'dynamic_page_activation',
                        max(
                            (
                                self._score_dynamic_image(image_url, 'page_specific')
                                for image_url in page_specific_urls
                            ),
                            default=0
                        )
                    )

            structured_groups: List[Dict] = []
            for json_block in dynamic_data.get('jsonData', []) or []:
                self._collect_preview_groups_from_data(json_block, 'browser.json', structured_groups)

            for window_name, window_block in (dynamic_data.get('windowData') or {}).items():
                self._collect_preview_groups_from_data(
                    window_block,
                    f'browser.window.{window_name}',
                    structured_groups
                )

            for group in structured_groups:
                entries = [
                    {
                        'url': candidate_url,
                        'source': 'json',
                        'score': self._score_dynamic_image(candidate_url, 'json')
                    }
                    for candidate_url in group.get('urls', [])
                ]
                valid_urls = await self._validate_image_entry_urls(entries)
                if len(valid_urls) > 1:
                    logging.info(
                        f"🧩 结构化数据提取到多页结果: source={group.get('source')}, pages={len(valid_urls)}"
                    )
                    return self._build_multi_image_result(
                        valid_urls,
                        url,
                        f"dynamic_structured_{group.get('source')}",
                        max((entry['score'] for entry in entries if entry['url'] in valid_urls), default=0)
                    )

            candidate_entries = self._collect_dynamic_image_candidates(dynamic_data)
            if not candidate_entries:
                if page_specific_urls:
                    page_specific_score = max(
                        [self._score_dynamic_image(image_url, 'page_specific') for image_url in page_specific_urls],
                        default=0
                    )
                    return self._build_multi_image_result(
                        page_specific_urls,
                        url,
                        'dynamic_page_activation',
                        page_specific_score
                    )
                return None

            page_candidates = [
                entry for entry in candidate_entries
                if self._is_design_page_candidate(entry['url'])
            ]

            if page_candidates:
                valid_page_urls = await self._validate_image_entry_urls(page_candidates)
                if valid_page_urls:
                    merged_page_urls: List[str] = []
                    seen_page_urls = set()
                    for image_url in page_specific_urls + valid_page_urls:
                        normalized_url = self._normalize_dynamic_candidate_url(image_url)
                        if not normalized_url or normalized_url in seen_page_urls:
                            continue
                        merged_page_urls.append(normalized_url)
                        seen_page_urls.add(normalized_url)
                    logging.info(f"🗂️ 检测到设计稿页面数: {len(valid_page_urls)}")
                    logging.info(f"page-specific merged design pages: {len(merged_page_urls)}")
                    if len(detected_page_markers) > len(merged_page_urls):
                        logging.warning(
                            f"⚠️ 页面标记数为 {len(detected_page_markers)}，"
                            f"但当前仅提取到 {len(valid_page_urls)} 张有效设计稿图片"
                        )

                    page_scores = [
                        entry['score'] for entry in page_candidates
                        if entry['url'] in merged_page_urls
                    ]
                    page_scores.extend(
                        self._score_dynamic_image(image_url, 'page_specific')
                        for image_url in page_specific_urls
                    )
                    return self._build_multi_image_result(
                        merged_page_urls,
                        url,
                        'dynamic_page_activation' if page_specific_urls else (
                            'dynamic_multi_page_extraction' if len(merged_page_urls) > 1 else 'dynamic_json_extraction'
                        ),
                        max(page_scores) if page_scores else 0
                    )

            if page_specific_urls:
                page_specific_score = max(
                    [self._score_dynamic_image(image_url, 'page_specific') for image_url in page_specific_urls],
                    default=0
                )
                return self._build_multi_image_result(
                    page_specific_urls,
                    url,
                    'dynamic_page_activation',
                    page_specific_score
                )

            best_candidate = max(candidate_entries, key=lambda entry: entry['score'], default=None)
            if best_candidate and await self.validator.validate_image_url(best_candidate['url']):
                return self._build_multi_image_result(
                    [best_candidate['url']],
                    url,
                    'dynamic_json_extraction',
                    best_candidate['score']
                )
            
            return None
            
        except Exception as e:
            logging.error(f"❌ 动态数据分析失败: {e}")
            return None
    
    def _extract_image_from_data(self, data) -> Optional[str]:
        """
        从数据结构中递归提取第一张相关图片URL
        """
        try:
            image_urls = self._extract_image_urls_from_data(data)
            return image_urls[0] if image_urls else None
        except Exception:
            return None

    def _extract_image_urls_from_data(self, data) -> List[str]:
        """
        从结构化数据中递归提取全部相关图片URL
        """
        image_fields = [
            'imageUrl', 'image_url', 'imgUrl', 'img_url',
            'previewUrl', 'preview_url', 'coverUrl', 'cover_url',
            'thumbnailUrl', 'thumbnail_url', 'picUrl', 'pic_url',
            'workUrl', 'work_url', 'designUrl', 'design_url',
            'originalUrl', 'original_url', 'hdUrl', 'hd_url',
            'url', 'src', 'sourceUrl', 'pageUrl'
        ]
        image_urls: List[str] = []
        seen = set()

        def add_candidate(raw_url) -> None:
            candidate = self._normalize_dynamic_candidate_url(raw_url)
            if not candidate or candidate in seen:
                return
            if not self._is_relevant_dynamic_image(candidate):
                return
            seen.add(candidate)
            image_urls.append(candidate)

        def walk(value) -> None:
            if isinstance(value, dict):
                for field in image_fields:
                    add_candidate(value.get(field))
                for nested_value in value.values():
                    walk(nested_value)
                return

            if isinstance(value, list):
                for item in value:
                    walk(item)
                return

            if not isinstance(value, str):
                return

            add_candidate(value)
            for match in re.findall(r'https?://[^"\'\s<>\)]+', value, re.IGNORECASE):
                add_candidate(match)

        walk(data)
        return image_urls

    def _extract_preview_urls_from_array(self, items) -> List[str]:
        """从结构化数组中提取预览图候选 URL。"""
        preview_fields = [
            'origin_img', 'originImg',
            'big_img', 'bigImg',
            'img', 'image', 'imageUrl', 'image_url',
            'preview', 'previewUrl', 'preview_url',
            'url', 'src',
            'cover', 'coverUrl', 'cover_url',
            'user_preview_ue', 'user_preview',
        ]

        urls: List[str] = []
        for item in items or []:
            if isinstance(item, str):
                urls.append(item)
                continue

            if not isinstance(item, dict):
                continue

            for field in preview_fields:
                value = item.get(field)
                if isinstance(value, str):
                    urls.append(value)

            nested_url = item.get('url')
            if isinstance(nested_url, dict):
                for field in preview_fields:
                    value = nested_url.get(field)
                    if isinstance(value, str):
                        urls.append(value)

        return urls

    def _normalize_preview_group_urls(self, urls: List[str]) -> List[str]:
        """规范化并过滤结构化预览数组中的设计稿 URL。"""
        normalized_urls = self._dedupe_keep_order(
            self._normalize_dynamic_candidate_url(url)
            for url in urls or []
        )
        return self._sort_urls_by_page_token([
            url for url in normalized_urls
            if self._is_design_page_candidate(url)
        ])

    def _collect_preview_groups_from_data(
        self,
        data,
        source: str = 'data',
        groups: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """递归收集 jsonData / windowData 中的多页预览数组。"""
        if groups is None:
            groups = []

        if not data:
            return groups

        if isinstance(data, list):
            group_urls = self._normalize_preview_group_urls(
                self._extract_preview_urls_from_array(data)
            )
            if len(group_urls) > 1:
                groups.append({
                    'source': source,
                    'urls': group_urls,
                })

            for index, item in enumerate(data):
                self._collect_preview_groups_from_data(item, f'{source}[{index}]', groups)
            return groups

        if not isinstance(data, dict):
            return groups

        for key, value in data.items():
            if isinstance(value, list):
                group_urls = self._normalize_preview_group_urls(
                    self._extract_preview_urls_from_array(value)
                )
                if len(group_urls) > 1:
                    groups.append({
                        'source': f'{source}.{key}',
                        'urls': group_urls,
                    })

            self._collect_preview_groups_from_data(value, f'{source}.{key}', groups)

        return groups

    def _extract_url_page_number(self, url: str) -> Optional[int]:
        """尝试从 URL 本身推断页码。"""
        if not isinstance(url, str):
            return None

        patterns = [
            r'(?:^|[\/_-])page[_-]?(\d+)(?:[._!?-]|$)',
            r'(?:^|[\/_-])p[_-]?(\d+)(?:[._!?-]|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return int(match.group(1))

        return None

    def _extract_818ps_preview_page_number(self, url: str) -> Optional[int]:
        """从 818ps user_preview_ue 这类文件名推断页码。"""
        if not isinstance(url, str):
            return None

        try:
            parsed_url = urlparse(url)
            path = str(parsed_url.path or '')
            lower_path = path.lower()
            if not any(segment in lower_path for segment in [
                '/user_preview_ue/',
                '/user_preview/',
                '/user_work/',
                '/works/',
            ]):
                return None

            filename = path.split('/')[-1] if path else ''
            filename = filename.split('!', 1)[0]
            match = re.match(
                r'^(.+?_\d+)(?:_(\d+))?\.(?:jpg|jpeg|png|webp)$',
                filename,
                re.IGNORECASE
            )
            if not match:
                return None

            return int(match.group(2)) + 1 if match.group(2) else 1
        except Exception:
            return None

    def _sort_urls_by_page_token(self, urls: List[str]) -> List[str]:
        """按 URL 中的页码线索排序，减少多页结果乱序。"""
        indexed_urls = []
        for index, url in enumerate(urls or []):
            indexed_urls.append({
                'url': url,
                'index': index,
                'page': self._extract_url_page_number(url) or self._extract_818ps_preview_page_number(url),
            })

        indexed_urls.sort(key=lambda item: (
            item['page'] is None,
            item['page'] if item['page'] is not None else 10**9,
            item['index'],
        ))
        return [item['url'] for item in indexed_urls]

    def _dedupe_keep_order(self, items) -> List[str]:
        """保持发现顺序去重。"""
        seen = set()
        ordered_items: List[str] = []
        for item in items or []:
            if not isinstance(item, str):
                continue
            normalized_item = item.strip()
            if not normalized_item or normalized_item in seen:
                continue
            seen.add(normalized_item)
            ordered_items.append(normalized_item)
        return ordered_items

    def _normalize_dynamic_candidate_url(self, url: Optional[str]) -> Optional[str]:
        """
        规范化动态提取出来的URL
        """
        if not isinstance(url, str):
            return None

        candidate = url.strip().strip('\'"')
        if not candidate:
            return None

        candidate = candidate.replace('\\/', '/')
        if candidate.startswith('//'):
            candidate = f'https:{candidate}'

        return candidate if candidate.startswith('http') else None

    async def _extract_page_specific_image_urls(self, dynamic_data: dict) -> List[str]:
        """Resolve per-page preview URLs captured from browser-side page activation."""
        page_snapshots = dynamic_data.get('pageSnapshots', []) or []
        if not page_snapshots and dynamic_data.get('pageSpecificImages'):
            page_snapshots = [
                {
                    'page': index + 1,
                    'previewUrls': [image_url]
                }
                for index, image_url in enumerate(dynamic_data.get('pageSpecificImages', []) or [])
            ]

        if not page_snapshots:
            return []

        ordered_snapshots = sorted(
            page_snapshots,
            key=lambda item: (
                int(item.get('page') or 0),
                str(item.get('label') or '')
            )
        )

        resolved_urls: List[str] = []
        seen_urls = set()

        for snapshot in ordered_snapshots:
            candidate_urls: List[str] = []
            for key in ['previewUrls', 'newUrls', 'resourceUrls', 'imageUrls']:
                for raw_url in snapshot.get(key, []) or []:
                    normalized_url = self._normalize_dynamic_candidate_url(raw_url)
                    if not normalized_url or normalized_url in candidate_urls:
                        continue
                    if not self._is_design_page_candidate(normalized_url):
                        continue
                    candidate_urls.append(normalized_url)

            if not candidate_urls:
                continue

            entries = [
                {
                    'url': candidate_url,
                    'source': 'page_specific',
                    'score': self._score_dynamic_image(candidate_url, 'page_specific')
                }
                for candidate_url in candidate_urls
            ]
            entries.sort(key=lambda entry: entry['score'], reverse=True)

            valid_urls = await self._validate_image_entry_urls(entries)
            if not valid_urls:
                continue

            chosen_url = valid_urls[0]
            if chosen_url in seen_urls:
                continue

            resolved_urls.append(chosen_url)
            seen_urls.add(chosen_url)

        return self._sort_urls_by_page_token(resolved_urls)

    def _collect_dynamic_image_candidates(self, dynamic_data: dict) -> List[Dict]:
        """
        统一收集动态页面中的图片候选
        """
        candidates_by_url: Dict[str, Dict] = {}

        def add_candidate(raw_url: Optional[str], source: str) -> None:
            candidate_url = self._normalize_dynamic_candidate_url(raw_url)
            if not candidate_url or not self._is_relevant_dynamic_image(candidate_url):
                return

            score = self._score_dynamic_image(candidate_url, source)
            existing = candidates_by_url.get(candidate_url)
            if existing and existing['score'] >= score:
                return

            candidates_by_url[candidate_url] = {
                'url': candidate_url,
                'source': source,
                'score': score
            }

        for image_url in dynamic_data.get('imageUrls', []) or []:
            add_candidate(image_url, 'direct')

        for image_url in dynamic_data.get('resourceUrls', []) or []:
            add_candidate(image_url, 'resource')

        for image_url in dynamic_data.get('pageSpecificImages', []) or []:
            add_candidate(image_url, 'page_specific')

        for page_snapshot in dynamic_data.get('pageSnapshots', []) or []:
            for key, source in [
                ('previewUrls', 'page_specific'),
                ('newUrls', 'page_specific'),
                ('resourceUrls', 'resource'),
                ('imageUrls', 'page_snapshot')
            ]:
                for image_url in page_snapshot.get(key, []) or []:
                    add_candidate(image_url, source)

        for image_url in self._extract_image_urls_from_content(dynamic_data.get('pageSource', '') or ''):
            add_candidate(image_url, 'page_source')

        for json_block in dynamic_data.get('jsonData', []) or []:
            for image_url in self._extract_image_urls_from_data(json_block):
                add_candidate(image_url, 'json')

        for window_block in (dynamic_data.get('windowData') or {}).values():
            for image_url in self._extract_image_urls_from_data(window_block):
                add_candidate(image_url, 'window')

        return list(candidates_by_url.values())

    async def _validate_image_entry_urls(self, entries: List[Dict]) -> List[str]:
        """
        并发校验候选URL，按原顺序返回有效结果
        """
        if not entries:
            return []

        results = await asyncio.gather(
            *(self.validator.validate_image_url(entry['url']) for entry in entries),
            return_exceptions=True
        )

        valid_urls: List[str] = []
        seen = set()
        for entry, result in zip(entries, results):
            if result is True and entry['url'] not in seen:
                valid_urls.append(entry['url'])
                seen.add(entry['url'])

        return self._sort_urls_by_page_token(valid_urls)

    def _build_multi_image_result(self, image_urls: List[str], original_url: str, source: str, score: int) -> Dict:
        """
        构建兼容单页和多页设计稿的统一结果结构
        """
        unique_urls: List[str] = []
        seen = set()
        for image_url in image_urls:
            normalized_url = self._normalize_dynamic_candidate_url(image_url)
            if normalized_url and normalized_url not in seen:
                unique_urls.append(normalized_url)
                seen.add(normalized_url)

        unique_urls = self._sort_urls_by_page_token(unique_urls)

        return {
            'imageUrl': unique_urls[0] if unique_urls else None,
            'imageUrls': unique_urls,
            'pages': [
                {
                    'page': index + 1,
                    'imageUrl': image_url
                }
                for index, image_url in enumerate(unique_urls)
            ],
            'pageCount': len(unique_urls),
            'isMultiPage': len(unique_urls) > 1,
            'platform': '818ps',
            'source': source,
            'score': score,
            'original_url': original_url
        }

    def _is_design_page_candidate(self, url: str) -> bool:
        """
        判断该URL更像设计稿页而不是编辑器素材
        """
        normalized_url = self._normalize_dynamic_candidate_url(url)
        if not normalized_url or not self._is_relevant_dynamic_image(normalized_url):
            return False

        url_lower = normalized_url.lower()
        exclude_keywords = [
            'editor/', 'crown', 'vip', 'badge', 'icon', 'logo',
            'material', 'element', 'asset', 'frame', 'mask',
            'sticker', 'watermark', 'toolbar', 'button',
            'qrcode', 'wechat_qrcode', 'vx-code', 'xcx-code',
            'index_hot_day', 'new-index/',
            'ips_user_preview_api',
            'ips_svg/', 'ips_group_word/', 'ips_icon/', 'ips_material/',
            'group_word/', 'wordart/', 'font/', 'text/', 'emoji/'
        ]
        if any(keyword in url_lower for keyword in exclude_keywords):
            return False

        trusted_domains = [
            'img.tuguaishou.com',
            'img.818ps.com',
            'cdn.818ps.com',
            'static.818ps.com'
        ]
        if not any(domain in url_lower for domain in trusted_domains):
            return False

        preferred_patterns = [
            'user_preview_ue',
            'user_preview',
            'user_work',
            '/works/',
            '/user_work/'
        ]
        return any(pattern in url_lower for pattern in preferred_patterns)

    def _is_relevant_dynamic_image(self, url: str) -> bool:
        """
        判断动态提取的图片URL是否与设计稿相关
        """
        normalized_url = self._normalize_dynamic_candidate_url(url)
        if not normalized_url:
            return False

        url_lower = normalized_url.lower()
        exclude_keywords = [
            'favicon', 'logo', 'avatar', 'sprite', 'loading',
            'placeholder', 'blank', 'ad', 'banner', 'editor/',
            'crown', 'vip', 'badge', 'toolbar', 'button',
            'material', 'element', 'sticker', 'mask', 'frame',
            'qrcode', 'wechat_qrcode', 'vx-code', 'xcx-code',
            'index_hot_day', 'new-index/',
            'ips_user_preview_api',
            'ips_svg/', 'ips_group_word/', 'ips_icon/', 'ips_material/',
            'group_word/', 'wordart/', 'font/', 'text/', 'emoji/'
        ]
        if any(keyword in url_lower for keyword in exclude_keywords):
            return False

        include_keywords = [
            'img.818ps.com', 'cdn.818ps.com', 'static.818ps.com',
            'img.tuguaishou.com', 'tuguaishou.com',
            'pic/', 'work/', 'design/', 'preview/', 'cover/',
            'user_preview', 'user_preview_ue', 'user_work',
            'template', 'auth_key=', '/works/'
        ]
        return any(keyword in url_lower for keyword in include_keywords)

    def _score_dynamic_image(self, url: str, source: str) -> int:
        """
        为动态提取的图片URL评分
        """
        score = 100
        url_lower = url.lower()
        path_lower = urlparse(url).path.lower()

        if 'img.tuguaishou.com' in url_lower:
            score += 80
        elif 'img.818ps.com' in url_lower:
            score += 60
        elif 'cdn.818ps.com' in url_lower:
            score += 45
        elif 'static.818ps.com' in url_lower:
            score += 35
        elif 'tuguaishou.com' in url_lower:
            score += 30

        if 'user_preview_ue' in url_lower:
            score += 95
        elif 'ips_user_preview_api' in url_lower:
            score -= 180
        elif 'user_preview' in url_lower:
            score += 75
        elif 'user_work' in url_lower:
            score += 50
        elif 'preview' in url_lower:
            score += 30
        elif 'work' in url_lower:
            score += 25

        if 'auth_key=' in url_lower:
            score += 35
        if '!l1600' in url_lower or '!l2000' in url_lower or '!l3000' in url_lower:
            score += 25

        if '.jpg' in path_lower or '.jpeg' in path_lower:
            score += 20
        elif '.png' in path_lower:
            score += 15
        elif '.webp' in path_lower:
            score += 10

        if 'window' in source:
            score += 30
        elif 'json' in source:
            score += 25
        elif 'share_api' in source:
            score += 95
        elif 'page_specific' in source:
            score += 60
        elif 'page_snapshot' in source:
            score += 35
        elif 'resource' in source:
            score += 20
        elif 'direct' in source:
            score += 15
        elif 'page_source' in source:
            score += 10

        if self._is_design_page_candidate(url):
            score += 70

        if any(keyword in url_lower for keyword in [
            'icon', 'thumb', 'small', 'asset', 'element',
            'ips_svg/', 'ips_group_word/', 'ips_icon/', 'group_word/'
        ]):
            score -= 240

        return score
    
    async def _extract_json_data(self, html_content: str, url: str) -> Optional[Dict]:
        """
        从HTML中提取JSON数据 - 新增方法
        """
        try:
            import json
            import re
            
            # 查找script标签中的JSON数据
            json_patterns = [
                r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
                r'<script[^>]*>(.*?window\.__INITIAL_STATE__\s*=\s*({.*?});.*?)</script>',
                r'<script[^>]*>(.*?window\.__APP_DATA__\s*=\s*({.*?});.*?)</script>',
                r'<script[^>]*>(.*?window\.pageData\s*=\s*({.*?});.*?)</script>',
                r'<script[^>]*>(.*?var\s+pageData\s*=\s*({.*?});.*?)</script>',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
                for match in matches:
                    try:
                        # 提取JSON部分
                        json_str = match if isinstance(match, str) else match[-1]
                        json_str = json_str.strip()
                        
                        if json_str.startswith('{') and json_str.endswith('}'):
                            data = json.loads(json_str)
                            image_urls = self._extract_image_urls_from_data(data)
                            if image_urls:
                                candidate_entries = [
                                    {
                                        'url': image_url,
                                        'source': 'json',
                                        'score': self._score_dynamic_image(image_url, 'json')
                                    }
                                    for image_url in image_urls
                                ]
                                page_candidates = [
                                    entry for entry in candidate_entries
                                    if self._is_design_page_candidate(entry['url'])
                                ]

                                if page_candidates:
                                    valid_page_urls = await self._validate_image_entry_urls(page_candidates)
                                    if valid_page_urls:
                                        logging.info(f"🎯 JSON提取找到设计稿页面: {len(valid_page_urls)} 张")
                                        page_scores = [
                                            entry['score'] for entry in page_candidates
                                            if entry['url'] in valid_page_urls
                                        ]
                                        return self._build_multi_image_result(
                                            valid_page_urls,
                                            url,
                                            'json_extraction',
                                            max(page_scores) if page_scores else 0
                                        )

                                best_candidate = max(candidate_entries, key=lambda entry: entry['score'], default=None)
                                if best_candidate and await self.validator.validate_image_url(best_candidate['url']):
                                    logging.info(f"🎯 JSON提取找到图片: {best_candidate['url']}")
                                    return self._build_multi_image_result(
                                        [best_candidate['url']],
                                        url,
                                        'json_extraction',
                                        best_candidate['score']
                                    )
                            
                            # 从JSON数据中提取图片
                            image_url = self._extract_image_from_data(data)
                            if image_url and await self.validator.validate_image_url(image_url):
                                logging.info(f"🎯 JSON提取找到图片: {image_url}")
                                return {
                                    'imageUrl': image_url,
                                    'platform': '818ps',
                                    'source': 'json_extraction',
                                    'original_url': url
                                }
                                
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logging.debug(f"JSON解析异常: {e}")
                        continue
            
            return None
            
        except Exception as e:
            logging.warning(f"⚠️ JSON数据提取失败: {e}")
            return None

    async def _extract_meta_image_from_html(self, html_content: str, url: str) -> Optional[Dict]:
        """
        从静态HTML的Meta标签中提取预览图
        很多分享页即使是SPA，也会预渲染 og:image / twitter:image
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            meta_selectors = [
                'meta[property="og:image"]',
                'meta[property="og:image:url"]',
                'meta[property="og:image:secure_url"]',
                'meta[name="twitter:image"]',
                'meta[name="twitter:image:src"]',
            ]

            for selector in meta_selectors:
                element = soup.select_one(selector)
                if not element:
                    continue

                image_url = (element.get('content') or '').strip()
                if not image_url:
                    continue

                if image_url.startswith('//'):
                    image_url = f'https:{image_url}'

                if not self._is_valid_image_src(image_url):
                    continue

                final_url = await self._try_watermark_removal(image_url)
                if await self.validator.validate_image_url(final_url):
                    logging.info(f"🎯 Meta标签找到图片: {final_url}")
                    return {
                        'imageUrl': final_url,
                        'platform': '818ps',
                        'source': 'meta_image',
                        'original_url': url
                    }

            return None

        except Exception as e:
            logging.warning(f"⚠️ Meta标签提取失败: {e}")
            return None
    
    async def _extract_with_beautifulsoup(self, html_content: str, url: str) -> Optional[Dict]:
        """
        使用BeautifulSoup进行结构化解析
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # 尝试多种选择器
            selectors = [
                f'img[src*="pic/"]',  # 包含pic/的图片
                'img[src*="img.818ps.com"]',
                'img[data-src*="pic/"]',
                'img.preview-image',
                'img.main-image',
                '.image-preview img',
                '.work-image img',
                '#showImg',
                '[style*="background-image"]'
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                for elem in elements:
                    img_src = elem.get('src') or elem.get('data-src')
                    style = elem.get('style', '')
                    
                    image_url = None
                    
                    if img_src and self._is_valid_image_src(img_src):
                        image_url = img_src if img_src.startswith('http') else f'https:{img_src}'
                    elif style and 'url(' in style:
                        match = re.search(r'url\([\'"]?([^\'"]+)[\'"]?\)', style)
                        if match:
                            bg_url = match.group(1)
                            if self._is_valid_image_src(bg_url):
                                image_url = bg_url if bg_url.startswith('http') else f'https:{bg_url}'
                    
                    if image_url:
                        logging.info(f"🎯 BeautifulSoup找到图片: {image_url}")
                        
                        # 尝试生成无水印变体
                        final_url = await self._try_watermark_removal(image_url)
                        
                        return {
                            'imageUrl': final_url,
                            'platform': '818ps',
                            'source': 'beautifulsoup_parsed',
                            'original_url': url
                        }
            
            return None
            
        except Exception as e:
            logging.warning(f"⚠️ BeautifulSoup解析失败: {e}")
            return None
    
    async def _extract_with_regex_fallback(self, html_content: str, url: str) -> Optional[Dict]:
        """
        源码正则回退机制 - 核心增强功能
        即使URL中没有参数，也能从页面源码中提取关键信息
        """
        try:
            logging.info("🔍 执行源码正则回退机制...")
            
            # 定义多种正则模式来搜索picId和upicId
            id_patterns = [
                # JavaScript变量定义
                r'var\s+picId\s*=\s*["\']?(\d+)["\']?',
                r'var\s+upicId\s*=\s*["\']?(\d+)["\']?',
                r'let\s+picId\s*=\s*["\']?(\d+)["\']?',
                r'let\s+upicId\s*=\s*["\']?(\d+)["\']?',
                r'const\s+picId\s*=\s*["\']?(\d+)["\']?',
                r'const\s+upicId\s*=\s*["\']?(\d+)["\']?',
                
                # 对象属性
                r'picId\s*:\s*["\']?(\d+)["\']?',
                r'upicId\s*:\s*["\']?(\d+)["\']?',
                r'pic_id\s*:\s*["\']?(\d+)["\']?',
                r'upic_id\s*:\s*["\']?(\d+)["\']?',
                
                # JSON配置
                r'"picId"\s*:\s*["\']?(\d+)["\']?',
                r'"upicId"\s*:\s*["\']?(\d+)["\']?',
                r'"pic_id"\s*:\s*["\']?(\d+)["\']?',
                r'"upic_id"\s*:\s*["\']?(\d+)["\']?',
                
                # 数据属性
                r'data-pic-id\s*=\s*["\'](\d+)["\']',
                r'data-upic-id\s*=\s*["\'](\d+)["\']',
                
                # URL参数
                r'picId=(\d+)',
                r'upicId=(\d+)',
                
                # 可能的API调用
                r'/api/[^"\']*picId[=/](\d+)',
                r'/api/[^"\']*upicId[=/](\d+)',
            ]
            
            pic_id = None
            upic_id = None
            
            # 搜索picId
            for pattern in id_patterns:
                if 'pic' in pattern.lower() and 'upic' not in pattern.lower():
                    matches = re.findall(pattern, html_content, re.IGNORECASE | re.MULTILINE)
                    if matches:
                        pic_id = matches[0]
                        logging.info(f"🎯 正则找到picId: {pic_id}")
                        break
            
            # 搜索upicId
            for pattern in id_patterns:
                if 'upic' in pattern.lower():
                    matches = re.findall(pattern, html_content, re.IGNORECASE | re.MULTILINE)
                    if matches:
                        upic_id = matches[0]
                        logging.info(f"🎯 正则找到upicId: {upic_id}")
                        break
            
            # 如果找到了参数，使用已知参数方法
            if pic_id and upic_id:
                logging.info(f"✅ 正则提取成功: picId={pic_id}, upicId={upic_id}")
                result = await self._extract_with_known_params(pic_id, upic_id)
                if result:
                    result['source'] = 'regex_fallback'
                    return result
            
            # 即使没有完整参数，也尝试搜索图片URL
            logging.info("🔍 搜索页面中的图片URL...")
            image_urls = self._extract_image_urls_from_content(html_content)
            candidate_entries = [
                {
                    'url': image_url,
                    'source': 'page_source',
                    'score': self._score_dynamic_image(image_url, 'page_source')
                }
                for image_url in image_urls
            ]
            page_candidates = [
                entry for entry in candidate_entries
                if self._is_design_page_candidate(entry['url'])
            ]

            if page_candidates:
                valid_page_urls = await self._validate_image_entry_urls(page_candidates)
                if valid_page_urls:
                    logging.info(f"🎯 正则回退找到设计稿页面: {len(valid_page_urls)} 张")
                    page_scores = [
                        entry['score'] for entry in page_candidates
                        if entry['url'] in valid_page_urls
                    ]
                    return self._build_multi_image_result(
                        valid_page_urls,
                        url,
                        'regex_image_search',
                        max(page_scores) if page_scores else 0
                    )
            
            for img_url in image_urls:
                if await self.validator.validate_image_url(img_url):
                    logging.info(f"✅ 正则找到有效图片: {img_url}")
                    
                    # 尝试生成无水印变体
                    final_url = await self._try_watermark_removal(img_url)
                    
                    return {
                        'imageUrl': final_url,
                        'platform': '818ps',
                        'source': 'regex_image_search',
                        'original_url': url
                    }
            
            return None
            
        except Exception as e:
            logging.error(f"❌ 正则回退机制失败: {e}")
            return None
    
    def _extract_image_urls_from_content(self, html_content: str) -> List[str]:
        """
        从HTML内容中提取所有可能的图片URL
        增强版：添加黑名单过滤，避免提取统计图片
        """
        urls = set()
        
        # 图片URL的正则模式
        patterns = [
            # 完整HTTP URL
            r'https?://[^"\'\s>]+\.(?:png|jpe?g|webp|gif)(?:![^"\'\s>]*)?(?:\?[^"\'\s>]*)?',
            # 协议相对URL
            r'//[^"\'\s>]+\.(?:png|jpe?g|webp|gif)(?:![^"\'\s>]*)?(?:\?[^"\'\s>]*)?',
            # 相对路径
            r'/[^"\'\s>]+\.(?:png|jpe?g|webp|gif)(?:![^"\'\s>]*)?(?:\?[^"\'\s>]*)?',
            # 818ps / 图怪兽常见预览路径，即使末尾不一定直接是标准扩展名也先收集
            r'https?://[^"\'\s>]+(?:user_preview_ue|user_preview|user_work|ips_user_preview_api)[^"\'\s>]*',
        ]
        
        # 黑名单关键词 - 过滤统计图片和小图标
        blacklist_keywords = [
            'p.gif',           # 统计图片 (如 818ps.com/p.gif)
            'favicon',         # 网站图标
            'icon',            # 各种图标
            'loading',         # 加载图片
            'track',           # 追踪图片
            'analytics',       # 分析图片
            'pixel',           # 像素图片
            'beacon',          # 信标图片
            'sprite',          # 精灵图
            'logo',            # Logo图片
            'avatar',          # 头像图片
            'thumb',           # 缩略图
            'small',           # 小图
            'mini',            # 迷你图
            'tiny',            # 微小图
            '1x1',             # 1x1像素图
            'blank',           # 空白图
            'placeholder',     # 占位图
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                # 清理和标准化URL
                clean_url = match.replace('\\', '/')
                if clean_url.startswith('//'):
                    clean_url = 'https:' + clean_url
                elif clean_url.startswith('/') and not clean_url.startswith('//'):
                    clean_url = 'https://818ps.com' + clean_url
                
                # 黑名单过滤 - 关键优化
                url_lower = clean_url.lower()
                is_blacklisted = any(keyword in url_lower for keyword in blacklist_keywords)
                
                if is_blacklisted:
                    logging.debug(f"🚫 黑名单过滤: {clean_url}")
                    continue
                
                # 进一步的相关性检查
                if self._is_relevant_image_url(clean_url):
                    urls.add(clean_url)
                    logging.debug(f"✅ 添加候选图片: {clean_url}")
        
        logging.info(f"🔍 从页面提取到 {len(urls)} 个候选图片URL (已过滤黑名单)")
        return list(urls)
    
    def _is_relevant_image_url(self, url: str) -> bool:
        """
        判断图片URL是否相关 - 增强版
        更严格的过滤规则，避免统计图片和小图标
        """
        url_lower = url.lower()
        
        # 严格的排除关键词 (扩展版)
        exclude_keywords = [
            'favicon', 'icon', 'logo', 'avatar', 'sprite', 
            'banner', 'ad', 'advertisement', 'tracking',
            'analytics', 'pixel', 'beacon', 'p.gif',
            'loading', 'placeholder', 'blank', '1x1',
            'thumb', 'small', 'mini', 'tiny', 'btn',
            'button', 'arrow', 'close', 'search'
        ]
        
        for keyword in exclude_keywords:
            if keyword in url_lower:
                return False
        
        # 包含的关键词 (提高相关性) - 更严格
        include_keywords = [
            'pic/', 'image/', 'img/', 'photo/', 'work/',
            'preview', 'show', 'display', 'main', 'content',
            'design', 'template', 'poster', 'cover'
        ]
        
        # 必须包含至少一个相关关键词
        has_relevant_keyword = any(keyword in url_lower for keyword in include_keywords)
        
        # 或者是818ps/tuguaishou的图片域名
        is_trusted_domain = any(domain in url_lower for domain in [
            'img.818ps.com', 'cdn.818ps.com', 'static.818ps.com',
            'tuguaishou.com'
        ])
        
        return has_relevant_keyword or is_trusted_domain
    
    def _is_valid_image_src(self, src: str) -> bool:
        """
        判断图片src是否有效
        """
        if not src:
            return False
        
        src_lower = src.lower()
        
        # 必须包含图片相关路径或域名
        valid_indicators = [
            'pic/', 'image/', 'img/', 'photo/',
            '818ps.com', 'tuguaishou.com',
            '.jpg', '.png', '.webp', '.jpeg'
        ]
        
        return any(indicator in src_lower for indicator in valid_indicators)
    
    async def _try_watermark_removal(self, image_url: str) -> str:
        """
        尝试生成无水印版本
        如果无水印版本无效，返回原URL
        """
        try:
            # 生成无水印变体
            variants = self.variant_builder.build_818ps_variants(image_url)
            
            # 验证变体
            for variant in variants:
                if await self.validator.validate_image_url(variant):
                    logging.info(f"✅ 找到无水印版本: {variant}")
                    return variant
            
            # 如果没有找到有效的无水印版本，返回原URL
            return image_url
            
        except Exception as e:
            logging.warning(f"⚠️ 无水印处理失败: {e}")
            return image_url
    
    async def _extract_from_js_variables(self, html_content: str, url: str) -> Optional[Dict]:
        """
        从JavaScript变量中提取配置信息
        """
        try:
            # 搜索常见的JS配置模式
            js_patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                r'window\.config\s*=\s*({.+?});',
                r'var\s+config\s*=\s*({.+?});',
                r'const\s+config\s*=\s*({.+?});',
            ]
            
            for pattern in js_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL)
                if matches:
                    try:
                        import json
                        config = json.loads(matches[0])
                        
                        # 尝试从配置中提取图片信息
                        pic_id = self._extract_from_config(config, ['picId', 'pic_id', 'id'])
                        upic_id = self._extract_from_config(config, ['upicId', 'upic_id', 'userId', 'user_id'])
                        
                        if pic_id and upic_id:
                            result = await self._extract_with_known_params(str(pic_id), str(upic_id))
                            if result:
                                result['source'] = 'js_config'
                                return result
                                
                    except json.JSONDecodeError:
                        continue
            
            return None
            
        except Exception as e:
            logging.warning(f"⚠️ JS变量提取失败: {e}")
            return None
    
    def _extract_from_config(self, config: dict, keys: List[str]) -> Optional[str]:
        """
        从配置对象中提取值
        支持嵌套查找
        """
        def recursive_search(obj, target_keys):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in target_keys:
                        return str(value)
                    if isinstance(value, (dict, list)):
                        result = recursive_search(value, target_keys)
                        if result:
                            return result
            elif isinstance(obj, list):
                for item in obj:
                    result = recursive_search(item, target_keys)
                    if result:
                        return result
            return None
        
        return recursive_search(config, keys)
    
    async def _extract_from_url_patterns(self, url: str) -> Optional[Dict]:
        """
        从URL模式中尝试提取信息
        最后的尝试方法
        """
        try:
            # 尝试从URL路径中提取可能的ID
            path_patterns = [
                r'/(\d+)/(\d+)',  # /123/456 格式
                r'id[=/](\d+)',   # id=123 或 id/123 格式
                r'pic[=/](\d+)',  # pic=123 格式
            ]
            
            for pattern in path_patterns:
                matches = re.findall(pattern, url)
                if matches:
                    if len(matches[0]) == 2:  # 两个ID
                        pic_id, upic_id = matches[0]
                        result = await self._extract_with_known_params(pic_id, upic_id)
                        if result:
                            result['source'] = 'url_pattern'
                            return result
            
            return None
            
        except Exception as e:
            logging.warning(f"⚠️ URL模式提取失败: {e}")
            return None
    
    async def _render_page_with_local_chrome(self, url: str) -> Optional[str]:
        """
        Re-declared near the end of the class so the dynamic-page fallback keeps
        the simple DOM-dump behaviour even if earlier experiments changed it.
        """
        try:
            from core.browser_service import BrowserService

            browser_service = BrowserService()
            return await asyncio.to_thread(
                browser_service.dump_dom_with_local_chrome,
                url
            )
        except Exception as error:
            logging.warning(f"⚠️ 本地Chrome渲染DOM失败: {error}")
            return None

    async def _try_extract_from_browser_resolved_share_url(self, url: str) -> Optional[Dict]:
        """Resolve `/u/` share shells to the real editor URL, then retry the official share API."""
        initial_share_params = self._extract_share_query_params(url)
        if '818ps.com/u/' not in (url or '').lower() or initial_share_params.get('share_id'):
            return None

        try:
            from core.browser_service import BrowserService

            browser_service = BrowserService()
            resolved_url = await asyncio.to_thread(
                browser_service.resolve_url_with_browser,
                url
            )
        except Exception as error:
            logging.warning(f"⚠️ 浏览器解析 818ps 分享壳页失败: {error}")
            return None

        if not isinstance(resolved_url, str) or not resolved_url.strip():
            return None

        resolved_url = resolved_url.strip()
        resolved_share_params = self._extract_share_query_params(resolved_url)
        if not resolved_share_params.get('share_id'):
            return None

        logging.info(
            "🔗 818ps 分享壳页已解析到编辑器地址，优先回退官方分享 API: "
            f"{resolved_url}"
        )
        share_api_result = await self._extract_from_share_api(resolved_url)
        if share_api_result:
            logging.info("✅ 浏览器解析后的编辑器地址命中官方分享 API")
        return share_api_result

    async def _extract_dynamic_page(self, url: str) -> Optional[Dict]:
        """
        Re-declared near the end of the class so 818ps `/u/` links can first use
        the browser-resolved editor URL to recover `share_id/upicId/share_uid`,
        then fall back to dynamic DOM analysis only when needed.
        """
        logging.info("🤖 动态页先尝试静态HTML/JSON回退...")
        initial_share_params = self._extract_share_query_params(url)
        is_share_shell = (
            '818ps.com/u/' in (url or '').lower()
            and not initial_share_params.get('share_id')
        )

        if is_share_shell:
            browser_resolved_result = await self._try_extract_from_browser_resolved_share_url(url)
            if browser_resolved_result:
                return browser_resolved_result

        static_result = await self._extract_dynamic_page_without_browser(url)
        if static_result:
            static_image_url = static_result.get('imageUrl')
            if not is_share_shell or not static_image_url or self._is_design_page_candidate(static_image_url):
                return static_result

            logging.warning(
                f"⚠️ 818ps /u/ 静态回退命中了非设计稿资源，继续走浏览器解析链路: {static_image_url}"
            )

        browser_resolved_result = await self._try_extract_from_browser_resolved_share_url(url)
        if browser_resolved_result:
            return browser_resolved_result

        try:
            from core.browser_service import BrowserService

            browser_service = BrowserService()
            dynamic_data = await browser_service.extract_dynamic_content(url)

            if not dynamic_data:
                return None

            initial_share_params = self._extract_share_query_params(url)
            resolved_dynamic_url = (
                dynamic_data.get('resolvedUrl')
                or dynamic_data.get('currentUrl')
                or dynamic_data.get('finalUrl')
            )
            if isinstance(resolved_dynamic_url, str):
                resolved_dynamic_url = resolved_dynamic_url.strip()
            else:
                resolved_dynamic_url = None

            if (
                resolved_dynamic_url
                and resolved_dynamic_url != url
                and not initial_share_params.get('share_id')
            ):
                resolved_share_params = self._extract_share_query_params(resolved_dynamic_url)
                if resolved_share_params.get('share_id'):
                    logging.info(
                        "🔁 动态渲染过程中获取到编辑器最终地址，回退官方分享 API: "
                        f"{resolved_dynamic_url}"
                    )
                    share_api_result = await self._extract_from_share_api(resolved_dynamic_url)
                    if share_api_result:
                        logging.info("✅ 动态渲染结果成功补齐分享参数并命中官方分享 API")
                        return share_api_result

            return await self._analyze_dynamic_data(dynamic_data, url)
        except Exception as e:
            logging.warning(f"⚠️ 浏览器动态抓取失败，动态页回退结束: {e}")
            return None

    async def close(self):
        """关闭资源"""
        if self.session:
            await self.session.close()
            self.session = None
        await self.validator.close()
