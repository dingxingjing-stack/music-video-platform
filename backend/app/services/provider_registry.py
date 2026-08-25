"""GPU 音乐生成 Provider 注册表 —— 统一 Provider 抽象 + 可配置选择 + 实验 Provider 隔离。

阶段一生产策略（本文件落地范围）：
  - Modal ACE-Step（L40S）是唯一 production Provider，默认选择固定为其。
  - 实验 Provider（AMD MI300X / RunPod / ...）尚未实现；后续接入时应满足：
      * 实现 BaseProvider 并 register()，production=False；
      * 不会被 select() 默认选中，也不影响 production fallback；
      * 仅可经显式配置（AI_GENERATION_PROVIDER=<name>）或独立实验开关启用，
        永不自动进入生产路径。
  - 契约：所有 Provider 实现 async generate(request: dict) -> dict：
      request : {"prompt", "lyrics", "duration"}
      return  : {"success": bool, "volume_files": dict|None, "error": str|None,
                 "provider": name}
    volume_files 即 Modal 端返回的共享卷文件名映射（full_wav/full_mp3/stems）。
  - HF 兜底策略不变：仍是 router 层的直接 Gradio 调用（禁 mock/假音频），
    不放入本注册表（注册表只承载 GPU 生成 Provider）。

成本观测（阶段一/二约定）：
  - 每次生成经 task_store.log_generation_cost() 记录：provider/gpu/result/
    container_duration_ms（web 容器侧实测远程调用墙钟，≈ Modal 对容器计费的
    GPU 秒）/estimated_cost_usd（实测时长 × GPU 单价，估算口径）。
  - cold_warm / model_load_ms / generation_ms / container_id 为阶段二
    （Modal 端 generate_full_song 返回元数据后）填充，阶段一保持 NULL，
    绝不使用估算值冒充实测。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Optional

from app.services.ace_step_client import (
    generate_full_song as ace_step_generate,
    QueueFullError,
)

# 显式选择 Provider 的环境变量；未设置/非法时回退 production 默认。
PROVIDER_ENV = "AI_GENERATION_PROVIDER"

# GPU 按秒单价（USD/秒），用于由实测 container 时长推算估算成本。
GPU_RATE_USD_PER_SEC: dict[str, float] = {
    "L40S": 0.000542,
}


def gpu_rate_usd_per_sec(gpu: str) -> float:
    """返回 GPU 按秒单价；未知型号返回 0.0（避免虚构成本）。"""
    return GPU_RATE_USD_PER_SEC.get(gpu, 0.0)


class BaseProvider(ABC):
    """统一生成 Provider 抽象。

    新增 GPU Provider（AMD MI300X / RunPod / 其他）时继承本类，
    保持 async generate(request: dict) -> dict 契约即可。
    """

    name: str = ""
    provider_type: str = ""
    capabilities: list[str] = []
    max_duration: int = 0
    gpu: str = ""
    production: bool = False

    @abstractmethod
    async def generate(self, request: dict) -> dict:
        """生成完整歌曲。request 含 prompt/lyrics/duration。"""

    async def health_check(self) -> dict:
        return {"healthy": True, "provider": self.name}


class ModalACEStepProvider(BaseProvider):
    """Modal ACE-Step（L40S）—— 唯一 production Provider。"""

    name = "modal_ace_step"
    provider_type = "modal_ace_step"
    capabilities = ["text_to_music", "lyrics_to_music", "stem_separation", "audio2audio"]
    max_duration = 300
    gpu = "L40S"
    production = True

    async def generate(self, request: dict) -> dict:
        try:
            # 仅在参数实际提供时传递，保持与旧版 Mock 兼容
            kwargs = {
                "prompt": request.get("prompt", ""),
                "lyrics": request.get("lyrics", ""),
                "duration": request.get("duration", 180),
            }
            # 仅在参数实际提供时传递新参数，保持向后兼容
            ref_audio = request.get("reference_audio")
            if ref_audio:
                kwargs["reference_audio"] = ref_audio
            enable_a2a = request.get("enable_audio2audio")
            if enable_a2a:
                kwargs["enable_audio2audio"] = enable_a2a
            ref_strength = request.get("reference_strength")
            if ref_strength is not None:
                kwargs["reference_strength"] = ref_strength

            result = await ace_step_generate(**kwargs)
            if result:
                return {"success": True, "volume_files": result, "provider": self.name}
            return {"success": False, "error": "ACE-Step generation failed", "provider": self.name}
        except QueueFullError:
            raise
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc), "provider": self.name}


class KaggleMusicGenSmallProvider(BaseProvider):
    """Kaggle 本地 MusicGen-Small (300M) — 实验 Provider，不影响生产默认。"""

    name = "musicgen_small"
    provider_type = "musicgen_small"
    capabilities = ["text_to_music"]
    max_duration = 30
    gpu = "T4"
    production = False

    async def generate(self, request: dict) -> dict:
        try:
            from app.services.inference.musicgen_local import MusicGenSmallLocalService

            svc = MusicGenSmallLocalService()
            if not svc.is_available():
                return {"success": False, "error": "MusicGen-small 模型未就绪，请先运行 download_mvp_models.py", "provider": self.name}
            import asyncio

            def _run():
                return svc.generate(
                    prompt=request.get("prompt", ""),
                    duration=float(request.get("duration", 10)),
                    temperature=float(request.get("temperature", 1.0)),
                )

            out = await asyncio.to_thread(_run)
            return {"success": True, "volume_files": {"full_wav": str(out)}, "provider": self.name}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc), "provider": self.name}


class KaggleCosyVoice2Provider(BaseProvider):
    """Kaggle 本地 CosyVoice2-0.5B — 实验 Provider (TTS/克隆)。"""

    name = "cosyvoice2"
    provider_type = "cosyvoice2"
    capabilities = ["tts", "voice_clone", "cross_lingual"]
    max_duration = 60
    gpu = "T4"
    production = False

    async def generate(self, request: dict) -> dict:
        try:
            from app.services.inference.cosyvoice_local import CosyVoice2LocalService

            svc = CosyVoice2LocalService()
            if not svc.is_available():
                return {"success": False, "error": "CosyVoice2 模型未就绪，请先运行 download_mvp_models.py", "provider": self.name}
            import asyncio

            def _run():
                return svc.tts(
                    text=request.get("text") or request.get("prompt") or "",
                    reference_audio=request.get("reference_audio"),
                    reference_text=request.get("reference_text"),
                )

            out = await asyncio.to_thread(_run)
            return {"success": True, "volume_files": {"full_wav": str(out)}, "provider": self.name}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc), "provider": self.name}


class ProviderRegistry:
    """Provider 注册表：注册、查询、配置选择。"""

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._default: Optional[str] = None

    def register(self, provider: BaseProvider) -> None:
        self._providers[provider.name] = provider
        if provider.production and self._default is None:
            self._default = provider.name

    def get(self, name: str) -> Optional[BaseProvider]:
        return self._providers.get(name)

    def list_providers(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "name": p.name,
                "provider_type": p.provider_type,
                "gpu": p.gpu,
                "production": p.production,
                "capabilities": list(p.capabilities),
                "max_duration": p.max_duration,
            }
            for name, p in self._providers.items()
        }

    def select(self, name: Optional[str] = None) -> BaseProvider:
        """返回生产使用的 Provider。

        优先级：显式参数 > 环境变量 AI_GENERATION_PROVIDER > production 默认。
        显式指定但未注册时回退 production 默认（并告警），保证生产路径永远
        稳定指向 Modal ACE-Step，不被实验 Provider 影响。
        """
        for cand in (name, os.getenv(PROVIDER_ENV)):
            if not cand:
                continue
            provider = self._providers.get(cand)
            if provider:
                return provider
            print(f"[Provider] 配置的 provider '{cand}' 未注册或不可用，回退 production 默认")
        assert self._default is not None, "ProviderRegistry 至少需要一个 production provider"
        return self._providers[self._default]


_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    """返回进程内单例注册表（线程/协程安全：初始化后只读）。"""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
        _registry.register(ModalACEStepProvider())
        _registry.register(KaggleMusicGenSmallProvider())
        _registry.register(KaggleCosyVoice2Provider())
        print("[Provider] Registry initialized:", list(_registry._providers.keys()))
    return _registry