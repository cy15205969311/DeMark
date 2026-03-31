"""
Gaoding crawler.

This crawler keeps the implementation isolated from the existing 818ps /
Canva / Chuangkit logic. It focuses on publicly accessible Gaoding pages such
as shared designs, template detail pages, and editor links that expose preview
images in HTML, JSON payloads, or browser-rendered resources.
"""
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional, Tuple
import html
import json
import logging
import re
import socket
import sys
import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Add project root to sys.path for direct execution compatibility.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.image_validator import ImageValidator


CandidateEntry = Tuple[str, str]


class GaodingCrawler:
    """Crawler for publicly accessible Gaoding design pages."""

    IMAGE_URL_PATTERN = re.compile(
        r'(?P<url>(?:https?:)?//[^\s"\'<>\\]+?\.(?:png|jpe?g|webp|gif)(?:\?[^\s"\'<>\\]*)?)',
        re.IGNORECASE,
    )

    POSITIVE_PATH_HINTS = (
        'preview',
        'cover',
        'poster',
        'image',
        'page',
        'pages',
        'artboard',
        'artboards',
        'slide',
        'slides',
        'canvas',
        'frame',
        'frames',
        'work',
        'template',
        'render',
    )

    NEGATIVE_PATH_HINTS = (
        'recommend',
        'banner',
        'search',
        'material',
        'resource',
        'sidebar',
        'widget',
        'header',
        'footer',
        'placeholder',
        'avatar',
        'icon',
        'logo',
        'hot',
        'ad',
    )

    def __init__(self):
        self.validator = ImageValidator()
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.gaoding.com/',
            'Origin': 'https://www.gaoding.com',
            'Cache-Control': 'no-cache',
        }

    async def extract_image(self, url: str, extracted_params: Optional[Dict] = None) -> Optional[Dict]:
        """Extract images from a Gaoding page."""
        del extracted_params

        session = None
        link_type = self._classify_link(url)

        try:
            logging.info(f"🎯 Start Gaoding extraction: {url}")
            logging.info(f"🔎 Gaoding link type: {link_type}")

            session = await self._create_session()

            static_result = await self._static_scraping(session, url, link_type)
            if static_result:
                return static_result

            # Listing pages are not stable inputs for one-design extraction.
            if link_type == 'listing':
                logging.info("ℹ️ Gaoding listing page detected, skip dynamic extraction")
                return None

            dynamic_result = await self._dynamic_scraping(url, link_type)
            if dynamic_result:
                return dynamic_result

            return None

        except Exception as error:
            logging.error(f"❌ Gaoding extraction failed: {error}")
            return None
        finally:
            if session:
                await session.close()

    async def _create_session(self) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)
        return aiohttp.ClientSession(connector=connector, timeout=timeout, headers=self.headers)

    def _classify_link(self, url: str) -> str:
        parsed = urlparse(url)
        path = (parsed.path or '').rstrip('/').lower()
        query = parse_qs(parsed.query)

        design_query_keys = {
            'templateId',
            'templateid',
            'template_id',
            'workId',
            'workid',
            'work_id',
            'shareId',
            'shareid',
            'share_id',
            'id',
        }

        if any(key in query for key in design_query_keys):
            if '/editor/design' in path:
                return 'editor'
            if '/templates/' in path:
                return 'template'
            return 'detail'

        if path in ['', '/creation', '/templates', '/create-design']:
            return 'listing'
        if '/editor/design' in path:
            return 'editor'
        if path.startswith('/templates/'):
            return 'template'
        if 'share' in path or 'invite' in path:
            return 'share'
        if path.startswith('/creation/'):
            return 'creation'
        return 'detail'

    async def _static_scraping(
        self,
        session: aiohttp.ClientSession,
        url: str,
        link_type: str
    ) -> Optional[Dict]:
        try:
            async with session.get(url, headers=self.headers) as response:
                if response.status != 200:
                    logging.info(f"ℹ️ Gaoding static page status={response.status}")
                    return None
                html_content = await response.text()

            if self._looks_like_anti_bot_page(html_content):
                logging.info("ℹ️ Gaoding static page hit anti-bot page")
                return None

            soup = BeautifulSoup(html_content, 'lxml')

            meta_entries = self._extract_meta_candidates(soup)
            dom_entries = self._extract_dom_candidates(soup)
            json_entries = self._extract_json_candidates(soup)
            text_entries = self._extract_contextual_urls_from_text(html_content)

            multi_page_entries = self._select_best_multi_page_group(json_entries)
            if multi_page_entries:
                valid_urls = await self._validate_urls_in_order(
                    [image_url for image_url, _ in multi_page_entries]
                )
                if len(valid_urls) >= 2:
                    return self._build_result(
                        valid_urls,
                        url,
                        'json-multi-page',
                        'static_json_group',
                        link_type,
                        score=1600,
                    )

            if meta_entries:
                meta_url = await self._pick_best_single_candidate(meta_entries, link_type, limit=4)
                if meta_url:
                    return self._build_result(
                        [meta_url],
                        url,
                        'meta',
                        'static_meta',
                        link_type,
                        score=900,
                    )

            all_entries = meta_entries + json_entries + dom_entries + text_entries
            best_url = await self._pick_best_single_candidate(all_entries, link_type)
            if best_url:
                return self._build_result(
                    [best_url],
                    url,
                    'static-candidate',
                    'static_candidate_selection',
                    link_type,
                    score=700,
                )

            return None

        except Exception as error:
            logging.debug(f"Gaoding static scraping failed: {error}")
            return None

    async def _dynamic_scraping(self, url: str, link_type: str) -> Optional[Dict]:
        browser_service = None
        try:
            from core.browser_service import BrowserService

            browser_service = BrowserService()

            page_data = await browser_service.extract_dynamic_content(url, headless=True)
            dynamic_result = await self._analyze_dynamic_data(page_data, url, link_type)
            if dynamic_result:
                return dynamic_result

            images = await browser_service.extract_images_from_page(url, headless=True)
            visible_entries: List[CandidateEntry] = []
            for item in images or []:
                candidate_url = self._normalize_candidate_url(item.get('src'))
                if not candidate_url or not self._is_gaoding_design_candidate(candidate_url):
                    continue
                visible_entries.append((candidate_url, f"dynamic:{item.get('type', 'img')}"))

            best_url = await self._pick_best_single_candidate(visible_entries, link_type, limit=8)
            if best_url:
                return self._build_result(
                    [best_url],
                    url,
                    'dynamic-visible',
                    'browser_visible_selection',
                    link_type,
                    score=1200,
                )

            return None

        except Exception as error:
            logging.debug(f"Gaoding dynamic scraping failed: {error}")
            return None
        finally:
            if browser_service:
                await browser_service.close()

    async def _analyze_dynamic_data(
        self,
        page_data: Optional[Dict[str, Any]],
        url: str,
        link_type: str
    ) -> Optional[Dict]:
        page_data = page_data or {}

        page_level_urls: List[str] = []
        seen_keys = set()

        for snapshot in page_data.get('pageSnapshots', []) or []:
            preview_entries: List[CandidateEntry] = []
            page_number = snapshot.get('page') or len(page_level_urls) + 1

            for preview_url in snapshot.get('previewUrls', []) or []:
                preview_entries.append((preview_url, f"pageSnapshots[{page_number}].previewUrls"))
            for preview_url in snapshot.get('newUrls', []) or []:
                preview_entries.append((preview_url, f"pageSnapshots[{page_number}].newUrls"))

            best_page_url = await self._pick_best_single_candidate(preview_entries, link_type, limit=6)
            if not best_page_url:
                continue

            candidate_key = self._candidate_key(best_page_url)
            if candidate_key in seen_keys:
                continue
            seen_keys.add(candidate_key)
            page_level_urls.append(best_page_url)

        if len(page_level_urls) >= 2:
            return self._build_result(
                page_level_urls,
                url,
                'dynamic-page-snapshots',
                'browser_page_snapshots',
                link_type,
                score=1800,
            )

        visible_candidates = page_data.get('visibleCandidates', []) or []
        visible_entries: List[Tuple[str, int]] = []
        for candidate in visible_candidates:
            if not isinstance(candidate, dict):
                continue
            candidate_url = self._normalize_candidate_url(candidate.get('url'))
            if not candidate_url or not self._is_gaoding_design_candidate(candidate_url):
                continue
            visible_entries.append((candidate_url, self._score_snapshot_candidate(candidate_url, candidate)))

        visible_entries.sort(key=lambda item: item[1], reverse=True)
        for candidate_url, score in visible_entries[:6]:
            if score <= 0:
                continue
            if await self.validator.validate_image_url(candidate_url):
                return self._build_result(
                    [candidate_url],
                    url,
                    'dynamic-visible-candidate',
                    'browser_visible_candidate',
                    link_type,
                    score=score,
                )

        merged_entries: List[CandidateEntry] = []
        merged_entries.extend((item, 'pageSpecificImages') for item in page_data.get('pageSpecificImages', []) or [])
        merged_entries.extend((item, 'imageUrls') for item in page_data.get('imageUrls', []) or [])
        merged_entries.extend((item, 'resourceUrls') for item in page_data.get('resourceUrls', []) or [])
        merged_entries.extend(self._extract_contextual_urls_from_text(page_data.get('pageSource', '') or ''))

        for json_item in page_data.get('jsonData', []) or []:
            merged_entries.extend(self._extract_candidates_from_data(json_item, 'jsonData'))
        for key, value in (page_data.get('windowData') or {}).items():
            merged_entries.extend(self._extract_candidates_from_data(value, f'windowData.{key}'))

        multi_page_entries = self._select_best_multi_page_group(merged_entries)
        if multi_page_entries:
            valid_urls = await self._validate_urls_in_order(
                [image_url for image_url, _ in multi_page_entries]
            )
            if len(valid_urls) >= 2:
                return self._build_result(
                    valid_urls,
                    url,
                    'dynamic-multi-page',
                    'browser_dynamic_group',
                    link_type,
                    score=1700,
                )

        best_url = await self._pick_best_single_candidate(merged_entries, link_type)
        if best_url:
            return self._build_result(
                [best_url],
                url,
                'dynamic-candidate',
                'browser_dynamic_candidate',
                link_type,
                score=1100,
            )

        return None

    def _looks_like_anti_bot_page(self, html_content: str) -> bool:
        lowered = (html_content or '').lower()
        return (
            '405异常访问' in html_content
            or '请求有异常行为' in html_content
            or '访问被阻止了' in html_content
            or 'security threat' in lowered
        )

    def _extract_meta_candidates(self, soup: BeautifulSoup) -> List[CandidateEntry]:
        candidates: List[CandidateEntry] = []
        meta_selectors = [
            ('meta[property="og:image"]', 'content', 'meta:og:image'),
            ('meta[name="twitter:image"]', 'content', 'meta:twitter:image'),
            ('link[rel="image_src"]', 'href', 'meta:image_src'),
        ]

        for selector, attr, hint in meta_selectors:
            element = soup.select_one(selector)
            if not element:
                continue
            candidate_url = self._normalize_candidate_url(element.get(attr))
            if candidate_url:
                candidates.append((candidate_url, hint))

        return candidates

    def _extract_dom_candidates(self, soup: BeautifulSoup) -> List[CandidateEntry]:
        candidates: List[CandidateEntry] = []

        for image in soup.select('img'):
            for attr in ('src', 'data-src', 'data-original', 'data-url'):
                candidate_url = self._normalize_candidate_url(image.get(attr))
                if candidate_url:
                    candidates.append((candidate_url, f'img:{attr}'))

            srcset = image.get('srcset') or ''
            if srcset:
                for part in srcset.split(','):
                    srcset_url = self._normalize_candidate_url(part.strip().split()[0])
                    if srcset_url:
                        candidates.append((srcset_url, 'img:srcset'))

        for source in soup.select('source'):
            candidate_url = self._normalize_candidate_url(source.get('srcset') or source.get('src'))
            if candidate_url:
                candidates.append((candidate_url, 'source'))

        for video in soup.select('video'):
            candidate_url = self._normalize_candidate_url(video.get('poster'))
            if candidate_url:
                candidates.append((candidate_url, 'video:poster'))

        return candidates

    def _extract_json_candidates(self, soup: BeautifulSoup) -> List[CandidateEntry]:
        candidates: List[CandidateEntry] = []

        for script in soup.find_all('script'):
            content = script.string or script.get_text()
            if not content:
                continue

            trimmed = content.strip()
            if not trimmed or trimmed[0] not in ['{', '[']:
                continue

            try:
                data = json.loads(trimmed)
            except Exception:
                continue

            candidates.extend(self._extract_candidates_from_data(data, 'script'))

        return candidates

    def _extract_candidates_from_data(self, data: Any, path: str) -> List[CandidateEntry]:
        candidates: List[CandidateEntry] = []

        if isinstance(data, dict):
            for key, value in data.items():
                next_path = f'{path}.{key}' if path else str(key)
                candidates.extend(self._extract_candidates_from_data(value, next_path))
            return candidates

        if isinstance(data, list):
            for index, item in enumerate(data):
                next_path = f'{path}[{index}]'
                candidates.extend(self._extract_candidates_from_data(item, next_path))
            return candidates

        if isinstance(data, str):
            candidate_url = self._normalize_candidate_url(data)
            if candidate_url:
                candidates.append((candidate_url, path))
            return candidates

        return candidates

    def _extract_contextual_urls_from_text(self, text: str) -> List[CandidateEntry]:
        if not text:
            return []

        candidates: List[CandidateEntry] = []
        pattern = re.compile(
            r'(?P<url>(?:https?:)?//[^\s"\'<>]+?\.(?:png|jpe?g|webp|gif)(?:\?[^\s"\'<>]*)?)',
            re.IGNORECASE,
        )

        for match in pattern.finditer(text):
            candidate_url = self._normalize_candidate_url(match.group('url'))
            if not candidate_url:
                continue

            context_start = max(0, match.start() - 96)
            context = text[context_start:match.start()]
            candidates.append((candidate_url, context))

        return candidates

    def _select_best_multi_page_group(self, entries: List[CandidateEntry]) -> List[CandidateEntry]:
        grouped_entries: Dict[str, List[CandidateEntry]] = {}

        for image_url, hint in entries:
            normalized_url = self._normalize_candidate_url(image_url)
            if not normalized_url or not self._is_gaoding_design_candidate(normalized_url):
                continue

            group_key = self._candidate_group_key(hint)
            if not group_key:
                continue

            grouped_entries.setdefault(group_key, []).append((normalized_url, hint))

        best_group: List[CandidateEntry] = []
        best_score = 0

        for group_key, group_entries in grouped_entries.items():
            deduped_group = self._dedupe_entries(group_entries)
            if len(deduped_group) < 2:
                continue

            lowered_group_key = group_key.lower()
            score = min(len(deduped_group), 6)

            if any(token in lowered_group_key for token in self.POSITIVE_PATH_HINTS):
                score += 6
            if any(token in lowered_group_key for token in self.NEGATIVE_PATH_HINTS):
                score -= 6
            if len(deduped_group) > 12:
                score -= 5

            if score > best_score:
                best_score = score
                best_group = deduped_group

        return best_group if best_score >= 7 else []

    def _candidate_group_key(self, hint: str) -> str:
        lowered_hint = (hint or '').lower()
        if not lowered_hint:
            return ''

        if '.' not in lowered_hint and '[' not in lowered_hint:
            return ''

        group_key = re.sub(r'\[\d+\]', '[]', lowered_hint)
        group_key = re.sub(
            r'\.(?:url|src|image|images|cover|covers|preview|previews|poster|thumbnail|source)$',
            '',
            group_key,
        )
        return group_key.strip('.')

    async def _pick_best_single_candidate(
        self,
        entries: List[CandidateEntry],
        link_type: str,
        limit: int = 12
    ) -> Optional[str]:
        candidates_by_key: Dict[str, Dict[str, Any]] = {}

        for image_url, hint in entries:
            normalized_url = self._normalize_candidate_url(image_url)
            if not normalized_url:
                continue

            score = self._score_candidate(normalized_url, hint, link_type)
            if score <= 0:
                continue

            candidate_key = self._candidate_key(normalized_url)
            existing = candidates_by_key.get(candidate_key)
            if existing and existing['score'] >= score:
                continue

            candidates_by_key[candidate_key] = {
                'url': normalized_url,
                'hint': hint,
                'score': score,
            }

        ordered_candidates = sorted(
            candidates_by_key.values(),
            key=lambda item: (-item['score'], item['url'])
        )

        for candidate in ordered_candidates[:limit]:
            if await self.validator.validate_image_url(candidate['url']):
                return candidate['url']

        return None

    async def _validate_urls_in_order(self, image_urls: List[str]) -> List[str]:
        valid_urls: List[str] = []
        for image_url in self._dedupe_urls(image_urls):
            if await self.validator.validate_image_url(image_url):
                valid_urls.append(image_url)
        return valid_urls

    def _score_candidate(self, image_url: str, hint: str, link_type: str) -> int:
        if not self._is_gaoding_design_candidate(image_url):
            return -1000

        score = 0
        url_lower = image_url.lower()
        hint_lower = (hint or '').lower()
        hostname = (urlparse(image_url).hostname or '').lower()

        if hostname.endswith('gaoding-market.dancf.com'):
            score += 260
        elif hostname.endswith('gaoding-market-fat.dancf.com'):
            score += 240
        elif hostname.endswith('dancf.com'):
            score += 120
        elif 'gaoding.com' in hostname:
            score += 80

        if '/market-operations/' in url_lower:
            score += 90
        if '/side/' in url_lower:
            score += 45

        if '.jpg' in url_lower or '.jpeg' in url_lower:
            score += 35
        elif '.png' in url_lower:
            score += 30
        elif '.webp' in url_lower:
            score += 20
        elif '.gif' in url_lower:
            score += 10

        if 'x-oss-process=' in url_lower:
            score -= 15

        for keyword, bonus in [
            ('source_preview_info', 340),
            ('original_preview_info', 320),
            ('export_url', 320),
            ('download_url', 300),
            ('original_url', 280),
            ('origin_url', 260),
            ('source_url', 240),
            ('raw_url', 220),
            ('full_url', 200),
            ('master_url', 200),
            ('hd_url', 180),
        ]:
            if keyword in hint_lower:
                score += bonus

        for keyword, bonus in [
            ('export', 220),
            ('download', 200),
            ('original', 180),
            ('origin', 160),
            ('source', 120),
            ('raw', 100),
            ('full', 80),
            ('master', 80),
            ('hd', 60),
        ]:
            if keyword in url_lower:
                score += bonus
            if keyword in hint_lower:
                score += bonus // 2

        for keyword, bonus in [
            ('preview', 60),
            ('cover', 120),
            ('poster', 90),
            ('page', 80),
            ('artboard', 90),
            ('slide', 80),
            ('frame', 75),
            ('work', 70),
            ('render', 70),
            ('template', 60),
            ('image', 45),
        ]:
            if keyword in url_lower:
                score += bonus
            if keyword in hint_lower:
                score += bonus // 2

        if 'preview_info' in hint_lower and 'source_preview_info' not in hint_lower:
            score -= 120
        if any(token in url_lower or token in hint_lower for token in ['watermark', 'with_wm', 'with-watermark']):
            score -= 260

        if 'meta:og:image' in hint_lower:
            score += 220
        elif 'meta:twitter:image' in hint_lower:
            score += 180
        elif 'video:poster' in hint_lower:
            score += 140
        elif hint_lower.startswith('img:'):
            score += 90

        if link_type == 'template' and ('template' in url_lower or 'template' in hint_lower):
            score += 60
        elif link_type == 'editor' and any(token in hint_lower for token in ['page', 'artboard', 'preview', 'cover']):
            score += 40
        elif link_type == 'share' and 'share' in hint_lower:
            score += 30

        if any(token in hint_lower for token in self.NEGATIVE_PATH_HINTS):
            score -= 90

        return score

    def _score_snapshot_candidate(
        self,
        image_url: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> int:
        meta = meta or {}
        score = self._score_candidate(image_url, str(meta.get('source') or ''), 'detail')
        score += min(int(meta.get('area') or 0) // 20000, 120)
        score += min(int(meta.get('visibleArea') or 0) // 12000, 160)
        if meta.get('isCentered'):
            score += 40
        if meta.get('isLarge'):
            score += 55
        return score

    def _normalize_candidate_url(self, raw_url: Any) -> Optional[str]:
        if not isinstance(raw_url, str):
            return None

        candidate_text = html.unescape(raw_url).strip()
        if not candidate_text:
            return None

        candidate_text = candidate_text.replace('\\/', '/')
        candidate_text = candidate_text.replace('\\u0026', '&')
        candidate_text = candidate_text.replace('\\u002F', '/')
        candidate_text = candidate_text.replace('\\u003A', ':')
        candidate_text = candidate_text.replace('\\u003a', ':')
        candidate_text = candidate_text.replace('\\u003D', '=')
        candidate_text = candidate_text.replace('\\u003d', '=')
        candidate_text = candidate_text.replace('&amp;', '&')
        candidate_text = candidate_text.rstrip('\\')

        match = self.IMAGE_URL_PATTERN.search(candidate_text)
        if not match:
            return None

        candidate_url = match.group('url').strip('\'"(),;]}')

        if candidate_url.startswith('//'):
            candidate_url = 'https:' + candidate_url

        if not candidate_url.startswith('http'):
            return None

        candidate_url = candidate_url.split('#', 1)[0]
        candidate_url = self._strip_gaoding_oss_process(candidate_url)
        return candidate_url

    def _strip_gaoding_oss_process(self, image_url: str) -> str:
        parsed = urlparse(image_url)
        hostname = (parsed.hostname or '').lower()
        if 'dancf.com' not in hostname and 'gaoding.com' not in hostname:
            return image_url

        filtered_query = []
        removed_oss = False
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
            if key.lower() == 'x-oss-process':
                removed_oss = True
                continue
            for value in values:
                filtered_query.append((key, value))

        if not removed_oss:
            return image_url

        normalized_query = urlencode(filtered_query, doseq=True)
        normalized = parsed._replace(query=normalized_query, fragment='')
        return urlunparse(normalized)

    def _candidate_key(self, image_url: str) -> str:
        parsed = urlparse(image_url)
        filtered_query = []
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
            if key.lower() in {'x-oss-process', 'format'}:
                continue
            for value in values:
                filtered_query.append((key, value))

        normalized_query = urlencode(filtered_query, doseq=True)
        normalized = parsed._replace(query=normalized_query, fragment='')
        return urlunparse(normalized)

    def _dedupe_entries(self, entries: List[CandidateEntry]) -> List[CandidateEntry]:
        seen = set()
        ordered_entries: List[CandidateEntry] = []
        for image_url, hint in entries:
            candidate_key = self._candidate_key(image_url)
            if candidate_key in seen:
                continue
            seen.add(candidate_key)
            ordered_entries.append((image_url, hint))
        return ordered_entries

    def _dedupe_urls(self, image_urls: List[str]) -> List[str]:
        seen = set()
        ordered_urls: List[str] = []
        for image_url in image_urls:
            normalized_url = self._normalize_candidate_url(image_url)
            if not normalized_url:
                continue
            candidate_key = self._candidate_key(normalized_url)
            if candidate_key in seen:
                continue
            seen.add(candidate_key)
            ordered_urls.append(normalized_url)
        return ordered_urls

    def _is_gaoding_design_candidate(self, image_url: str) -> bool:
        normalized_url = self._normalize_candidate_url(image_url)
        if not normalized_url:
            return False

        url_lower = normalized_url.lower()
        hostname = (urlparse(normalized_url).hostname or '').lower()
        if 'gaoding.com' not in hostname and 'dancf.com' not in hostname:
            return False

        if re.search(r'\.(?:svg|ico|css|js)(?:[?#]|$)', url_lower):
            return False

        blocked_keywords = [
            'favicon',
            'icon',
            'logo',
            'avatar',
            'badge',
            'button',
            'toolbar',
            'cursor',
            'placeholder',
            'header',
            'footer',
            'sprite',
            'apps/gaoding/assets/',
            '/design-tokens/',
            '/npm:@gdesign/',
        ]
        if any(keyword in url_lower for keyword in blocked_keywords):
            return False

        return bool(
            re.search(r'\.(?:png|jpe?g|webp|gif)(?:[?#]|$)', url_lower)
            or '/market-operations/' in url_lower
            or any(keyword in url_lower for keyword in ['/preview', '/cover', '/poster', '/render'])
        )

    def _build_result(
        self,
        image_urls: List[str],
        original_url: str,
        source: str,
        method: str,
        link_type: str,
        score: int = 0
    ) -> Optional[Dict]:
        normalized_urls = self._dedupe_urls(image_urls)
        if not normalized_urls:
            return None

        return {
            'imageUrl': normalized_urls[0],
            'imageUrls': normalized_urls,
            'pages': [
                {
                    'page': index + 1,
                    'imageUrl': image_url,
                }
                for index, image_url in enumerate(normalized_urls)
            ],
            'pageCount': len(normalized_urls),
            'isMultiPage': len(normalized_urls) > 1,
            'platform': 'Gaoding',
            'source': source,
            'method': method,
            'score': score,
            'linkType': link_type,
            'original_url': original_url,
        }

    async def close(self):
        if self.validator:
            await self.validator.close()
