"""Animation discovery with explicit output/asset provenance and byte diagnostics."""
import asyncio
import html
import json
import logging
import re
from collections import Counter
from urllib.parse import urlparse
from bs4 import BeautifulSoup


def media_hint(url, mime=''):
    if url.startswith('blob:'):
        return 'blob'
    if 'gif' in mime or re.search(r'\.gif(?:[!?/#]|$)', urlparse(url).path, re.I) or url.startswith('data:image/gif'):
        return 'gif'
    if 'webp' in mime or '.webp' in urlparse(url).path.lower():
        return 'webp'
    if mime.startswith('video/') or re.search(r'\.(mp4|webm)(?:[!?/#]|$)', url, re.I):
        return 'video'
    return 'image'


class AnimationDiscovery:
    def __init__(self, task):
        self.task = task
        self.required = urlparse(task.url).hostname == 'gif.818ps.com'
        self.required_pages = set()
        self.candidates = {}
        self.checked = {}
        self.diagnostics = []
        self.output_pages = set()
        self.duplicate_count = 0

    def remember(self, record):
        url = record.get('url')
        if not isinstance(url, str) or not url.startswith(('http://', 'https://', 'data:image/', 'blob:')):
            return
        # Tracking GIFs and editor icons are not design animation candidates.
        parsed = urlparse(url)
        path = parsed.path.lower()
        if parsed.hostname == 'p.818ps.com' or any(p in path for p in ('/index_img/', '/specificwordpreview/', '/fonts/')):
            return
        if url in self.candidates:
            old = self.candidates[url]
            self.duplicate_count += 1
            old['sources'] = list(dict.fromkeys(old['sources'] + [record.get('source', 'unknown')]))
            if record.get('role') == 'output':
                number = record.get('page', 1)
                old.setdefault('pages', {})[number] = old.get('pages', {}).get(number, False) or record.get('identityConfirmed', True)
                old.update(role='output')
            if record.get('bodyBase64') is not None:
                old['bodyBase64'] = record['bodyBase64']
            old.update({k: v for k, v in record.items() if k in ('httpStatus', 'contentType', 'finalUrl', 'contentLength')})
        else:
            self.candidates[url] = dict(record, sources=[record.get('source', 'unknown')],
                                        pages={record.get('page', 1): record.get('identityConfirmed', True)}
                                        if record.get('role') == 'output' else {})

    def read_html(self, content):
        soup = BeautifulSoup(content or '', 'html.parser')
        for element in soup.select('img, source, video, meta[property="og:image"]'):
            for attr in ('src', 'data-src', 'srcset', 'poster', 'content'):
                value = element.get(attr)
                if not value:
                    continue
                values = [value] if attr != 'srcset' or value.startswith('data:') else value.split(',')
                for url in values:
                    url = url.strip().split()[0] if url.strip() else ''
                    if media_hint(url) not in ('gif','webp','video','blob'):
                        continue
                    output = '/gif_complete_img/' in urlparse(url).path or element.get('property') == 'og:image'
                    number = self.task.crawler._extract_url_page_number(url)
                    self.remember(dict(url=url, source='static_html:'+attr, role='output' if output else 'asset',
                                       page=number or 1, identityConfirmed=bool(number)))

    def structured(self, data, source, asset_context=False):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                return
        if isinstance(data, list):
            for item in data:
                self.structured(item, source, asset_context)
        if not isinstance(data, dict):
            return
        # Observed GIF editor schema: pageInfo is board inventory; gifInfo is a layer.
        doc = data.get('doc')
        if isinstance(doc, dict):
            attrs = doc.get('pageAttr')
            page_info = attrs.get('pageInfo', []) if isinstance(attrs, dict) else []
            if isinstance(page_info, list):
                for number, page in enumerate(page_info, 1):
                    gifs = page.get('gifInfo') if isinstance(page, dict) else None
                    if isinstance(page, dict) and any(isinstance(g, dict) and (g.get('id') or g.get('imagePath'))
                                                      for g in (gifs if isinstance(gifs, list) else [])):
                        self.required = True
                        self.required_pages.add(number)
                if self.required_pages:
                    self.task.expect(len(page_info))
        for key, value in data.items():
            if key in ('preview', 'previews') and isinstance(value, list):
                for number, item in enumerate(value, 1):
                    url = item if isinstance(item, str) else None
                    if isinstance(item, dict):
                        url = next((item[k] for k in ('imageUrl','previewUrl','url','preview')
                                    if isinstance(item.get(k), str)), None)
                    if url and (self.required or media_hint(url) in ('gif', 'video')):
                        self.remember(dict(url=html.unescape(url), page=self.task.number(item, url, number),
                                           role='asset' if asset_context else 'output', source=source))
            if isinstance(value, (dict, list)):
                self.structured(value, source, asset_context or key in ('assets','work','gifInfo','materials','elements'))
            elif isinstance(value, str) and value.startswith(('http', 'data:image/', 'blob:')) and media_hint(value) != 'image':
                self.remember(dict(url=value, role='asset', source=source + ':' + key))

    def capture(self, capture):
        if urlparse(capture.get('currentUrl', '')).hostname == 'gif.818ps.com':
            self.required = True
        for record in capture.get('mediaCandidates', []) + capture.get('mediaResponses', []):
            url = record.get('url', '')
            path = urlparse(url).path.lower()
            if re.search(r'\.(?:js|css|woff2?|svg)(?:$|!)', path):
                continue
            if record.get('source', '').startswith('performance_') and not (
                    media_hint(url) != 'image' or '/gif_complete_img/' in path or
                    self.task.crawler._is_design_page_candidate(url)):
                continue
            output = ('/gif_complete_img/' in path or self.task.crawler._is_design_page_candidate(url)
                      or (record.get('isMainPreview') and '/ips_gif_asset/' not in path))
            if not (self.required or media_hint(url, record.get('contentType', '')) != 'image'):
                continue
            # SVG/font/UI requests cannot establish an animation resource.
            if record.get('contentType', '').startswith('image/svg'):
                continue
            number = (self.task.crawler._extract_url_page_number(url) or
                      self.task.crawler._extract_818ps_preview_page_number(url))
            self.remember(dict(record, role='output' if output else 'asset', page=number or 1,
                               identityConfirmed=bool(number) or self.task.expected == 1))

    async def validate(self):
        async def check(record):
            url = record['url']
            headers = self.task.request_headers.get(url, {})
            key = (url, tuple(sorted(headers.items())))
            # A newly captured body or corrected request context warrants one fresh check.
            key += (bool(record.get('bodyBase64')),)
            if key not in self.checked:
                async with self.task.limit:
                    report = await self.task.crawler.validator.inspect_media(url, headers, record)
                self.checked[key] = report
                self.diagnostics.append(dict(report, source=record['sources'], role=record.get('role')))
                logging.getLogger('demark.818ps').debug('request_id=%s media=%s', self.task.request_id, report)
            report = self.checked[key]
            record['detectedType'] = report.get('mediaType')
            if record.get('role') != 'output' or not report.get('valid'):
                return
            for number, confirmed in record.get('pages', {}).items():
                self.output_pages.add(number)
                wants_animation = number in self.required_pages or (self.required and not self.required_pages)
                # Videos retain their real format in diagnostics, never enter imageUrls as GIF.
                if report.get('mediaType', '').startswith('video/'):
                    continue
                if wants_animation and report['animationStatus'] != 'animated':
                    continue
                page = dict(page=number, imageUrl=url, source=record['sources'][0],
                            identityConfirmed=confirmed,
                            **{k: report.get(k) for k in ('mediaType', 'frameCount', 'animationStatus', 'mediaFile')})
                def quality(p):
                    return (p.get('identityConfirmed', True), p.get('animationStatus') == 'animated',
                            p.get('mediaType') == 'image/gif', (p.get('width') or 0) * (p.get('height') or 0))
                page.update(width=report.get('width'), height=report.get('height'))
                if number in self.task.pages and quality(self.task.pages[number]) >= quality(page):
                    continue
                self.task.pages[number] = page
                if page['source'] not in self.task.sources:
                    self.task.sources.append(page['source'])
        await asyncio.gather(*(check(r) for r in self.candidates.values()))
        # A Blob can be correlated with an observed HTTP response by exact content,
        # never by guessing a URL from its generated identifier.
        originals = {r.get('mediaFile'): r.get('finalUrl', r['url']) for r in self.checked.values()
                     if r.get('valid') and r['url'].startswith(('http://', 'https://'))}
        for report in self.diagnostics:
            original = originals.get(report.get('mediaFile'))
            if report['url'].startswith('blob:') and original:
                report['originalRequestUrl'] = original
                for page in self.task.pages.values():
                    if page['imageUrl'] == report['url']:
                        page['originalMediaUrl'] = original

    def summaries(self):
        hints = Counter(media_hint('blob:' if r['url'].startswith('blob:') else '', r.get('detectedType') or
                                   r.get('contentType', '')) if r.get('detectedType') or r.get('contentType')
                        else media_hint(r['url']) for r in self.candidates.values())
        reports = list(self.checked.values())
        failures = Counter(r['failureReason'] for r in reports if r.get('failureReason'))
        self.task.log('动画发现', candidates=len(self.candidates), **{k: hints[k] for k in ('gif','webp','video','blob')})
        self.task.log('动画验证', checked=len(reports), valid=sum(r['valid'] for r in reports),
                      animated=sum(r['animationStatus'] == 'animated' for r in reports),
                      rejected=sum(not r['valid'] for r in reports))
        self.task.log('失败分类', **{k: failures[k] for k in ('http_error','mime_mismatch','invalid_signature','timeout','empty')})
        return dict(animationCandidateCount=len(self.candidates), animationDuplicateCount=self.duplicate_count,
                    animationCheckedCount=len(reports), animationFailures=dict(failures),
                    # Response details are DEBUG only; summaries and reasons are safe to return.
                    animationDiagnostics=[{k: v for k, v in r.items() if k not in ('url','finalUrl','mediaFile')}
                                          for r in self.diagnostics])
