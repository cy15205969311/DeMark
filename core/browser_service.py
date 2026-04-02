"""
浏览器服务 - 驱动配置清洗版
解决Chrome驱动兼容性问题，移除冲突配置
"""
import logging
import os
import sys
import re
import subprocess
import tempfile
from typing import Optional, Dict, List, Any
import time

class BrowserService:
    """
    浏览器服务 - 增强版
    解决Chrome驱动配置冲突，支持多种Chrome安装路径
    """
    
    def __init__(self):
        self.driver = None
        self.chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(os.getenv('USERNAME', '')),
            r"C:\Program Files\Chromium\Application\chrome.exe",
        ]
    
    def _find_chrome_executable(self) -> Optional[str]:
        """
        查找Chrome可执行文件路径
        """
        for path in self.chrome_paths:
            if os.path.exists(path):
                logging.info(f"✅ 找到Chrome浏览器: {path}")
                return path
        
        logging.warning("⚠️ 未找到Chrome浏览器")
        return None

    def dump_dom_with_local_chrome(
        self,
        url: str,
        virtual_time_budget_ms: int = 12000,
        timeout_seconds: int = 40
    ) -> Optional[str]:
        """
        直接调用本机 Chrome 输出渲染后的 DOM。

        这条路径不依赖 chromedriver，适合在动态页静态源码不够、
        但又不希望把成功率完全压在 Selenium 上时使用。
        """
        chrome_path = self._find_chrome_executable()
        if not chrome_path:
            logging.warning("⚠️ 无法执行本地Chrome渲染：未找到Chrome浏览器")
            return None

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        temp_output = tempfile.NamedTemporaryFile(
            prefix=f"demark_chrome_dump_{os.getpid()}_{int(time.time() * 1000)}_",
            suffix=".html",
            delete=False
        )
        output_path = temp_output.name
        temp_output.close()

        command = [
            chrome_path,
            "--headless=new",
            "--disable-gpu",
            "--disable-extensions",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-popup-blocking",
            "--run-all-compositor-stages-before-draw",
            f"--virtual-time-budget={int(virtual_time_budget_ms)}",
            "--window-size=1600,3200",
            "--dump-dom",
            url,
        ]

        try:
            logging.info(f"🌐 使用本地Chrome渲染DOM: {url}")
            if os.name == "nt":
                def ps_quote(value: str) -> str:
                    return "'" + value.replace("'", "''") + "'"

                argument_list = "@(" + ",".join(
                    ps_quote(argument) for argument in command[1:]
                ) + ")"
                script = (
                    f"$p = Start-Process -FilePath {ps_quote(command[0])} "
                    f"-ArgumentList {argument_list} "
                    f"-RedirectStandardOutput {ps_quote(output_path)} "
                    f"-Wait -PassThru; "
                    f"exit $p.ExitCode"
                )
                completed = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        script,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=timeout_seconds + 10,
                    creationflags=creation_flags,
                    check=False,
                )
            else:
                with open(output_path, "w", encoding="utf-8", errors="ignore") as output_file:
                    completed = subprocess.run(
                        command,
                        stdout=output_file,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        encoding="utf-8",
                        errors="ignore",
                        timeout=timeout_seconds,
                        creationflags=creation_flags,
                        check=False,
                    )
        except subprocess.TimeoutExpired:
            logging.warning("⚠️ 本地Chrome渲染DOM超时")
            return None
        except Exception as error:
            logging.warning(f"⚠️ 本地Chrome渲染DOM失败: {error}")
            return None

        try:
            with open(output_path, "r", encoding="utf-8", errors="ignore") as output_file:
                dom_content = output_file.read().strip()
        except Exception as error:
            logging.warning(f"⚠️ 读取本地Chrome渲染DOM失败: {error}")
            return None
        finally:
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except OSError:
                pass

        if completed.returncode != 0:
            logging.warning(
                f"⚠️ 本地Chrome渲染DOM返回异常退出码: {completed.returncode}"
            )

        if not dom_content or "<html" not in dom_content.lower():
            logging.warning("⚠️ 本地Chrome未输出有效DOM内容")
            return None

        logging.info(f"✅ 本地Chrome渲染DOM成功 ({len(dom_content)} 字符)")
        return dom_content

    def _get_chrome_version(self) -> Optional[int]:
        """
        获取本地Chrome浏览器的主版本号
        """
        chrome_path = self._find_chrome_executable()
        if not chrome_path:
            return None

        version_sources = [
            self._get_windows_file_version,
            self._get_version_from_command,
        ]

        for getter in version_sources:
            try:
                major_version = getter(chrome_path)
                if major_version:
                    logging.info(f"🔍 检测到Chrome版本: {major_version}")
                    return major_version
            except Exception as e:
                logging.debug(f"Chrome版本探测方法失败: {getter.__name__} - {e}")

        logging.warning("⚠️ 未能自动检测到Chrome版本，将交给驱动自动匹配")
        return None

    def _parse_chrome_major_version(self, version_text: str) -> Optional[int]:
        """
        从任意版本字符串中提取Chrome主版本号
        """
        if not version_text:
            return None

        version_match = re.search(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', version_text)
        if version_match:
            return int(version_match.group(1))

        version_match = re.search(r'(\d+)\.', version_text)
        if version_match:
            return int(version_match.group(1))

        return None

    def _dedupe_keep_order(self, items: List[str]) -> List[str]:
        """Deduplicate strings while preserving discovery order."""
        seen = set()
        ordered_items: List[str] = []

        for item in items:
            if not isinstance(item, str):
                continue
            normalized_item = item.strip()
            if not normalized_item or normalized_item in seen:
                continue
            seen.add(normalized_item)
            ordered_items.append(normalized_item)

        return ordered_items

    def _extract_page_number(self, label: Any) -> Optional[int]:
        """Extract page numbers from labels such as 第1页."""
        if not isinstance(label, str):
            return None

        match = re.search(r'\u7b2c\s*(\d+)\s*\u9875', label)
        if not match:
            return None

        return int(match.group(1))

    def _score_preview_candidate(self, candidate: Dict[str, Any], preferred_urls: Optional[set] = None) -> int:
        """Score preview-like image candidates captured from the browser DOM."""
        url = str(candidate.get('url') or '').strip()
        if not url:
            return -1000

        url_lower = url.lower()
        blocked_keywords = [
            'ips_svg/',
            'ips_group_word/',
            'ips_icon/',
            'ips_material/',
            'ips_user_preview_api',
            'editor/',
            'material/',
            'element/',
            'asset/',
            'sticker',
            'watermark',
            'toolbar',
            'button',
            'crown',
            'badge',
            'vip',
            'icon',
            'logo',
        ]
        if any(keyword in url_lower for keyword in blocked_keywords):
            return -1000

        score = 0
        if preferred_urls and url in preferred_urls:
            score += 220

        if 'user_preview_ue' in url_lower:
            score += 480
        elif 'user_preview' in url_lower:
            score += 380
        elif 'preview' in url_lower:
            score += 140

        if 'auth_key=' in url_lower:
            score += 50
        if '!l1600' in url_lower or '!l2000' in url_lower or '!l3000' in url_lower:
            score += 50

        if '.jpg' in url_lower or '.jpeg' in url_lower:
            score += 35
        elif '.png' in url_lower:
            score += 20

        area = int(candidate.get('area') or 0)
        visible_area = int(candidate.get('visibleArea') or 0)
        score += min(area // 12000, 90)
        score += min(visible_area // 6000, 140)

        source = str(candidate.get('source') or '')
        if source in ['src', 'currentSrc']:
            score += 30
        elif 'background' in source:
            score += 20
        elif source == 'resource':
            score += 15

        if candidate.get('isCentered'):
            score += 25
        if candidate.get('isLarge'):
            score += 35

        return score

    def _select_snapshot_preview_urls(
        self,
        snapshot: Optional[Dict[str, Any]],
        preferred_urls: Optional[List[str]] = None,
        limit: int = 3
    ) -> List[str]:
        """Pick the best preview-like URLs from one browser snapshot."""
        snapshot = snapshot or {}
        preferred_set = {
            url.strip()
            for url in (preferred_urls or [])
            if isinstance(url, str) and url.strip()
        }
        candidates_by_url: Dict[str, Dict[str, Any]] = {}

        def add_candidate(raw_url: Optional[str], **meta: Any) -> None:
            if not isinstance(raw_url, str):
                return

            candidate_url = raw_url.strip()
            if not candidate_url:
                return

            candidate = {
                'url': candidate_url,
                'source': meta.get('source', ''),
                'area': int(meta.get('area') or 0),
                'visibleArea': int(meta.get('visibleArea') or 0),
                'isCentered': bool(meta.get('isCentered')),
                'isLarge': bool(meta.get('isLarge')),
            }
            candidate['score'] = self._score_preview_candidate(candidate, preferred_set)
            if candidate['score'] <= 0:
                return

            existing = candidates_by_url.get(candidate_url)
            if existing and existing['score'] >= candidate['score']:
                return

            candidates_by_url[candidate_url] = candidate

        for visible_candidate in snapshot.get('visibleCandidates', []) or []:
            if not isinstance(visible_candidate, dict):
                continue

            add_candidate(
                visible_candidate.get('url'),
                source=visible_candidate.get('source', ''),
                area=visible_candidate.get('area', 0),
                visibleArea=visible_candidate.get('visibleArea', 0),
                isCentered=visible_candidate.get('isCentered', False),
                isLarge=visible_candidate.get('isLarge', False),
            )

        for resource_url in snapshot.get('resourceUrls', []) or []:
            add_candidate(resource_url, source='resource')

        for image_url in snapshot.get('imageUrls', []) or []:
            add_candidate(image_url, source='imageUrls')

        ordered_candidates = sorted(
            candidates_by_url.values(),
            key=lambda item: (
                -item['score'],
                -item['visibleArea'],
                -item['area'],
                item['url'],
            )
        )

        return [item['url'] for item in ordered_candidates[:limit]]

    def _merge_dynamic_capture(self, base: Optional[Dict[str, Any]], snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge one browser snapshot into the accumulated dynamic extraction result."""
        merged: Dict[str, Any] = dict(base or {})
        snapshot = snapshot or {}

        merged.setdefault('pageSource', '')
        merged.setdefault('windowData', {})
        merged.setdefault('jsonData', [])
        merged.setdefault('apiData', {})
        merged.setdefault('imageUrls', [])
        merged.setdefault('resourceUrls', [])
        merged.setdefault('visibleCandidates', [])
        merged.setdefault('pageMarkers', [])
        merged.setdefault('scrollTrace', [])
        merged.setdefault('pageSnapshots', [])
        merged.setdefault('pageSpecificImages', [])

        page_source = snapshot.get('pageSource') or ''
        if len(page_source) >= len(merged.get('pageSource', '')):
            merged['pageSource'] = page_source

        merged['windowData'].update(snapshot.get('windowData') or {})
        merged['apiData'].update(snapshot.get('apiData') or {})

        existing_json_keys = {repr(item) for item in merged['jsonData']}
        for json_item in snapshot.get('jsonData') or []:
            json_key = repr(json_item)
            if json_key not in existing_json_keys:
                merged['jsonData'].append(json_item)
                existing_json_keys.add(json_key)

        merged['imageUrls'] = self._dedupe_keep_order(
            merged['imageUrls'] + (snapshot.get('imageUrls') or [])
        )
        merged['resourceUrls'] = self._dedupe_keep_order(
            merged['resourceUrls'] + (snapshot.get('resourceUrls') or [])
        )
        merged['pageMarkers'] = self._dedupe_keep_order(
            merged['pageMarkers'] + (snapshot.get('pageMarkers') or [])
        )

        visible_candidates_by_url: Dict[str, Dict[str, Any]] = {}
        for candidate in (merged.get('visibleCandidates') or []) + (snapshot.get('visibleCandidates') or []):
            if not isinstance(candidate, dict):
                continue

            candidate_url = str(candidate.get('url') or '').strip()
            if not candidate_url:
                continue

            existing = visible_candidates_by_url.get(candidate_url)
            current_visible_area = int(candidate.get('visibleArea') or 0)
            current_area = int(candidate.get('area') or 0)
            if existing:
                existing_visible_area = int(existing.get('visibleArea') or 0)
                existing_area = int(existing.get('area') or 0)
                if (existing_visible_area, existing_area) >= (current_visible_area, current_area):
                    continue

            visible_candidates_by_url[candidate_url] = candidate

        merged['visibleCandidates'] = list(visible_candidates_by_url.values())

        if snapshot.get('scrollState'):
            merged['scrollTrace'].append(snapshot['scrollState'])

        return merged

    def _capture_dynamic_snapshot(self, driver) -> Dict[str, Any]:
        """Capture one DOM snapshot after the current render state settles."""
        return driver.execute_script("""
            var result = {
                pageSource: document.documentElement.outerHTML,
                windowData: {},
                jsonData: [],
                apiData: {},
                imageUrls: [],
                resourceUrls: [],
                visibleCandidates: [],
                pageMarkers: [],
                scrollState: null
            };

            var imageUrlSet = new Set();
            var resourceUrlSet = new Set();
            var pageMarkerSet = new Set();
            var visibleCandidateMap = Object.create(null);

            function normalizeUrl(rawUrl) {
                if (!rawUrl || typeof rawUrl !== 'string') return null;
                var candidate = rawUrl.trim().replace(/\\\\\\//g, '/');
                if (!candidate) return null;
                if (candidate.startsWith('//')) candidate = 'https:' + candidate;
                if (!candidate.startsWith('http')) return null;
                return candidate;
            }

            function addUrl(rawUrl) {
                var normalized = normalizeUrl(rawUrl);
                if (normalized) imageUrlSet.add(normalized);
            }

            function rememberVisibleCandidate(rawUrl, meta) {
                var normalized = normalizeUrl(rawUrl);
                if (!normalized) return;

                imageUrlSet.add(normalized);

                var candidate = {
                    url: normalized,
                    source: meta.source || '',
                    width: Math.round(meta.width || 0),
                    height: Math.round(meta.height || 0),
                    area: Math.round(meta.area || 0),
                    visibleArea: Math.round(meta.visibleArea || 0),
                    top: Math.round(meta.top || 0),
                    left: Math.round(meta.left || 0),
                    centerDistance: Math.round(meta.centerDistance || 0),
                    isCentered: !!meta.isCentered,
                    isLarge: !!meta.isLarge,
                    tagName: meta.tagName || '',
                    className: meta.className || ''
                };

                var existing = visibleCandidateMap[normalized];
                if (!existing || candidate.visibleArea > existing.visibleArea || candidate.area > existing.area) {
                    visibleCandidateMap[normalized] = candidate;
                }
            }

            function addUrlsFromStyle(styleValue) {
                if (!styleValue || styleValue === 'none') return;
                var regex = /url\\((['"]?)([^'")]+)\\1\\)/g;
                var match;
                while ((match = regex.exec(styleValue)) !== null) {
                    addUrl(match[2]);
                }
            }

            try {
                if (window.__INITIAL_STATE__) result.windowData.initialState = window.__INITIAL_STATE__;
                if (window.__APP_DATA__) result.windowData.appData = window.__APP_DATA__;
                if (window.pageData) result.windowData.pageData = window.pageData;
                if (window.workData) result.windowData.workData = window.workData;
                if (window.imageData) result.windowData.imageData = window.imageData;
            } catch (e) {}

            try {
                var scripts = document.querySelectorAll('script[type="application/json"], script:not([src])');
                scripts.forEach(function(script) {
                    try {
                        var content = script.textContent || script.innerHTML || '';
                        var trimmed = content.trim();
                        if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
                            result.jsonData.push(JSON.parse(trimmed));
                        }
                    } catch (e) {}
                });
            } catch (e) {}

            try {
                performance.getEntriesByType('resource').forEach(function(entry) {
                    try {
                        var resourceUrl = normalizeUrl(entry.name);
                        if (!resourceUrl) return;

                        if (
                            /\\.(?:png|jpe?g|webp|gif)(?:[?#]|$)/i.test(resourceUrl) ||
                            /user_preview|preview|auth_key=|ips_user_preview_api/i.test(resourceUrl)
                        ) {
                            resourceUrlSet.add(resourceUrl);
                            imageUrlSet.add(resourceUrl);
                        }
                    } catch (e) {}
                });
            } catch (e) {}

            try {
                var elements = document.querySelectorAll('*');
                elements.forEach(function(el) {
                    try {
                        var rect = el.getBoundingClientRect();
                        var width = Math.max(rect.width || 0, 0);
                        var height = Math.max(rect.height || 0, 0);
                        var area = width * height;
                        var visibleWidth = Math.max(0, Math.min(rect.right, window.innerWidth) - Math.max(rect.left, 0));
                        var visibleHeight = Math.max(0, Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0));
                        var visibleArea = visibleWidth * visibleHeight;
                        var centerX = rect.left + (rect.width / 2);
                        var centerY = rect.top + (rect.height / 2);
                        var centerDistance = Math.abs(centerX - (window.innerWidth / 2)) + Math.abs(centerY - (window.innerHeight / 2));
                        var isCentered = centerDistance < Math.max(window.innerWidth, window.innerHeight) * 0.45;
                        var isLarge = width >= 240 && height >= 240;
                        var baseMeta = {
                            width: width,
                            height: height,
                            area: area,
                            visibleArea: visibleArea,
                            top: rect.top || 0,
                            left: rect.left || 0,
                            centerDistance: centerDistance,
                            isCentered: isCentered,
                            isLarge: isLarge,
                            tagName: el.tagName || '',
                            className: String(el.className || '')
                        };

                        ['src', 'data-src', 'data-original', 'data-url', 'data-background', 'href', 'poster'].forEach(function(attr) {
                            var attrValue = el.getAttribute(attr);
                            addUrl(attrValue);
                            if (area > 2500 || visibleArea > 2500) {
                                rememberVisibleCandidate(attrValue, Object.assign({source: attr}, baseMeta));
                            }
                        });

                        if (el.src) {
                            addUrl(el.src);
                            if (area > 2500 || visibleArea > 2500) {
                                rememberVisibleCandidate(el.src, Object.assign({source: 'src'}, baseMeta));
                            }
                        }
                        if (el.currentSrc) {
                            addUrl(el.currentSrc);
                            if (area > 2500 || visibleArea > 2500) {
                                rememberVisibleCandidate(el.currentSrc, Object.assign({source: 'currentSrc'}, baseMeta));
                            }
                        }

                        var srcset = el.getAttribute('srcset') || '';
                        if (srcset) {
                            srcset.split(',').forEach(function(part) {
                                var srcsetUrl = part.trim().split(/\\s+/)[0];
                                addUrl(srcsetUrl);
                                if (area > 2500 || visibleArea > 2500) {
                                    rememberVisibleCandidate(srcsetUrl, Object.assign({source: 'srcset'}, baseMeta));
                                }
                            });
                        }

                        addUrlsFromStyle(el.getAttribute('style') || '');
                        var computedStyle = window.getComputedStyle(el);
                        addUrlsFromStyle(computedStyle.backgroundImage);
                        addUrlsFromStyle(computedStyle.background);
                        addUrlsFromStyle(computedStyle.maskImage);

                        [
                            computedStyle.backgroundImage,
                            computedStyle.background,
                            computedStyle.maskImage
                        ].forEach(function(styleValue) {
                            if (!styleValue || styleValue === 'none') return;

                            var regex = /url\\((['"]?)([^'")]+)\\1\\)/g;
                            var match;
                            while ((match = regex.exec(styleValue)) !== null) {
                                if (area > 2500 || visibleArea > 2500) {
                                    rememberVisibleCandidate(match[2], Object.assign({source: 'background'}, baseMeta));
                                }
                            }
                        });

                        var text = (el.innerText || el.textContent || '').trim();
                        var normalizedPageMatch = text.replace(/\\s+/g, '').match(/^\\u7b2c(\\d+)\\u9875$/);
                        if (normalizedPageMatch) {
                            pageMarkerSet.add('\\u7b2c' + normalizedPageMatch[1] + '\\u9875');
                        }
                        var pageMatch = text.match(/^第\\s*(\\d+)\\s*页/);
                        if (pageMatch) {
                            pageMarkerSet.add('第' + pageMatch[1] + '页');
                        }
                    } catch (e) {}
                });
            } catch (e) {}

            result.imageUrls = Array.from(imageUrlSet);
            result.resourceUrls = Array.from(resourceUrlSet);
            result.visibleCandidates = Object.keys(visibleCandidateMap).map(function(key) {
                return visibleCandidateMap[key];
            });
            result.pageMarkers = Array.from(pageMarkerSet);
            return result;
        """)

    def _activate_dynamic_page(self, driver, page_number: int) -> Dict[str, Any]:
        """Try to click a specific page card in the sidebar like a real user."""
        return driver.execute_script("""
            var targetPage = arguments[0];
            var targetLabel = '\\u7b2c' + targetPage + '\\u9875';

            function normalizeText(value) {
                return (value || '').replace(/\\s+/g, '').trim();
            }

            function extractPage(text) {
                var match = normalizeText(text).match(/^\\u7b2c(\\d+)\\u9875$/);
                return match ? parseInt(match[1], 10) : null;
            }

            function getPageMarkerElements() {
                var markers = [];
                Array.from(document.querySelectorAll('*')).forEach(function(el) {
                    try {
                        if (!isVisible(el)) return;

                        var rawText = String(el.innerText || el.textContent || '').trim();
                        if (!rawText) return;

                        var page = extractPage(rawText);
                        if (!page) {
                            var prefixMatch = rawText.match(/^第\\s*(\\d+)\\s*页/);
                            if (prefixMatch) {
                                page = parseInt(prefixMatch[1], 10);
                            }
                        }

                        if (!page) return;

                        markers.push({
                            page: page,
                            label: '\\u7b2c' + page + '\\u9875',
                            el: el
                        });
                    } catch (e) {}
                });

                markers.sort(function(a, b) { return a.page - b.page; });
                return markers;
            }

            function isVisible(el) {
                if (!el) return false;
                var rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }

            function findClickable(el) {
                var current = el;
                var best = null;
                var bestScore = -1000000;

                function scoreElement(node) {
                    try {
                        if (!isVisible(node)) return -1000000;

                        var rect = node.getBoundingClientRect();
                        var area = Math.max(rect.width || 0, 0) * Math.max(rect.height || 0, 0);
                        var style = window.getComputedStyle(node);
                        var className = String(node.className || '');
                        var text = normalizeText(node.innerText || node.textContent || '');
                        var score = 0;

                        if (
                            node.tagName === 'BUTTON' ||
                            node.tagName === 'A' ||
                            node.getAttribute('role') === 'button' ||
                            node.tabIndex >= 0 ||
                            typeof node.onclick === 'function' ||
                            (style.cursor || '').indexOf('pointer') >= 0
                        ) {
                            score += 260;
                        }

                        if (/page|thumb|item|card|preview|cover|list|nav|panel|switch/i.test(className)) {
                            score += 140;
                        }

                        if (text.indexOf(targetPage.toString()) >= 0 && text.indexOf('\\u9875') >= 0) {
                            score += 180;
                        }

                        if (node === el) {
                            score += 120;
                        }

                        if (node.tagName === 'HTML' || node.tagName === 'BODY') {
                            score -= 500;
                        }

                        if (/render-core|rootLayout|root/i.test(className)) {
                            score -= 260;
                        }

                        if (area <= 0) {
                            score -= 300;
                        } else if (area <= 200000) {
                            score += 80;
                        } else if (area <= 600000) {
                            score += 20;
                        } else {
                            score -= 180;
                        }

                        if (rect.width <= 420 && rect.height <= 420) {
                            score += 50;
                        }

                        return score;
                    } catch (e) {
                        return -1000000;
                    }
                }

                for (var depth = 0; current && depth < 6; depth += 1) {
                    try {
                        var score = scoreElement(current);
                        if (score > bestScore) {
                            best = current;
                            bestScore = score;
                        }
                    } catch (e) {}

                    current = current.parentElement;
                }

                return best || el;
            }

            var markers = getPageMarkerElements();
            var marker = markers.find(function(item) { return item.page === targetPage; });
            if (!marker) {
                return {
                    requestedPage: targetPage,
                    label: targetLabel,
                    clicked: false,
                    reason: 'marker_not_found',
                    availablePages: Array.from(new Set(markers.map(function(item) { return item.label; })))
                };
            }

            var target = findClickable(marker.el);
            try {
                target.scrollIntoView({block: 'center', inline: 'nearest'});
            } catch (e) {}

            var rect = target.getBoundingClientRect();
            var clientX = Math.max(rect.left + Math.min(rect.width / 2, Math.max(rect.width - 8, 1)), 1);
            var clientY = Math.max(rect.top + Math.min(rect.height / 2, Math.max(rect.height - 8, 1)), 1);
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

            if (marker.el !== target) {
                try {
                    marker.el.click();
                    clicked = true;
                } catch (e) {}
            }

            try {
                var overlay = document.elementFromPoint(clientX, clientY);
                if (overlay && overlay !== target && overlay !== marker.el) {
                    overlay.click();
                    clicked = true;
                }
            } catch (e) {}

            try {
                target.focus({preventScroll: true});
            } catch (e) {}

            return {
                requestedPage: targetPage,
                label: targetLabel,
                clicked: clicked,
                reason: clicked ? 'clicked' : 'no_click_effect',
                targetTag: target.tagName || '',
                targetClass: String(target.className || ''),
                targetWidth: Math.round(rect.width || 0),
                targetHeight: Math.round(rect.height || 0),
                availablePages: Array.from(new Set(markers.map(function(item) { return item.label; })))
            };
        """, page_number)

    def _scroll_dynamic_page(self, driver, round_index: int) -> Dict[str, Any]:
        """Simulate human scrolling through the editor canvas and lazy-loaded page list."""
        return driver.execute_script("""
            var roundIndex = arguments[0] || 0;

            function normalizeText(value) {
                return (value || '').replace(/\\s+/g, '').trim();
            }

            function extractPage(text) {
                var match = normalizeText(text).match(/^\\u7b2c(\\d+)\\u9875$/);
                return match ? parseInt(match[1], 10) : null;
            }

            function getPageMarkerElements() {
                var markers = [];
                Array.from(document.querySelectorAll('*')).forEach(function(el) {
                    try {
                        var page = extractPage(el.innerText || el.textContent || '');
                        if (page) {
                            var normalizedRect = el.getBoundingClientRect();
                            if (normalizedRect.width > 0 && normalizedRect.height > 0) {
                                markers.push({
                                    page: page,
                                    text: '\\u7b2c' + page + '\\u9875',
                                    el: el
                                });
                            }
                            return;
                        }

                        var text = (el.innerText || el.textContent || '').trim();
                        var match = text.match(/^第\\s*(\\d+)\\s*页/);
                        if (!match) return;

                        var rect = el.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) return;

                        markers.push({
                            page: parseInt(match[1], 10),
                            text: '第' + parseInt(match[1], 10) + '页',
                            el: el
                        });
                    } catch (e) {}
                });

                markers.sort(function(a, b) { return a.page - b.page; });
                return markers;
            }

            var pageMarkers = getPageMarkerElements();
            var focusedPage = null;

            if (pageMarkers.length) {
                var targetMarker = pageMarkers[Math.min(roundIndex, pageMarkers.length - 1)];
                try {
                    targetMarker.el.scrollIntoView({block: 'center', inline: 'nearest'});
                    focusedPage = targetMarker.page;
                } catch (e) {}
            }

            var moved = 0;
            var candidates = Array.from(document.querySelectorAll('*')).filter(function(el) {
                try {
                    var style = window.getComputedStyle(el);
                    var overflowY = style.overflowY || '';
                    var rect = el.getBoundingClientRect();
                    return (
                        rect.width > 180 &&
                        rect.height > 180 &&
                        el.scrollHeight > el.clientHeight + 120 &&
                        ['auto', 'scroll', 'overlay'].indexOf(overflowY) !== -1
                    );
                } catch (e) {
                    return false;
                }
            }).sort(function(a, b) {
                return (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight);
            }).slice(0, 8);

            candidates.forEach(function(el) {
                try {
                    var before = el.scrollTop;
                    var step = Math.max(el.clientHeight * 0.85, 260);
                    el.scrollTop = Math.min(el.scrollTop + step, el.scrollHeight);
                    if (el.scrollTop > before) moved += 1;
                } catch (e) {}
            });

            try {
                var docEl = document.scrollingElement || document.documentElement || document.body;
                var beforeDoc = docEl.scrollTop;
                var docStep = Math.max(window.innerHeight * 0.9, 320);
                docEl.scrollTop = Math.min(docEl.scrollTop + docStep, docEl.scrollHeight);
                if (docEl.scrollTop > beforeDoc) moved += 1;
            } catch (e) {}

            try {
                window.dispatchEvent(new Event('scroll'));
            } catch (e) {}

            return {
                moved: moved,
                focusedPage: focusedPage,
                pageMarkers: pageMarkers.map(function(item) { return item.text; }),
                scrollableContainers: candidates.length
            };
        """, round_index)

    def _get_windows_file_version(self, chrome_path: str) -> Optional[int]:
        """
        Windows 下优先通过文件元数据读取版本，避免直接执行 chrome.exe --version 卡住
        """
        if os.name != 'nt':
            return None

        try:
            escaped_path = chrome_path.replace("'", "''")
            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Item -LiteralPath '{escaped_path}').VersionInfo.ProductVersion"
            ]
            version_output = subprocess.check_output(
                command,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=5,
                encoding='utf-8',
                errors='ignore'
            )
            return self._parse_chrome_major_version(version_output.strip())
        except subprocess.TimeoutExpired:
            logging.debug("Windows 文件版本检测超时")
            return None

    def _get_version_from_command(self, chrome_path: str) -> Optional[int]:
        """
        通过 chrome.exe --version 获取版本，作为通用回退方案
        """
        try:
            version_output = subprocess.check_output(
                [chrome_path, '--version'],
                stderr=subprocess.STDOUT,
                text=True,
                timeout=5,
                encoding='utf-8',
                errors='ignore'
            )
            return self._parse_chrome_major_version(version_output.strip())
        except subprocess.TimeoutExpired:
            logging.warning("⚠️ Chrome版本命令检测超时")
            return None

    def _extract_browser_version_from_error(self, error: Exception) -> Optional[int]:
        """
        从驱动异常里反推出真实浏览器版本
        """
        error_text = str(error)
        patterns = [
            r'Current browser version is (\d+)\.',
            r'Current browser version is (\d+)',
            r'browser version is (\d+)\.',
        ]

        for pattern in patterns:
            version_match = re.search(pattern, error_text, re.IGNORECASE)
            if version_match:
                return int(version_match.group(1))

        return None

    def _build_driver_kwargs(self, options, version_main: Optional[int] = None) -> dict:
        """
        构建 undetected-chromedriver 参数
        """
        kwargs = {
            'options': options,
            'driver_executable_path': None,
        }
        if version_main is not None:
            kwargs['version_main'] = version_main
        return kwargs

    def _build_chrome_options(self, uc, chrome_path: str, headless: bool):
        """
        每次驱动创建都生成一份新的 ChromeOptions，避免重试时复用对象。
        """
        options = uc.ChromeOptions()

        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')

        options.add_argument('--aggressive-cache-discard')
        options.add_argument('--disable-background-networking')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-renderer-backgrounding')

        options.add_argument('--enable-javascript')
        options.add_argument('--allow-running-insecure-content')
        options.add_argument('--disable-web-security')

        if headless:
            options.add_argument('--headless=new')

        options.add_argument('--window-size=1920,1080')
        options.binary_location = chrome_path
        return options
    
    def _get_stealth_driver(self, headless: bool = True):
        """
        获取隐身Chrome驱动 - 清洗版配置
        移除所有冲突的实验性选项
        """
        try:
            # 动态导入以避免依赖问题
            import undetected_chromedriver as uc
            
            logging.info("🤖 启动隐身Chrome驱动...")
            
            # 查找Chrome可执行文件
            chrome_path = self._find_chrome_executable()
            if not chrome_path:
                raise Exception("未找到Chrome浏览器，请安装Chrome: https://www.google.com/chrome/")
            
            # 基础Chrome选项 - 仅保留兼容性好的配置
            options = uc.ChromeOptions()
            
            # 基础性能优化选项
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            # 注意: 为了支持动态渲染，不禁用JavaScript
            # options.add_argument('--disable-javascript')  # 移除此选项
            
            # 网络优化
            options.add_argument('--aggressive-cache-discard')
            options.add_argument('--disable-background-networking')
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-renderer-backgrounding')
            
            # 动态渲染支持
            options.add_argument('--enable-javascript')  # 明确启用JavaScript
            options.add_argument('--allow-running-insecure-content')
            options.add_argument('--disable-web-security')  # 允许跨域请求
            
            # 隐身模式
            if headless:
                options.add_argument('--headless=new')
                logging.info("🔇 启用无头模式")
            
            # 窗口大小
            options.add_argument('--window-size=1920,1080')
            
            # 指定Chrome可执行文件路径
            options.binary_location = chrome_path
            
            # ❌ 绝对不要添加这些冲突配置 (会导致新版Chrome崩溃):
            # options.add_experimental_option("excludeSwitches", [...])
            # options.add_experimental_option('useAutomationExtension', False)
            
            logging.info("🔧 Chrome选项配置完成")
            
            # 创建驱动实例 - 版本锁定策略
            try:
                # 获取本地Chrome版本
                chrome_version = self._get_chrome_version()
                version_candidates = []
                attempted_versions = set()

                def enqueue_version(version_candidate):
                    key = 'auto' if version_candidate is None else int(version_candidate)
                    if key in attempted_versions:
                        return
                    attempted_versions.add(key)
                    version_candidates.append(version_candidate)

                enqueue_version(chrome_version)
                enqueue_version(None)

                driver = None
                last_error = None

                while version_candidates:
                    version_main = version_candidates.pop(0)
                    try:
                        if version_main is None:
                            logging.info("🔄 尝试让驱动自动匹配当前Chrome版本")
                        else:
                            logging.info(f"🔒 尝试使用 Chrome {version_main} 对应驱动")

                        attempt_options = self._build_chrome_options(uc, chrome_path, headless)
                        driver = uc.Chrome(**self._build_driver_kwargs(attempt_options, version_main))
                        break
                    except Exception as e:
                        last_error = e
                        logging.error(f"❌ Chrome驱动创建失败: {e}")

                        inferred_version = self._extract_browser_version_from_error(e)
                        if inferred_version and inferred_version != version_main:
                            logging.info(f"🔁 从异常中识别到真实浏览器版本 {inferred_version}，加入重试")
                            enqueue_version(inferred_version)

                if driver is None:
                    raise last_error or RuntimeError("Chrome驱动初始化失败")
                
                # 设置超时
                driver.set_page_load_timeout(30)
                driver.implicitly_wait(10)
                
                # 执行增强隐身脚本 - 支持动态渲染页面
                driver.execute_script("""
                    // 基础反检测
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5],
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['zh-CN', 'zh', 'en'],
                    });
                    
                    // 增强脚本 - 支持动态渲染
                    window.chrome = {
                        runtime: {}
                    };
                    Object.defineProperty(navigator, 'permissions', {
                        get: () => ({
                            query: () => Promise.resolve({state: 'granted'})
                        })
                    });
                """)
                
                logging.info("✅ 版本锁定Chrome驱动启动成功")
                return driver
                
            except Exception as e:
                logging.error(f"❌ Chrome驱动创建失败: {e}")
                
                # 提供详细的错误诊断
                if 'version' in str(e).lower():
                    actual_version = self._extract_browser_version_from_error(e)
                    logging.info("💡 解决方案: Chrome版本不匹配")
                    if actual_version:
                        logging.info(f"   1. 当前浏览器主版本是 {actual_version}，请确认驱动已匹配该版本")
                    else:
                        logging.info("   1. 请确认浏览器与驱动主版本一致")
                    logging.info("   2. 运行: pip install --upgrade undetected-chromedriver")
                elif 'permission' in str(e).lower():
                    logging.info("💡 解决方案: 权限问题")
                    logging.info("   1. 以管理员权限运行程序")
                    logging.info("   2. 关闭所有Chrome进程后重试")
                elif 'path' in str(e).lower():
                    logging.info("💡 解决方案: 路径问题")
                    logging.info(f"   1. 确认Chrome安装路径: {chrome_path}")
                    logging.info("   2. 重新安装Chrome浏览器")
                else:
                    logging.info("💡 通用解决方案:")
                    logging.info("   1. 重启计算机")
                    logging.info("   2. 清理Chrome用户数据")
                    logging.info("   3. 重新安装Chrome和驱动")
                
                raise e
                
        except ImportError as e:
            logging.error("❌ undetected-chromedriver模块未安装")
            logging.info("💡 解决方案: pip install undetected-chromedriver")
            raise e
        except Exception as e:
            logging.error(f"❌ 浏览器服务启动失败: {e}")
            raise e
    
    async def get_page_content(self, url: str, headless: bool = True) -> Optional[str]:
        """
        获取页面内容
        """
        driver = None
        try:
            logging.info(f"🌐 获取页面内容: {url}")
            
            # 获取驱动
            driver = self._get_stealth_driver(headless=headless)
            
            # 访问页面
            driver.get(url)
            
            # 等待页面加载
            time.sleep(3)
            
            # 模拟滚动触发懒加载
            driver.execute_script("window.scrollBy(0, window.innerHeight);")
            time.sleep(2)
            
            # 获取页面源码
            page_source = driver.page_source
            
            logging.info(f"✅ 页面内容获取成功 ({len(page_source)} 字符)")
            return page_source
            
        except Exception as e:
            logging.error(f"❌ 页面内容获取失败: {e}")
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                    logging.info("✅ Chrome驱动已关闭")
                except:
                    pass
    
    async def extract_dynamic_content(self, url: str, headless: bool = True) -> dict:
        """
        提取动态渲染页面的内容 - 支持JSON深度提取
        专门用于处理ue.818ps.com等动态渲染页面
        """
        driver = None
        try:
            logging.info(f"🌐 提取动态渲染内容: {url}")
            
            # 获取驱动
            driver = self._get_stealth_driver(headless=headless)
            
            # 访问页面
            driver.get(url)
            
            # 等待动态内容加载
            time.sleep(5)  # 增加等待时间

            resolved_url = None
            try:
                resolved_url = driver.current_url
            except Exception:
                resolved_url = None

            page_data: Dict[str, Any] = {
                'requestedUrl': url,
                'currentUrl': resolved_url or url,
            }
            if resolved_url and resolved_url != url:
                page_data['resolvedUrl'] = resolved_url
            page_data = self._merge_dynamic_capture(page_data, self._capture_dynamic_snapshot(driver))

            previous_image_count = len(page_data.get('imageUrls', []))
            idle_rounds = 0

            for round_index in range(8):
                scroll_state = self._scroll_dynamic_page(driver, round_index)
                time.sleep(1.2)

                snapshot = self._capture_dynamic_snapshot(driver)
                snapshot['scrollState'] = scroll_state
                page_data = self._merge_dynamic_capture(page_data, snapshot)

                current_image_count = len(page_data.get('imageUrls', []))
                gained_images = current_image_count - previous_image_count
                previous_image_count = current_image_count

                logging.info(
                    f"🔄 动态页滚动采样 #{round_index + 1}: "
                    f"moved={scroll_state.get('moved', 0)}, "
                    f"focusedPage={scroll_state.get('focusedPage')}, "
                    f"markers={len(page_data.get('pageMarkers', []))}, "
                    f"newImages={gained_images}, totalImages={current_image_count}"
                )

                if scroll_state.get('moved', 0) <= 0 and gained_images <= 0:
                    idle_rounds += 1
                else:
                    idle_rounds = 0

                if idle_rounds >= 2:
                    break

            page_snapshots: List[Dict[str, Any]] = []
            page_specific_images: List[str] = []
            seen_snapshot_urls = set(
                self._dedupe_keep_order(
                    (page_data.get('imageUrls') or []) + (page_data.get('resourceUrls') or [])
                )
            )
            page_targets = [
                page_number
                for page_number in (
                    self._extract_page_number(label)
                    for label in page_data.get('pageMarkers', [])
                )
                if page_number is not None
            ]

            for page_number in sorted(set(page_targets)):
                activation_state = self._activate_dynamic_page(driver, page_number)
                time.sleep(1.2)

                snapshot = self._capture_dynamic_snapshot(driver)
                snapshot['page'] = page_number
                snapshot['label'] = f'第{page_number}页'
                snapshot['activation'] = activation_state

                snapshot_url_pool = self._dedupe_keep_order(
                    (snapshot.get('imageUrls') or []) + (snapshot.get('resourceUrls') or [])
                )
                newly_observed_urls = [
                    image_url for image_url in snapshot_url_pool
                    if image_url not in seen_snapshot_urls
                ]
                preview_urls = self._select_snapshot_preview_urls(
                    snapshot,
                    preferred_urls=newly_observed_urls,
                    limit=3
                )

                snapshot['newUrls'] = newly_observed_urls
                snapshot['previewUrls'] = preview_urls

                page_data = self._merge_dynamic_capture(page_data, snapshot)
                page_snapshots.append(snapshot)
                if preview_urls:
                    page_specific_images.append(preview_urls[0])

                seen_snapshot_urls.update(snapshot_url_pool)
                logging.info(
                    f"📄 动态页逐页激活 #{page_number}: "
                    f"clicked={activation_state.get('clicked')}, "
                    f"newUrls={len(newly_observed_urls)}, "
                    f"previewUrls={preview_urls[:2]}"
                )

            page_data['pageSnapshots'] = page_snapshots
            page_data['pageSpecificImages'] = self._dedupe_keep_order(page_specific_images)

            try:
                final_current_url = driver.current_url
            except Exception:
                final_current_url = None

            if isinstance(final_current_url, str) and final_current_url.strip():
                final_current_url = final_current_url.strip()
                page_data['currentUrl'] = final_current_url
                if final_current_url != url:
                    page_data['resolvedUrl'] = final_current_url

            logging.info(f"✅ 动态内容提取完成")
            logging.info(f"   JSON数据块: {len(page_data.get('jsonData', []))} 个")
            logging.info(f"   图片URL: {len(page_data.get('imageUrls', []))} 个")
            logging.info(f"   Window数据: {len(page_data.get('windowData', {}))} 个属性")
            logging.info(f"   页面标记: {len(page_data.get('pageMarkers', []))} 个 {page_data.get('pageMarkers', [])}")
            
            logging.info(f"   resourceUrls: {len(page_data.get('resourceUrls', []))}")
            logging.info(f"   pageSpecificImages: {page_data.get('pageSpecificImages', [])}")
            return page_data
            
        except Exception as e:
            logging.error(f"❌ 动态内容提取失败: {e}")
            return {}
        finally:
            if driver:
                try:
                    driver.quit()
                    logging.info("✅ Chrome驱动已关闭")
                except:
                    pass
    
    async def extract_images_from_page(self, url: str, headless: bool = True) -> list:
        """
        从页面提取图片元素 - 增强版 (支持背景图提取)
        专门处理 SPA 应用的背景图和 Canvas 渲染图片
        """
        driver = None
        try:
            logging.info(f"🖼️ 从页面提取图片 (增强版): {url}")
            
            # 获取驱动
            driver = self._get_stealth_driver(headless=headless)
            
            # 访问页面
            driver.get(url)
            
            # 等待页面加载
            time.sleep(5)  # 增加等待时间，确保 SPA 完全加载
            
            # 模拟滚动触发懒加载
            driver.execute_script("window.scrollBy(0, window.innerHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollBy(0, -window.innerHeight);")
            time.sleep(1)
            
            # 执行增强的图片提取脚本
            image_data = driver.execute_script("""
                var result = {
                    images: [],
                    backgroundImages: [],
                    canvasImages: [],
                    allImages: []
                };
                
                // 1. 提取传统 <img> 标签
                try {
                    var images = document.querySelectorAll('img');
                    images.forEach(function(img) {
                        var src = img.src || img.getAttribute('data-src') || img.getAttribute('data-original');
                        if (src && src.startsWith('http')) {
                            var imgData = {
                                src: src,
                                width: img.naturalWidth || img.width || 0,
                                height: img.naturalHeight || img.height || 0,
                                alt: img.alt || '',
                                className: img.className || '',
                                type: 'img'
                            };
                            imgData.size = imgData.width * imgData.height;
                            result.images.push(imgData);
                            result.allImages.push(imgData);
                        }
                    });
                } catch(e) {
                    console.log('Error extracting img tags:', e);
                }
                
                // 2. 提取背景图片 - 核心增强功能
                try {
                    var allElements = document.querySelectorAll('*');
                    allElements.forEach(function(el) {
                        try {
                            var computedStyle = window.getComputedStyle(el);
                            var backgroundImage = computedStyle.backgroundImage;
                            
                            if (backgroundImage && backgroundImage !== 'none' && backgroundImage.includes('url(')) {
                                // 提取 url("...") 中的链接
                                var matches = backgroundImage.match(/url\\(['"]?([^'"\\)]+)['"]?\\)/g);
                                if (matches) {
                                    matches.forEach(function(match) {
                                        var urlMatch = match.match(/url\\(['"]?([^'"\\)]+)['"]?\\)/);
                                        if (urlMatch && urlMatch[1]) {
                                            var bgUrl = urlMatch[1];
                                            
                                            // 过滤掉小图标和非 HTTP 链接
                                            if (bgUrl.startsWith('http') && 
                                                !bgUrl.includes('favicon') && 
                                                !bgUrl.includes('icon') &&
                                                !bgUrl.includes('sprite') &&
                                                !bgUrl.includes('cursor') &&
                                                (bgUrl.includes('.jpg') || bgUrl.includes('.png') || 
                                                 bgUrl.includes('.webp') || bgUrl.includes('.jpeg'))) {
                                                
                                                var bgData = {
                                                    src: bgUrl,
                                                    width: el.offsetWidth || 0,
                                                    height: el.offsetHeight || 0,
                                                    className: el.className || '',
                                                    tagName: el.tagName || '',
                                                    type: 'background'
                                                };
                                                bgData.size = bgData.width * bgData.height;
                                                result.backgroundImages.push(bgData);
                                                result.allImages.push(bgData);
                                            }
                                        }
                                    });
                                }
                            }
                        } catch(e) {
                            // 忽略单个元素的错误
                        }
                    });
                } catch(e) {
                    console.log('Error extracting background images:', e);
                }
                
                // 3. 提取 Canvas 元素 (如果有的话)
                try {
                    var canvases = document.querySelectorAll('canvas');
                    canvases.forEach(function(canvas) {
                        try {
                            if (canvas.width > 100 && canvas.height > 100) {
                                // 尝试将 Canvas 转换为 Data URL
                                var dataUrl = canvas.toDataURL('image/png');
                                if (dataUrl && dataUrl.startsWith('data:image')) {
                                    var canvasData = {
                                        src: dataUrl,
                                        width: canvas.width,
                                        height: canvas.height,
                                        className: canvas.className || '',
                                        type: 'canvas'
                                    };
                                    canvasData.size = canvasData.width * canvasData.height;
                                    result.canvasImages.push(canvasData);
                                    result.allImages.push(canvasData);
                                }
                            }
                        } catch(e) {
                            // Canvas 可能有跨域限制，忽略错误
                        }
                    });
                } catch(e) {
                    console.log('Error extracting canvas images:', e);
                }
                
                // 4. 查找可能的图片容器元素
                try {
                    var containers = document.querySelectorAll('[class*="image"], [class*="photo"], [class*="picture"], [class*="preview"], [class*="thumbnail"]');
                    containers.forEach(function(container) {
                        try {
                            var computedStyle = window.getComputedStyle(container);
                            var backgroundImage = computedStyle.backgroundImage;
                            
                            if (backgroundImage && backgroundImage !== 'none' && backgroundImage.includes('url(')) {
                                var urlMatch = backgroundImage.match(/url\\(['"]?([^'"\\)]+)['"]?\\)/);
                                if (urlMatch && urlMatch[1]) {
                                    var containerUrl = urlMatch[1];
                                    if (containerUrl.startsWith('http')) {
                                        var containerData = {
                                            src: containerUrl,
                                            width: container.offsetWidth || 0,
                                            height: container.offsetHeight || 0,
                                            className: container.className || '',
                                            type: 'container_background'
                                        };
                                        containerData.size = containerData.width * containerData.height;
                                        result.backgroundImages.push(containerData);
                                        result.allImages.push(containerData);
                                    }
                                }
                            }
                        } catch(e) {
                            // 忽略单个容器的错误
                        }
                    });
                } catch(e) {
                    console.log('Error extracting container images:', e);
                }
                
                return result;
            """)
            
            # 处理提取结果
            all_images = image_data.get('allImages', [])
            
            logging.info(f"✅ 图片提取完成:")
            logging.info(f"   传统 <img> 标签: {len(image_data.get('images', []))} 个")
            logging.info(f"   背景图片: {len(image_data.get('backgroundImages', []))} 个")
            logging.info(f"   Canvas 图片: {len(image_data.get('canvasImages', []))} 个")
            logging.info(f"   总计: {len(all_images)} 个")
            
            return all_images
            
        except Exception as e:
            logging.error(f"❌ 增强图片提取失败: {e}")
            return []
        finally:
            if driver:
                try:
                    driver.quit()
                    logging.info("✅ Chrome驱动已关闭")
                except:
                    pass
    
    def resolve_url_with_browser(
        self,
        url: str,
        headless: bool = True,
        wait_seconds: float = 5.0
    ) -> Optional[str]:
        """
        Resolve the final in-browser URL for dynamic share-shell pages such as
        818ps `/u/` links that only reveal `share_id` after the editor boots.
        """
        driver = None
        try:
            logging.info(f"🌐 使用本地浏览器解析最终地址: {url}")
            driver = self._get_stealth_driver(headless=headless)
            driver.get(url)
            time.sleep(max(wait_seconds, 0))

            resolved_url = None
            try:
                resolved_url = driver.current_url
            except Exception:
                resolved_url = None

            if not resolved_url:
                try:
                    resolved_url = driver.execute_script(
                        "return window.location.href || location.href || '';"
                    )
                except Exception:
                    resolved_url = None

            if isinstance(resolved_url, str):
                resolved_url = resolved_url.strip()

            if resolved_url:
                logging.info(f"✅ 浏览器最终地址: {resolved_url}")
                return resolved_url

            logging.warning("⚠️ 浏览器未返回有效的最终地址")
            return None
        except Exception as error:
            logging.warning(f"⚠️ 浏览器解析最终地址失败: {error}")
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                    logging.info("✅ Chrome驱动已关闭")
                except Exception:
                    pass

    def check_chrome_installation(self) -> dict:
        """
        检查Chrome安装状态
        """
        result = {
            'installed': False,
            'path': None,
            'version': None,
            'message': ''
        }
        
        chrome_path = self._find_chrome_executable()
        if chrome_path:
            result['installed'] = True
            result['path'] = chrome_path
            result['message'] = f"✅ Chrome已安装: {chrome_path}"
            
            chrome_version = self._get_chrome_version()
            if chrome_version:
                result['version'] = f"{chrome_version}.x"
            else:
                result['version'] = "版本获取失败"
        else:
            result['message'] = "❌ 未检测到Chrome浏览器，建议安装: https://www.google.com/chrome/"
        
        return result
    
    async def extract_meta_images(self, url: str, headless: bool = True) -> dict:
        """
        提取页面中的 Meta 标签图片 - 专门用于 Canva 等平台
        增强 og:image 和 twitter:image 的提取能力
        """
        driver = None
        try:
            logging.info(f"🔍 提取Meta标签图片: {url}")
            
            # 获取驱动
            driver = self._get_stealth_driver(headless=headless)
            
            # 访问页面
            driver.get(url)
            
            # 等待页面加载
            time.sleep(3)
            
            # 执行JavaScript提取Meta标签
            meta_data = driver.execute_script("""
                var result = {
                    ogImage: null,
                    twitterImage: null,
                    otherMetaImages: [],
                    allImages: []
                };
                
                // 1. 提取 og:image
                var ogImageMeta = document.querySelector('meta[property="og:image"]');
                if (ogImageMeta && ogImageMeta.content) {
                    result.ogImage = ogImageMeta.content;
                }
                
                // 2. 提取 twitter:image
                var twitterImageMeta = document.querySelector('meta[name="twitter:image"]');
                if (twitterImageMeta && twitterImageMeta.content) {
                    result.twitterImage = twitterImageMeta.content;
                }
                
                // 3. 提取其他可能的Meta图片标签
                var otherMetaSelectors = [
                    'meta[property="og:image:url"]',
                    'meta[name="twitter:image:src"]',
                    'meta[property="image"]',
                    'meta[name="image"]',
                    'meta[property="og:image:secure_url"]'
                ];
                
                otherMetaSelectors.forEach(function(selector) {
                    var meta = document.querySelector(selector);
                    if (meta && meta.content) {
                        result.otherMetaImages.push({
                            selector: selector,
                            content: meta.content
                        });
                    }
                });
                
                // 4. 提取所有图片URL作为备用
                var images = document.querySelectorAll('img[src], img[data-src]');
                images.forEach(function(img) {
                    var src = img.src || img.getAttribute('data-src');
                    if (src && src.startsWith('http')) {
                        result.allImages.push({
                            src: src,
                            alt: img.alt || '',
                            width: img.naturalWidth || img.width || 0,
                            height: img.naturalHeight || img.height || 0
                        });
                    }
                });
                
                return result;
            """)
            
            logging.info(f"✅ Meta标签提取完成")
            logging.info(f"   og:image: {'✅' if meta_data.get('ogImage') else '❌'}")
            logging.info(f"   twitter:image: {'✅' if meta_data.get('twitterImage') else '❌'}")
            logging.info(f"   其他Meta图片: {len(meta_data.get('otherMetaImages', []))} 个")
            logging.info(f"   所有图片: {len(meta_data.get('allImages', []))} 个")
            
            return meta_data
            
        except Exception as e:
            logging.error(f"❌ Meta标签提取失败: {e}")
            return {}
        finally:
            if driver:
                try:
                    driver.quit()
                    logging.info("✅ Chrome驱动已关闭")
                except:
                    pass

    async def close(self):
        """关闭浏览器服务"""
        if self.driver:
            try:
                self.driver.quit()
                logging.info("✅ 浏览器服务已关闭")
            except:
                pass
            finally:
                self.driver = None
