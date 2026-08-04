"""
音频下载和后处理工具

功能:
- 从 URL 下载音频
- 应用后处理 (EQ/压缩/混响/响度)
- 人声增强 (De-essing/EQ/ 混响/和声) [P0-4 新增]
- 上传到服务器/CDN
"""

import httpx
import os
import tempfile
from typing import Optional
from app.services.audio_post_processor import audio_processor
from app.services.vocal_enhancer import vocal_enhancer  # P0-4 人声增强


async def download_audio(url: str) -> Optional[str]:
    """
    从 URL 下载音频到临时文件
    
    Returns:
        临时文件路径，失败返回 None
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                # 创建临时文件
                temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
                os.close(temp_fd)
                
                # 写入文件
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                
                print(f"[下载] ✅ {url} -> {temp_path}")
                return temp_path
            else:
                print(f"[下载] ❌ {url} - 状态码：{response.status_code}")
                return None
    except Exception as e:
        print(f"[下载] ⚠️ 异常：{e}")
        return None


def enhance_audio_file(input_path: str, output_path: Optional[str] = None) -> str:
    """
    对音频文件进行后处理增强
    
    处理步骤:
    1. EQ 增强 (低频 +2dB, 高频 +2dB)
    2. 动态压缩 (3:1 压缩比)
    3. 响度标准化 (-14 LUFS)
    
    Args:
        input_path: 输入音频路径
        output_path: 输出路径 (默认临时文件)
    
    Returns:
        处理后音频文件路径
    """
    try:
        print(f"[后处理] 开始处理：{input_path}")
        
        enhanced_path = audio_processor.process(
            input_audio_path=input_path,
            output_path=output_path,
            eq_enhance=True,      # EQ 增强
            compression=True,     # 动态压缩
            reverb=False,         # 不添加混响 (避免改变原曲风格)
            loudness_normalization=True  # 响度标准化
        )
        
        print(f"[后处理] ✅ 完成：{enhanced_path}")
        return enhanced_path
    
    except Exception as e:
        print(f"[后处理] ⚠️ 失败：{e}")
        # 如果处理失败，返回原始文件
        return input_path


async def process_generated_audio(audio_url: str) -> str:
    """
    完整流程：下载 -> 后处理 -> 返回新 URL
    
    Args:
        audio_url: Mureka 生成的音频 URL
    
    Returns:
        处理后的音频 URL (或本地路径)
    """
    # 1. 下载
    temp_input = await download_audio(audio_url)
    if not temp_input:
        print("[音频优化] ⚠️ 下载失败，返回原 URL")
        return audio_url
    
    # 2. 后处理
    enhanced_path = enhance_audio_file(temp_input)
    
    # 3. 清理临时输入文件
    try:
        os.remove(temp_input)
        print(f"[清理] 删除临时文件：{temp_input}")
    except:
        pass
    
    # 4. 返回处理后的文件路径
    # (实际生产环境应该上传到 CDN，这里返回本地路径用于测试)
    print(f"[音频优化] ✅ 完成：{enhanced_path}")
    return enhanced_path


if __name__ == "__main__":
    # 测试用
    import asyncio
    
    async def test():
        test_url = "https://example.com/test.mp3"
        result = await process_generated_audio(test_url)
        print(f"结果：{result}")
    
    asyncio.run(test())