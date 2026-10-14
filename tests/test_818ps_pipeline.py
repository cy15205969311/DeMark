"""Deterministic 818ps extraction tests; no external service or browser required."""
import asyncio
import json
import io
import zipfile
import os
import threading
import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.browser_service import BrowserService
from core.image_extractor import ImageExtractor
from crawlers.tuguaishou_818ps import Tuguaishou818psCrawler
from crawlers.tuguaishou_pipeline import ExtractionTask
from utils.image_validator import ImageValidator
from utils.url_parser import URLParser


EDITOR = 'https://ue.818ps.com/v4/?upicId=12&share_id=34&share_uid=56'
SHELL = 'https://818ps.com/u/test'


def image(page):
    return f'https://img.tuguaishou.com/user_preview_ue/page-{page}.jpg?auth_key=test'


class Response:
    status = 200
    url = SHELL

    def __init__(self, content):
        self.content = content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def text(self):
        return self.content


@pytest.fixture
def crawler(monkeypatch):
    crawler = Tuguaishou818psCrawler()
    crawler._ensure_session = AsyncMock()
    crawler.session = SimpleNamespace(get=Mock(return_value=Response('<html></html>')),
                                      close=AsyncMock(), closed=False)
    crawler.validator.validate_image_url = AsyncMock(return_value=True)
    crawler._fetch_json = AsyncMock(return_value=None)
    monkeypatch.setattr(BrowserService, 'open_818ps_page', AsyncMock(return_value={}))
    monkeypatch.setattr(BrowserService, 'capture_818ps_pages', AsyncMock(return_value={}))
    monkeypatch.setattr(BrowserService, 'close', AsyncMock())
    return crawler


@pytest.mark.asyncio
@pytest.mark.parametrize('count', [1, 8])
async def test_structured_complete_design_skips_browser(crawler, count):
    crawler._fetch_json.return_value = {'data': {'pageCount': count, 'preview': [image(n) for n in range(1, count + 1)]}}
    start = time.monotonic()
    result = await crawler.extract_image(EDITOR)
    assert result['pageCount'] == count
    assert [page['page'] for page in result['pages']] == list(range(1, count + 1))
    assert result['completenessStatus'] == 'complete'
    assert result['missingPages'] == []
    assert result['metadata']['duplicateUrlCount'] == 0
    assert result['metadata']['totalMs'] < 1000
    assert time.monotonic() - start < 1
    BrowserService.open_818ps_page.assert_not_awaited()
    assert crawler._fetch_json.await_count == 4
    await crawler.close()


@pytest.mark.asyncio
async def test_cover_does_not_stop_before_full_dynamic_document(crawler):
    crawler.session.get.return_value = Response(f'<img src="{image(1)}">')
    BrowserService.open_818ps_page.return_value = {
        'currentUrl': EDITOR,
        'networkData': [{'pageCount': 3, 'preview': [image(1), image(2), image(3)]}],
    }
    result = await crawler.extract_image(SHELL)
    assert result['imageUrls'] == [image(1), image(2), image(3)]
    assert result['expectedPageCount'] == 3
    assert result['completenessStatus'] == 'complete'
    BrowserService.open_818ps_page.assert_awaited_once()
    BrowserService.capture_818ps_pages.assert_not_awaited()
    BrowserService.close.assert_awaited_once()
    assert crawler.session.get.call_count == 1
    await crawler.close()


@pytest.mark.asyncio
async def test_partial_api_only_activates_missing_pages(crawler):
    crawler._fetch_json.return_value = {'pageCount': 3, 'preview': [image(1), image(3)]}
    BrowserService.open_818ps_page.return_value = {'currentUrl': EDITOR}
    BrowserService.capture_818ps_pages.return_value = {
        'pageSnapshots': [{'page': 2, 'previewUrls': [image(2)], 'previewUpdated': True}],
    }
    result = await crawler.extract_image(EDITOR)
    BrowserService.capture_818ps_pages.assert_awaited_once_with([2], known_pages=[1, 3], discover=False)
    BrowserService.open_818ps_page.assert_awaited_once_with(EDITOR)
    assert crawler._fetch_json.await_count == 4  # Never re-query the same sharing parameters.
    assert result['completenessStatus'] == 'complete'
    assert result['imageUrls'] == [image(1), image(2), image(3)]
    await crawler.close()


@pytest.mark.asyncio
async def test_failed_missing_page_preserves_gap_and_partial_status(crawler):
    crawler._fetch_json.return_value = {'pageCount': 3, 'preview': [image(1), image(3)]}
    BrowserService.open_818ps_page.return_value = {'currentUrl': EDITOR}
    result = await crawler.extract_image(EDITOR)
    assert result['pageCount'] == 2
    assert [page['page'] for page in result['pages']] == [1, 3]
    assert result['missingPages'] == [2]
    assert result['completenessStatus'] == 'partial'
    normalized = ImageExtractor()._normalize_result_images(result)
    assert normalized['pages'] == result['pages']
    assert normalized['missingPages'] == [2]
    await crawler.close()


@pytest.mark.asyncio
async def test_identical_urls_keep_distinct_structured_page_identity(crawler):
    crawler._fetch_json.return_value = {'pageCount': 2, 'preview': [
        {'page': 1, 'url': image(1)}, {'page': 2, 'url': image(1)}]}
    result = await crawler.extract_image(EDITOR)
    assert result['pageCount'] == 2
    assert result['imageUrls'] == [image(1), image(1)]
    assert result['metadata']['duplicateUrlCount'] == 1
    assert result['metadata']['uniqueImageCount'] == 1
    assert result['completenessStatus'] == 'complete'
    assert ImageExtractor()._normalize_result_images(result)['pageCount'] == 2
    assert crawler.validator.validate_image_url.await_count == 1
    await crawler.close()


@pytest.mark.asyncio
async def test_expired_signature_is_missing_without_unsigned_rewrite(crawler):
    expired = image(2).replace('test', 'expired')
    crawler._fetch_json.return_value = {'pageCount': 2, 'preview': [image(1), expired]}
    crawler.validator.validate_image_url.side_effect = lambda url, request_headers=None: 'expired' not in url
    BrowserService.open_818ps_page.return_value = {'currentUrl': EDITOR}
    result = await crawler.extract_image(EDITOR)
    assert result['completenessStatus'] == 'partial'
    assert result['missingPages'] == [2]
    assert result['imageUrls'] == [image(1)]
    assert all('auth_key=' in call.args[0] for call in crawler.validator.validate_image_url.call_args_list)
    await crawler.close()


@pytest.mark.asyncio
async def test_unconfirmed_count_returns_unknown_and_markers_do_not_prove_total(crawler):
    BrowserService.open_818ps_page.return_value = {
        'currentUrl': SHELL, 'imageUrls': [image(1)], 'pageMarkers': ['第1页', '第2页'],
    }
    result = await crawler.extract_image(SHELL)
    assert result['pageCount'] == 1
    assert result['expectedPageCount'] is None
    assert result['completenessStatus'] == 'unknown'
    assert result['missingPages'] == []
    BrowserService.capture_818ps_pages.assert_awaited_once_with([2], known_pages=[1], discover=True)
    await crawler.close()


@pytest.mark.asyncio
async def test_preview_not_updated_cannot_be_assigned_to_next_page(crawler):
    task = ExtractionTask(crawler, SHELL)
    task.expect(2)
    await task.add([{'page': 1, 'imageUrl': image(1), 'source': 'structured'}])
    await task.add_capture({'pageSnapshots': [
        {'page': 2, 'previewUrls': [image(1)], 'previewUpdated': False}]})
    assert task.result()['missingPages'] == [2]
    assert task.result()['completenessStatus'] == 'partial'
    await crawler.close()


@pytest.mark.asyncio
async def test_asset_arrays_and_thumbnails_are_not_pages(crawler):
    task = ExtractionTask(crawler, SHELL)
    records = task.structured({'assets': [image(1), image(2)], 'thumbnails': [image(3)]}, 'api')
    assert records == []
    assert task.expected is None
    await crawler.close()


@pytest.mark.asyncio
async def test_empty_valid_images_keeps_expected_count(crawler):
    crawler._fetch_json.return_value = {'pageCount': 3, 'preview': [image(1), image(2), image(3)]}
    crawler.validator.validate_image_url.return_value = False
    result = await crawler.extract_image(EDITOR)
    assert result['success'] is False
    assert result['expectedPageCount'] == 3
    assert result['missingPages'] == [1, 2, 3]
    assert result['completenessStatus'] == 'partial'
    await crawler.close()


@pytest.mark.asyncio
async def test_browser_failure_retains_valid_partial_result_and_closes(crawler):
    crawler._fetch_json.return_value = {'pageCount': 2, 'preview': [image(1)]}
    BrowserService.open_818ps_page.side_effect = RuntimeError('driver unavailable')
    result = await crawler.extract_image(EDITOR)
    assert result['imageUrls'] == [image(1)]
    assert result['missingPages'] == [2]
    BrowserService.close.assert_awaited_once()
    await crawler.close()


@pytest.mark.asyncio
async def test_request_id_and_task_summary_logging(crawler, caplog):
    crawler._fetch_json.return_value = {'pageCount': 1, 'preview': [image(1)]}
    with caplog.at_level(logging.INFO):
        first = await crawler.extract_image(EDITOR)
        second = await crawler.extract_image(EDITOR)
    assert first['request_id'] != second['request_id']
    assert len([record for record in caplog.records if '[任务开始]' in record.message]) == 2
    assert len([record for record in caplog.records if '[任务结束]' in record.message]) == 2
    assert all('request_id=' in record.message for record in caplog.records if record.name == 'demark.818ps')
    assert not any('auth_key=' in record.message for record in caplog.records)
    await crawler.close()


@pytest.mark.asyncio
async def test_dispatcher_never_uses_single_image_shortcuts(monkeypatch):
    extractor = ImageExtractor()
    extractor.url_parser.parse_share_url = Mock(return_value={'success': True, 'parsed_url': EDITOR,
                                                             'platform': '818ps', 'pic_id': '1', 'upic_id': '2'})
    extractor.third_party_api.extract_with_cache = AsyncMock()
    extractor._selenium_extract = AsyncMock()
    extractor._build_818ps_urls_from_params = AsyncMock()
    extractor.crawlers['818ps'].extract_image = AsyncMock(return_value={
        'platform': '818ps', 'pages': [{'page': 3, 'imageUrl': image(3)}], 'expectedPageCount': 3,
        'source': 'test'})
    result = await extractor.extract_image(EDITOR, '818ps')
    assert result['completenessStatus'] == 'partial'
    assert result['missingPages'] == [1, 2]
    extractor.third_party_api.extract_with_cache.assert_not_awaited()
    extractor._selenium_extract.assert_not_awaited()
    extractor._build_818ps_urls_from_params.assert_not_awaited()
    await extractor.close()


@pytest.mark.asyncio
async def test_validation_preserves_context_and_does_not_share_negative_cache():
    validator = ImageValidator(verbose=False)
    validator._validate_async_fast = AsyncMock(side_effect=lambda url, headers: headers.get('Referer') == EDITOR)
    assert not await validator.validate_image_url(image(1))
    assert await validator.validate_image_url(image(1), request_headers={'Referer': EDITOR})
    assert validator._validate_async_fast.await_count == 2
    assert validator._validate_async_fast.call_args.args[1]['Referer'] == EDITOR
    await validator.close()


def test_driver_startup_has_one_fallback_and_reuses_cached_path(monkeypatch, tmp_path):
    import undetected_chromedriver as uc
    service = BrowserService()
    chrome = tmp_path / 'chrome.exe'
    chrome.touch()
    driver_path = tmp_path / 'driver.exe'
    driver_path.touch()
    driver = Mock(service=SimpleNamespace(path=str(driver_path)))
    monkeypatch.setattr(service, '_find_chrome_executable', lambda: str(chrome))
    monkeypatch.setattr(service, '_get_chrome_version', lambda: 140)
    monkeypatch.setattr(service, '_prepare_818ps_driver', lambda uc, version: str(driver_path))
    chrome_factory = Mock(side_effect=[RuntimeError('Current browser version is 141.0.1'), driver])
    monkeypatch.setattr(uc, 'Chrome', chrome_factory)
    assert service._get_818ps_driver() is driver
    assert service._get_818ps_driver() is driver
    assert chrome_factory.call_count == 2
    assert chrome_factory.call_args.kwargs['version_main'] == 141
    driver.set_page_load_timeout.assert_called_once_with(15)
    # A subsequent task can use the known executable without another version probe.
    other = BrowserService()
    monkeypatch.setattr(other, '_find_chrome_executable', lambda: str(chrome))
    monkeypatch.setattr(other, '_get_chrome_version', Mock(side_effect=AssertionError('version re-probed')))
    BrowserService._chrome_versions[(str(chrome), chrome.stat().st_mtime)] = 141
    chrome_factory.side_effect = None
    chrome_factory.return_value = Mock(service=SimpleNamespace(path=str(driver_path)))
    other._get_818ps_driver()
    assert chrome_factory.call_args.kwargs['driver_executable_path'] == str(driver_path)


def test_driver_failure_stops_after_two_attempts(monkeypatch, tmp_path):
    import undetected_chromedriver as uc
    service = BrowserService()
    chrome = tmp_path / 'chrome.exe'
    chrome.touch()
    monkeypatch.setattr(service, '_find_chrome_executable', lambda: str(chrome))
    monkeypatch.setattr(service, '_get_chrome_version', lambda: 140)
    monkeypatch.setattr(service, '_prepare_818ps_driver', lambda uc, version: None)
    factory = Mock(side_effect=RuntimeError('startup failed'))
    monkeypatch.setattr(uc, 'Chrome', factory)
    with pytest.raises(RuntimeError, match='startup failed'):
        service._get_818ps_driver()
    assert factory.call_count == 2
    assert service.driver is None


def test_network_body_waits_for_finished_and_keeps_signed_request_headers():
    service = BrowserService()
    def event(method, params):
        return {'message': json.dumps({'message': {'method': method, 'params': params}})}
    service.driver = Mock()
    service.driver.get_log.side_effect = [
        [event('Network.requestWillBeSent', {'requestId': 'a', 'request': {'url': image(1), 'headers': {'Referer': EDITOR}}}),
         event('Network.responseReceived', {'requestId': 'a', 'response': {'url': 'https://818ps.com/api/test', 'mimeType': 'application/json'}})],
        [event('Network.loadingFinished', {'requestId': 'a', 'encodedDataLength': 100})],
    ]
    service.driver.execute_cdp_cmd.return_value = {'body': json.dumps({'pageCount': 1, 'preview': [image(1)]})}
    assert service._read_818ps_network() == []
    assert service._read_818ps_network() == [{'pageCount': 1, 'preview': [image(1)]}]
    assert service._818ps_request_headers[image(1)]['Referer'] == EDITOR


def test_browser_discovery_and_missing_page_capture_use_one_navigation(monkeypatch):
    service = BrowserService()
    driver = Mock(current_url=EDITOR)
    monkeypatch.setattr(service, '_get_818ps_driver', lambda: driver)
    service.driver = driver
    def snapshot(url):
        return {'currentUrl': EDITOR, 'visibleCandidates': [dict(url=url, isLarge=True, isCentered=True,
                                                               area=600000, visibleArea=600000)]}
    snapshots = iter([snapshot(image(1)), snapshot(image(1)), snapshot(image(2)), snapshot(image(2))])
    monkeypatch.setattr(service, '_snapshot_818ps', lambda: next(snapshots))
    monkeypatch.setattr(service, '_activate_dynamic_page', lambda driver, page: {'clicked': True})
    monkeypatch.setattr('core.browser_service.time.sleep', lambda _: None)
    service._open_818ps_page(SHELL)
    result = service._capture_818ps_pages([2])
    driver.get.assert_called_once_with(SHELL)
    assert result['pageSnapshots'][0]['page'] == 2
    assert result['pageSnapshots'][0]['previewUrls'] == [image(2)]
    assert result['pageSnapshots'][0]['previewUpdated'] is True


@pytest.mark.asyncio
async def test_upic_id_alone_queries_public_data_before_browser(crawler):
    crawler._fetch_json.return_value = {'pageCount': 1, 'preview': [image(1)]}
    result = await crawler.extract_image('https://ue.818ps.com/v4/?upicId=12')
    assert crawler._fetch_json.await_count == 2
    assert result['completenessStatus'] == 'complete'
    BrowserService.open_818ps_page.assert_not_awaited()
    await crawler.close()


@pytest.mark.asyncio
async def test_duplicate_strings_in_preview_list_preserve_board_order(crawler):
    crawler._fetch_json.return_value = {'preview': [image(1), image(1)]}
    result = await crawler.extract_image(EDITOR)
    assert [page['page'] for page in result['pages']] == [1, 2]
    assert result['pageCount'] == 2
    assert result['metadata']['duplicateUrlCount'] == 1
    assert result['completenessStatus'] == 'unknown'
    await crawler.close()


@pytest.mark.asyncio
async def test_preview_array_alone_does_not_prove_document_count(crawler):
    crawler._fetch_json.return_value = {'preview': [image(1), image(2)]}
    result = await crawler.extract_image(EDITOR)
    assert result['pageCount'] == 2
    assert result['expectedPageCount'] is None
    assert result['completenessStatus'] == 'unknown'
    BrowserService.open_818ps_page.assert_awaited_once()
    await crawler.close()


@pytest.mark.asyncio
async def test_unidentified_cover_cannot_satisfy_later_known_page_count(crawler):
    cover = 'https://img.tuguaishou.com/user_preview_ue/cover.jpg'
    task = ExtractionTask(crawler, SHELL)
    await task.add([dict(page=1, imageUrl=cover, identityConfirmed=False, source='cover')])
    task.expect(1)
    assert not task.complete()
    assert task.result()['missingPages'] == [1]
    await task.add([dict(page=1, imageUrl=image(1), source='structured')])
    assert task.complete()
    assert task.result()['imageUrls'] == [image(1)]
    await crawler.close()


def test_link_cleanup_preserves_encoded_share_parameters():
    parser = URLParser()
    url = EDITOR + '&token=a%26b%2Bc'
    assert parser.parse_share_url(url)['parsed_url'] == url


def test_driver_shutdown_is_idempotent():
    service = BrowserService()
    driver = Mock()
    original_quit = driver.quit
    service._make_818ps_close_idempotent(driver)
    driver.quit()
    driver.quit()
    original_quit.assert_called_once()


def test_candidate_filter_does_not_inspect_signature_text(crawler):
    signed = 'https://img.tuguaishou.com/user_preview_ue/deadbeef.jpg?auth_key=logo-icon-ad'
    assert crawler._is_design_page_candidate(signed)
    assert signed in crawler._extract_image_urls_from_content(f'<img src="{signed}">')
    assert not crawler._is_design_page_candidate('https://img.tuguaishou.com/ips_icon/item.png')


def test_driver_download_is_cached_and_uses_explicit_request_timeouts(monkeypatch, tmp_path):
    service = BrowserService()
    patcher = SimpleNamespace(executable_path=str(tmp_path / 'unused.exe'), data_path=str(tmp_path), platform_name='win32')
    uc = SimpleNamespace(Patcher=lambda **kwargs: patcher)
    manifest = {'milestones': {'155': {'version': '155.0.1', 'downloads': {'chromedriver': [
        {'platform': 'win32', 'url': 'https://driver.example/driver.zip'}]}}}}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as package:
        package.writestr('chromedriver-win32/chromedriver.exe', b'fixture driver')
    opener = Mock(side_effect=[io.BytesIO(json.dumps(manifest).encode()), io.BytesIO(archive.getvalue())])
    monkeypatch.setattr('core.browser_service.urlopen', opener)
    path = service._prepare_818ps_driver(uc, 155)
    assert opener.call_args_list[0].kwargs['timeout'] == 6
    assert opener.call_args_list[1].kwargs['timeout'] == 5
    assert os.path.isfile(path)
    monkeypatch.setattr('core.browser_service.subprocess.run', Mock(return_value=SimpleNamespace(stdout='ChromeDriver 155.0.1')))
    assert service._prepare_818ps_driver(uc, 155) == path
    assert opener.call_count == 2


@pytest.mark.asyncio
async def test_cancellation_waits_for_driver_ownership_before_cleanup(monkeypatch):
    service = BrowserService()
    started = threading.Event()
    finish = threading.Event()
    driver = Mock()
    def open_page(url):
        started.set()
        finish.wait(timeout=2)
        service.driver = driver
        return {}
    monkeypatch.setattr(service, '_open_818ps_page', open_page)
    async def run():
        try:
            return await service.open_818ps_page(SHELL)
        finally:
            await service.close()
    operation = asyncio.create_task(run())
    await asyncio.to_thread(started.wait, 2)
    operation.cancel()
    await asyncio.sleep(0)
    assert not operation.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    driver.quit.assert_called_once()
    assert service.driver is None


@pytest.mark.asyncio
async def test_current_first_page_is_revisited_after_other_pages_update(crawler):
    crawler._fetch_json.return_value = {'pageCount': 2}
    BrowserService.open_818ps_page.return_value = {'currentUrl': EDITOR}
    BrowserService.capture_818ps_pages.side_effect = [
        {'pageSnapshots': [{'page': 2, 'previewUrls': [image(2)], 'previewUpdated': True}]},
        {'pageSnapshots': [{'page': 1, 'previewUrls': [image(1)], 'previewUpdated': True}]},
    ]
    result = await crawler.extract_image(EDITOR)
    assert BrowserService.capture_818ps_pages.call_args_list[0].args[0] == [1, 2]
    assert BrowserService.capture_818ps_pages.call_args_list[1].args[0] == [1]
    assert result['completenessStatus'] == 'complete'
    assert result['imageUrls'] == [image(1), image(2)]
    BrowserService.open_818ps_page.assert_awaited_once()
    await crawler.close()
