"""
HeartMuLa 音乐生成服务
基于 HeartMuLa 3B 模型的音乐生成服务
支持文本/歌词到音乐的生成

Kaggle T4 适配（严格 Dataset 方式 — 安全修正）：
  - HeartMuLa 3B 必须且仅能从 /kaggle/input/heartmula-3b（Kaggle Dataset，只读）加载
  - 若 Dataset 不存在 / 不完整（缺 config.json 或 *.safetensors），必须直接报错，
    明确提示挂载 Dataset；禁止自动下载到 /kaggle/working，禁止回落到 working
  - 不允许任何代码路径把 HeartMuLa 3B 下载到 /kaggle/working（6.5GB 会占满 19.5GB）
  - 本文件不含 snapshot_download，不触发任何自动下载；下载仅允许用户手动创建 Dataset
  - 非 Kaggle / Modal 生产环境仍走 HEARTMULA_API_URL 远程推理，兼容现有调用
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

# HeartMuLa 模型配置
HEARTMULA_MODEL_URL = os.getenv("HEARTMULA_MODEL_URL", "https://api.heartmula.ai/v1/generate")
HEARTMULA_API_KEY = os.getenv("HEARTMULA_API_KEY", "")
HEARTMULA_MODEL_NAME = os.getenv("HEARTMULA_MODEL_NAME", "heartmula-3b")

# Kaggle 严格 Dataset 路径：只读，不占 /kaggle/working，不得回落到 working
HEARTMULA_KAGGLE_DATASET_PATH = os.getenv("HEARTMULA_KAGGLE_DATASET_PATH", "/kaggle/input/heartmula-3b")
# 显式开关：仅当 HEARTMULA_LOCAL_ENABLED=true 才尝试走本地 Dataset；否则走 API
HEARTMULA_LOCAL_ENABLED = os.getenv("HEARTMULA_LOCAL_ENABLED", "false").lower() in ("1", "true", "yes")


class HeartMuLaDatasetError(RuntimeError):
    """HeartMuLa Dataset 缺失/不完整 — 禁止自动下载到 /kaggle/working。"""


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
    sample_rate: int = 44100
    channels: int = 2
    format: str = "wav"
    error: Optional[str] = None
    task_id: Optional[str] = None
    metadata: Optional[dict] = None


class HeartMuLaService:
    """HeartMuLa 音乐生成服务"""
    
    BASE_URL = os.getenv("HEARTMULA_API_URL", "https://api.heartmula.ai/v1")
    
    def __init__(self):
        self.api_key = os.getenv("HEARTMULA_API_KEY", "")
        self.api_url = os.getenv("HEARTMULA_API_URL", "https://api.heartmula.ai/v1/generate")
        
        if not self.api_key:
            raise ValueError("HEARTMULA_API_KEY environment variable is required")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
    
    async def generate_music(self, request: HeartMuLaRequest) -> dict:
        """
        生成音乐
        
        Returns:
            dict with keys: success, audio_url, duration, error, task_id
        """
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
                    self.base_url,
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
    
    def _build_payload(self, request: "HeartMuLaRequest") -> dict:
        """构建请求载荷"""
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
        """解析响应"""
        # 假设 API 返回格式
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


# 全局实例
heartmula_service = None

def get_heartmula_service():
    global heartmula_service
    if heartmula_service is None:
        try:
            heartmula_service = HeartMuLaService()
        except ValueError:
            # API key not configured
            pass
    return heartmula_service