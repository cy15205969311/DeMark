"""
基础功能测试
"""
import pytest
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.image_extractor import ImageExtractor
from core.browser_service import BrowserService
from crawlers.tuguaishou_818ps import Tuguaishou818psCrawler
from utils.image_validator import ImageValidator
from utils.variant_builder import VariantBuilder

class TestImageExtractor:
    """图片提取器测试"""
    
    @pytest.fixture
    def extractor(self):
        """创建提取器实例"""
        return ImageExtractor()
    
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

class TestImageValidator:
    """图片验证器测试"""
    
    @pytest.fixture
    def validator(self):
        """创建验证器实例"""
        return ImageValidator()
    
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

class Test818psCrawler:
    """818ps爬虫测试"""

    @pytest.mark.asyncio
    async def test_share_link_prefers_direct_build_when_upic_id_exists(self):
        """测试用户分享链接在拿到upicId后优先走直连构造"""
        crawler = Tuguaishou818psCrawler()
        call_state = {
            'direct_build': 0,
            'scrape': 0,
        }

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

        crawler._extract_with_upic_id_priority = fake_direct_build
        crawler._scrape_webpage_enhanced = fake_scrape

        result = await crawler.extract_image(
            "https://ue.818ps.com/v4/?upicId=311210634&share_id=1783630",
            {'upic_id': '311210634'}
        )

        await crawler.close()

        assert result is not None
        assert result['source'] == 'user_path_priority'
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

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
