"""
快速测试脚本 - 验证核心功能
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.url_parser import URLParser
from core.image_extractor import ImageExtractor

async def test_url_parser():
    """测试URL解析器"""
    print("🔍 测试URL解析器...")
    
    parser = URLParser()
    
    test_urls = [
        "点击链接加入图怪兽中的文件「初始01」邀请人：阿达 https://818ps.com/u/002dJRky-1?user_source=r1537041",
        "https://818ps.com/preview?picId=12345&upicId=67890",
        "https://www.canva.com/design/DAFxxxxx/view"
    ]
    
    for url in test_urls:
        print(f"\n📎 测试URL: {url[:50]}...")
        result = parser.parse_share_url(url)
        
        if result.get('success'):
            print(f"✅ 解析成功")
            print(f"   平台: {result.get('platform')}")
            print(f"   处理后URL: {result.get('parsed_url', '')[:80]}...")
        else:
            print(f"❌ 解析失败: {result.get('error')}")

async def test_image_extractor():
    """测试图片提取器"""
    print("\n🎯 测试图片提取器...")
    
    extractor = ImageExtractor()
    
    # 使用一个简单的测试URL
    test_url = "https://818ps.com/preview?picId=12345&upicId=67890"
    
    try:
        print(f"📎 测试URL: {test_url}")
        result = await extractor.extract_image(test_url, "818ps")
        
        print("✅ 提取成功")
        print(f"   图片URL: {result.get('imageUrl', 'N/A')}")
        print(f"   来源: {result.get('source', 'N/A')}")
        
    except Exception as e:
        print(f"❌ 提取失败: {e}")
    finally:
        await extractor.close()

async def main():
    """主测试函数"""
    print("🧪 开始快速功能测试")
    print("=" * 50)
    
    try:
        await test_url_parser()
        await test_image_extractor()
        
        print("\n" + "=" * 50)
        print("✅ 测试完成！核心功能正常")
        
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    if not success:
        sys.exit(1)