"""Opt-in Chrome smoke test against an isolated local page, never a live share."""
import base64
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from core.browser_service import BrowserService
from crawlers.tuguaishou_818ps import Tuguaishou818psCrawler
from PIL import Image


@pytest.mark.skipif(os.getenv('DEMARK_818PS_BROWSER_TEST') != '1', reason='Opt-in local Chrome integration test')
@pytest.mark.asyncio
async def test_real_chrome_reuses_session_and_confirms_main_preview_update():
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
    page = '''<!doctype html><meta charset="utf-8"><title>818ps local fixture</title>
    <body><aside style="position:fixed;left:20px;top:20px">共2页
    <button class="page-nav" onclick="document.querySelector('img').src='/user_preview_ue/page-1.png'">第1页</button>
    <button class="page-nav" onclick="document.querySelector('img').src='/user_preview_ue/page-2.png'">第2页</button>
    </aside><img style="position:absolute;left:520px;top:80px;width:900px;height:600px"
    src="/user_preview_ue/page-1.png"></body>'''.encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            is_image = self.path.endswith('.png')
            content = png if is_image else page
            self.send_response(200)
            self.send_header('Content-Type', 'image/png' if is_image else 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    browser = BrowserService()
    browser.request_id = 'local-integration'
    try:
        capture = await browser.open_818ps_page(f'http://127.0.0.1:{server.server_port}/')
        driver = browser.driver
        assert capture['expectedPageCount'] == 2
        assert {'第1页', '第2页'} <= set(capture['pageMarkers'])
        result = await browser.capture_818ps_pages([2], known_pages=[1])
        assert browser.driver is driver
        assert result['pageSnapshots'][0]['page'] == 2
        assert result['pageSnapshots'][0]['previewUpdated'] is True
        assert result['pageSnapshots'][0]['previewUrls'][0].endswith('/page-2.png')
        unchanged = await browser.capture_818ps_pages([2])
        assert unchanged['pageSnapshots'] == []
        assert browser.driver is driver
    finally:
        await browser.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert browser.driver is None


@pytest.mark.skipif(os.getenv('DEMARK_818PS_BROWSER_TEST') != '1', reason='Opt-in local Chrome integration test')
@pytest.mark.asyncio
async def test_real_chrome_collects_network_data_sources_and_blob_without_renavigation():
    stream = io.BytesIO()
    Image.new('RGB',(24,32),'red').save(stream,format='GIF',save_all=True,
        append_images=[Image.new('RGB',(24,32),'blue')],duration=80,loop=0)
    gif = stream.getvalue()
    encoded = base64.b64encode(gif).decode()
    page = ('''<!doctype html><meta charset="utf-8"><body>共1页
    <section class="preview"><img width="400" height="500" src="/user_preview_ue/no-extension"></section>
    <img id="blob"><img src="data:image/gif;base64,ENCODED">
    <picture><source srcset="/from-srcset 1x"><img data-src="/lazy-source"></picture>
    <video poster="/poster"><source src="/video-source" type="video/mp4"></video>
    <div style="background-image:url('/background.gif')"></div>
    <script>
      fetch('/user_preview_ue/no-extension').then(r=>r.blob()).then(b=>document.querySelector('#blob').src=URL.createObjectURL(b));
    </script></body>''').replace('ENCODED',encoded).encode()
    navigations = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            is_html = self.path == '/'
            if is_html:
                navigations.append(self.path)
            content = page if is_html else gif
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8' if is_html else 'image/gif')
            self.send_header('Content-Length',str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        def log_message(self,*args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    browser = BrowserService()
    crawler = Tuguaishou818psCrawler()
    try:
        await browser.open_818ps_page(f'http://127.0.0.1:{server.server_port}/')
        driver = browser.driver
        capture = await browser.capture_818ps_animation()
        records = capture['mediaCandidates']
        assert any(r['url'].startswith('data:image/gif') for r in records)
        blob = next(r for r in records if r['url'].startswith('blob:'))
        assert base64.b64decode(blob['bodyBase64']) == gif
        assert any(r['url'].endswith('/from-srcset') for r in records)
        assert any(r['url'].endswith('/video-source') for r in records)
        assert any(r['url'].endswith('/poster') for r in records)
        assert any(r['url'].endswith('/background.gif') for r in records)
        resource = next(r for r in capture['mediaResponses'] if '/user_preview_ue/' in r['url'])
        assert resource['httpStatus'] == 200 and resource['contentType'] == 'image/gif'
        assert resource['resourceType'] in ('Image','Fetch') and base64.b64decode(resource['bodyBase64']) == gif
        report = await crawler.validator.inspect_media(resource['url'], captured=resource)
        assert report['valid'] and report['frameCount'] == 2
        assert browser.driver is driver and navigations == ['/']
    finally:
        await browser.close()
        await crawler.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.skipif(not os.getenv('DEMARK_818PS_LIVE_URL'), reason='Requires an explicitly supplied live share URL')
@pytest.mark.asyncio
async def test_live_shared_animation_preserves_original_bytes(tmp_path):
    from pathlib import Path
    from utils.downloader import ImageDownloader
    crawler = Tuguaishou818psCrawler()
    downloader = ImageDownloader(str(tmp_path))
    try:
        result = await crawler.extract_image(os.environ['DEMARK_818PS_LIVE_URL'])
        assert result['pageCount'] == 1 and result['missingPages'] == []
        assert result['completenessStatus'] == 'complete'
        assert result['mediaType'] == 'image/gif' and result['animationStatus'] == 'animated'
        with Image.open(result['pages'][0]['mediaFile']) as image:
            assert image.n_frames == result['frameCount'] > 1
            image.seek(image.n_frames-1)
            image.load()
            dimensions = image.size
        saved = await downloader.download_image(result['imageUrl'], platform='818ps')
        assert saved['success'] and Path(saved['file_path']).suffix == '.gif'
        assert Path(saved['file_path']).read_bytes() == Path(result['pages'][0]['mediaFile']).read_bytes()
        print(json.dumps(dict(pageCount=result['pageCount'],expectedPageCount=result['expectedPageCount'],
                              frameCount=result['frameCount'],mediaType=result['mediaType'],
                              completenessStatus=result['completenessStatus'],missingPages=result['missingPages'],
                              size=Path(result['pages'][0]['mediaFile']).stat().st_size,
                              dimensions=dimensions,elapsed_ms=result['metadata']['totalMs']), ensure_ascii=False))
    finally:
        await downloader.close()
        await crawler.close()
