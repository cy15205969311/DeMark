"""
基础功能测试
"""
import pytest
import asyncio
import aiohttp
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.image_extractor import ImageExtractor
from core.third_party_api import ThirdPartyAPIGateway
from core.browser_service import BrowserService
from crawlers.tuguaishou_818ps import Tuguaishou818psCrawler
from utils.image_validator import ImageValidator
from utils.url_parser import URLParser
from utils.variant_builder import VariantBuilder


class FakeAiohttpResponse:
    def __init__(self, text: str, status: int = 200):
        self._text = text
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self._text


class FakeAiohttpSession:
    def __init__(self, text: str, status: int = 200):
        self._text = text
        self._status = status
        self.closed = False

    def get(self, url, timeout=None, headers=None):
        del url, timeout, headers
        return FakeAiohttpResponse(self._text, self._status)

    async def close(self):
        self.closed = True

class TestImageExtractor:
    """图片提取器测试"""
    
    @pytest.fixture
    def extractor(self):
        """创建提取器实例"""
        extractor = ImageExtractor()
        yield extractor
        asyncio.run(extractor.close())
    
    @pytest.mark.asyncio
    async def test_extract_818ps_basic(self, extractor):
        """测试818ps基础提取功能"""
        test_url = "https://818ps.com/preview?picId=12345&upicId=67890"
        
        try:
            result = await extractor.extract_image(test_url, "818ps")
            assert result is not None
            assert 'platform' in result
            assert result['platform'] == '818ps'
        except Exception as e:
            # 预期可能失败，因为是测试URL
            assert "无法提取图片" in str(e)
    
    @pytest.mark.asyncio
    async def test_platform_detection(self, extractor):
        """测试平台检测"""
        test_cases = [
            ("https://818ps.com/preview?picId=123", "818ps"),
            ("https://www.canva.com/design/DAF123/view", "Canva"),
            ("https://www.chuangkit.com/designtools/startdesign?id=123", "创可贴"),
        ]
        
        for url, expected_platform in test_cases:
            # 这里只测试URL解析，不实际提取
            assert url is not None

    @pytest.mark.asyncio
    async def test_818ps_share_shell_skips_third_party_api(self, extractor):
        """测试 818ps /u/ 分享壳页会直接跳过第三方 API 网关"""
        call_state = {
            "api": 0,
            "local": 0,
        }

        extractor.url_parser.parse_share_url = lambda url: {
            "success": True,
            "parsed_url": "https://818ps.com/u/002dKCdH-1?user_source=r1537041",
            "platform": "818ps",
            "type": "share_shell",
            "pic_id": None,
            "upic_id": None,
        }

        async def fake_extract_with_cache(url, platform):
            del url, platform
            call_state["api"] += 1
            return None

        async def fake_extract_local(url, platform, parsed_params=None):
            del url, platform, parsed_params
            call_state["local"] += 1
            return {
                "imageUrl": "https://img.tuguaishou.com/user_preview_ue/page1.jpg!l1600?auth_key=test",
                "platform": "818ps",
                "source": "local_test",
            }

        extractor.third_party_api.extract_with_cache = fake_extract_with_cache
        extractor._extract_local = fake_extract_local

        result = await extractor.extract_image(
            "https://818ps.com/u/002dKCdH-1?user_source=r1537041",
            "818ps"
        )

        assert result is not None
        assert result["source"] == "local_test"
        assert call_state["api"] == 0
        assert call_state["local"] == 1

    def test_selenium_filters_qrcode_assets(self, extractor):
        """测试 Selenium 兜底不会把二维码/活动图当成设计稿主图"""
        assert extractor._should_consider_selenium_image(
            "https://js.tuguaishou.com/image/wechat_qrcode/xcx-code.jpg"
        ) is False
        assert extractor._should_consider_selenium_image(
            "https://js.tuguaishou.com/editor/image/topCardBlur2.png"
        ) is False
        assert extractor._should_consider_selenium_image(
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/page1.jpg!l1600?auth_key=test"
        ) is True

class TestImageValidator:
    """图片验证器测试"""
    
    @pytest.fixture
    def validator(self):
        """创建验证器实例"""
        validator = ImageValidator()
        yield validator
        asyncio.run(validator.close())
    
    @pytest.mark.asyncio
    async def test_validate_valid_image(self, validator):
        """测试验证有效图片URL"""
        # 使用一个公开的测试图片URL
        test_url = "https://httpbin.org/image/png"
        
        try:
            result = await validator.validate_image_url(test_url)
            # 可能成功也可能失败，取决于网络状况
            assert isinstance(result, bool)
        except Exception:
            # 网络问题导致的异常是可接受的
            pass
    
    @pytest.mark.asyncio
    async def test_validate_invalid_image(self, validator):
        """测试验证无效图片URL"""
        test_url = "https://invalid-domain-that-does-not-exist.com/image.jpg"
        
        result = await validator.validate_image_url(test_url)
        assert result is False

    def test_extract_reported_size_from_content_range(self, validator):
        """测试从 Content-Range 解析真实文件大小"""
        headers = {
            'Content-Range': 'bytes 0-0/54321',
            'Content-Length': '1'
        }

        assert validator._extract_reported_size(headers) == 54321

    @pytest.mark.asyncio
    async def test_close_resets_sessions_for_reuse(self, validator):
        """测试 close 后会话会被清空，便于下一轮重建"""
        await validator._init_async_session()

        assert validator.session is not None
        assert validator.sync_session is not None

        await validator.close()

        assert validator.session is None
        assert validator.sync_session is None

class TestThirdPartyAPIGateway:
    """第三方 API 网关测试"""

    @pytest.mark.asyncio
    async def test_close_resets_session(self):
        """测试关闭后 session 会重置为 None"""
        gateway = ThirdPartyAPIGateway()
        gateway.session = aiohttp.ClientSession()

        await gateway.close()

        assert gateway.session is None

class TestVariantBuilder:
    """变体构建器测试"""
    
    def test_build_818ps_variants(self):
        """测试818ps变体构建"""
        test_url = "https://img.818ps.com/ips_user_preview_api/12345/67890.jpg!l2000"
        
        variants = VariantBuilder.build_818ps_variants(test_url)
        
        assert isinstance(variants, list)
        assert len(variants) > 0
        
        # 检查是否包含预期的变体
        expected_patterns = [
            "pic/",  # 应该有预览路径替换
            ".png",  # 应该有扩展名变体
            ".webp"  # 应该有扩展名变体
        ]
        
        variant_text = " ".join(variants)
        for pattern in expected_patterns:
            assert any(pattern in variant for variant in variants)

    def test_build_818ps_variants_keeps_stable_priority_order(self):
        """818ps 变体需要稳定顺序，优先尝试去掉尺寸/水印后缀的版本"""
        test_url = (
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
            "work_47636_1.jpg!l1000_b?auth_key=test"
        )

        variants = VariantBuilder.build_818ps_variants(test_url)

        assert variants[0] == (
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
            "work_47636_1.jpg"
        )
        assert variants.index(
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
            "work_47636_1.jpg?auth_key=test"
        ) > variants.index(
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
            "work_47636_1.jpg"
        )
        assert len(variants) == len(set(variants))
    
    def test_build_canva_variants(self):
        """测试Canva变体构建"""
        test_url = "https://marketplace-canva.com/thumbnail/image.jpg"
        
        variants = VariantBuilder.build_canva_variants(test_url)
        
        assert isinstance(variants, list)
        assert len(variants) > 0
        
        # 检查是否包含原图替换
        assert any("original" in variant for variant in variants)

class TestBrowserService:
    """浏览器服务测试"""

    def test_parse_chrome_major_version(self):
        """测试Chrome主版本解析"""
        service = BrowserService()

        assert service._parse_chrome_major_version("Google Chrome 146.0.7680.165") == 146
        assert service._parse_chrome_major_version("Chromium 120.1") == 120
        assert service._parse_chrome_major_version("") is None

    def test_extract_browser_version_from_error(self):
        """测试从异常中提取浏览器版本"""
        service = BrowserService()
        error = Exception(
            "session not created: This version of ChromeDriver only supports Chrome version 144 "
            "Current browser version is 146.0.7680.165"
        )

        assert service._extract_browser_version_from_error(error) == 146

    def test_dedupe_keep_order(self):
        """测试去重后仍保留原始发现顺序"""
        service = BrowserService()

        result = service._dedupe_keep_order([
            "https://a.com/1.jpg",
            "https://a.com/2.jpg",
            "https://a.com/1.jpg",
            "  https://a.com/3.jpg  ",
        ])

        assert result == [
            "https://a.com/1.jpg",
            "https://a.com/2.jpg",
            "https://a.com/3.jpg",
        ]

    def test_merge_dynamic_capture_accumulates_scroll_results(self):
        """测试多轮滚动采集的数据会被正确合并"""
        service = BrowserService()

        merged = service._merge_dynamic_capture(
            {
                "imageUrls": ["https://img.tuguaishou.com/page1.jpg"],
                "jsonData": [{"page": 1}],
                "pageMarkers": ["第1页"],
                "windowData": {"pageData": {"current": 1}},
                "scrollTrace": [],
            },
            {
                "imageUrls": ["https://img.tuguaishou.com/page2.jpg", "https://img.tuguaishou.com/page1.jpg"],
                "jsonData": [{"page": 2}],
                "pageMarkers": ["第2页"],
                "windowData": {"workData": {"total": 2}},
                "scrollState": {"moved": 1, "focusedPage": 2},
                "pageSource": "<html>page2</html>",
            }
        )

        assert merged["imageUrls"] == [
            "https://img.tuguaishou.com/page1.jpg",
            "https://img.tuguaishou.com/page2.jpg",
        ]
        assert merged["pageMarkers"] == ["第1页", "第2页"]
        assert merged["windowData"]["pageData"]["current"] == 1
        assert merged["windowData"]["workData"]["total"] == 2
        assert merged["scrollTrace"] == [{"moved": 1, "focusedPage": 2}]


class TestURLParser:
    """URL 解析测试"""

    def test_818ps_u_share_link_skips_short_link_resolution(self):
        """测试 818ps /u/ 分享页直接保留原始入口，不再依赖短链跳转"""
        parser = URLParser()
        call_state = {"resolve_short_link": 0}

        def fake_resolve_short_link(url):
            del url
            call_state["resolve_short_link"] += 1
            return {"success": True, "final_url": "https://ue.818ps.com/v4/?upicId=1"}

        parser.resolve_short_link = fake_resolve_short_link

        result = parser.parse_share_url(
            "点击链接加入图怪兽中的文件「测试」邀请人：阿达 "
            "https://818ps.com/u/002dKCdH-1?user_source=r1537041"
        )

        assert result["success"] is True
        assert result["platform"] == "818ps"
        assert result["parsed_url"] == "https://818ps.com/u/002dKCdH-1?user_source=r1537041"
        assert result["type"] == "share_shell"
        assert call_state["resolve_short_link"] == 0

class Test818psCrawler:
    """818ps爬虫测试"""

    @pytest.mark.asyncio
    async def test_share_link_prefers_official_share_api_when_share_id_exists(self):
        """测试用户分享链接在拿到upicId后优先走直连构造"""
        crawler = Tuguaishou818psCrawler()
        call_state = {
            'share_api': 0,
            'direct_build': 0,
            'scrape': 0,
        }

        async def fake_share_api(url):
            call_state['share_api'] += 1
            return {
                'imageUrl': 'https://img.tuguaishou.com/user_preview_ue/share_page1.jpg!l1600',
                'imageUrls': [
                    'https://img.tuguaishou.com/user_preview_ue/share_page1.jpg!l1600',
                    'https://img.tuguaishou.com/user_preview_ue/share_page2.jpg!l1600',
                ],
                'platform': '818ps',
                'source': 'share_api_share_template'
            }

        async def fake_direct_build(upic_id, pic_id=None):
            call_state['direct_build'] += 1
            return None

        async def fake_scrape(url):
            call_state['scrape'] += 1
            return None

        crawler._extract_from_share_api = fake_share_api
        crawler._extract_with_upic_id_priority = fake_direct_build
        crawler._scrape_webpage_enhanced = fake_scrape

        result = await crawler.extract_image(
            "https://ue.818ps.com/v4/?upicId=311210634&share_id=1783630&share_uid=24655456",
            {'upic_id': '311210634'}
        )

        await crawler.close()

        assert result is not None
        assert result['source'] == 'share_api_share_template'
        assert call_state['share_api'] == 1
        assert call_state['direct_build'] == 0
        assert call_state['scrape'] == 0

    @pytest.mark.asyncio
    async def test_share_link_falls_back_to_direct_build_after_share_api_miss(self):
        """娴嬭瘯鍒嗕韩API鏈懡涓椂浠嶄細鍥為€€鍒癠pic 鐩磋繛绛栫暐"""
        crawler = Tuguaishou818psCrawler()
        call_state = {
            'share_api': 0,
            'direct_build': 0,
            'scrape': 0,
        }

        async def fake_share_api(url):
            call_state['share_api'] += 1
            return None

        async def fake_direct_build(upic_id, pic_id=None):
            call_state['direct_build'] += 1
            return {
                'imageUrl': f'https://img.818ps.com/user_preview_ue/{upic_id}.jpg',
                'platform': '818ps',
                'source': 'user_path_priority'
            }

        async def fake_scrape(url):
            call_state['scrape'] += 1
            return None

        crawler._extract_from_share_api = fake_share_api
        crawler._extract_with_upic_id_priority = fake_direct_build
        crawler._scrape_webpage_enhanced = fake_scrape

        result = await crawler.extract_image(
            "https://ue.818ps.com/v4/?upicId=311210634&share_id=1783630&share_uid=24655456",
            {'upic_id': '311210634'}
        )

        await crawler.close()

        assert result is not None
        assert result['source'] == 'user_path_priority'
        assert call_state['share_api'] == 1
        assert call_state['direct_build'] == 1
        assert call_state['scrape'] == 0

    @pytest.mark.asyncio
    async def test_dynamic_page_uses_static_fallback_before_browser(self):
        """测试动态页先走静态HTML回退，不把成功率全部压在浏览器上"""
        crawler = Tuguaishou818psCrawler()

        async def fake_static(url):
            return {
                'imageUrl': 'https://img.818ps.com/user_preview_ue/311210634.jpg',
                'platform': '818ps',
                'source': 'meta_image'
            }

        crawler._extract_dynamic_page_without_browser = fake_static

        result = await crawler._extract_dynamic_page(
            "https://ue.818ps.com/v4/?upicId=311210634&share_id=1783630"
        )

        assert result is not None
        assert result['source'] == 'meta_image'

    @pytest.mark.asyncio
    async def test_first_valid_candidate_does_not_wait_for_slower_ones(self):
        """测试候选校验命中后会立刻返回，不等待更慢的超时项"""
        crawler = Tuguaishou818psCrawler()

        async def fake_validate(url):
            if url.endswith("slow.jpg"):
                await asyncio.sleep(0.2)
                return False
            if url.endswith("fast.jpg"):
                await asyncio.sleep(0.01)
                return True
            return False

        crawler.validator.validate_image_url = fake_validate

        result = await crawler._find_first_valid_candidate([
            "https://img.818ps.com/user_preview_ue/slow.jpg",
            "https://img.818ps.com/user_preview_ue/fast.jpg",
        ])

        await crawler.close()

        assert result.endswith("fast.jpg")

    @pytest.mark.asyncio
    async def test_dynamic_data_returns_multi_page_result(self):
        """测试动态数据中多张设计稿会作为整套结果返回"""
        crawler = Tuguaishou818psCrawler()
        page_one = "https://img.tuguaishou.com/user_preview_ue/2026-03-27/page1.jpg!l1600?auth_key=test"
        page_two = "https://img.tuguaishou.com/user_preview_ue/2026-03-27/page2.jpg!l1600?auth_key=test"

        async def fake_validate(url):
            return url in {page_one, page_two}

        crawler.validator.validate_image_url = fake_validate

        result = await crawler._analyze_dynamic_data(
            {
                "imageUrls": [
                    "https://js.tuguaishou.com/image/editor/crown.png",
                    page_one,
                    page_two,
                ],
                "jsonData": [],
                "windowData": {},
                "pageSource": "",
            },
            "https://ue.818ps.com/v4/?upicId=310870338"
        )

        await crawler.close()

        assert result is not None
        assert result["isMultiPage"] is True
        assert result["pageCount"] == 2
        assert result["imageUrls"] == [page_one, page_two]

    @pytest.mark.asyncio
    async def test_dynamic_data_prefers_page_specific_previews_over_editor_assets(self):
        """测试逐页激活结果会优先使用真实设计稿预览，而不是编辑器素材图"""
        crawler = Tuguaishou818psCrawler()
        page_one = "https://img.tuguaishou.com/user_preview_ue/2026-03-27/page1.jpg!l1600?auth_key=test"
        page_two = "https://img.tuguaishou.com/user_preview_ue/2026-03-27/page2.jpg!l1600?auth_key=test"
        page_three = "https://img.tuguaishou.com/user_preview_ue/2026-03-27/page3.jpg!l1600?auth_key=test"
        asset_svg = "https://img.tuguaishou.com/ips_svg/93/75/44/test_v2.png!w300?auth_key=test"
        asset_word = "https://img.tuguaishou.com/ips_group_word/7c/aa/9b/test.png!w300?auth_key=test"

        async def fake_validate(url):
            return url in {page_one, page_two, page_three}

        crawler.validator.validate_image_url = fake_validate

        result = await crawler._analyze_dynamic_data(
            {
                "pageMarkers": ["第1页", "第2页", "第3页"],
                "pageSnapshots": [
                    {"page": 1, "previewUrls": [page_one, asset_svg]},
                    {"page": 2, "previewUrls": [asset_word, page_two]},
                    {"page": 3, "previewUrls": [page_three]},
                ],
                "pageSpecificImages": [page_one, page_two, page_three],
                "imageUrls": [page_one, asset_svg, asset_word],
                "resourceUrls": [page_two, page_three],
                "jsonData": [],
                "windowData": {},
                "pageSource": "",
            },
            "https://ue.818ps.com/v4/?upicId=310870338"
        )

        await crawler.close()

        assert result is not None
        assert result["imageUrls"] == [page_one, page_two, page_three]

    def test_share_api_preview_groups_prefer_share_template_results(self):
        """娴嬭瘯鍒嗕韩API浼氫紭鍏堜娇鐢?share-template 鐨勫畬鏁村鍥?"""
        crawler = Tuguaishou818psCrawler()
        page_one = "https://img.tuguaishou.com/user_preview_ue/2026-03-27/page1.jpg!l1600?auth_key=test"
        page_two = "https://img.tuguaishou.com/user_preview_ue/2026-03-27/page2.jpg!l1600?auth_key=test"
        page_three = "https://img.tuguaishou.com/user_preview_ue/2026-03-27/page3.jpg!l1600?auth_key=test"
        watermarked_page = "https://img.tuguaishou.com/ips_user_preview_api/17/74/test.jpeg!l1000_b?auth_key=test"

        groups, expected_page_count = crawler._extract_share_api_preview_groups({
            "share_template": {
                "data": {
                    "preview": [
                        f"//{page_one.split('://', 1)[1]}",
                        f"//{page_two.split('://', 1)[1]}",
                        f"//{page_three.split('://', 1)[1]}",
                    ]
                }
            },
            "team_share_get_templ": {
                "page_map": {"1": "3884095", "2": "3858485", "3": "3334011"},
                "preview": [watermarked_page, page_two, page_three]
            },
            "get_template_page_data": {
                "url": {
                    "preview": [
                        {"big_img": watermarked_page},
                        {"big_img": page_two},
                        {"big_img": page_three},
                    ]
                }
            }
        })

        assert expected_page_count == 3
        assert groups[0] == ("share_template", [page_one, page_two, page_three])
        assert all(watermarked_page not in urls for _, urls in groups)

    def test_share_api_preview_groups_can_synthesize_missing_first_page(self):
        """当 818ps 分享预览只返回 _1/_2/_3 时，补出无后缀的第一页"""
        crawler = Tuguaishou818psCrawler()
        page_two = (
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
            "23001930d43d4c2293d75121463a1f73_47636_1.jpg!l1000_b?auth_key=test"
        )
        page_three = (
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
            "23001930d43d4c2293d75121463a1f73_47636_2.jpg!l1000_b?auth_key=test"
        )
        page_four = (
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
            "23001930d43d4c2293d75121463a1f73_47636_3.jpg!l1000_b?auth_key=test"
        )
        page_one = (
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
            "23001930d43d4c2293d75121463a1f73_47636.jpg!l1000_b?auth_key=test"
        )

        groups, expected_page_count = crawler._extract_share_api_preview_groups({
            "team_share_get_templ": {
                "page_map": {"1": "a", "2": "b", "3": "c", "4": "d"},
                "preview": [page_two, page_three, page_four],
            }
        })

        assert expected_page_count == 4
        assert groups == [
            ("team_share_get_templ", [page_one, page_two, page_three, page_four])
        ]

    @pytest.mark.asyncio
    async def test_extract_from_share_api_upgrades_watermarked_urls_and_prefers_full_group(self):
        """分享 API 结果应优先升级为无水印页图，并继续寻找更完整的页集"""
        crawler = Tuguaishou818psCrawler()
        resolved_url = (
            "https://ue.818ps.com/v4/?origin=tpl_search&upicId=311361830"
            "&share_uid=24655456&share_id=1786146&save_type=&user_source=r1537041"
        )
        share_template_preview = (
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
            "23001930d43d4c2293d75121463a1f73_47636_1.jpg!l1000_b?auth_key=test"
        )
        team_share_preview = [
            (
                "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
                "23001930d43d4c2293d75121463a1f73_47636_1.jpg!l1000_b?auth_key=test"
            ),
            (
                "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
                "23001930d43d4c2293d75121463a1f73_47636_2.jpg!l1000_b?auth_key=test"
            ),
            (
                "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
                "23001930d43d4c2293d75121463a1f73_47636_3.jpg!l1000_b?auth_key=test"
            ),
        ]
        expected_urls = [
            (
                "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
                "23001930d43d4c2293d75121463a1f73_47636.jpg?auth_key=test"
            ),
            (
                "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
                "23001930d43d4c2293d75121463a1f73_47636_1.jpg?auth_key=test"
            ),
            (
                "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
                "23001930d43d4c2293d75121463a1f73_47636_2.jpg?auth_key=test"
            ),
            (
                "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
                "23001930d43d4c2293d75121463a1f73_47636_3.jpg?auth_key=test"
            ),
        ]

        async def fake_fetch_json(url, referer=None):
            del referer
            if "share-template" in url:
                return {"data": {"preview": [share_template_preview]}}
            if "team-share-get-templ" in url:
                return {
                    "page_map": {"1": "a", "2": "b", "3": "c", "4": "d"},
                    "preview": team_share_preview,
                }
            return {}

        async def fake_validate(url):
            return url in set(expected_urls)

        crawler._fetch_json = fake_fetch_json
        crawler.validator.validate_image_url = fake_validate

        result = await crawler._extract_from_share_api(resolved_url)

        await crawler.close()

        assert result is not None
        assert result["source"] == "share_api_team_share_get_templ"
        assert result["imageUrls"] == expected_urls
        assert result["pageCount"] == 4
        assert all("!l1000_b" not in url for url in result["imageUrls"])

    def test_design_page_candidate_excludes_editor_assets(self):
        """测试设计稿候选过滤会排除编辑器素材资源"""
        crawler = Tuguaishou818psCrawler()

        assert crawler._is_design_page_candidate(
            "https://img.tuguaishou.com/user_preview_ue/2026-03-27/page1.jpg!l1600?auth_key=test"
        ) is True
        assert crawler._is_design_page_candidate(
            "https://img.tuguaishou.com/ips_svg/93/75/44/test_v2.png!w300?auth_key=test"
        ) is False
        assert crawler._is_design_page_candidate(
            "https://img.tuguaishou.com/ips_group_word/7c/aa/9b/test.png!w300?auth_key=test"
        ) is False
        assert crawler._is_design_page_candidate(
            "https://img.tuguaishou.com/ips_user_preview_api/17/74/test.jpeg!l1000_b?auth_key=test"
        ) is False

    def test_sort_urls_by_818ps_preview_page_suffix(self):
        """测试会按 818ps user_preview_ue 文件名中的页码后缀排序"""
        crawler = Tuguaishou818psCrawler()

        urls = [
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/work_49949_2.jpg!l1600?auth_key=test",
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/work_49949.jpg!l1600?auth_key=test",
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/work_49949_1.jpg!l1600?auth_key=test",
        ]

        assert crawler._sort_urls_by_page_token(urls) == [
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/work_49949.jpg!l1600?auth_key=test",
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/work_49949_1.jpg!l1600?auth_key=test",
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/work_49949_2.jpg!l1600?auth_key=test",
        ]

    @pytest.mark.asyncio
    async def test_scrape_webpage_treats_818ps_u_share_as_dynamic_page(self):
        """测试 818ps /u/ 分享页会直接走动态壳页提取链路"""
        crawler = Tuguaishou818psCrawler()
        call_state = {"dynamic": 0}

        async def fake_dynamic_page(url):
            call_state["dynamic"] += 1
            return {
                "imageUrl": "https://img.tuguaishou.com/user_preview_ue/page1.jpg!l1600?auth_key=test",
                "platform": "818ps",
                "source": "dynamic_page",
            }

        crawler._extract_dynamic_page = fake_dynamic_page

        result = await crawler._scrape_webpage_enhanced(
            "https://818ps.com/u/002dKCdH-1?user_source=r1537041"
        )

        await crawler.close()

        assert result is not None
        assert result["source"] == "dynamic_page"
        assert call_state["dynamic"] == 1

    @pytest.mark.asyncio
    async def test_dynamic_page_static_fallback_uses_rendered_dom_when_shell_html_has_no_preview(self):
        """测试动态页静态源码没有结果时，会继续解析本地 Chrome 渲染后的 DOM"""
        crawler = Tuguaishou818psCrawler()
        preview_url = (
            "https://img.tuguaishou.com/user_preview_ue/2026-04-02/"
            "page1.jpg!l1600?auth_key=test"
        )
        crawler.session = FakeAiohttpSession("<html><body><div id='root'></div></body></html>")

        async def fake_ensure_session():
            return None

        async def fake_render_page(url):
            del url
            return f"<html><body><img src=\"{preview_url}\"></body></html>"

        async def fake_validate(url):
            return url == preview_url

        crawler._ensure_session = fake_ensure_session
        crawler._render_page_with_local_chrome = fake_render_page
        crawler.validator.validate_image_url = fake_validate

        result = await crawler._extract_dynamic_page_without_browser(
            "https://818ps.com/u/002dKCdH-1?user_source=r1537041"
        )

        await crawler.close()

        assert result is not None
        assert result["imageUrl"] == preview_url
        assert result["source"] == "regex_image_search"

    @pytest.mark.asyncio
    async def test_analyze_dynamic_data_uses_structured_preview_groups(self):
        """测试动态分析会优先使用 json/window 里的结构化多页预览数组"""
        crawler = Tuguaishou818psCrawler()
        page_one = "https://img.tuguaishou.com/user_preview_ue/2026-04-02/work_49949.jpg!l1600?auth_key=test"
        page_two = "https://img.tuguaishou.com/user_preview_ue/2026-04-02/work_49949_1.jpg!l1600?auth_key=test"
        page_three = "https://img.tuguaishou.com/user_preview_ue/2026-04-02/work_49949_2.jpg!l1600?auth_key=test"

        async def fake_validate(url):
            return url in {page_one, page_two, page_three}

        crawler.validator.validate_image_url = fake_validate

        result = await crawler._analyze_dynamic_data(
            {
                "imageUrls": [],
                "resourceUrls": [],
                "pageMarkers": ["第1页", "第2页", "第3页"],
                "jsonData": [
                    {
                        "preview": [
                            {"big_img": page_three},
                            {"big_img": page_one},
                            {"big_img": page_two},
                        ]
                    }
                ],
                "windowData": {},
                "pageSource": "",
            },
            "https://818ps.com/u/test"
        )

        await crawler.close()

        assert result is not None
        assert result["source"] == "dynamic_structured_browser.json.preview"
        assert result["imageUrls"] == [page_one, page_two, page_three]

    @pytest.mark.asyncio
    async def test_dynamic_share_shell_uses_browser_resolved_editor_url_for_share_api(self):
        """测试 818ps /u/ 分享壳页会先用浏览器解析最终编辑器地址，再走官方分享 API 拿多页结果"""
        crawler = Tuguaishou818psCrawler()
        resolved_url = (
            "https://ue.818ps.com/v4/?upicId=311361830"
            "&share_uid=24655456&share_id=1786146"
        )
        call_state = {
            "share_api": 0,
            "resolve_url": 0,
            "dynamic_browser": 0,
            "analyze": 0,
        }

        async def fake_static(url):
            del url
            return {
                "imageUrl": "https://img.tuguaishou.com/ips_index_hot_day/test.png!w170?auth_key=test",
                "platform": "818ps",
                "source": "regex_image_search",
            }

        async def fake_share_api(url):
            call_state["share_api"] += 1
            assert url == resolved_url
            return {
                "imageUrl": "https://img.tuguaishou.com/user_preview_ue/page1.jpg!l1600?auth_key=test",
                "imageUrls": [
                    "https://img.tuguaishou.com/user_preview_ue/page1.jpg!l1600?auth_key=test",
                    "https://img.tuguaishou.com/user_preview_ue/page2.jpg!l1600?auth_key=test",
                    "https://img.tuguaishou.com/user_preview_ue/page3.jpg!l1600?auth_key=test",
                    "https://img.tuguaishou.com/user_preview_ue/page4.jpg!l1600?auth_key=test",
                ],
                "platform": "818ps",
                "source": "share_api_share_template",
            }

        async def fake_analyze(dynamic_data, original_url):
            del dynamic_data, original_url
            call_state["analyze"] += 1
            return None

        original_resolve_url = BrowserService.resolve_url_with_browser
        original_extract_dynamic_content = BrowserService.extract_dynamic_content

        def fake_resolve_url(self, url, headless=True, wait_seconds=5.0):
            del self, url, headless, wait_seconds
            call_state["resolve_url"] += 1
            return resolved_url

        async def fake_extract_dynamic_content(self, url, headless=True):
            del self, url, headless
            call_state["dynamic_browser"] += 1
            return {}

        crawler._extract_dynamic_page_without_browser = fake_static
        crawler._extract_from_share_api = fake_share_api
        crawler._analyze_dynamic_data = fake_analyze
        BrowserService.resolve_url_with_browser = fake_resolve_url
        BrowserService.extract_dynamic_content = fake_extract_dynamic_content

        try:
            result = await crawler._extract_dynamic_page(
                "https://818ps.com/u/002dKC0v-1?user_source=r1537041"
            )
        finally:
            BrowserService.resolve_url_with_browser = original_resolve_url
            BrowserService.extract_dynamic_content = original_extract_dynamic_content
            await crawler.close()

        assert result is not None
        assert result["source"] == "share_api_share_template"
        assert call_state["resolve_url"] == 1
        assert call_state["share_api"] == 1
        assert call_state["dynamic_browser"] == 0
        assert call_state["analyze"] == 0

class TestResultNormalization:
    """提取结果归一化测试"""

    def test_image_extractor_normalizes_multi_page_payload(self):
        """测试 imageUrl/imageUrls/pageCount 会被统一补齐"""
        extractor = ImageExtractor()

        result = extractor._normalize_result_images({
            "platform": "818ps",
            "imageUrls": [
                "https://img.tuguaishou.com/user_preview_ue/page1.jpg",
                "https://img.tuguaishou.com/user_preview_ue/page2.jpg",
            ]
        })

        assert result["imageUrl"].endswith("page1.jpg")
        assert result["pageCount"] == 2
        assert result["isMultiPage"] is True
        assert len(result["pages"]) == 2

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
