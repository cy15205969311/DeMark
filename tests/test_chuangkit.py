import pytest

from crawlers.chuangkit_crawler import ChuangkitCrawler


class TestChuangkitCrawler:
    def test_candidate_filter_prefers_design_assets(self):
        crawler = ChuangkitCrawler()

        assert crawler._is_chuangkit_design_candidate(
            "https://pri-cdn-oss.chuangkit.com/svg_build/render_result/2026/03/27/page1?sign=test"
        ) is True
        assert crawler._is_chuangkit_design_candidate(
            "https://www.chuangkit.com/distheadless/img/share_header.png"
        ) is False
        assert crawler._is_chuangkit_design_candidate(
            "https://www.chuangkit.com/favicon.ico"
        ) is False

    def test_snapshot_scoring_prefers_centered_main_canvas_over_sidebar_cards(self):
        crawler = ChuangkitCrawler()
        main_url = "https://pri-cdn-oss.chuangkit.com/svg_build/render_result/2026/03/27/main-page?sign=a"
        sidebar_url = "https://pri-cdn-oss.chuangkit.com/svg_build/render_result/2026/03/27/sidebar-card?sign=b"

        main_score = crawler._score_snapshot_candidate(
            main_url,
            {
                "width": 720,
                "height": 1280,
                "area": 921600,
                "visibleArea": 680000,
                "left": 820,
                "centerDistance": 80,
                "isCentered": True,
                "isLarge": True,
                "source": "background",
            },
            set(),
        )
        sidebar_score = crawler._score_snapshot_candidate(
            sidebar_url,
            {
                "width": 180,
                "height": 320,
                "area": 57600,
                "visibleArea": 57600,
                "left": 120,
                "centerDistance": 960,
                "isCentered": False,
                "isLarge": False,
                "source": "src",
            },
            set(),
        )

        assert main_score > sidebar_score

    @pytest.mark.asyncio
    async def test_dynamic_browser_path_returns_multi_page_result(self):
        crawler = ChuangkitCrawler()

        page_one = "https://pri-cdn-oss.chuangkit.com/svg_build/render_result/2026/03/27/page1?sign=1"
        page_two = "https://pri-cdn-oss.chuangkit.com/svg_build/render_result/2026/03/27/page2?sign=2"
        page_three = "https://pri-cdn-oss.chuangkit.com/svg_build/render_result/2026/03/27/page3?sign=3"

        snapshots = [
            {
                "visibleCandidates": [
                    {
                        "url": page_one,
                        "width": 720,
                        "height": 1280,
                        "area": 921600,
                        "visibleArea": 680000,
                        "left": 820,
                        "centerDistance": 60,
                        "isCentered": True,
                        "isLarge": True,
                        "source": "background",
                    },
                    {
                        "url": "https://pri-cdn-oss.chuangkit.com/svg_build/render_result/2026/03/27/sidebar?sign=x",
                        "width": 180,
                        "height": 320,
                        "area": 57600,
                        "visibleArea": 57600,
                        "left": 120,
                        "centerDistance": 960,
                        "isCentered": False,
                        "isLarge": False,
                        "source": "src",
                    },
                ],
                "resourceUrls": [page_one],
                "imageUrls": [page_one],
                "pageSource": "",
            },
            {
                "visibleCandidates": [
                    {
                        "url": page_two,
                        "width": 720,
                        "height": 1280,
                        "area": 921600,
                        "visibleArea": 680000,
                        "left": 820,
                        "centerDistance": 60,
                        "isCentered": True,
                        "isLarge": True,
                        "source": "background",
                    }
                ],
                "resourceUrls": [page_one, page_two],
                "imageUrls": [page_one, page_two],
                "pageSource": "",
            },
            {
                "visibleCandidates": [
                    {
                        "url": page_three,
                        "width": 720,
                        "height": 1280,
                        "area": 921600,
                        "visibleArea": 680000,
                        "left": 820,
                        "centerDistance": 60,
                        "isCentered": True,
                        "isLarge": True,
                        "source": "background",
                    }
                ],
                "resourceUrls": [page_one, page_two, page_three],
                "imageUrls": [page_one, page_two, page_three],
                "pageSource": "",
            },
        ]

        class FakeDriver:
            def get(self, url):
                return None

            def quit(self):
                return None

        class FakeBrowserService:
            def __init__(self):
                self.index = 0
                self.driver = None

            def _get_stealth_driver(self, headless=True):
                return FakeDriver()

            def _capture_dynamic_snapshot(self, driver):
                snapshot = snapshots[self.index]
                self.index += 1
                return snapshot

            async def close(self):
                return None

        async def fake_validate(url):
            return url in {page_one, page_two, page_three}

        crawler.validator.validate_image_url = fake_validate
        crawler._extract_chuangkit_page_numbers = lambda driver: [1, 2, 3]
        crawler._activate_chuangkit_page = lambda driver, page_number: {"clicked": True, "requestedPage": page_number}

        result = await crawler._extract_multi_page_with_browser(
            FakeBrowserService(),
            "https://www.chuangkit.com/sharedesign?d=test",
            "share",
        )

        await crawler.close()

        assert result is not None
        assert result["isMultiPage"] is True
        assert result["pageCount"] == 3
        assert result["imageUrls"] == [page_one, page_two, page_three]

    @pytest.mark.asyncio
    async def test_resource_preload_urls_can_form_multi_page_result_without_page_clicks(self):
        crawler = ChuangkitCrawler()

        page_one = "https://pri-cdn-oss.chuangkit.com/svg_build/render_result/2026/03/27/page1?sign=1"
        page_two = "https://pri-cdn-oss.chuangkit.com/svg_build/render_result/2026/03/27/page2?sign=2"
        page_three = "https://pri-cdn-oss.chuangkit.com/svg_build/render_result/2026/03/27/page3?sign=3"

        class FakeDriver:
            def get(self, url):
                return None

            def quit(self):
                return None

        class FakeBrowserService:
            def _get_stealth_driver(self, headless=True):
                return FakeDriver()

            def _capture_dynamic_snapshot(self, driver):
                return {
                    "visibleCandidates": [],
                    "resourceUrls": [page_one, page_two, page_three],
                    "imageUrls": [page_one, page_two, page_three],
                    "pageSource": "",
                }

            async def close(self):
                return None

        async def fake_validate(url):
            return url in {page_one, page_two, page_three}

        crawler.validator.validate_image_url = fake_validate
        crawler._extract_chuangkit_page_numbers = lambda driver: []

        result = await crawler._extract_multi_page_with_browser(
            FakeBrowserService(),
            "https://www.chuangkit.com/sharedesign?d=test",
            "share",
        )

        await crawler.close()

        assert result is not None
        assert result["isMultiPage"] is True
        assert result["pageCount"] == 3
        assert result["imageUrls"] == [page_one, page_two, page_three]
