import pytest

from crawlers.gaoding_crawler import GaodingCrawler
from utils.image_validator import ImageValidator
from utils.url_parser import URLParser


class TestGaodingCrawler:
    def test_extract_preview_bundle_from_html_uses_preview_and_extends_previews(self):
        crawler = GaodingCrawler()
        html_content = """
        <script>
        {&quot;preview_info&quot;:{&quot;url&quot;:&quot;https://gdesign-dam-hw.dancf.com/work/preview/page-1.jpg?auth_key=a&quot;},
         &quot;source_preview_info&quot;:{&quot;url&quot;:null},
         &quot;extends_previews&quot;:[
            {&quot;url&quot;:&quot;https://gdesign-dam-hw.dancf.com/work/preview/page-2.jpg?auth_key=b&quot;},
            {&quot;url&quot;:&quot;https://gdesign-dam-hw.dancf.com/work/preview/page-3.jpg?auth_key=c&quot;}
         ]}
        </script>
        """

        bundle = crawler._extract_preview_bundle_from_html(html_content)

        assert [item[0] for item in bundle] == [
            "https://gdesign-dam-hw.dancf.com/work/preview/page-1.jpg?auth_key=a",
            "https://gdesign-dam-hw.dancf.com/work/preview/page-2.jpg?auth_key=b",
            "https://gdesign-dam-hw.dancf.com/work/preview/page-3.jpg?auth_key=c",
        ]

    def test_extract_preview_bundle_from_html_prefers_source_preview_info(self):
        crawler = GaodingCrawler()
        html_content = """
        <script>
        {&quot;preview_info&quot;:{&quot;url&quot;:&quot;https://gdesign-dam-hw.dancf.com/work/preview/page-1-watermark.jpg?auth_key=a&quot;},
         &quot;source_preview_info&quot;:{&quot;url&quot;:&quot;https://gdesign-dam-hw.dancf.com/work/export/page-1.jpg?auth_key=z&quot;},
         &quot;extends_previews&quot;:[
            {&quot;url&quot;:&quot;https://gdesign-dam-hw.dancf.com/work/preview/page-2.jpg?auth_key=b&quot;}
         ]}
        </script>
        """

        bundle = crawler._extract_preview_bundle_from_html(html_content)

        assert [item[0] for item in bundle] == [
            "https://gdesign-dam-hw.dancf.com/work/export/page-1.jpg?auth_key=z",
            "https://gdesign-dam-hw.dancf.com/work/preview/page-2.jpg?auth_key=b",
        ]

    def test_candidate_filter_accepts_market_preview_and_blocks_app_assets(self):
        crawler = GaodingCrawler()

        assert crawler._is_gaoding_design_candidate(
            "https://gaoding-market.dancf.com/market-operations/market/side/abc/1769158051967.png"
        ) is True
        assert crawler._is_gaoding_design_candidate(
            "https://gaoding-market-fat.dancf.com/market-operations/market/side/def/1757242458411.png"
        ) is True
        assert crawler._is_gaoding_design_candidate(
            "https://cdn.dancf.com/apps/gaoding/assets/logo.png"
        ) is False
        assert crawler._is_gaoding_design_candidate(
            "https://cdn.dancf.com/apps/gaoding/assets/index.css"
        ) is False

    def test_normalize_candidate_url_trims_embedded_json_suffix(self):
        crawler = GaodingCrawler()
        raw_value = (
            'https://gdesign-dam-hw.dancf.com/36032268203706456/'
            'uuid-0406bd6e-049f-4b51-bc10-5a8471854206-hash-516349685/'
            'e9191578dff248dbb6b398d05baf32ba.jpg'
            '?auth_key=1774944000-3339ad25e78f4f529db84976d9cbfcfb-0-76f8adc24965e286903d500127cd7aa7'
            '","width":1242,"height":1656,"ext":"{\\"ratio\\":4}"'
        )

        normalized = crawler._normalize_candidate_url(raw_value)

        assert normalized == (
            "https://gdesign-dam-hw.dancf.com/36032268203706456/"
            "uuid-0406bd6e-049f-4b51-bc10-5a8471854206-hash-516349685/"
            "e9191578dff248dbb6b398d05baf32ba.jpg"
            "?auth_key=1774944000-3339ad25e78f4f529db84976d9cbfcfb-0-76f8adc24965e286903d500127cd7aa7"
        )

    def test_normalize_candidate_url_keeps_oss_query_intact_before_stripping_it(self):
        crawler = GaodingCrawler()
        raw_value = (
            'https://gdesign-dam-hw.dancf.com/36032286163588249/'
            'uuid-a2ebd3e9-b39c-473f-9f20-3c61d606e083-hash-3222547394/'
            '936145473b8b4655b4be6203edc833b6.jpg'
            '?auth_key=1774958400-ae586116a7c24476a752368e353798af-0-e706ddcd48888604e5cd91ee8d3cf915'
            '&x-oss-process=image/resize,m_fill,w_1200'
            '","width":1242,"height":1656'
        )

        normalized = crawler._normalize_candidate_url(raw_value)

        assert normalized == (
            "https://gdesign-dam-hw.dancf.com/36032286163588249/"
            "uuid-a2ebd3e9-b39c-473f-9f20-3c61d606e083-hash-3222547394/"
            "936145473b8b4655b4be6203edc833b6.jpg"
            "?auth_key=1774958400-ae586116a7c24476a752368e353798af-0-e706ddcd48888604e5cd91ee8d3cf915"
        )

    def test_normalize_candidate_url_strips_invalid_bare_oss_resize_param(self):
        crawler = GaodingCrawler()
        raw_value = (
            "https://gdesign-dam-hw.dancf.com/work/export/final-artboard.jpg"
            "?auth_key=test123&x-oss-process=image/resize"
        )

        normalized = crawler._normalize_candidate_url(raw_value)

        assert normalized == (
            "https://gdesign-dam-hw.dancf.com/work/export/final-artboard.jpg"
            "?auth_key=test123"
        )

    def test_select_best_multi_page_group_prefers_page_like_json_path(self):
        crawler = GaodingCrawler()
        page_one = "https://gaoding-market.dancf.com/work/pages/page1.png"
        page_two = "https://gaoding-market.dancf.com/work/pages/page2.png"
        banner = "https://gaoding-market.dancf.com/market-operations/market/side/banner.png"

        entries = crawler._extract_candidates_from_data(
            {
                "work": {
                    "pages": [
                        {"image": page_one},
                        {"image": page_two},
                    ],
                    "banner": {
                        "image": banner,
                    },
                }
            },
            "root",
        )

        best_group = crawler._select_best_multi_page_group(entries)

        assert [item[0] for item in best_group] == [page_one, page_two]

    @pytest.mark.asyncio
    async def test_pick_best_single_candidate_prefers_meta_image(self):
        crawler = GaodingCrawler()
        og_image = "https://gaoding-market.dancf.com/work/preview/main-cover.png"
        banner = "https://gaoding-market.dancf.com/market-operations/market/side/banner.png"

        async def fake_validate(url):
            return url in {og_image, banner}

        crawler.validator.validate_image_url = fake_validate

        result = await crawler._pick_best_single_candidate(
            [
                (banner, "img:src"),
                (og_image, "meta:og:image"),
            ],
            "template",
        )

        await crawler.close()

        assert result == og_image

    @pytest.mark.asyncio
    async def test_pick_best_single_candidate_prefers_export_over_preview_info(self):
        crawler = GaodingCrawler()
        preview_image = "https://gdesign-dam-hw.dancf.com/work/preview/with-watermark.jpg"
        export_image = "https://gdesign-dam-hw.dancf.com/work/export/final-artboard.jpg"

        async def fake_validate(url):
            return url in {preview_image, export_image}

        crawler.validator.validate_image_url = fake_validate

        result = await crawler._pick_best_single_candidate(
            [
                (preview_image, "windowData.work.preview_info.url"),
                (export_image, "windowData.work.export_url"),
            ],
            "share",
        )

        await crawler.close()

        assert result == export_image

    @pytest.mark.asyncio
    async def test_analyze_dynamic_data_builds_multi_page_result_from_page_snapshots(self):
        crawler = GaodingCrawler()
        page_one = "https://gaoding-market.dancf.com/work/pages/page1.png"
        page_two = "https://gaoding-market.dancf.com/work/pages/page2.png"
        sidebar = "https://gaoding-market.dancf.com/market-operations/market/side/sidebar.png"

        async def fake_validate(url):
            return url in {page_one, page_two}

        crawler.validator.validate_image_url = fake_validate

        result = await crawler._analyze_dynamic_data(
            {
                "pageSnapshots": [
                    {"page": 1, "previewUrls": [page_one, sidebar]},
                    {"page": 2, "previewUrls": [sidebar, page_two]},
                ],
                "visibleCandidates": [],
                "imageUrls": [],
                "resourceUrls": [],
                "pageSource": "",
            },
            "https://www.gaoding.com/editor/design?workId=test",
            "editor",
        )

        await crawler.close()

        assert result is not None
        assert result["platform"] == "Gaoding"
        assert result["isMultiPage"] is True
        assert result["pageCount"] == 2
        assert result["imageUrls"] == [page_one, page_two]

    @pytest.mark.asyncio
    async def test_static_scraping_builds_multi_page_result_from_html_preview_bundle(self):
        crawler = GaodingCrawler()
        page_one = "https://gdesign-dam-hw.dancf.com/work/preview/page-1.jpg?auth_key=a"
        page_two = "https://gdesign-dam-hw.dancf.com/work/preview/page-2.jpg?auth_key=b"
        page_three = "https://gdesign-dam-hw.dancf.com/work/preview/page-3.jpg?auth_key=c"

        html_content = f"""
        <html><head></head><body>
        <script>
        {{&quot;preview_info&quot;:{{&quot;url&quot;:&quot;{page_one}&quot;}},
         &quot;source_preview_info&quot;:{{&quot;url&quot;:null}},
         &quot;extends_previews&quot;:[
            {{&quot;url&quot;:&quot;{page_two}&quot;}},
            {{&quot;url&quot;:&quot;{page_three}&quot;}}
         ]}}
        </script>
        </body></html>
        """

        async def fake_validate(url):
            return url in {page_one, page_two, page_three}

        crawler.validator.validate_image_url = fake_validate

        class FakeResponse:
            status = 200

            def __init__(self, body):
                self._body = body

            async def text(self):
                return self._body

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakeSession:
            def __init__(self, body):
                self._body = body

            def get(self, *args, **kwargs):
                return FakeResponse(self._body)

        result = await crawler._static_scraping(
            FakeSession(html_content),
            "https://www.gaoding.com/dam/share/test",
            "share",
        )

        await crawler.close()

        assert result is not None
        assert result["isMultiPage"] is True
        assert result["pageCount"] == 3
        assert result["imageUrls"] == [page_one, page_two, page_three]
        assert result["method"] == "static_html_preview_bundle"


class TestGaodingIntegration:
    def test_url_parser_detects_gaoding_platform(self):
        parser = URLParser()

        assert parser._detect_platform(
            "https://www.gaoding.com/editor/design?templateId=123"
        ) == "Gaoding"
        assert parser._detect_platform(
            "https://www.gaoding.com/templates/poster-template"
        ) == "Gaoding"

    def test_url_parser_strips_gaoding_share_fragment_text(self):
        parser = URLParser()

        result = parser.parse_share_url(
            "https://www.gaoding.com/dam/share/RgQONAoAy0AkCoQVR0PHE#我分享了「[放假通知爆款热点大字...]」"
        )

        assert result["success"] is True
        assert result["platform"] == "Gaoding"
        assert result["parsed_url"] == "https://www.gaoding.com/dam/share/RgQONAoAy0AkCoQVR0PHE"

    def test_image_validator_uses_gaoding_headers_for_dancf_hosts(self):
        validator = ImageValidator()

        headers = validator._get_anti_hotlink_headers(
            "https://gaoding-market.dancf.com/market-operations/market/side/abc/preview.png"
        )

        assert headers["Referer"] == "https://www.gaoding.com/"
        assert headers["Origin"] == "https://www.gaoding.com"
