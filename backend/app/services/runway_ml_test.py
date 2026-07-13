"""
RunwayML API 联调测试脚本 (P3-2)

使用方法:
1. 配置 .env 文件：RUNWAYML_API_KEY=your_key
2. 运行：python -m app.services.runway_ml_test
3. 查看测试结果
"""

import asyncio
import os
from app.services.runway_ml import RunwayMLService

async def test_all():
    """测试所有 AI 特效功能"""
    
    print("=" * 60)
    print("🎬 RunwayML AI 特效联调测试")
    print("=" * 60)
    
    # 检查 API Key
    api_key = os.getenv('RUNWAYML_API_KEY')
    if not api_key:
        print("\n❌ 错误：RUNWAYML_API_KEY 未配置")
        print("\n请编辑 backend/.env 文件，添加:")
        print("  RUNWAYML_API_KEY=your_api_key_here")
        print("\n获取 API Key: https://runwayml.com → Settings → API")
        return False
    
    print(f"\n✅ API Key 已配置")
    
    try:
        service = RunwayMLService()
        print("✅ 服务初始化成功")
    except Exception as e:
        print(f"\n❌ 服务初始化失败：{e}")
        return False
    
    # 测试用例
    test_image = "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=512"
    
    print("\n" + "=" * 60)
    print("📋 测试用例")
    print("=" * 60)
    print(f"测试图片：{test_image}")
    
    # 测试 1: 背景移除 (最简单)
    print("\n[1/3] 测试背景移除...")
    try:
        result = await service.remove_background(test_image)
        print(f"  ✅ 背景移除成功")
        print(f"     Task ID: {result.get('task_id', 'N/A')}")
        if 'output_url' in result:
            print(f"     结果：{result['output_url']}")
    except Exception as e:
        print(f"  ❌ 背景移除失败：{e}")
    
    # 测试 2: 图生视频
    print("\n[2/3] 测试图生视频...")
    try:
        result = await service.generate_video(
            image_url=test_image,
            prompt="camera zoom in slowly",
            motion_score=5,
            duration=4
        )
        print(f"  ✅ 视频生成任务已提交")
        print(f"     Task ID: {result['task_id']}")
        
        # 查询状态
        print(f"  📊 查询状态...")
        await asyncio.sleep(5)  # 等待 5 秒
        status = await service.get_status(result['task_id'])
        print(f"     状态：{status['status']}")
        print(f"     进度：{status.get('progress', 0)}%")
        if status.get('output_url'):
            print(f"     结果：{status['output_url']}")
    except Exception as e:
        print(f"  ❌ 图生视频失败：{e}")
    
    # 测试 3: API 配额查询
    print("\n[3/3] 查询 API 配额...")
    try:
        # 注意：RunwayML 目前不提供公开配额查询 API
        print(f"  ℹ️  配额查询：请查看 RunwayML 官网 Dashboard")
        print(f"     https://app.runwayml.com/settings")
    except Exception as e:
        print(f"  ❌ 配额查询失败：{e}")
    
    # 清理
    await service.close()
    
    print("\n" + "=" * 60)
    print("✅ 测试完成!")
    print("=" * 60)
    print("\n💡 下一步:")
    print("  1. 如果测试通过，前端可以开始使用 AI 特效")
    print("  2. 访问 http://localhost:3000 → 工具 → AI 特效")
    print("  3. 上传图片，测试真实效果")
    print("\n⚠️  注意事项:")
    print("  • 免费额度：125 credits/月")
    print("  • 图生视频：$0.35/秒 (4 秒=$1.4)")
    print("  • 建议在 Dashboard 设置使用上限")
    
    return True

if __name__ == '__main__':
    print("\n🚀 开始 RunwayML API 联调测试...\n")
    success = asyncio.run(test_all())
    exit(0 if success else 1)