"""Local byte/media fixtures: never require a live 818ps token or browser."""
import asyncio
import base64
import io
import json
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

import pytest
from PIL import Image

from core.image_extractor import ImageExtractor
from core.browser_service import BrowserService
from crawlers.tuguaishou_818ps import Tuguaishou818psCrawler
from crawlers.tuguaishou_pipeline import ExtractionTask
from utils.downloader import ImageDownloader
from utils.image_validator import ImageValidator
from utils.media_inspector import decode


def image_bytes(format, frames=1):
    images = [Image.new('RGB', (24, 32), color) for color in ('red', 'blue', 'green')[:frames]]
    stream = io.BytesIO()
    images[0].save(stream, format=format, save_all=frames > 1, append_images=images[1:], duration=80, loop=0)
    return stream.getvalue()


@pytest.fixture(scope='module')
def media_server():
    bodies = dict(gif=image_bytes('GIF', 3), webp=image_bytes('WEBP', 3), png=image_bytes('PNG'),
                  jpg=image_bytes('JPEG'), video=b'\x00\x00\x00\x18ftypisom' + b'0' * 24)
    hits = Counter()
    class Handler(BaseHTTPRequestHandler):
        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
        def log_message(self, *args):
            pass
        def do_GET(self):
            hits[self.path] += 1
            name = self.path.split('?')[0].strip('/')
            status, mime, body = 200, 'image/gif', bodies['gif']
            if name == 'protected' and (self.headers.get('Referer') != 'https://gif.818ps.com/' or
                                        self.headers.get('Cookie') != 'access=ok' or self.path != '/protected?sig=a%2Bb'):
                status = 403
            elif name in ('403', '404', '429', '500'):
                status = int(name)
            elif name in ('webp', 'png', 'jpg', 'video'):
                mime, body = {'webp':'image/webp', 'png':'image/png', 'jpg':'image/jpeg', 'video':'video/mp4'}[name], bodies[name]
            elif name == 'octet':
                mime = 'application/octet-stream'
            elif name == 'html':
                mime, body = 'text/html', b'<html>error</html>'
            elif name == 'false-mime':
                mime, body = 'image/gif', b'<html>error</html>'
            elif name == 'empty':
                body = b''
            elif name == 'slow':
                time.sleep(.2)
            elif name == 'partial':
                status, body = 206, bodies['gif'][:20]
            elif name == 'redirect':
                self.send_response(302)
                self.send_header('Location', '/no-extension')
                self.end_headers()
                return
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', bodies, hits
    server.shutdown()
    thread.join()


@pytest.mark.asyncio
@pytest.mark.parametrize('path,mime,frames', [('direct.gif','image/gif',3),('no-extension','image/gif',3),
    ('octet','image/gif',3),('webp','image/webp',3),('png','image/png',1),('jpg','image/jpeg',1)])
async def test_byte_validation_not_suffix_or_minimum_size(media_server, path, mime, frames):
    root, bodies, _ = media_server
    validator = ImageValidator(inspect_bytes=True)
    try:
        report = await validator.inspect_media(root+'/'+path)
        assert report['valid'] and report['mediaType'] == mime
        assert report['frameCount'] == frames
        assert (report['width'], report['height']) == (24,32)
        assert report['animationStatus'] == ('animated' if frames > 1 else 'static')
        assert Path(report['mediaFile']).read_bytes() == bodies[{'image/gif':'gif','image/webp':'webp','image/png':'png','image/jpeg':'jpg'}[mime]]
    finally:
        await validator.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('path,reason', [('html','invalid_signature'),('false-mime','invalid_signature'),
    ('403','http_error'),('404','http_error'),('429','http_error'),('500','http_error'),
    ('empty','empty'),('partial','incomplete_response'),('slow','timeout')])
async def test_rejected_responses_have_real_failure_reasons(media_server, path, reason):
    validator = ImageValidator()
    try:
        report = await validator.inspect_media(media_server[0]+'/'+path, timeout=.05 if path == 'slow' else 2)
        assert not report['valid'] and report['failureReason'] == reason
        assert report['frameCount'] is None
    finally:
        await validator.close()


@pytest.mark.asyncio
async def test_signature_context_redirect_and_size_limit(media_server):
    root, _, _ = media_server
    validator = ImageValidator()
    try:
        url = root+'/protected?sig=a%2Bb'
        assert not (await validator.inspect_media(url))['valid']
        good = await validator.inspect_media(url, {'Referer':'https://gif.818ps.com/','Cookie':'access=ok'})
        assert good['valid'] and good['finalUrl'] == url
        redirected = await validator.inspect_media(root+'/redirect')
        assert redirected['valid'] and redirected['finalUrl'] == root+'/no-extension'
        assert (await validator.inspect_media(root+'/direct.gif', max_bytes=10))['failureReason'] == 'size_limit'
    finally:
        await validator.close()


@pytest.mark.asyncio
async def test_data_blob_full_frames_and_downloader_preserves_bytes(media_server, tmp_path):
    _, bodies, _ = media_server
    validator = ImageValidator()
    downloader = ImageDownloader(str(tmp_path))
    encoded = base64.b64encode(bodies['gif']).decode()
    try:
        for url, captured in [('data:image/gif;base64,'+encoded,None),
                              ('blob:https://gif.818ps.com/fixture',dict(bodyBase64=encoded,contentType='image/gif'))]:
            report = await validator.inspect_media(url, captured=captured)
            assert report['valid'] and report['frameCount'] == 3
            downloaded = await downloader.download_image(url, platform='818ps')
            assert downloaded['success'] and Path(downloaded['file_path']).suffix == '.gif'
            assert Path(downloaded['file_path']).read_bytes() == bodies['gif']
        assert (await validator.inspect_media('blob:https://gif.818ps.com/missing'))['failureReason'] == 'blob_unavailable'
    finally:
        await downloader.close()
        await validator.close()


def design(previews, animation_pages=(1,)):
    return dict(doc=dict(pageAttr=dict(pageInfo=[dict(gifInfo=[dict(id='asset')] if p in animation_pages else [])
                                                for p in range(1,len(previews)+1)])), preview=previews)


@pytest.mark.asyncio
async def test_one_board_many_frames_and_prefer_original_gif(media_server):
    root, _, _ = media_server
    crawler = Tuguaishou818psCrawler()
    task = ExtractionTask(crawler, 'https://gif.818ps.com/?upicId=12')
    try:
        await task.add(task.structured(design([root+'/direct.gif']), 'public'))
        await task.add(task.structured({'preview':[root+'/webp']}, 'other_public'))
        result = task.result()
        assert (result['pageCount'], result['frameCount'], result['mediaType']) == (1,3,'image/gif')
        assert result['completenessStatus'] == 'complete' and result['missingPages'] == []
        assert result['imageUrl'].endswith('/direct.gif')
    finally:
        await crawler.close()


@pytest.mark.asyncio
async def test_mixed_boards_and_frame_counts_are_independent(media_server):
    root, _, _ = media_server
    crawler = Tuguaishou818psCrawler()
    task = ExtractionTask(crawler, 'https://gif.818ps.com/')
    try:
        await task.add(task.structured(design([root+'/direct.gif', root+'/png']), 'public'))
        result = task.result()
        assert result['pageCount'] == 2 and result['frameCount'] is None
        assert [p['frameCount'] for p in result['pages']] == [3,1]
        assert result['completenessStatus'] == 'complete'
    finally:
        await crawler.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('path,media_type', [('png','image/png'),('video','video/mp4'),('403','unknown')])
async def test_static_first_frame_video_and_errors_cannot_complete_animation(media_server, path, media_type):
    root, _, _ = media_server
    crawler = Tuguaishou818psCrawler()
    task = ExtractionTask(crawler, 'https://gif.818ps.com/')
    try:
        await task.add(task.structured(design([root+'/'+path]), 'public'))
        result = task.result()
        assert result['pageCount'] == 0 and result['missingPages'] == [1]
        assert result['completenessStatus'] == 'partial' and result['success'] is False
        if media_type != 'unknown':
            assert result['mediaType'] == media_type
        assert ImageExtractor._normalize_result_images(None, result)['completenessStatus'] == 'partial'
    finally:
        await crawler.close()


@pytest.mark.asyncio
async def test_unknown_total_duplicates_and_invalid_deduplication(media_server):
    root, _, hits = media_server
    crawler = Tuguaishou818psCrawler()
    task = ExtractionTask(crawler, 'https://gif.818ps.com/')
    try:
        url = root+'/404?dedupe=1'
        before = hits[url.split(root)[1]]
        records = task.structured({'preview':[root+'/direct.gif',url]}, 'public')
        await task.add(records)
        await task.add(records)
        assert hits['/404?dedupe=1'] - before == 1
        assert task.result()['completenessStatus'] == 'unknown'
        assert task.result()['expectedPageCount'] is None
        assert task.result()['pageCount'] == 1
        assert task.animation.summaries()['animationFailures']['http_error'] == 1
    finally:
        await crawler.close()


@pytest.mark.asyncio
async def test_shared_url_preserves_two_board_identities(media_server):
    crawler = Tuguaishou818psCrawler()
    task = ExtractionTask(crawler, 'https://gif.818ps.com/')
    try:
        url = media_server[0]+'/direct.gif'
        await task.add(task.structured(design([url,url], (1,2)), 'public'))
        result = task.result()
        assert result['pageCount'] == 2 and [p['page'] for p in result['pages']] == [1,2]
        assert result['metadata']['duplicateUrlCount'] == 1 and result['missingPages'] == []
    finally:
        await crawler.close()


def test_gif87a_and_decode_error():
    data = image_bytes('GIF').replace(b'GIF89a',b'GIF87a',1)
    base = dict(valid=False, contentType='image/gif')
    assert decode(data,dict(base))['frameCount'] == 1
    assert decode(b'GIF89a\x00\x00',dict(base))['failureReason'] == 'decode_error'


@pytest.mark.asyncio
async def test_concurrent_close_has_one_owner_and_keeps_real_errors(caplog):
    validator = ImageValidator()
    sync = validator.sync_session
    sync.close = Mock()
    session = Mock(close=AsyncMock(side_effect=RuntimeError('fixture close failed')))
    validator.session = session
    await asyncio.gather(validator.close(),validator.close(),validator.close())
    session.close.assert_awaited_once()
    sync.close.assert_called_once()
    assert 'fixture close failed' in caplog.text
    assert '同步会话已关闭' not in caplog.text


@pytest.mark.asyncio
async def test_captured_http_failure_never_reissues_invalid_request(media_server):
    root, _, hits = media_server
    crawler = Tuguaishou818psCrawler()
    task = ExtractionTask(crawler, 'https://gif.818ps.com/')
    url = root+'/403?from-browser=1'
    before = hits['/403?from-browser=1']
    try:
        task.animation.remember(dict(url=url, role='output', page=1, source='network_response',
                                     httpStatus=403, contentType='text/html'))
        await task.animation.validate()
        await task.animation.validate()
        assert hits['/403?from-browser=1'] == before
        assert len(task.animation.checked) == 1
        assert task.animation.diagnostics[0]['failureReason'] == 'http_error'
    finally:
        await crawler.close()


@pytest.mark.asyncio
async def test_targeted_animation_recovery_uses_one_existing_browser(media_server, monkeypatch):
    root, bodies, _ = media_server
    crawler = Tuguaishou818psCrawler()
    response = SimpleNamespace(status=200, url='https://gif.818ps.com/', text=AsyncMock(return_value='<html></html>'))
    context = Mock(__aenter__=AsyncMock(return_value=response), __aexit__=AsyncMock())
    crawler._ensure_session = AsyncMock()
    crawler.session = SimpleNamespace(get=Mock(return_value=context), close=AsyncMock())
    crawler._extract_from_share_api = AsyncMock(return_value=None)
    first = dict(currentUrl='https://gif.818ps.com/', networkData=[design([root+'/png'])], pageMarkers=['第1页'])
    second = dict(currentUrl='https://gif.818ps.com/', networkData=[design([root+'/direct.gif'])])
    open_page = AsyncMock(return_value=first)
    recover = AsyncMock(return_value=second)
    pages = AsyncMock()
    close = AsyncMock()
    monkeypatch.setattr(BrowserService,'open_818ps_page',open_page)
    monkeypatch.setattr(BrowserService,'capture_818ps_animation',recover)
    monkeypatch.setattr(BrowserService,'capture_818ps_pages',pages)
    monkeypatch.setattr(BrowserService,'close',close)
    try:
        result = await crawler.extract_image('https://818ps.com/g/test')
        assert result['pageCount'] == 1 and result['frameCount'] == 3
        assert result['completenessStatus'] == 'complete'
        assert result['metadata']['animationCheckedCount'] == 2
        open_page.assert_awaited_once()
        recover.assert_awaited_once()
        pages.assert_not_awaited()
        close.assert_awaited_once()
    finally:
        await crawler.close()


@pytest.mark.asyncio
async def test_blob_tracks_observed_original_request_by_bytes(media_server):
    root, bodies, _ = media_server
    crawler = Tuguaishou818psCrawler()
    task = ExtractionTask(crawler,'https://gif.818ps.com/')
    try:
        encoded = base64.b64encode(bodies['gif']).decode()
        for url in (root+'/direct.gif','blob:https://gif.818ps.com/test-original'):
            task.animation.remember(dict(url=url, role='asset', source='network_response' if url.startswith('http') else 'dom_src',
                                         bodyBase64=encoded,contentType='image/gif'))
        await task.animation.validate()
        blob = next(r for r in task.animation.diagnostics if r['url'].startswith('blob:'))
        assert blob['originalRequestUrl'] == root+'/direct.gif'
        assert task.result()['pageCount'] == 0  # matching an asset never makes it an output
    finally:
        await crawler.close()


@pytest.mark.asyncio
async def test_confirming_board_two_does_not_confirm_an_unnumbered_cover(media_server):
    crawler = Tuguaishou818psCrawler()
    task = ExtractionTask(crawler,'https://gif.818ps.com/')
    task.expect(2)
    url = media_server[0]+'/direct.gif'
    try:
        task.animation.remember(dict(url=url,role='output',page=1,identityConfirmed=False,source='dom'))
        await task.add([dict(imageUrl=url,page=2,source='browser_page_activation')])
        result = task.result()
        assert result['missingPages'] == [1] and result['completenessStatus'] == 'partial'
        assert result['pages'][1]['identityConfirmed'] is True
        assert result['pages'][0]['identityConfirmed'] is False
    finally:
        await crawler.close()


@pytest.mark.asyncio
async def test_nested_asset_previews_are_never_board_outputs(media_server):
    crawler = Tuguaishou818psCrawler()
    task = ExtractionTask(crawler,'https://gif.818ps.com/')
    try:
        records = task.structured({'pageCount':1,'assets':[{'preview':[media_server[0]+'/direct.gif']}]},'public')
        await task.add(records)
        assert records == [] and task.result()['pageCount'] == 0
        assert task.result()['completenessStatus'] == 'partial'
        assert all(r['role'] == 'asset' for r in task.animation.diagnostics)
    finally:
        await crawler.close()


@pytest.mark.asyncio
async def test_animation_recovery_activates_only_missing_board(media_server, monkeypatch):
    root = media_server[0]
    crawler = Tuguaishou818psCrawler()
    response = SimpleNamespace(status=200, url='https://gif.818ps.com/', text=AsyncMock(return_value='<html></html>'))
    crawler._ensure_session = AsyncMock()
    crawler.session = SimpleNamespace(get=Mock(return_value=Mock(
        __aenter__=AsyncMock(return_value=response),__aexit__=AsyncMock())),close=AsyncMock())
    crawler._extract_from_share_api = AsyncMock(return_value=None)
    first = dict(currentUrl='https://gif.818ps.com/',networkData=[design([root+'/direct.gif',root+'/403'],(1,2))])
    extra = dict(pageSnapshots=[dict(page=2,previewUpdated=True,previewUrls=[root+'/direct.gif?board=2'])])
    pages = AsyncMock(return_value=extra)
    preview = AsyncMock()
    monkeypatch.setattr(BrowserService,'open_818ps_page',AsyncMock(return_value=first))
    monkeypatch.setattr(BrowserService,'capture_818ps_pages',pages)
    monkeypatch.setattr(BrowserService,'capture_818ps_animation',preview)
    monkeypatch.setattr(BrowserService,'close',AsyncMock())
    try:
        result = await crawler.extract_image('https://818ps.com/g/test')
        assert result['pageCount'] == 2 and result['completenessStatus'] == 'complete'
        assert [p['frameCount'] for p in result['pages']] == [3,3]
        pages.assert_awaited_once_with([2],known_pages=[1],discover=False)
        preview.assert_not_awaited()
    finally:
        await crawler.close()
