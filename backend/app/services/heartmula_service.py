"""
HeartMuLa 音乐生成服务
支持两种模式：
1. API 模式（默认）：调用远程 HEARTMULA_API_URL
2. 本地推理模式：HEARTMULA_LOCAL_ENABLED=true，使用 HeartMuLaLocalService 直接在 GPU 上推理

Kaggle T4 适配（严格 Dataset 方式 — 安全修正）：
  - HeartMuLa 3B 必须且仅能从 /kaggle/input/heartmula-3b（Kaggle Dataset，只读）加载
  - 若 Dataset 不存在 / 不完整（缺 config.json 或 *.safetensors），必须直接报错，
    明确提示挂载 Dataset；禁止自动下载到 /kaggle/working，禁止回落到 working
  - 不允许任何代码路径把 HeartMuLa 3B 下载到 /kaggle/working（6.5GB 会占满 19.5GB）
  - 本文件不含 snapshot_download，不触发任何自动下载；下载仅允许用户手动创建 Dataset
  - 非 Kaggle / Modal 生产环境仍走 HEARTMULA_API_URL 远程推理，兼容现有调用
  - HF Spaces / RunPod / 本地 GPU：启用 HEARTMULA_LOCAL_ENABLED=true 走本地推理
"""

import logging
import os
import httpx
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel
from enum import Enum

logger = logging.getLogger(__name__)

# HeartMuLa 模型配置（API 模式）
HEARTMULA_MODEL_URL = os.getenv("HEARTMULA_MODEL_URL", "https://api.heartmula.ai/v1/generate")
HEARTMULA_API_KEY = os.getenv("HEARTMULA_API_KEY", "")
HEARTMULA_MODEL_NAME = os.getenv("HEARTMULA_MODEL_NAME", "heartmula-3b")

# Kaggle 严格 Dataset 路径：只读，不占 /kaggle/working，不得回落到 working
HEARTMULA_KAGGLE_DATASET_PATH = os.getenv("HEARTMULA_KAGGLE_DATASET_PATH", "/kaggle/input/heartmula-3b")

# 本地推理模式开关
# - true: 使用 HeartMuLaLocalService 直接在本地 GPU 推理（HF Spaces / RunPod / 本地 GPU）
# - false: 使用远程 API（默认，兼容现有 Modal/生产环境）
HEARTMULA_LOCAL_ENABLED = os.getenv("HEARTMULA_LOCAL_ENABLED", "false").lower() in ("1", "true", "yes")


class HeartMuLaDatasetError(RuntimeError):
    """HeartMuLa Dataset 缺失/不完整 — 禁止自动下载到 /kaggle/working。"""


class HeartMuLaLocalError(RuntimeError):
    """HeartMuLa 本地推理错误（GPU/模型/CUDA/依赖问题）"""


def _is_kaggle_env() -> bool:
    return Path("/kaggle/input").exists() or Path("/kaggle/working").exists()


def is_heartmula_dataset_available(dataset_path: str = HEARTMULA_KAGGLE_DATASET_PATH) -> bool:
    """检查 HeartMuLa 3B Dataset 是否已在 /kaggle/input/heartmula-3b 且完整。

    完整判定：目录存在且包含 config.json 且至少一个 .safetensors 或 pytorch_model.bin。
    不完整则视为不可用，且禁止回落到 /kaggle/working 下载。
    """
    p = Path(dataset_path)
    if not p.is_dir():
        return False
    has_config = (p / "config.json").exists()
    has_weights = any(p.glob("*.safetensors")) or (p / "pytorch_model.bin").exists() or (p / "model.safetensors").exists()
    # 也接受 Kaggle 常见子目录形式（如 /kaggle/input/heartmula-3b/heartmula-3b/）
    if not has_weights:
        for sub in p.iterdir():
            if sub.is_dir() and (sub / "config.json").exists() and any(sub.glob("*.safetensors")):
                return True
    return has_config and has_weights


def _heartmula_missing_detail(dataset_path: str = HEARTMULA_KAGGLE_DATASET_PATH) -> str:
    p = Path(dataset_path)
    if not p.exists():
        return f"路径不存在: {dataset_path}"
    if not p.is_dir():
        return f"路径不是目录: {dataset_path}"
    missing = []
    if not (p / "config.json").exists():
        missing.append("config.json")
    if not any(p.glob("*.safetensors")) and not (p / "pytorch_model.bin").exists():
        missing.append("*.safetensors / pytorch_model.bin")
    # 检查子目录
    for sub in p.iterdir():
        if sub.is_dir() and (sub / "config.json").exists() and any(sub.glob("*.safetensors")):
            return ""  # 实际完整
    return f"缺失: {', '.join(missing)} (ls: {', '.join(x.name for x in p.iterdir())})" if missing else ""


def require_heartmula_dataset(dataset_path: str = HEARTMULA_KAGGLE_DATASET_PATH) -> str:
    """严格校验 HeartMuLa Dataset：不存在或不完整则抛 HeartMuLaDatasetError。

    - 不下载
    - 不回落到 /kaggle/working
    - 错误信息明确提示挂载 Dataset
    """
    if is_heartmula_dataset_available(dataset_path):
        return dataset_path
    detail = _heartmula_missing_detail(dataset_path)
    raise HeartMuLaDatasetError(
        f"[HeartMuLa] Dataset 不可用 — 禁止自动下载到 /kaggle/working。\n"
        f"  期望路径: {dataset_path} (Kaggle Dataset, 只读, 不占 19.5GB working)\n"
        f"  原因: {detail or '目录为空或结构不正确'}\n"
        f"  解决: 在 Kaggle Notebook 右侧 Add data 挂载 HeartMuLa-3B Dataset 到 /kaggle/input/heartmula-3b，\n"
        f"        确保包含 config.json + *.safetensors；不要尝试下载到 /kaggle/working。\n"
        f"  当前禁止任何自动 fallback 到 /kaggle/working（安全修正）。"
    )


def get_heartmula_local_path() -> Optional[str]:
    """返回 HeartMuLa 本地权重路径（仅当 Dataset 严格可用且 HEARTMULA_LOCAL_ENABLED 时）。

    - Kaggle + HEARTMULA_LOCAL_ENABLED=true + Dataset 完整 → 返回 Dataset 路径
    - 否则：Kaggle 但 Dataset 不完整 → 抛 HeartMuLaDatasetError（不回落）
    - 非 Kaggle 或未启用 → 返回 None，走 API（兼容 Modal 生产）
    """
    if not HEARTMULA_LOCAL_ENABLED:
        return None
    # Kaggle 环境下严格要求 Dataset
    if _is_kaggle_env():
        return require_heartmula_dataset(HEARTMULA_KAGGLE_DATASET_PATH)
    # 非 Kaggle 本地调试：如路径存在则返回，否则走 API
    if is_heartmula_dataset_available():
        return HEARTMULA_KAGGLE_DATASET_PATH
    return None


def assert_no_heartmula_working_download() -> None:
    """安全断言：禁止任何 HeartMuLa 权重出现在 /kaggle/working。

    供启动检查调用；如检测到则报错，提示清理。
    """
    forbidden = Path("/kaggle/working/heartmula-3b")
    if forbidden.exists():
        raise HeartMuLaDatasetError(
            f"[HeartMuLa 安全] 检测到 /kaggle/working 下存在 HeartMuLa 权重: {forbidden} — "
            f"这会占满 19.5GB。HeartMuLa 必须仅通过 /kaggle/input/heartmula-3b Dataset 挂载，请删除 working 下的副本。"
        )
    # 也检查常见误下载位置
    for p in [Path("/kaggle/working/cache/hf/hub/models--HeartMuLa-3b"), Path("/kaggle/working/models/heartmula")]:
        if p.exists():
            raise HeartMuLaDatasetError(f"[HeartMuLa 安全] 禁止路径存在: {p} — 请清理并改用 Dataset。")


# HeartMuLa 支持的参数
class HeartMuLaStyle(str, Enum):
    POP = "pop"
    ROCK = "rock"
    ELECTRONIC = "electronic"
    HIP_HOP = "hip-hop"
    RNB = "r&b"
    JAZZ = "jazz"
    CLASSICAL = "classical"
    AMBIENT = "ambient"
    CINEMATIC = "cinematic"
    LO_FI = "lo-fi"
    COUNTRY = "country"
    FOLK = "folk"
    REGGAE = "reggae"
    BLUES = "blues"
    FUNK = "funk"
    SOUL = "soul"
    DISCO = "disco"
    HOUSE = "house"
    TECHNO = "techno"
    TRANCE = "trance"
    DUBSTEP = "dubstep"
    DRUM_AND_BASS = "drum-and-bass"
    AMBIENT_ELECTRONIC = "ambient-electronic"
    CHILLWAVE = "chillwave"
    SYNTHWAVE = "synthwave"
    VAPORWAVE = "vaporwave"


class HeartMuLaVocalType(str, Enum):
    AUTO = "auto"
    MALE = "male"
    FEMALE = "female"
    INSTRUMENTAL = "instrumental"
    CHILD = "child"
    CHOIR = "choir"


class HeartMuLaStructure(str, Enum):
    VERSE_CHORUS = "verse-chorus"
    VERSE_CHORUS_BRIDGE = "verse-chorus-bridge"
    VERSE_VERSE_CHORUS = "verse-verse-chorus"
    ABA = "aba"
    ABAB = "abab"
    THROUGH_COMPOSED = "through-composed"
    INTRO_VERSE_CHORUS_OUTRO = "intro-verse-chorus-outro"
    MINIMAL = "minimal"


class HeartMuLaRequest(BaseModel):
    """HeartMuLa 音乐生成请求"""
    prompt: str  # 音乐描述/提示词
    lyrics: Optional[str] = None  # 可选歌词
    style: str = "pop"  # 音乐风格
    duration: int = 180  # 时长（秒），默认3分钟
    tempo: Optional[int] = None  # BPM
    key: Optional[str] = None  # 调性
    time_signature: str = "4/4"  # 拍号
    vocal_type: HeartMuLaVocalType = HeartMuLaVocalType.AUTO
    structure: HeartMuLaStructure = HeartMuLaStructure.VERSE_CHORUS
    temperature: float = 1.0  # 采样温度
    top_p: float = 0.95
    top_k: int = 50
    seed: Optional[int] = None  # 随机种子


class HeartMuLaResponse(BaseModel):
    """HeartMuLa 音乐生成响应"""
    success: bool
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    sample_rate: int = 48000  # HeartCodec 输出 48kHz
    channels: int = 2
    format: str = "wav"
    error: Optional[str] = None
    task_id: Optional[str] = None
    metadata: Optional[dict] = None


class HeartMuLaService:
    """
    HeartMuLa 音乐生成服务 - 统一接口
    
    两种模式自动选择：
    - HEARTMULA_LOCAL_ENABLED=true: 本地 GPU 推理（HeartMuLaLocalService）
    - HEARTMULA_LOCAL_ENABLED=false: 远程 API 调用（原有逻辑）
    
    两种模式返回相同格式响应，上层调用无感知。
    """
    
    def __init__(self, local_mode: Optional[bool] = None):
        """
        初始化服务
        
        Args:
            local_mode: 强制指定模式
                - True: 强制本地推理
                - False: 强制远程 API
                - None: 自动根据 HEARTMULA_LOCAL_ENABLED 环境变量决定
        """
        # 模式选择
        if local_mode is not None:
            self.local_mode = local_mode
        else:
            self.local_mode = HEARTMULA_LOCAL_ENABLED
        
        # API 模式配置
        self.api_key = os.getenv("HEARTMULA_API_KEY", "")
        self.api_url = os.getenv("HEARTMULA_API_URL", "https://api.heartmula.ai/v1/generate")
        
        if not self.local_mode:
            if not self.api_key:
                raise ValueError("HEARTMULA_API_KEY environment variable is required for API mode")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        } if self.api_key else {}
        
        # 本地服务实例（延迟初始化）
        self._local_service = None
        
        logger.info(f"HeartMuLaService 初始化: mode={'local' if self.local_mode else 'api'}")
    
    @property
    def local_service(self):
        """获取本地服务单例（懒加载）"""
        if self._local_service is None:
            if not self.local_mode:
                raise HeartMuLaLocalError("本地模式未启用，无法获取本地服务")
            # 导入时才加载，避免 CPU 环境报错
            from app.services.heartmula_local import get_heartmula_local_service
            self._local_service = get_heartmula_local_service()
        return self._local_service
    
    async def generate_music(self, request: HeartMuLaRequest) -> dict:
        """
        生成音乐 - 统一入口
        
        根据模式自动路由到本地推理或远程 API
        
        Returns:
            dict with keys: success, audio_url, duration, error, task_id, metadata
        """
        if self.local_mode:
            return await self._generate_local(request)
        else:
            return await self._generate_api(request)
    
    async def _generate_local(self, request: HeartMuLaRequest) -> dict:
        """本地 GPU 推理生成"""
        try:
            # 调用本地服务
            result = await self.local_service.generate(
                prompt=request.prompt,
                lyrics=request.lyrics or request.prompt,
                duration=request.duration,
                topk=request.top_k,
                temperature=request.temperature,
                cfg_scale=1.5,  # 固定值，与官方 pipeline 一致
            )
            
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "本地生成失败"),
                    "task_id": None,
                }
            
            # 上传音频到 R2 并获取预签名 URL
            audio_url = await self._upload_audio_to_r2(result["audio_bytes"])
            
            return {
                "success": True,
                "audio_url": audio_url,
                "duration": result.get("duration"),
                "sample_rate": result.get("sample_rate", 48000),
                "channels": result.get("channels", 2),
                "format": "wav",
                "error": None,
                "task_id": f"heartmula-local-{os.urandom(4).hex()}",
                "metadata": {
                    "mode": "local",
                    "model": "HeartMuLa-oss-3B-happy-new-year",
                    "codec": "HeartCodec-oss-20260123",
                    "device": "cuda",
                    "lazy_load": True,
                }
            }
            
        except HeartMuLaLocalError as e:
            logger.error(f"HeartMuLa 本地推理错误: {e}")
            return {
                "success": False,
                "error": f"本地推理失败: {str(e)}",
                "task_id": None,
            }
        except Exception as e:
            logger.exception("HeartMuLa 本地生成异常")
            return {
                "success": False,
                "error": f"本地生成异常: {str(e)}",
                "task_id": None,
            }
    
    async def _generate_api(self, request: HeartMuLaRequest) -> dict:
        """远程 API 生成（原有逻辑）"""
        if not self.api_key:
            return {
                "success": False,
                "error": "HEARTMULA_API_KEY not configured",
                "task_id": None
            }
        
        try:
            payload = self._build_payload(request)
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=300.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_response(data)
                elif response.status_code == 429:
                    return {"success": False, "error": "Rate limited", "task_id": None}
                elif response.status_code == 400:
                    error_data = response.json()
                    return {"success": False, "error": f"Bad request: {error_data.get('detail', 'Unknown error')}", "task_id": None}
                else:
                    return {"success": False, "error": f"API error: {response.status_code}", "task_id": None}
                    
        except httpx.TimeoutException:
            return {"success": False, "error": "Request timeout", "task_id": None}
        except Exception as e:
            return {"success": False, "error": str(e), "task_id": None}
    
    async def _upload_audio_to_r2(self, audio_bytes: bytes) -> str:
        """上传音频字节到 R2 并返回预签名下载 URL"""
        import uuid
        import tempfile
        from app.services.cdn_uploader import cdn_uploader
        
        # 写入临时文件
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        try:
            key = f"heartmula/{uuid.uuid4().hex}.wav"
            await cdn_uploader.upload_private(tmp_path, key, "audio/wav")
            presigned_url = cdn_uploader.get_presigned_download_url(key, expires_in=3600)
            return presigned_url
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    
    def _build_payload(self, request: "HeartMuLaRequest") -> dict:
        """构建请求载荷（API 模式）"""
        payload = {
            "prompt": request.prompt,
            "duration": request.duration,
            "style": request.style,
        }
        
        if request.lyrics:
            payload["lyrics"] = request.lyrics
        if request.tempo:
            payload["tempo"] = request.tempo
        if request.key:
            payload["key"] = request.key
        if request.time_signature:
            payload["time_signature"] = request.time_signature
        if request.vocal_type:
            payload["vocal_type"] = request.vocal_type.value
        if request.structure:
            payload["structure"] = request.structure.value
        if request.temperature != 1.0:
            payload["temperature"] = request.temperature
        if request.top_p != 0.95:
            payload["top_p"] = request.top_p
        if request.top_k != 50:
            payload["top_k"] = request.top_k
        if request.seed is not None:
            payload["seed"] = request.seed
            
        return payload
    
    def _parse_response(self, data: dict) -> dict:
        """解析 API 响应"""
        audio_url = (
            data.get("audio_url") or
            data.get("output_url") or
            data.get("url") or
            data.get("data", {}).get("audio_url") or
            data.get("data", {}).get("url")
        )
        
        task_id = data.get("task_id") or data.get("id")
        duration = data.get("duration")
        
        return {
            "success": bool(audio_url),
            "audio_url": audio_url,
            "duration": duration,
            "task_id": audio_url and str(hash(audio_url))[:8] or None,
            "error": None if audio_url else "No audio URL in response"
        }
    
    def get_mode(self) -> str:
        """获取当前模式"""
        return "local" if self.local_mode else "api"
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """获取显存统计（仅本地模式可用）"""
        if self.local_mode and self._local_service is not None:
            return self._local_service.get_memory_stats()
        return {"available": False, "mode": self.get_mode()}


# 全局实例工厂
_heartmula_service_instance: Optional[HeartMuLaService] = None


def get_heartmula_service(local_mode: Optional[bool] = None) -> Optional[HeartMuLaService]:
    """
    获取 HeartMuLa 服务单例
    
    Args:
        local_mode: 强制指定模式（None=自动）
    
    Returns:
        HeartMuLaService 实例，或 None（API 模式且未配置 API_KEY）
    """
    global _heartmula_service_instance
    
    if _heartmula_service_instance is None:
        try:
            _heartmula_service_instance = HeartMuLaService(local_mode=local_mode)
        except ValueError as e:
            if not HEARTMULA_LOCAL_ENABLED:
                # API 模式且无 API_KEY
                logger.warning(f"HeartMuLaService 初始化失败: {e}")
                return None
            raise
    
    return _heartmula_service_instance


def is_heartmula_local_available() -> bool:
    """检查本地推理是否可用（不抛异常，用于健康检查）"""
    try:
        from app.services.heartmula_local import is_heartmula_local_available as _check
        return _check()
    except Exception:
        return False