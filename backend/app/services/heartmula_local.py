"""
HeartMuLa 3B + HeartCodec 本地推理服务
用于 Hugging Face Spaces (Docker GPU) / RunPod Serverless / Kaggle T4 等 GPU 环境

设计原则：
- 单例模式：模型只加载一次，复用 pipeline
- lazy_load=True：T4 16GB VRAM 必须开启，HeartMuLa 和 HeartCodec 交替加载
- 从 Hugging Face Hub 运行时下载权重（不打包进镜像）
- 无 Mock fallback：任何 GPU/模型/CUDA/依赖问题直接抛出异常
- 复用官方 HeartMuLaGenPipeline（已在 Kaggle T4 验证）
- 支持 HF Spaces 环境变量配置
"""

import os
import torch
import torchaudio
import asyncio
import tempfile
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# 全局单例
_heartmula_local_instance: Optional["HeartMuLaLocalService"] = None


@dataclass
class HeartMuLaLocalConfig:
    """HeartMuLa 本地推理配置 - 通过环境变量可覆盖"""
    # 模型仓库（官方推荐版本）
    model_repo: str = "HeartMuLa/HeartMuLa-oss-3B-happy-new-year"
    codec_repo: str = "HeartMuLa/HeartCodec-oss-20260123"
    version: str = "3B"
    
    # 设备与精度（T4 16GB 优化）
    device: str = "cuda"  # 强制 GPU，CPU 环境不运行推理
    mula_dtype: str = "bfloat16"   # HeartMuLa: bfloat16 (约 7.5 GB)
    codec_dtype: str = "float32"   # HeartCodec: float32 (约 8-10 GB，bf16 会降质)
    lazy_load: bool = True         # 关键：交替加载，峰值显存 ~10-12 GB
    
    # 缓存目录
    cache_dir: str = "/models/heartmula"
    
    # 生成参数默认值
    default_topk: int = 50
    default_temperature: float = 1.0
    default_cfg_scale: float = 1.5
    default_max_audio_length_ms: int = 240_000  # 4 分钟上限
    
    # 运行时检查
    require_gpu: bool = True
    min_vram_gb: float = 14.0  # T4 16GB 留 margin

    def __post_init__(self):
        # 环境变量覆盖
        self.model_repo = os.getenv("HEARTMULA_MODEL_REPO", self.model_repo)
        self.codec_repo = os.getenv("HEARTCODEC_MODEL_REPO", self.codec_repo)
        self.version = os.getenv("HEARTMULA_VERSION", self.version)
        self.device = os.getenv("HEARTMULA_DEVICE", self.device)
        self.mula_dtype = os.getenv("HEARTMULA_DTYPE", self.mula_dtype)
        self.codec_dtype = os.getenv("HEARTCODEC_DTYPE", self.codec_dtype)
        self.lazy_load = os.getenv("HEARTMULA_LAZY_LOAD", str(self.lazy_load)).lower() in ("1", "true", "yes")
        self.cache_dir = os.getenv("HEARTMULA_CACHE_DIR", self.cache_dir)
        self.require_gpu = os.getenv("HEARTMULA_REQUIRE_GPU", str(self.require_gpu)).lower() in ("1", "true", "yes")


class HeartMuLaLocalError(Exception):
    """HeartMuLa 本地推理专用异常 - 区别于网络/API 错误"""
    pass


class HeartMuLaLocalService:
    """
    HeartMuLa 本地推理服务 - 单例模式
    
    使用官方 HeartMuLaGenPipeline：
    - HeartMuLa: 文本/歌词 -> 音频 tokens
    - HeartCodec: 音频 tokens -> WAV 音频
    - lazy_load=True: T4 16GB 显存管理
    """
    
    def __init__(self, config: Optional[HeartMuLaLocalConfig] = None):
        self.config = config or HeartMuLaLocalConfig()
        self._pipeline = None
        self._models_loaded = False
        self._load_lock = asyncio.Lock()
        
        # 验证环境
        self._validate_environment()
        
        # 同步初始化（下载权重、创建 pipeline）
        self._initialize_pipeline()
    
    def _validate_environment(self):
        """启动时验证 GPU/CUDA/依赖 - 失败即报错，不回退"""
        # 1. 必须有 GPU
        if self.config.require_gpu and not torch.cuda.is_available():
            raise HeartMuLaLocalError(
                "GPU 不可用：torch.cuda.is_available() == False。"
                "HeartMuLa 本地推理需要 NVIDIA GPU。"
                "请检查：Docker --gpus all、CUDA 驱动、基础镜像是否包含 CUDA。"
            )
        
        # 2. 显存检查
        if torch.cuda.is_available():
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            gpu_name = torch.cuda.get_device_name(0)
            logger.info(f"检测到 GPU: {gpu_name}, VRAM: {vram_gb:.2f} GB")
            
            if vram_gb < self.config.min_vram_gb:
                raise HeartMuLaLocalError(
                    f"显存不足：检测到 {vram_gb:.2f} GB，最低需要 {self.config.min_vram_gb} GB (T4 16GB 标准)。"
                    f"当前 GPU: {gpu_name}。"
                    "建议：使用 T4 16GB 或更大显存 GPU，或启用 lazy_load=True。"
                )
        
        # 3. CUDA 版本检查
        cuda_version = torch.version.cuda
        logger.info(f"PyTorch CUDA 版本: {cuda_version}")
        if cuda_version is None:
            raise HeartMuLaLocalError("PyTorch 未编译 CUDA 支持，请安装 cu121 版本的 PyTorch")
        
        # 4. heartlib 导入检查
        try:
            from heartlib import HeartMuLaGenPipeline
            logger.info("heartlib 导入成功")
        except ImportError as e:
            raise HeartMuLaLocalError(
                f"heartlib 导入失败: {e}。"
                "请确保已安装: pip install git+https://github.com/HeartMuLa/heartlib.git@main"
            )
        
        # 5. vector_quantize_pytorch 检查
        try:
            import vector_quantize_pytorch
            logger.info("vector_quantize_pytorch 导入成功")
        except ImportError as e:
            raise HeartMuLaLocalError(
                f"vector_quantize_pytorch 导入失败: {e}。"
                "HeartCodec 依赖此库，请安装: pip install vector_quantize_pytorch"
            )
    
    def _initialize_pipeline(self):
        """下载权重并创建 HeartMuLaGenPipeline（同步阻塞，启动时执行）"""
        from huggingface_hub import snapshot_download
        from heartlib import HeartMuLaGenPipeline
        
        cache_dir = Path(self.config.cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"模型缓存目录: {cache_dir}")
        logger.info(f"HeartMuLa 仓库: {self.config.model_repo}")
        logger.info(f"HeartCodec 仓库: {self.config.codec_repo}")
        logger.info(f"版本: {self.config.version}")
        logger.info(f"设备: {self.config.device}, HeartMuLa dtype: {self.config.mula_dtype}, HeartCodec dtype: {self.config.codec_dtype}")
        logger.info(f"lazy_load: {self.config.lazy_load}")
        
        # --- 1. 下载 HeartMuLa 权重 ---
        mula_dir = cache_dir / f"HeartMuLa-oss-{self.config.version}"
        if not mula_dir.exists() or not any(mula_dir.glob("*.safetensors")):
            logger.info(f"下载 HeartMuLa 权重到 {mula_dir} ...")
            snapshot_download(
                repo_id=self.config.model_repo,
                local_dir=mula_dir,
                local_dir_use_symlinks=False,
            )
            logger.info("HeartMuLa 权重下载完成")
        else:
            logger.info(f"HeartMuLa 权重已存在: {mula_dir}")
        
        # 验证 HeartMuLa 文件
        self._verify_model_dir(mula_dir, "HeartMuLa")
        
        # --- 2. 下载 HeartCodec 权重 ---
        codec_dir = cache_dir / "HeartCodec-oss"
        if not codec_dir.exists() or not any(codec_dir.glob("*.safetensors")):
            logger.info(f"下载 HeartCodec 权重到 {codec_dir} ...")
            snapshot_download(
                repo_id=self.config.codec_repo,
                local_dir=codec_dir,
                local_dir_use_symlinks=False,
            )
            logger.info("HeartCodec 权重下载完成")
        else:
            logger.info(f"HeartCodec 权重已存在: {codec_dir}")
        
        # 验证 HeartCodec 文件
        self._verify_model_dir(codec_dir, "HeartCodec")
        
        # --- 3. 下载 tokenizer.json 和 gen_config.json (来自 HeartMuLaGen 仓库) ---
        gen_repo = "HeartMuLa/HeartMuLaGen"
        tokenizer_path = cache_dir / "tokenizer.json"
        gen_config_path = cache_dir / "gen_config.json"
        
        if not tokenizer_path.exists() or not gen_config_path.exists():
            logger.info(f"下载 tokenizer.json 和 gen_config.json 从 {gen_repo} ...")
            snapshot_download(
                repo_id=gen_repo,
                local_dir=cache_dir,
                local_dir_use_symlinks=False,
                allow_patterns=["tokenizer.json", "gen_config.json"],
            )
            logger.info("tokenizer.json 和 gen_config.json 下载完成")
        else:
            logger.info("tokenizer.json 和 gen_config.json 已存在")
        
        # 验证必要文件
        for f in [tokenizer_path, gen_config_path]:
            if not f.exists():
                raise HeartMuLaLocalError(f"必要文件缺失: {f}")
        
        # --- 4. 创建 HeartMuLaGenPipeline ---
        logger.info("创建 HeartMuLaGenPipeline...")
        device_map = {
            "mula": torch.device(self.config.device),
            "codec": torch.device(self.config.device),
        }
        dtype_map = {
            "mula": getattr(torch, self.config.mula_dtype),
            "codec": getattr(torch, self.config.codec_dtype),
        }
        
        self._pipeline = HeartMuLaGenPipeline.from_pretrained(
            pretrained_path=str(cache_dir),
            device=device_map,
            dtype=dtype_map,
            version=self.config.version,
            lazy_load=self.config.lazy_load,
        )
        
        self._models_loaded = True
        logger.info("HeartMuLaGenPipeline 创建成功")
        
        # 打印显存使用情况
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / (1024**3)
            reserved = torch.cuda.memory_reserved() / (1024**3)
            logger.info(f"初始化后显存: allocated={allocated:.2f} GB, reserved={reserved:.2f} GB")
    
    def _verify_model_dir(self, model_dir: Path, name: str):
        """验证模型目录完整性"""
        if not model_dir.exists():
            raise HeartMuLaLocalError(f"{name} 目录不存在: {model_dir}")
        
        config_file = model_dir / "config.json"
        if not config_file.exists():
            raise HeartMuLaLocalError(f"{name} 缺少 config.json: {config_file}")
        
        # 至少一个 safetensors 文件
        safetensors = list(model_dir.glob("*.safetensors"))
        if not safetensors:
            raise HeartMuLaLocalError(f"{name} 缺少 *.safetensors 权重文件: {model_dir}")
        
        # 检查 index 文件（分片模型需要）
        index_file = model_dir / "model.safetensors.index.json"
        if len(safetensors) > 1 and not index_file.exists():
            logger.warning(f"{name} 多片权重但缺少 model.safetensors.index.json: {model_dir}")
        
        total_size = sum(f.stat().st_size for f in safetensors) / (1024**3)
        logger.info(f"{name} 验证通过: {len(safetensors)} 个权重文件, 总大小 {total_size:.2f} GB")
    
    @property
    def pipeline(self):
        """获取 pipeline（懒加载已在初始化时完成）"""
        if self._pipeline is None:
            raise HeartMuLaLocalError("Pipeline 未初始化")
        return self._pipeline
    
    def generate_sync(
        self,
        lyrics: str,
        tags: str,
        max_audio_length_ms: Optional[int] = None,
        topk: Optional[int] = None,
        temperature: Optional[float] = None,
        cfg_scale: Optional[float] = None,
    ) -> bytes:
        """
        同步生成音频（在线程池中运行）
        
        Returns:
            WAV 音频字节数据
        """
        if not self._models_loaded:
            raise HeartMuLaLocalError("模型未加载完成")
        
        # 使用默认值
        max_audio_length_ms = max_audio_length_ms or self.config.default_max_audio_length_ms
        topk = topk or self.config.default_topk
        temperature = temperature or self.config.default_temperature
        cfg_scale = cfg_scale or self.config.default_cfg_scale
        
        # 创建临时文件
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            lyrics_path = tmpdir_path / "lyrics.txt"
            tags_path = tmpdir_path / "tags.txt"
            output_path = tmpdir_path / "output.wav"
            
            # 写入歌词和标签
            lyrics_path.write_text(lyrics, encoding="utf-8")
            tags_path.write_text(tags, encoding="utf-8")
            
            # 执行生成（同步阻塞）
            with torch.no_grad():
                self.pipeline(
                    {"lyrics": str(lyrics_path), "tags": str(tags_path)},
                    max_audio_length_ms=max_audio_length_ms,
                    save_path=str(output_path),
                    topk=topk,
                    temperature=temperature,
                    cfg_scale=cfg_scale,
                )
            
            # 读取生成的音频
            if not output_path.exists():
                raise HeartMuLaLocalError(f"生成失败：输出文件不存在 {output_path}")
            
            audio_bytes = output_path.read_bytes()
            
            # 验证音频有效性
            self._validate_audio(audio_bytes, output_path)
            
            return audio_bytes
    
    def _validate_audio(self, audio_bytes: bytes, output_path: Path):
        """验证生成的音频有效性（非静音、正确采样率等）"""
        try:
            info = torchaudio.info(str(output_path))
        except Exception as e:
            raise HeartMuLaLocalError(f"音频文件读取失败: {e}")
        
        # 采样率检查（HeartCodec 输出 48kHz）
        if info.sample_rate != 48000:
            raise HeartMuLaLocalError(f"采样率异常: {info.sample_rate} Hz，期望 48000 Hz")
        
        # 时长检查
        duration = info.num_frames / info.sample_rate
        if duration < 1.0:
            raise HeartMuLaLocalError(f"音频时长过短: {duration:.2f} 秒")
        
        # 静音检查
        waveform, _ = torchaudio.load(str(output_path))
        max_amplitude = waveform.abs().max().item()
        if max_amplitude < 0.001:
            raise HeartMuLaLocalError(f"音频疑似静音: max_amplitude={max_amplitude:.6f}")
        
        logger.info(f"音频验证通过: {duration:.2f}s, {info.sample_rate}Hz, {info.num_channels}ch, max_amp={max_amplitude:.4f}")
    
    async def generate(
        self,
        prompt: str,
        lyrics: str,
        duration: int,
        topk: Optional[int] = None,
        temperature: Optional[float] = None,
        cfg_scale: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        异步生成音频（包装同步调用到线程池）
        
        Returns:
            {
                "success": True,
                "audio_bytes": bytes,
                "duration": float,
                "sample_rate": int,
                "channels": int,
            }
        """
        # 限制最大时长
        max_ms = min(duration * 1000, self.config.default_max_audio_length_ms)
        
        # 标签使用 prompt，歌词使用 lyrics
        tags = prompt.lower().strip()
        lyrics_text = lyrics.strip() if lyrics else prompt
        
        # 在线程池中运行同步生成（避免阻塞事件循环）
        loop = asyncio.get_event_loop()
        audio_bytes = await loop.run_in_executor(
            None,
            self.generate_sync,
            lyrics_text,
            tags,
            max_ms,
            topk,
            temperature,
            cfg_scale,
        )
        
        # 获取音频信息
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        try:
            info = torchaudio.info(tmp_path)
            duration_sec = info.num_frames / info.sample_rate
        finally:
            os.unlink(tmp_path)
        
        return {
            "success": True,
            "audio_bytes": audio_bytes,
            "duration": duration_sec,
            "sample_rate": info.sample_rate,
            "channels": info.num_channels,
        }
    
    def get_memory_stats(self) -> Dict[str, float]:
        """获取当前显存使用统计"""
        if not torch.cuda.is_available():
            return {"available": False}
        
        return {
            "available": True,
            "allocated_gb": torch.cuda.memory_allocated() / (1024**3),
            "reserved_gb": torch.cuda.memory_reserved() / (1024**3),
            "max_allocated_gb": torch.cuda.max_memory_allocated() / (1024**3),
            "max_reserved_gb": torch.cuda.max_memory_reserved() / (1024**3),
            "total_gb": torch.cuda.get_device_properties(0).total_memory / (1024**3),
        }


def get_heartmula_local_service(config: Optional[HeartMuLaLocalConfig] = None) -> HeartMuLaLocalService:
    """获取 HeartMuLa 本地服务单例"""
    global _heartmula_local_instance
    
    if _heartmula_local_instance is None:
        _heartmula_local_instance = HeartMuLaLocalService(config)
    
    return _heartmula_local_instance


async def initialize_heartmula_local(config: Optional[HeartMuLaLocalConfig] = None) -> HeartMuLaLocalService:
    """异步初始化入口（用于 FastAPI lifespan）"""
    return get_heartmula_local_service(config)


def is_heartmula_local_available() -> bool:
    """检查本地推理是否可用（不抛异常，用于健康检查）"""
    try:
        if not torch.cuda.is_available():
            return False
        from heartlib import HeartMuLaGenPipeline
        import vector_quantize_pytorch
        return True
    except Exception:
        return False