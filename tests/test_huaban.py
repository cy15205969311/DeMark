from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.image_extractor import ImageExtractor
from crawlers.huaban_crawler import HuabanCrawler
from utils.downloader import ImageDownloader
from utils.image_validator import ImageValidator
from utils.url_parser import URLParser


PREVIEW_ONLY_PIN = {
    "pin_id": 6860695449,
    "raw_text": "Preview-only Huaban material",
    "tags": ["green", "scrapbook"],
    "file": {
        "key": "3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz",
        "type": "image/png",
        "url": (
            "https://gd-hbimg-edge.huaban.com/"
            "3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz"
            "?auth_key=test"
        ),
    },
    "board": {
        "title": "贴纸元素",
    },
    "extra": {
        "material_id": 194784409,
    },
    "file_material": {
        "file_id": 899163427,
        "material_id": 194784409,
        "material_type": "psd",
        "source_type": "produced",
        "editable": 0,
    },
    "source": None,
    "link": None,
    "original": None,
}

PUBLIC_PIN = {
    **PREVIEW_ONLY_PIN,
    "pin_id": 6860695451,
    "raw_text": "Public image pin",
    "extra": {},
    "file_material": {},
}


class TestHuabanCrawler:
    def test_classify_link_supports_pin_board_and_discovery(self):
        crawler = HuabanCrawler()

        assert crawler._classify_link("https://huaban.com/pins/6860695449") == "pin"
        assert crawler._classify_link("https://huaban.com/boards/77052553") == "board"
        assert crawler._classify_link("https://huaban.com/discovery") == "discovery"

    def test_normalize_pin_image_url_prefers_raw_host(self):
        crawler = HuabanCrawler()

        image_url = crawler._normalize_pin_image_url(PREVIEW_ONLY_PIN)

        assert image_url == (
            "https://hbimg.huabanimg.com/"
            "3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz"
        )

    def test_build_pin_entry_marks_preview_only_material(self):
        crawler = HuabanCrawler()

        entry = crawler._build_pin_entry(PREVIEW_ONLY_PIN)

        assert entry is not None
        assert entry["previewOnly"] is True
        assert "仅返回带水印预览图" in entry["previewOnlyReason"]

    def test_forward_list_params_caps_limit(self):
        crawler = HuabanCrawler()

        params = crawler._forward_list_params("https://huaban.com/discovery?limit=999&category=design")

        assert params["limit"] == str(crawler.MAX_LIST_LIMIT)
        assert params["category"] == "design"

    @pytest.mark.asyncio
    async def test_build_feed_result_returns_multi_image_payload_for_public_pins(self):
        crawler = HuabanCrawler()
        second_pin = {
            **PUBLIC_PIN,
            "pin_id": 6860695450,
            "raw_text": "Second public image pin",
            "file": {
                "key": "028a74f8a29e52587f96000c042ce88c335153bdee413-j3QJaC",
                "type": "image/png",
                "url": (
                    "https://gd-hbimg-edge.huaban.com/"
                    "028a74f8a29e52587f96000c042ce88c335153bdee413-j3QJaC"
                    "?auth_key=test"
                ),
            },
        }

        async def fake_validate(url):
            return url in {
                "https://hbimg.huabanimg.com/3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz",
                "https://hbimg.huabanimg.com/028a74f8a29e52587f96000c042ce88c335153bdee413-j3QJaC",
            }

        crawler.validator.validate_image_url = fake_validate

        result = await crawler._build_feed_result(
            [PUBLIC_PIN, second_pin],
            "https://huaban.com/discovery?limit=2",
            link_type="discovery",
            source="huaban-discovery-api",
            method="discovery_api",
        )

        await crawler.close()

        assert result is not None
        assert result["platform"] == "Huaban"
        assert result["linkType"] == "discovery"
        assert result["pageCount"] == 2
        assert result["isMultiPage"] is True
        assert result["imageUrls"] == [
            "https://hbimg.huabanimg.com/3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz",
            "https://hbimg.huabanimg.com/028a74f8a29e52587f96000c042ce88c335153bdee413-j3QJaC",
        ]

    @pytest.mark.asyncio
    async def test_build_feed_result_returns_preview_image_when_all_candidates_are_watermarked(self):
        crawler = HuabanCrawler()

        async def fake_validate(url):
            return url == "https://hbimg.huabanimg.com/3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz"

        crawler.validator.validate_image_url = fake_validate

        result = await crawler._build_feed_result(
            [PREVIEW_ONLY_PIN],
            "https://huaban.com/boards/77052553",
            link_type="board",
            source="huaban-board-api",
            method="board_pins_api",
        )

        await crawler.close()

        assert result is not None
        assert result["status"] == "preview_image"
        assert result["warningText"] == "已提取公开预览图，可直接下载，但可能包含平台水印，未获取到无水印原素材"
        assert result["platform"] == "Huaban"
        assert result["imageUrl"] == "https://hbimg.huabanimg.com/3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz"
        assert "仅返回带水印预览图" in result["error"]


class TestHuabanIntegration:
    @pytest.mark.asyncio
    async def test_image_extractor_returns_preview_image_result_without_gateway_for_huaban(self):
        extractor = ImageExtractor()
        preview_reason = (
            "该花瓣素材公开接口仅返回带水印预览图，未暴露公开无水印PSD下载字段；"
            "如需原素材，通常需要在花瓣站内登录有权限的账号后下载。"
        )

        extractor.url_parser.parse_share_url = lambda url: {
            "success": True,
            "parsed_url": url,
            "platform": "Huaban",
        }
        gateway_mock = AsyncMock(return_value=None)
        extractor.third_party_api.extract_with_cache = gateway_mock
        extractor._extract_local = AsyncMock(return_value={
            "status": "preview_image",
            "error": preview_reason,
            "warningText": "已提取公开预览图，可直接下载，但可能包含平台水印，未获取到无水印原素材",
            "platform": "Huaban",
            "source": "huaban-pin-api",
            "imageUrl": "https://hbimg.huabanimg.com/3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz",
        })

        result = await extractor.extract_image("https://huaban.com/pins/6860695449", "Huaban")
        await extractor.close()

        gateway_mock.assert_not_awaited()
        assert result["status"] == "preview_image"
        assert result["platform"] == "Huaban"
        assert result["warningText"] == "已提取公开预览图，可直接下载，但可能包含平台水印，未获取到无水印原素材"
        assert result["imageUrl"] == "https://hbimg.huabanimg.com/3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz"
        assert result["processed_url"] == "https://huaban.com/pins/6860695449"

    def test_url_parser_detects_huaban_platform(self):
        parser = URLParser()

        assert parser._detect_platform("https://huaban.com/pins/6860695449?from=share&share_text=") == "Huaban"
        assert parser._detect_platform("https://hbimg.huabanimg.com/3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz") == "Huaban"

    def test_parse_share_url_strips_huaban_extra_text(self):
        parser = URLParser()

        result = parser.parse_share_url(
            "https://huaban.com/pins/6860695449?from=share&share_text=\n这张来自花瓣网的图不错哦"
        )

        assert result["success"] is True
        assert result["platform"] == "Huaban"
        assert result["parsed_url"] == "https://huaban.com/pins/6860695449?from=share&share_text="

    def test_image_validator_uses_huaban_headers_for_raw_host(self):
        validator = ImageValidator()

        headers = validator._get_anti_hotlink_headers(
            "https://hbimg.huabanimg.com/3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz"
        )

        assert headers["Referer"] == "https://huaban.com/"
        assert headers["Origin"] == "https://huaban.com"

    def test_downloader_resolves_extension_from_content_type_for_huaban_raw_url(self):
        downloader = ImageDownloader()

        resolved_path = downloader._resolve_download_path(
            Path("downloads/Huaban_20260331_deadbeef.jpg"),
            "https://hbimg.huabanimg.com/3e76f76c650c8d5988d02856160a82b7904bfb6c3641c-P59ekz",
            "image/png",
        )

        assert resolved_path.suffix == ".png"
