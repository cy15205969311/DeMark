"""818ps task orchestration: page identity, completeness and one browser session."""
import asyncio
import html
import json
import logging
import re
import time
import uuid
from urllib.parse import urlparse

from bs4 import BeautifulSoup


class ExtractionTask:
    def __init__(self, crawler, url):
        self.crawler = crawler
        self.url = url
        self.request_id = uuid.uuid4().hex[:12]
        self.started = time.monotonic()
        self.expected = None
        self.pages = {}
        self.discovered = set()
        self.sources = []
        self.validation = {}
        self.request_headers = {}
        self.limit = asyncio.Semaphore(8)
        self.stats = dict(candidateCount=0, filteredCount=0, duplicateCount=0,
                          validatedCount=0, stageMs={})
        from crawlers.tuguaishou_animation import AnimationDiscovery
        self.animation = AnimationDiscovery(self)

    def log(self, stage, **fields):
        logging.getLogger('demark.818ps').info(
            '[%s] request_id=%s %s', stage, self.request_id,
            ' '.join(f'{key}={value}' for key, value in fields.items()))

    def expect(self, count):
        try:
            count = int(count)
        except (TypeError, ValueError):
            return
        if count > 0:
            self.expected = max(self.expected or 0, count)

    def number(self, item, url, position):
        if isinstance(item, dict):
            for key in ('page', 'pageNumber', 'pageNo', 'page_index', 'pageIndex'):
                try:
                    number = int(item[key]) + (1 if key in ('page_index', 'pageIndex') else 0)
                    if number > 0:
                        return number
                except (KeyError, TypeError, ValueError):
                    pass
        return (self.crawler._extract_url_page_number(url)
                or self.crawler._extract_818ps_preview_page_number(url) or position)

    def structured(self, data, source):
        self.animation.structured(data, source)
        return self._structured(data, source)

    def _structured(self, data, source):
        """Read only page/preview collections, never arbitrary arrays of assets."""
        records = []
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                return records
        if isinstance(data, list):
            for item in data:
                records.extend(self._structured(item, source))
            return records
        if not isinstance(data, dict):
            return records
        for key in ('expectedPageCount', 'pageCount', 'page_count', 'totalPages', 'total_pages'):
            self.expect(data.get(key))
        for key, value in data.items():
            if key in ('page_map', 'pageInfo', 'artboards', 'pages') and isinstance(value, (list, dict)):
                self.expect(len(value))
            if key in ('preview', 'previews', 'pages', 'artboards', 'pageInfo', 'page_map') and (
                    isinstance(value, list) or (key == 'page_map' and isinstance(value, dict))):
                items = list(value.values()) if isinstance(value, dict) else value
                # Preview arrays can be a cover or a subset. Only an explicit total
                # or a page inventory establishes the document's expected count.
                for position, item in enumerate(items, 1):
                    raw_url = item if isinstance(item, str) else None
                    if isinstance(item, dict):
                        raw_url = next((item.get(k) for k in
                                        ('origin_img', 'big_img', 'imageUrl', 'previewUrl', 'img', 'url', 'preview')
                                        if isinstance(item.get(k), str)), None)
                    url = self.crawler._normalize_dynamic_candidate_url(raw_url)
                    number = self.number(item, url, position)
                    if isinstance(item, str) and items.count(item) > 1:
                        number = position
                    self.discovered.add(number)
                    if url:
                        record = dict(page=number, imageUrl=url, source=source)
                        if isinstance(item, dict):
                            page_id = item.get('pageId') or item.get('artboardId') or item.get('id')
                            if page_id is not None:
                                record['pageId'] = page_id
                        records.append(record)
            if isinstance(value, (dict, list)) and key not in ('assets','work','gifInfo','materials','elements'):
                records.extend(self._structured(value, source))
        return records

    def read_html(self, content, source='embedded_json'):
        records = []
        self.animation.read_html(content)
        soup = BeautifulSoup(content or '', 'html.parser')
        for script in soup.find_all('script'):
            text = script.string or script.get_text()
            try:
                payload = json.loads(text)
            except (ValueError, TypeError):
                match = re.search(r'(?:__INITIAL_STATE__|__NEXT_DATA__|__NUXT__)\s*=\s*(\{.*\})\s*;?\s*$',
                                  text, re.DOTALL)
                if not match:
                    continue
                try:
                    payload = json.loads(match.group(1))
                except ValueError:
                    continue
            records.extend(self.structured(payload, source))
        return records

    async def validate(self, url):
        headers = self.request_headers.get(url)
        cache_key = (url, tuple(sorted((headers or {}).items())))
        if cache_key not in self.validation:
            async def run():
                async with self.limit:
                    try:
                        operation = (self.crawler.validator.validate_image_url(url, request_headers=headers)
                                     if headers else self.crawler.validator.validate_image_url(url))
                        return await asyncio.wait_for(operation, 8)
                    except Exception as error:
                        logging.getLogger('demark.818ps').debug('Image validation: %s', type(error).__name__)
                        return False
            self.validation[cache_key] = asyncio.create_task(run())
        return await self.validation[cache_key]

    async def add(self, records):
        self.stats['candidateCount'] += len(records)
        from crawlers.tuguaishou_animation import media_hint
        for record in records:
            url = record['imageUrl']
            if self.animation.required or media_hint(url) in ('gif', 'webp', 'video', 'blob'):
                if media_hint(url) in ('gif', 'video'):
                    self.animation.required = True
                self.animation.remember(dict(url=url, page=record['page'], role='output',
                                             source=record.get('source', 'structured')))
        await self.animation.validate()
        async def resolve(record):
            number, url = record['page'], record['imageUrl']
            if url in self.animation.candidates and self.animation.candidates[url].get('role') == 'output':
                return None
            if number in self.pages and self.pages[number].get('identityConfirmed', True):
                self.stats['duplicateCount'] += 1
                return None
            variant_urls = self.crawler._build_818ps_variant_candidates(url)
            if not self.crawler._is_design_page_candidate(url) and not any(
                    self.crawler._is_design_page_candidate(candidate) for candidate in variant_urls):
                self.stats['filteredCount'] += 1
                return None
            # Keep the exact signed URL first. Variants may not discard signatures.
            candidates = variant_urls + [url] if '!l1000_b' in url else [url] + variant_urls
            query = urlparse(url).query
            for candidate in dict.fromkeys(candidates):
                if not self.crawler._is_design_page_candidate(candidate):
                    continue
                if query and urlparse(candidate).query != query:
                    continue
                if url in self.request_headers and urlparse(candidate).hostname == urlparse(url).hostname:
                    self.request_headers.setdefault(candidate, self.request_headers[url])
                if await self.validate(candidate):
                    report = self.crawler.validator.media_reports.get(candidate, {})
                    if report.get('animationStatus') == 'animated':
                        self.animation.required = True
                        self.animation.required_pages.add(number)
                    return dict(record, imageUrl=candidate,
                                **{k: report[k] for k in ('mediaType', 'animationStatus', 'frameCount', 'mediaFile') if k in report})
            return None
        results = await asyncio.gather(*(resolve(record) for record in records))
        for record in results:
            if record:
                number = record['page']
                if number in self.pages and self.pages[number].get('identityConfirmed', True):
                    self.stats['duplicateCount'] += 1
                    continue
                self.pages[number] = record
                source = record.get('source', 'structured')
                if source not in self.sources:
                    self.sources.append(source)
        self.stats['validatedCount'] = len(self.pages)

    def merge(self, result):
        if not result:
            return
        self.expect(result.get('expectedPageCount'))
        for page in result.get('pages', []):
            if page['page'] not in self.pages or not self.pages[page['page']].get('identityConfirmed', True):
                record = dict(page)
                record.setdefault('source', result.get('source', 'share_api'))
                self.pages[page['page']] = record
        if not result.get('pages'):
            urls = result.get('imageUrls') or [result.get('imageUrl')]
            for position, url in enumerate(urls, 1):
                if url and self.crawler._is_design_page_candidate(url):
                    self.pages.setdefault(self.number({}, url, position), dict(page=self.number({}, url, position), imageUrl=url))
        if result.get('source') not in (None, 'none') and result.get('source') not in self.sources:
            self.sources.append(result['source'])
        for key in ('candidateCount', 'filteredCount', 'duplicateCount'):
            self.stats[key] += result.get('metadata', {}).get(key, 0)
        self.stats['validatedCount'] = len(self.pages)

    def result(self):
        pages = [self.pages[n] for n in sorted(self.pages)]
        urls = [page['imageUrl'] for page in pages]
        animation_targets = (self.animation.required_pages or
                             (set(range(1, self.expected + 1)) if self.expected else self.animation.output_pages))
        animation_missing = [n for n in animation_targets
                             if self.animation.required and (n not in self.pages or
                                self.pages[n].get('animationStatus') != 'animated')]
        missing = [n for n in range(1, (self.expected or 0) + 1)
                   if n not in self.pages or not self.pages[n].get('identityConfirmed', True) or n in animation_missing]
        status = ('complete' if not missing and len(pages) == self.expected else 'partial') if self.expected else 'unknown'
        metadata = dict(self.stats, totalMs=round((time.monotonic() - self.started) * 1000),
                        uniqueImageCount=len(set(urls)), duplicateUrlCount=len(urls) - len(set(urls)))
        result = dict(imageUrl=urls[0] if urls else None, thumbnailUrl=urls[0] if urls else None,
                    imageUrls=urls, images=list(urls), pages=pages, pageCount=len(pages),
                    isMultiPage=len(pages) > 1, expectedPageCount=self.expected,
                    completenessStatus=status, missingPages=missing, source='+'.join(self.sources) or 'none',
                    metadata=metadata, request_id=self.request_id, platform='818ps', original_url=self.url)
        if self.animation.required or self.animation.candidates:
            first = pages[0] if pages else {}
            output_reports = [r for r in self.animation.diagnostics if r.get('role') == 'output' and r.get('valid')]
            if not first and output_reports:
                first = output_reports[0]
            result.update(animationRequired=self.animation.required, animationMissingPages=sorted(animation_missing),
                          mediaType=first.get('mediaType'), frameCount=first.get('frameCount') if len(pages) == 1 else None,
                          animationStatus=('animated' if any(p.get('animationStatus') == 'animated' for p in pages)
                                           else first.get('animationStatus', 'unknown')))
            if self.animation.required and (animation_missing or not any(
                    p.get('animationStatus') == 'animated' for p in pages)):
                result.update(success=False, error='动画资源未提取成功；静态首帧或背景素材不能替代整稿动画')
                result['completenessStatus'] = 'partial' if self.expected else 'unknown'
        return result

    def complete(self):
        return self.result()['completenessStatus'] == 'complete'

    async def add_capture(self, capture):
        self.request_headers.update(capture.get('requestHeadersByUrl', {}))
        self.expect(capture.get('expectedPageCount'))
        self.animation.capture(capture)
        records = []
        for payload in capture.get('networkData', []) + capture.get('jsonData', []):
            records.extend(self.structured(payload, 'browser_structured'))
        records.extend(self.structured(capture.get('windowData', {}), 'browser_structured'))
        records.extend(self.read_html(capture.get('pageSource', '')))
        self.expect(capture.get('expectedPageCount'))
        for label in capture.get('pageMarkers', []):
            match = re.search(r'第\s*(\d+)\s*页', label)
            if match:
                self.discovered.add(int(match.group(1)))
        await self.add(records)
        for snapshot in capture.get('pageSnapshots', []):
            if snapshot.get('previewUpdated') is not True:
                continue
            for url in snapshot.get('previewUrls', [])[:1]:
                await self.add([dict(page=snapshot['page'], imageUrl=url, source='browser_page_activation')])
        # Global resources without page identity cannot prove completeness.
        candidates = self.crawler._collect_dynamic_image_candidates(capture)
        global_records = []
        for item in candidates:
            url = item['url']
            number = (self.crawler._extract_url_page_number(url)
                      or self.crawler._extract_818ps_preview_page_number(url))
            if number and self.crawler._is_design_page_candidate(url):
                global_records.append(dict(page=number, imageUrl=url, source='browser_preview'))
        await self.add(global_records)
        if not self.pages:
            # An unnumbered main preview is usable, but does not prove a document's page count.
            visible = [item for item in capture.get('visibleCandidates', [])
                       if item.get('isLarge') and item.get('isCentered')]
            visible.sort(key=lambda item: item.get('visibleArea', 0), reverse=True)
            if visible:
                await self.add([dict(page=1, imageUrl=visible[0]['url'], source='browser_main_preview', identityConfirmed=False)])


async def extract_design(crawler, url, params=None):
    from core.browser_service import BrowserService
    task = ExtractionTask(crawler, url)
    browser = None
    result = None
    queried = set()
    task.log('任务开始', platform='818ps')
    async def query(editor_url):
        share = crawler._extract_share_query_params(editor_url)
        key = (share.get('share_id'), share.get('upic_id'), share.get('share_uid'))
        if (key[0] or key[1]) and key not in queried:
            queried.add(key)
            await stage('公开数据', lambda: crawler._extract_from_share_api(editor_url, extraction_task=task), merge=True)

    async def stage(name, operation, merge=False):
        start = time.monotonic()
        task.log(name, state='start')
        try:
            result = await operation()
            if merge and result and result.get('request_id') != task.request_id:
                task.merge(result)
            return result
        except Exception as error:
            logging.getLogger('demark.818ps').warning('[%s] request_id=%s error=%s reason=%s',
                                                    name, task.request_id, type(error).__name__, error)
            return None
        finally:
            elapsed = round((time.monotonic() - start) * 1000)
            task.stats['stageMs'][name] = task.stats['stageMs'].get(name, 0) + elapsed
            task.log(name, state='end', elapsed_ms=elapsed, page_count=len(task.pages))

    try:
        url = html.unescape(url.strip())
        share = crawler._extract_share_query_params(url)
        for key, value in (params or {}).items():
            if value and not share.get(key):
                share[key] = value
        editor_url = url if crawler._extract_share_query_params(url).get('share_id') else (
            crawler._build_editor_url_from_share_params(share) or url)
        await query(editor_url)
        if not task.complete():
            async def static():
                await crawler._ensure_session()
                async with crawler.session.get(url, timeout=10) as response:
                    if response.status != 200:
                        return
                    content = await response.text()
                    await task.add(task.read_html(content))
                    if not task.pages:
                        candidates = crawler._extract_image_urls_from_content(content)
                        candidates = [url for url in candidates if crawler._is_design_page_candidate(url)]
                        numbered = [(crawler._extract_url_page_number(candidate)
                                     or crawler._extract_818ps_preview_page_number(candidate), candidate)
                                    for candidate in candidates]
                        await task.add([dict(page=number, imageUrl=candidate, source='static_preview')
                                        for number, candidate in numbered if number])
                        if not task.pages and candidates:
                            await task.add([dict(page=1, imageUrl=candidates[0], source='static_preview',
                                                 identityConfirmed=False)])
                    resolved = crawler._extract_editor_share_url_from_text(content, url)
                    if resolved:
                        return resolved
                    return str(getattr(response, 'url', '') or '')
            resolved = await stage('静态数据', static)
            if resolved:
                editor_url = resolved if crawler._extract_share_query_params(resolved).get('share_id') else editor_url
                await query(editor_url)
        if not task.complete():
            browser = BrowserService()
            browser.request_id = task.request_id
            capture = await stage('浏览器发现', lambda: browser.open_818ps_page(editor_url))
            if capture:
                resolved = capture.get('currentUrl') or editor_url
                await query(resolved)
                await task.add_capture(capture)
                task.log('画板发现', expected=task.expected, valid=len(task.pages), markers=len(task.discovered))
                if task.animation.required and not task.complete():
                    # Analyze captured bytes/failures first, then one existing-page preview action.
                    if task.expected and task.expected > 1:
                        targets = task.result()['missingPages']
                        known = [n for n in task.pages if n not in targets]
                        if targets:
                            extra = await stage('动画缺页补采', lambda: browser.capture_818ps_pages(
                                targets, known_pages=known, discover=False))
                            if extra:
                                await task.add_capture(extra)
                    if not task.complete():
                        extra = await stage('动画补采', browser.capture_818ps_animation)
                        if extra:
                            await task.add_capture(extra)
                for recovery_round in range(0 if task.animation.required else 2):
                    if task.complete():
                        break
                    known = [page for page, record in task.pages.items() if record.get('identityConfirmed', True)]
                    targets = sorted((set(range(1, task.expected + 1)) if task.expected else task.discovered) - set(known))
                    before = (len(known), task.expected, len(task.discovered))
                    if targets or not task.expected:
                        extra = await stage('缺页补采', lambda: browser.capture_818ps_pages(
                            targets, known_pages=known, discover=not bool(task.expected)))
                        if extra:
                            await task.add_capture(extra)
                    after = (sum(record.get('identityConfirmed', True) for record in task.pages.values()),
                             task.expected, len(task.discovered))
                    if after == before:
                        break
        result = task.result()
        if not result['pageCount']:
            result.update(success=False)
            result.setdefault('error', '未取得有效的整页预览图')
        result['metadata'].update(task.animation.summaries())
        task.log('动画结果', mediaType=result.get('mediaType'), animationStatus=result.get('animationStatus'),
                 frameCount=result.get('frameCount'))
        task.log('图片验证', candidates=task.stats['candidateCount'], valid=len(task.pages))
        task.log('完整性', expected=task.expected, actual=len(task.pages), status=result['completenessStatus'], missing=result['missingPages'])
        return result
    except Exception as error:
        logging.getLogger('demark.818ps').warning('[任务失败] request_id=%s error=%s reason=%s',
                                                task.request_id, type(error).__name__, error)
        result = task.result()
        if not result['pageCount']:
            result.update(success=False, error=f'{type(error).__name__}: {error}')
        return result
    finally:
        if browser:
            await browser.close()
        for pending in task.validation.values():
            if not pending.done():
                pending.cancel()
        if task.validation:
            await asyncio.gather(*task.validation.values(), return_exceptions=True)
        if result:
            result['metadata']['totalMs'] = round((time.monotonic() - task.started) * 1000)
        task.log('任务结束', total_ms=round((time.monotonic() - task.started) * 1000), page_count=len(task.pages))
