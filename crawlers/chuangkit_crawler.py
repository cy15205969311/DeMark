"""
创客贴 (Chuangkit) 爬虫
支持分享页主画布提取与套图逐页抓取。
"""
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional, Tuple
import logging
import sys
import os
import re
import time
from urllib.parse import urljoin, urlparse

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.image_validator import ImageValidator


class ChuangkitCrawler:
    """创客贴爬虫，优先提取当前设计稿，再尝试逐页构造套图结果。"""

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
        """提取创客贴图片，优先动态抓取套图。"""
        session = None
        try:
            logging.info(f"🧩 开始创客贴抓取: {url}")

            link_type = (
                'share' if '/sharedesign' in url
                else 'design' if '/designs/' in url
                else 'template' if '/templates/' in url
                else 'other'
            )
            logging.info(f"📋 链接类型: {link_type}")

            import socket
            connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=False)
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), connector=connector)

            # 分享页往往是动态渲染，优先走动态抓取，避免静态 meta 误命中封面图。
            result = await self._dynamic_scraping(url, link_type)
            if result:
                return result

            result = await self._static_scraping(session, url, link_type)
            if result:
                return result

            return None

        except Exception as error:
            logging.error(f"❌ 创客贴抓取异常: {error}")
            return None
        finally:
            if session:
                await session.close()

    async def _static_scraping(
        self,
        session: aiohttp.ClientSession,
        url: str,
        link_type: str
    ) -> Optional[Dict]:
        """静态抓取兜底，主要处理明确暴露的预览图。"""
        try:
            async with session.get(url, headers=self.headers) as response:
                if response.status != 200:
                    return None
                html_content = await response.text()

            soup = BeautifulSoup(html_content, 'lxml')

            meta_selectors = [
                ('meta[property="og:image"]', 'content'),
                ('meta[name="twitter:image"]', 'content'),
                ('link[rel="image_src"]', 'href')
            ]

            for selector, attr in meta_selectors:
                element = soup.select_one(selector)
                if not element or not element.get(attr):
                    continue

                image_url = self._normalize_candidate_url(element[attr])
                if not image_url or not self._is_chuangkit_design_candidate(image_url):
                    continue

                if await self.validator.validate_image_url(image_url):
                    return self._build_result(
                        [image_url],
                        url,
                        'meta',
                        'meta_extraction',
                        link_type,
                        score=200
                    )

            selectors = [
                'img[src*="chuangkit"]',
                'img[src*="render_result"]',
                '.design-preview img',
                '.template-preview img',
                '.share-preview img'
            ]

            candidate_urls: List[str] = []
            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    img_src = element.get('src') or element.get('data-src')
                    if not img_src:
                        continue
                    image_url = self._normalize_candidate_url(
                        img_src if img_src.startswith('http') else urljoin(url, img_src)
                    )
                    if image_url:
                        candidate_urls.append(image_url)

            valid_urls = await self._validate_urls_in_order(candidate_urls)
            if valid_urls:
                return self._build_result(
                    [valid_urls[0]],
                    url,
                    'dom',
                    'dom_extraction',
                    link_type,
                    score=180
                )

            return None

        except Exception as error:
            logging.debug(f"静态抓取失败: {error}")
            return None

    async def _dynamic_scraping(self, url: str, link_type: str) -> Optional[Dict]:
        """动态抓取，优先逐页提取套图，失败后退回旧版候选图选择。"""
        browser_service = None
        try:
            from core.browser_service import BrowserService

            browser_service = BrowserService()

            result = await self._extract_multi_page_with_browser(browser_service, url, link_type)
            if result:
                return result

            images = await browser_service.extract_images_from_page(url, headless=True)
            if images:
                logging.info(f"📊 找到 {len(images)} 个图片")

                scored_images = []
                for img in images:
                    src = self._normalize_candidate_url(img.get('src'))
                    if not src:
                        continue
                    score = self._calculate_fallback_score({**img, 'src': src})
                    scored_images.append({'data': {**img, 'src': src}, 'score': score})
                    logging.info(f"🎯 图片评分: {src[:60]}... → {score}分")

                scored_images.sort(key=lambda item: item['score'], reverse=True)

                for candidate in scored_images:
                    candidate_url = candidate['data']['src']
                    if candidate['score'] <= 100:
                        continue
                    if not self._is_chuangkit_design_candidate(candidate_url):
                        continue
                    if not await self.validator.validate_image_url(candidate_url):
                        continue

                    logging.info(f"✅ 选择图片 (评分: {candidate['score']})")
                    return self._build_result(
                        [candidate_url],
                        url,
                        'selenium-extraction',
                        'dynamic_extraction',
                        link_type,
                        score=candidate['score']
                    )

            return None

        except Exception as error:
            logging.debug(f"动态抓取失败: {error}")
            return None
        finally:
            if browser_service:
                await browser_service.close()

    async def _extract_multi_page_with_browser(
        self,
        browser_service,
        url: str,
        link_type: str
    ) -> Optional[Dict]:
        """用真实浏览器逐页点击创客贴分页，提取整套设计稿。"""
        driver = None
        try:
            logging.info(f"🖼️ 开始创客贴套图提取: {url}")
            driver = browser_service._get_stealth_driver(headless=True)
            driver.get(url)

            time.sleep(6)

            initial_snapshot = browser_service._capture_dynamic_snapshot(driver)
            initial_url, initial_score = await self._select_best_snapshot_url(initial_snapshot)
            initial_render_urls = await self._validate_urls_in_order(
                self._extract_render_result_urls(initial_snapshot)
            )

            page_numbers = self._extract_chuangkit_page_numbers(driver)
            if page_numbers:
                logging.info(f"📄 创客贴识别到分页: {page_numbers}")
            else:
                logging.info("📄 创客贴未识别到分页数字，按单页主画布处理")

            if initial_render_urls:
                logging.info(f"🗂️ 创客贴预加载设计稿资源: {len(initial_render_urls)}")

            if len(initial_render_urls) > 1 and (not page_numbers or len(initial_render_urls) >= len(page_numbers)):
                return self._build_result(
                    initial_render_urls,
                    url,
                    'dynamic-resource-pages',
                    'dynamic_resource_collection',
                    link_type,
                    score=max(initial_score, 1800)
                )

            result_urls: List[str] = []
            seen_result_keys = set()
            scores: List[int] = []

            for image_url in initial_render_urls:
                result_urls.append(image_url)
                seen_result_keys.add(self._candidate_key(image_url))
                scores.append(max(initial_score, 1800))

            if initial_url and self._candidate_key(initial_url) not in seen_result_keys:
                result_urls.append(initial_url)
                seen_result_keys.add(self._candidate_key(initial_url))
                scores.append(initial_score)

            known_pool_keys = {
                self._candidate_key(candidate_url)
                for candidate_url in self._collect_snapshot_url_pool(initial_snapshot)
            }

            page_sequence = page_numbers[1:] if initial_url else page_numbers

            for page_number in page_sequence:
                activation = self._activate_chuangkit_page(driver, page_number)
                time.sleep(1.5)

                snapshot = browser_service._capture_dynamic_snapshot(driver)
                snapshot_pool = self._collect_snapshot_url_pool(snapshot)
                preferred_urls = [
                    candidate_url
                    for candidate_url in snapshot_pool
                    if self._candidate_key(candidate_url) not in known_pool_keys
                ]

                selected_url, selected_score = await self._select_best_snapshot_url(
                    snapshot,
                    preferred_urls=preferred_urls
                )

                logging.info(
                    f"📄 创客贴逐页采样 #{page_number}: "
                    f"clicked={activation.get('clicked')}, "
                    f"newUrls={len(preferred_urls)}, "
                    f"selected={selected_url[:80] if selected_url else 'None'}"
                )

                known_pool_keys.update(self._candidate_key(candidate_url) for candidate_url in snapshot_pool)

                new_render_urls = await self._validate_urls_in_order(
                    [
                        candidate_url
                        for candidate_url in self._extract_render_result_urls(snapshot)
                        if self._candidate_key(candidate_url) not in seen_result_keys
                    ]
                )
                for image_url in new_render_urls:
                    result_urls.append(image_url)
                    seen_result_keys.add(self._candidate_key(image_url))
                    scores.append(max(selected_score, 1800))

                if not selected_url:
                    continue

                candidate_key = self._candidate_key(selected_url)
                if candidate_key in seen_result_keys:
                    continue

                result_urls.append(selected_url)
                seen_result_keys.add(candidate_key)
                scores.append(selected_score)

            if result_urls:
                return self._build_result(
                    self._dedupe_urls(result_urls),
                    url,
                    'dynamic-multipage' if len(result_urls) > 1 else 'dynamic-main-canvas',
                    'dynamic_page_activation',
                    link_type,
                    score=max(scores) if scores else 0
                )

            return None

        except Exception as error:
            logging.debug(f"创客贴套图浏览器提取失败: {error}")
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                    logging.info("✅ Chrome驱动已关闭")
                except Exception:
                    pass

    def _extract_chuangkit_page_numbers(self, driver) -> List[int]:
        """识别创客贴底部页码按钮。"""
        try:
            page_numbers = driver.execute_script("""
                function normalizeText(value) {
                    return (value || '').replace(/\\s+/g, '').trim();
                }

                function isVisible(el) {
                    if (!el) return false;
                    var rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                }

                var values = [];
                Array.from(document.querySelectorAll('*')).forEach(function(el) {
                    try {
                        if (!isVisible(el)) return;
                        var text = normalizeText(el.innerText || el.textContent || '');
                        if (!/^\\d+$/.test(text)) return;

                        var rect = el.getBoundingClientRect();
                        var className = String(el.className || '').toLowerCase();
                        var parentClass = String((el.parentElement && el.parentElement.className) || '').toLowerCase();

                        if (rect.top < window.innerHeight * 0.7) return;
                        if (rect.width < 10 || rect.height < 10) return;
                        if (
                            !/page|pager|pagination|footer|thumb|index|num|item|switch/.test(className + ' ' + parentClass) &&
                            rect.top < window.innerHeight - 140
                        ) {
                            return;
                        }

                        values.push(parseInt(text, 10));
                    } catch (e) {}
                });

                values = Array.from(new Set(values)).filter(function(value) {
                    return Number.isFinite(value) && value > 0 && value < 100;
                });
                values.sort(function(a, b) { return a - b; });
                return values;
            """)

            if not isinstance(page_numbers, list):
                return []

            return [page_number for page_number in page_numbers if isinstance(page_number, int)]
        except Exception:
            return []

    def _activate_chuangkit_page(self, driver, page_number: int) -> Dict[str, Any]:
        """点击创客贴底部分页数字。"""
        try:
            return driver.execute_script("""
                var targetPage = String(arguments[0]);

                function normalizeText(value) {
                    return (value || '').replace(/\\s+/g, '').trim();
                }

                function isVisible(el) {
                    if (!el) return false;
                    var rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                }

                function scoreCandidate(el) {
                    var rect = el.getBoundingClientRect();
                    var className = String(el.className || '').toLowerCase();
                    var parentClass = String((el.parentElement && el.parentElement.className) || '').toLowerCase();
                    var score = 0;
                    if (rect.top >= window.innerHeight * 0.7) score += 180;
                    if (rect.top >= window.innerHeight - 120) score += 100;
                    if (/page|pager|pagination|footer|thumb|index|num|item|switch/.test(className + ' ' + parentClass)) score += 120;
                    if (rect.width >= 20 && rect.height >= 20) score += 40;
                    return score;
                }

                var candidates = Array.from(document.querySelectorAll('*')).filter(function(el) {
                    if (!isVisible(el)) return false;
                    return normalizeText(el.innerText || el.textContent || '') === targetPage;
                }).sort(function(a, b) {
                    return scoreCandidate(b) - scoreCandidate(a);
                });

                var target = candidates[0];
                if (!target) {
                    return {
                        requestedPage: targetPage,
                        clicked: false,
                        reason: 'page_not_found'
                    };
                }

                try {
                    target.scrollIntoView({block: 'center', inline: 'center'});
                } catch (e) {}

                var rect = target.getBoundingClientRect();
                var clientX = rect.left + Math.min(rect.width / 2, Math.max(rect.width - 8, 1));
                var clientY = rect.top + Math.min(rect.height / 2, Math.max(rect.height - 8, 1));
                var clicked = false;

                function dispatchMouse(el, type) {
                    try {
                        el.dispatchEvent(new MouseEvent(type, {
                            view: window,
                            bubbles: true,
                            cancelable: true,
                            clientX: clientX,
                            clientY: clientY,
                            buttons: 1
                        }));
                        return true;
                    } catch (e) {
                        return false;
                    }
                }

                ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(function(type) {
                    if (dispatchMouse(target, type)) {
                        clicked = true;
                    }
                });

                try {
                    target.click();
                    clicked = true;
                } catch (e) {}

                return {
                    requestedPage: targetPage,
                    clicked: clicked,
                    reason: clicked ? 'clicked' : 'no_click_effect',
                    targetClass: String(target.className || '')
                };
            """, page_number)
        except Exception:
            return {
                'requestedPage': str(page_number),
                'clicked': False,
                'reason': 'script_error'
            }

    def _collect_snapshot_url_pool(self, snapshot: Dict[str, Any]) -> List[str]:
        """收集一次快照中的所有候选 URL。"""
        urls: List[str] = []

        for candidate in snapshot.get('visibleCandidates', []) or []:
            urls.append(candidate.get('url'))

        for image_url in snapshot.get('resourceUrls', []) or []:
            urls.append(image_url)

        for image_url in snapshot.get('imageUrls', []) or []:
            urls.append(image_url)

        for image_url in self._extract_urls_from_text(snapshot.get('pageSource', '') or ''):
            urls.append(image_url)

        return self._dedupe_urls(urls)

    def _extract_render_result_urls(self, snapshot: Dict[str, Any]) -> List[str]:
        """从快照资源中按发现顺序提取创客贴设计稿渲染图。"""
        urls: List[str] = []

        for image_url in snapshot.get('resourceUrls', []) or []:
            urls.append(image_url)

        for image_url in snapshot.get('imageUrls', []) or []:
            urls.append(image_url)

        for image_url in self._extract_urls_from_text(snapshot.get('pageSource', '') or ''):
            urls.append(image_url)

        return [
            image_url
            for image_url in self._dedupe_urls(urls)
            if 'svg_build/render_result/' in image_url.lower() or 'render_result/' in image_url.lower()
        ]

    async def _select_best_snapshot_url(
        self,
        snapshot: Dict[str, Any],
        preferred_urls: Optional[List[str]] = None
    ) -> Tuple[Optional[str], int]:
        """从一次创客贴快照中选出最像主设计稿的图片。"""
        candidates = self._collect_snapshot_candidates(snapshot, preferred_urls=preferred_urls)

        for candidate in candidates[:8]:
            if await self.validator.validate_image_url(candidate['url']):
                return candidate['url'], candidate['score']

        return None, 0

    def _collect_snapshot_candidates(
        self,
        snapshot: Dict[str, Any],
        preferred_urls: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """聚合创客贴主画布候选，并按可信度排序。"""
        preferred_keys = {
            self._candidate_key(candidate_url)
            for candidate_url in (preferred_urls or [])
            if self._normalize_candidate_url(candidate_url)
        }
        candidates_by_key: Dict[str, Dict[str, Any]] = {}

        def add_candidate(raw_url: Optional[str], meta: Optional[Dict[str, Any]] = None) -> None:
            candidate_url = self._normalize_candidate_url(raw_url)
            if not candidate_url:
                return

            candidate_key = self._candidate_key(candidate_url)
            score = self._score_snapshot_candidate(candidate_url, meta or {}, preferred_keys)
            if score <= 0:
                return

            candidate = {
                'url': candidate_url,
                'score': score,
                'meta': meta or {}
            }

            existing = candidates_by_key.get(candidate_key)
            if existing and existing['score'] >= score:
                return

            candidates_by_key[candidate_key] = candidate

        for visible_candidate in snapshot.get('visibleCandidates', []) or []:
            if not isinstance(visible_candidate, dict):
                continue
            add_candidate(visible_candidate.get('url'), visible_candidate)

        for image_url in preferred_urls or []:
            add_candidate(image_url, {'source': 'preferred', 'preferred': True})

        for image_url in snapshot.get('resourceUrls', []) or []:
            add_candidate(image_url, {'source': 'resource'})

        for image_url in snapshot.get('imageUrls', []) or []:
            add_candidate(image_url, {'source': 'image'})

        for image_url in self._extract_urls_from_text(snapshot.get('pageSource', '') or ''):
            add_candidate(image_url, {'source': 'page_source'})

        ordered_candidates = sorted(
            candidates_by_key.values(),
            key=lambda item: (
                -item['score'],
                -int(item['meta'].get('visibleArea') or 0),
                -int(item['meta'].get('area') or 0),
                item['url']
            )
        )

        return ordered_candidates

    def _score_snapshot_candidate(
        self,
        url: str,
        meta: Dict[str, Any],
        preferred_keys: set
    ) -> int:
        """为创客贴候选图打分，重点偏向主画布的大图。"""
        normalized_url = self._normalize_candidate_url(url)
        if not normalized_url or not self._is_chuangkit_design_candidate(normalized_url):
            return -1000

        score = 0
        candidate_key = self._candidate_key(normalized_url)
        url_lower = normalized_url.lower()
        host = (urlparse(normalized_url).hostname or '').lower()

        if candidate_key in preferred_keys:
            score += 220

        if 'pri-cdn-oss.chuangkit.com' in host:
            score += 320
        elif 'chuangkit' in host:
            score += 160

        if 'svg_build/render_result/' in url_lower:
            score += 560
        elif 'render_result' in url_lower:
            score += 320
        elif any(keyword in url_lower for keyword in ['design', 'preview', 'work']):
            score += 90

        if 'sign=' in url_lower:
            score += 40

        width = int(meta.get('width') or 0)
        height = int(meta.get('height') or 0)
        area = int(meta.get('area') or (width * height))
        visible_area = int(meta.get('visibleArea') or 0)
        left = float(meta.get('left') or 0)
        center_distance = float(meta.get('centerDistance') or 0)
        source = str(meta.get('source') or '')

        if visible_area >= 450000:
            score += 680
        elif visible_area >= 180000:
            score += 360
        elif visible_area >= 60000:
            score += 120

        if area >= 900000:
            score += 180
        elif area >= 300000:
            score += 100

        if width >= 600 and height >= 900:
            score += 200
        elif width >= 320 and height >= 480:
            score += 90

        if meta.get('isCentered'):
            score += 320
        if meta.get('isLarge'):
            score += 160

        if source in ['src', 'currentSrc', 'background']:
            score += 40
        elif source == 'resource':
            score += 20

        # 创客贴分享页左侧推荐模板多在左栏，主设计稿通常更靠中间。
        if left and left < 460 and not meta.get('isCentered') and width < 420:
            score -= 340

        if center_distance and center_distance > 900:
            score -= 120

        return score

    def _calculate_fallback_score(self, img_data: Dict[str, Any]) -> int:
        """回退到旧版图片元素提取时的评分。"""
        score = 100

        width = int(img_data.get('width') or 0)
        height = int(img_data.get('height') or 0)
        src = str(img_data.get('src') or '').lower()
        img_type = img_data.get('type', '')

        if width > 100 and height > 100:
            score += 200
        if width > 200 and height > 200:
            score += 300

        if 'chuangkit' in src:
            score += 300
        if 'svg_build/render_result/' in src:
            score += 500
        elif any(keyword in src for keyword in ['design', 'template', 'work', 'preview']):
            score += 180
        if any(keyword in src for keyword in ['main', 'primary']):
            score += 120

        if any(keyword in src for keyword in ['distheadless/img/share_', 'logo', 'icon', 'avatar', 'sprite']):
            score -= 500

        if img_type == 'background':
            score += 120
        elif img_type == 'canvas':
            score += 160

        return score

    async def _validate_urls_in_order(self, candidate_urls: List[str]) -> List[str]:
        """按发现顺序校验 URL，保留有效设计稿。"""
        valid_urls: List[str] = []
        seen_keys = set()

        for candidate_url in candidate_urls:
            normalized_url = self._normalize_candidate_url(candidate_url)
            if not normalized_url or not self._is_chuangkit_design_candidate(normalized_url):
                continue

            candidate_key = self._candidate_key(normalized_url)
            if candidate_key in seen_keys:
                continue

            if await self.validator.validate_image_url(normalized_url):
                valid_urls.append(normalized_url)
                seen_keys.add(candidate_key)

        return valid_urls

    def _extract_urls_from_text(self, text: str) -> List[str]:
        """从源码或文本块中抓取创客贴图片 URL。"""
        if not isinstance(text, str) or not text:
            return []

        urls: List[str] = []

        for match in re.findall(r'https?://[^"\'\s<>\)]+', text, re.IGNORECASE):
            urls.append(match)

        for match in re.findall(r'//[^"\'\s<>\)]+', text, re.IGNORECASE):
            urls.append(f'https:{match}')

        return self._dedupe_urls(urls)

    def _dedupe_urls(self, urls: List[Optional[str]]) -> List[str]:
        """按去查询参数后的路径去重，保留首个可用 URL。"""
        deduped_urls: List[str] = []
        seen_keys = set()

        for raw_url in urls:
            normalized_url = self._normalize_candidate_url(raw_url)
            if not normalized_url:
                continue

            candidate_key = self._candidate_key(normalized_url)
            if candidate_key in seen_keys:
                continue

            deduped_urls.append(normalized_url)
            seen_keys.add(candidate_key)

        return deduped_urls

    def _normalize_candidate_url(self, url: Optional[str]) -> Optional[str]:
        """规范化候选 URL。"""
        if not isinstance(url, str):
            return None

        candidate = url.strip().strip('\'"')
        if not candidate:
            return None

        candidate = candidate.replace('\\/', '/')
        if candidate.startswith('//'):
            candidate = f'https:{candidate}'

        if not candidate.startswith('http'):
            return None

        return candidate

    def _candidate_key(self, url: str) -> str:
        """用无签名路径作为创客贴候选图去重键。"""
        normalized_url = self._normalize_candidate_url(url)
        if not normalized_url:
            return ''

        parsed_url = urlparse(normalized_url)
        return f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}".lower()

    def _is_chuangkit_design_candidate(self, url: str) -> bool:
        """判断 URL 是否像创客贴设计稿页，而不是站点装饰资源。"""
        normalized_url = self._normalize_candidate_url(url)
        if not normalized_url:
            return False

        parsed_url = urlparse(normalized_url)
        host = (parsed_url.hostname or '').lower()
        url_lower = normalized_url.lower()

        if 'chuangkit' not in host:
            return False

        blocked_keywords = [
            'distheadless/img/share_',
            'share_header',
            'logo',
            'icon',
            'avatar',
            'sprite',
            'favicon',
            'emoji',
            'toolbar',
            'button',
            'placeholder',
            'default',
        ]
        if any(keyword in url_lower for keyword in blocked_keywords):
            return False

        return any(keyword in url_lower for keyword in [
            'render_result',
            'svg_build',
            'preview',
            'design',
            'work',
        ])

    def _build_result(
        self,
        image_urls: List[str],
        original_url: str,
        source: str,
        method: str,
        link_type: str,
        score: int = 0
    ) -> Optional[Dict]:
        """构造兼容单页和套图的统一结果结构。"""
        normalized_urls = self._dedupe_urls(image_urls)
        if not normalized_urls:
            return None

        return {
            'imageUrl': normalized_urls[0],
            'imageUrls': normalized_urls,
            'pages': [
                {
                    'page': index + 1,
                    'imageUrl': image_url
                }
                for index, image_url in enumerate(normalized_urls)
            ],
            'pageCount': len(normalized_urls),
            'isMultiPage': len(normalized_urls) > 1,
            'platform': 'Chuangkit',
            'source': source,
            'method': method,
            'score': score,
            'linkType': link_type,
            'original_url': original_url
        }

    async def close(self):
        """关闭资源。"""
        if self.validator:
            await self.validator.close()
