from unittest.mock import AsyncMock

import pytest

from core.image_extractor import ImageExtractor


class TestImageExtractorNormalization:
    def test_normalize_result_images_merges_pages_lists_and_thumbnail_without_creating_fake_pages(self):
        extractor = ImageExtractor()

        result = extractor._normalize_result_images(
            {
                "platform": "Gaoding",
                "pages": [
                    {"page": 2, "imageUrl": "https://cdn.example.com/page-2.png"},
                    {"page": 1, "imageUrl": "https://cdn.example.com/page-1.png"},
                ],
                "images": [
                    "https://cdn.example.com/page-2.png",
                    "https://cdn.example.com/page-3.png",
                ],
                "thumbnailUrl": "https://cdn.example.com/thumb.png",
            }
        )

        assert result["imageUrl"] == "https://cdn.example.com/page-1.png"
        assert result["imageUrls"] == [
            "https://cdn.example.com/page-1.png",
            "https://cdn.example.com/page-2.png",
            "https://cdn.example.com/page-3.png",
        ]
        assert result["images"] == result["imageUrls"]
        assert result["thumbnailUrl"] == "https://cdn.example.com/thumb.png"
        assert result["pageCount"] == 3
        assert result["isMultiPage"] is True

    def test_normalize_result_images_uses_thumbnail_as_last_resort(self):
        extractor = ImageExtractor()

        result = extractor._normalize_result_images(
            {
                "platform": "Chuangkit",
                "thumbnailUrl": "https://cdn.example.com/fallback-thumb.png",
            }
        )

        assert result["imageUrl"] == "https://cdn.example.com/fallback-thumb.png"
        assert result["imageUrls"] == ["https://cdn.example.com/fallback-thumb.png"]
        assert result["pageCount"] == 1
        assert result["isMultiPage"] is False


class TestImageExtractorChuangkitFallback:
    @pytest.mark.asyncio
    async def test_chuangkit_returns_local_multi_page_over_api_single(self):
        extractor = ImageExtractor()
        extractor.url_parser.parse_share_url = lambda url: {
            "success": True,
            "parsed_url": url,
            "platform": "Chuangkit",
        }
        extractor.third_party_api.extract_with_cache = AsyncMock(
            return_value={
                "success": True,
                "imageUrl": "https://cdn.example.com/api-single.png",
            }
        )
        extractor.validator.validate_image_url = AsyncMock(return_value=True)
        extractor._extract_local = AsyncMock(
            return_value={
                "platform": "Chuangkit",
                "imageUrls": [
                    "https://cdn.example.com/local-page-1.png",
                    "https://cdn.example.com/local-page-2.png",
                ],
            }
        )
        extractor._selenium_extract = AsyncMock(return_value=None)

        result = await extractor.extract_image("https://www.chuangkit.com/sharedesign?d=test", "Chuangkit")
        await extractor.close()

        assert result["imageUrls"] == [
            "https://cdn.example.com/local-page-1.png",
            "https://cdn.example.com/local-page-2.png",
        ]
        assert result["isMultiPage"] is True

    @pytest.mark.asyncio
    async def test_chuangkit_falls_back_to_api_single_when_local_is_not_multi_page(self):
        extractor = ImageExtractor()
        extractor.url_parser.parse_share_url = lambda url: {
            "success": True,
            "parsed_url": url,
            "platform": "Chuangkit",
        }
        extractor.third_party_api.extract_with_cache = AsyncMock(
            return_value={
                "success": True,
                "imageUrl": "https://cdn.example.com/api-single.png",
            }
        )
        extractor.validator.validate_image_url = AsyncMock(return_value=True)
        extractor._extract_local = AsyncMock(
            return_value={
                "platform": "Chuangkit",
                "imageUrl": "https://cdn.example.com/local-single.png",
            }
        )
        extractor._selenium_extract = AsyncMock(return_value=None)

        result = await extractor.extract_image("https://www.chuangkit.com/sharedesign?d=test", "Chuangkit")
        await extractor.close()

        extractor._selenium_extract.assert_not_awaited()
        assert result["imageUrl"] == "https://cdn.example.com/api-single.png"
        assert result["source"] == "api-gateway"
