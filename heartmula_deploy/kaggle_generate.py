#!/usr/bin/env python3
"""
HeartMuLa 最小生成测试脚本
在 kaggle_setup.py 成功后运行
"""

import sys
import os
import torch

# === 强制路径优先级 (必须在最前面) ===
HEARTMULA_ENV = Path("/kaggle/working/heartmula_env")
HEARTLIB_SRC = Path("/kaggle/working/heartlib/src")
sys.path.insert(0, str(HEARTMULA_ENV))
sys.path.insert(0, str(HEARTLIB_SRC))

from pathlib import Path

MODEL_DIR = Path("/kaggle/working/pretrained")
HEARTMULA_MODEL_DIR = MODEL_DIR / "HeartMuLa-oss-3B"
HEARTCODEC_MODEL_DIR = MODEL_DIR / "HeartCodec-oss"


def main():
    print("=" * 60)
    print("HeartMuLa 音乐生成测试")
    print("=" * 60)
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"设备: {device}")
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
    
    # === 导入 HeartLib ===
    from heartlib.heartmula import HeartMuLa
    from heartlib.heartcodec import HeartCodec
    from heartlib.pipelines import MusicGenerationPipeline
    
    print("\n加载模型...")
    
    # 加载 HeartMuLa
    print(f"HeartMuLa: {HEARTMULA_MODEL_DIR}")
    mular = HeartMuLa.from_pretrained(str(HEARTMULA_MODEL_DIR)).to(device)
    mular.eval()
    print("✓ HeartMuLa 加载完成")
    
    # 加载 HeartCodec
    print(f"HeartCodec: {HEARTCODEC_MODEL_DIR}")
    codec = HeartCodec.from_pretrained(str(HEARTCODEC_MODEL_DIR)).to(device)
    codec.eval()
    print("✓ HeartCodec 加载完成")
    
    # 使用官方 Pipeline (如果存在)
    try:
        pipeline = MusicGenerationPipeline(
            model=mular,
            codec=codec,
            device=device,
        )
        print("✓ Pipeline 创建成功")
    except Exception as e:
        print(f"Pipeline 不可用，使用手动生成: {e}")
        pipeline = None
    
    # === 生成测试 ===
    print("\n开始生成测试...")
    
    prompt = "A beautiful piano melody, peaceful and emotional"
    duration = 10  # 秒
    
    with torch.no_grad():
        if pipeline:
            # 使用官方 pipeline
            output = pipeline.generate(
                prompt=prompt,
                duration=duration,
                temperature=1.0,
                top_k=250,
                top_p=0.95,
            )
        else:
            # 手动调用 (根据实际 API 调整)
            # 这里需要查看官方示例的具体调用方式
            print("请根据官方示例调整生成代码")
            output = None
    
    if output is not None:
        # 保存音频
        import torchaudio
        output_path = "/kaggle/working/generated_test.wav"
        torchaudio.save(output_path, output.cpu(), sample_rate=44100)
        print(f"✓ 音频已保存: {output_path}")
        print(f"  形状: {output.shape}")
        print(f"  时长: {output.shape[-1] / 44100:.2f} 秒")
    else:
        print("⚠ 生成未产生输出，需检查 API")
    
    print("\n测试完成")


if __name__ == "__main__":
    main()