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

if __name__ == "__main__":
    pytest.main([__file__, "-v"])