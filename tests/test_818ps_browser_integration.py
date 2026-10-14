"""Opt-in Chrome smoke test against an isolated local page, never a live share."""
import base64
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from core.browser_service import BrowserService


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
