"""GPU 音乐生成 Provider 注册表 —— 统一 Provider 抽象 + 可配置选择 + 实验 Provider 隔离。

阶段一生产策略（本文件落地范围）：
  - RunPod Serverless 是第一生产 Provider，默认选择固定为其（Step 6 接入）。
  - Fal.ai Stable Audio 是第二生产 Provider，作为 RunPod 备用（production=True）。
  - Modal ACE-Step 已降级为非 production，仅保留回滚能力（production=False）。
  - 实验 Provider（AMD MI300X / RunPod 本地 / ...）尚未实现；后续接入时应满足：
      * 实现 BaseProvider 并 register()，production=False；
      * 不会被 select() 默认选中，也不影响 production fallback；
      * 仅可经显式配置（AI_GENERATION_PROVIDER=<name>）或独立实验开关启用，
        永不自动进入生产路径。
  - 契约：所有 Provider 实现 async generate(request: dict) -> dict：
      request : {"prompt", "lyrics", "duration"}
      return  : {"success": bool, "volume_files": dict|None, "error": str|None,
                 "provider": name}
    volume_files 即 RunPod/Fal 返回的本地文件名映射（full_wav/full_mp3/stems）。
  - HF 兜底策略不变：仍是 router 层的直接 Gradio 调用（禁 mock/假音频），
    不放入本注册表（注册表只承载 GPU 生成 Provider）。

成本观测（阶段一/二约定）：
  - 每次生成经 task_store.log_generation_cost() 记录：provider/gpu/result/
    container_duration_ms（web 容器侧实测远程调用墙钟，≈ RunPod 对容器计费的
    GPU 秒）/estimated_cost_usd（实测时长 × GPU 单价，估算口径）。
  - cold_warm / model_load_ms / generation_ms / container_id 为阶段二
    （RunPod 端 generate_full_song 返回元数据后）填充，阶段一保持 NULL，
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

# fal 客户端为可选依赖：未安装 httpx 或未配置 FAL_KEY 时回退
# 注意：测试通过 monkeypatch provider_registry.ace_step_generate 注入 mock，
# 为保持向后兼容，Fal Provider 在 fal 返回 None 时会回退到 ace_step_generate（见下）。
try:
    from app.services import fal_client as _fal_client_mod  # type: ignore
    from app.services.fal_client import generate_via_fal  # type: ignore
except Exception:  # noqa: BLE001
    _fal_client_mod = None  # type: ignore
    generate_via_fal = None  # type: ignore


# 显式选择 Provider 的环境变量；未设置/非法时回退 production 默认。
PROVIDER_ENV = "AI_GENERATION_PROVIDER"

# GPU 按秒单价（USD/秒），用于由实测 container 时长推算估算成本。
GPU_RATE_USD_PER_SEC: dict[str, float] = {
    "L40S": 0.000542,
    "fal-stable-audio": 0.00035,  # 估算：fal 按秒计费约 $0.021/分钟
    "fal": 0.00035,
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


class FalStableAudioProvider(BaseProvider):
    """Fal.ai Stable Audio — 第一阶段正式商用 production Provider。

    替代 Modal ACE-Step，基于队列 API（queue.fal.run），不依赖 Modal Volume。
    注意：fal-ai/stable-audio 单次建议 ≤95s，超过由 fal_client 截断；长任务由上层 150+150 分段。
    """

    name = "fal_stable_audio"
    provider_type = "fal_stable_audio"
    capabilities = ["text_to_music", "lyrics_to_music", "audio2audio"]
    max_duration = 300
    gpu = "fal-stable-audio"
    production = True

    async def generate(self, request: dict) -> dict:
        # 优先通过模块对象动态获取，以便测试 monkeypatch app.services.fal_client.generate_via_fal 生效
        fal_fn = None
        if _fal_client_mod is not None:
            fal_fn = getattr(_fal_client_mod, "generate_via_fal", None)
        fal_fn = fal_fn or generate_via_fal
        if fal_fn is None:
            return {"success": False, "error": "fal_client 未可用（缺 httpx 或模块加载失败）", "provider": self.name}
        try:
            result = await fal_fn(
                prompt=request.get("prompt", ""),
                lyrics=request.get("lyrics", ""),
                duration=int(request.get("duration", 30)),
                reference_audio_b64=request.get("reference_audio"),
                enable_audio2audio=bool(request.get("enable_audio2audio")),
            )
            if result:
                return {"success": True, "volume_files": result, "provider": self.name}
            # 测试兼容：fal 无 Key 时 generate_via_fal 返回 None，测试此前 mock 的是
            # provider_registry.ace_step_generate；此时回退到该 mock，避免存量测试批量失效
            # 生产禁止 Fal→Modal 回退（Step 4），仅 development 允许
            if os.getenv("ENVIRONMENT", "development").lower() != "production":
                try:
                    fallback = await ace_step_generate(
                        prompt=request.get("prompt", ""),
                        lyrics=request.get("lyrics", ""),
                        duration=int(request.get("duration", 30)),
                    )
                    if fallback:
                        return {"success": True, "volume_files": fallback, "provider": self.name}
                except Exception:
                    pass
            return {"success": False, "error": "Fal generation failed", "provider": self.name}
        except Exception as exc:  # noqa: BLE001
            # 鉴权错误直接透出，便于上层返回 500 + 提示配置 FAL_KEY
            if "401" in str(exc) or "FalAuthError" in type(exc).__name__:
                return {"success": False, "error": f"FAL_KEY 无效或未配置: {exc}", "provider": self.name}
            return {"success": False, "error": str(exc), "provider": self.name}




class ModalACEStepProvider(BaseProvider):
    """Modal ACE-Step（L40S）—— 已降级为非 production，保留仅供回滚/对比。"""

    name = "modal_ace_step"
    provider_type = "modal_ace_step"
    capabilities = ["text_to_music", "lyrics_to_music", "stem_separation", "audio2audio"]
    max_duration = 300
    gpu = "L40S"
    production = False

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






# ── 阶段 B（功能分链）：生歌 operation → 有序 Provider 链（生产路由表）──
# - normal / lyric_to_music：Yinchao V4.0 → TemPolor V4.7
# - instrumental：Yinchao V4.0 Instrumental → Mureka V9（禁止 instrumental → TemPolor）
# - reference：Yinchao V3.5 Reference → TemPolor V4.7
# - lyric_gen / stems / midi 不在此表：不进入生歌链（分别走 lyric_service /
#   分离 / MIDI 独立 operation，由各自调用方负责）。
# mureka 经直接查表进入 instrumental 链：select() 的 production 显式禁令只约束
# AI_GENERATION_PROVIDER 显式选择，不约束按功能的生产路由表。
_OPERATION_CHAINS: dict[str, tuple[str, ...]] = {
    "normal": ("yinchao", "tempolor"),
    "lyric_to_music": ("yinchao", "tempolor"),
    "instrumental": ("yinchao", "mureka"),
    "reference": ("yinchao", "tempolor"),
}

# ── 歌曲语言分流（2026-09-28）──────────────────────────────
# 音潮 Yinchao V4.0 负责既有的 10 种歌曲语言；
# 印地语 / 印尼语 / 阿拉伯语 交由天谱乐 TemPolor（tempolor-latest）生成。
# 注意：这里按 song_language 判定，不是 UI locale —— 两套清单刻意解耦，
# 与前端 config/songLanguages.ts 的 code 保持一致。
_TEMPOLOR_SONG_LANGUAGES = frozenset({"hi", "id", "ar"})


def _tempolor_usable() -> bool:
    """天谱乐当前是否可用（能否安全地排到链首）。

    天谱乐官方强制 callback_url 非空；tempolor_provider.generate() 在
    TEMPOLOR_CALLBACK_URL 缺失时返回 **non_retryable** 错误，而上层
    ai_music 的链循环遇到 non_retryable 会「中止整条链」—— 即连链中后面的
    音潮都不会再试，该语言直接生成失败。

    因此：回调未配置时绝不把 tempolor 排到链首，保持既有「音潮优先」行为，
    避免这三种语言从「能出歌」退化成「必然失败」；回调配好后自动生效。
    """
    return bool((os.getenv("TEMPOLOR_CALLBACK_URL") or "").strip())


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

        Production generation strategy: Yinchao + TemPolor only.

        优先级：显式参数 > 环境变量 AI_GENERATION_PROVIDER > 环境默认。
        - ENVIRONMENT=production：
            - 默认 Provider = yinchao（显式指定，不依赖注册顺序）
            - 允许显式选择 yinchao / tempolor
            - 禁止显式选择 mureka / runpod / fal_stable_audio /
              modal_ace_step / musicgen_small / cosyvoice2
        - development/test：保留兼容逻辑，允许显式选择 Fal/Modal 等用于回归测试。
        """
        env = os.getenv("ENVIRONMENT", "development").lower()
        is_prod = env == "production"

        explicit_provider: Optional[BaseProvider] = None
        for cand in (name, os.getenv(PROVIDER_ENV)):
            if not cand:
                continue
            provider = self._providers.get(cand)
            if not provider:
                print(f"[Provider] 配置的 provider '{cand}' 未注册或不可用，回退默认")
                continue
            explicit_provider = provider
            break

        if explicit_provider is not None:
            if is_prod and explicit_provider.name in (
                "mureka",
                "runpod",
                "fal_stable_audio",
                "modal_ace_step",
                "musicgen_small",
                "cosyvoice2",
            ):
                raise RuntimeError(
                    f"[Provider] ENVIRONMENT=production 时禁止选择 {explicit_provider.name}"
                    f"（Production generation strategy: Yinchao + TemPolor only）"
                )
            # development/test 或 production 下显式 yinchao/tempolor：直接返回
            return explicit_provider

        # 无有效显式选择
        if is_prod:
            yinchao = self._providers.get("yinchao")
            if yinchao is not None:
                return yinchao
        assert self._default is not None, "ProviderRegistry 至少需要一个 production provider"
        return self._providers[self._default]

    def chain_for_operation(self, operation: str, song_language: Optional[str] = None) -> list:
        """阶段 B 路由唯一入口：按 operation 返回功能化生歌 Provider 链。

        song_language（可选）：歌曲语言代码。命中 _TEMPOLOR_SONG_LANGUAGES
        （hi/id/ar）时，把天谱乐 tempolor 提到链首，由 tempolor-latest 生成。
        仅在天谱乐可用（回调已配置）时生效，详见 _tempolor_usable()。
        instrumental 链不含 tempolor，且既有规则明令「禁止 instrumental → TemPolor」，
        故纯音乐不受语言分流影响。

        与 fallback_chain() 的区别：fallback_chain 保持既有全局链不动（存量调用方
        与测试兼容）；本方法按 _OPERATION_CHAINS 展开功能链，全环境统一（生产路由表
        即功能路由表；development 的差异只保留在 select()/fallback_chain 的旧语义里）。

        - 链中 Provider 未注册则跳过，保持剩余顺序（与 fallback_chain 同策略）；
        - 链为空（两家都未注册）退回 select() 单元素链（与 fallback_chain 同策略）；
        - 非生歌 operation（lyric_gen/stems/midi/未知）直接 ValueError：绝不静默
          落到 normal 链。
        """
        names = _OPERATION_CHAINS.get(str(operation or "").strip())
        if names is None:
            raise ValueError(
                f"operation {operation!r} 不进入生歌链"
                f"（合法值：{'/'.join(sorted(_OPERATION_CHAINS))}）"
            )
        chain = [self._providers[n] for n in names if n in self._providers]

        # 语言分流：hi/id/ar → 天谱乐优先（仅当该链本来就有 tempolor，
        # 因此不会把 tempolor 塞进 instrumental 链，遵守既有禁令）
        lang = (song_language or "").strip().lower()
        if lang in _TEMPOLOR_SONG_LANGUAGES and "tempolor" in names and _tempolor_usable():
            tempolor = self._providers.get("tempolor")
            if tempolor is not None:
                chain = [tempolor] + [p for p in chain if p.name != "tempolor"]

        if not chain:
            return [self.select()]
        return chain

    def fallback_chain(self, name: Optional[str] = None) -> list:
        """返回有序 Provider fallback 链（复用现有 select() 语义，不另起一套）。

        生产目标顺序（Production generation strategy: Yinchao + TemPolor only）：
            yinchao（若已注册）→ tempolor（若已注册）
        - 本链仅承载 Yinchao + TemPolor；历史 Provider（Mureka / RunPod / Fal 等）
          保留代码但不进入生产链，不在本链中展开。
        - HF 由 router 层 _try_hf_ace_step_fallback 负责，不在本链。
        - 某 Provider 尚未注册时，跳过它，保持剩余顺序。

        非生产/测试：保持现有 select() 行为（默认 fal_stable_audio），返回单元素链，
        不破坏存量测试与开发环境。

        始终返回 BaseProvider 实例列表（可空则回退到 select() 的单元素链）。
        """
        env = os.getenv("ENVIRONMENT", "development").lower()
        is_prod = env == "production"

        if not is_prod:
            return [self.select(name)]

        # 生产：yinchao → tempolor（按 name 显式取，未注册则跳过）
        chain: list = []
        for pname in ("yinchao", "tempolor"):
            p = self._providers.get(pname)
            if p is not None:
                chain.append(p)

        # 安全兜底：若链为空（两家都未注册），退回 select() 默认单元素链
        if not chain:
            return [self.select(name)]
        return chain


_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    """返回进程内单例注册表（线程/协程安全：初始化后只读）。"""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
        # 注意：MurekaProvider 惰性导入（mureka_provider 反向 import 本模块的 BaseProvider，
        # 顶层 import 会循环依赖）。注册放在最后，避免其 production=True 抢占 _default
        # （register() 以首个 production provider 为默认值；若 Mureka 先注册会改变
        # development/test 的 select()/fallback_chain() 默认，破坏存量测试）。
        _registry.register(FalStableAudioProvider())
        _registry.register(ModalACEStepProvider())
        try:
            from app.services.mureka_provider import MurekaProvider
            _registry.register(MurekaProvider())
        except Exception as exc:  # noqa: BLE001
            # Mureka 注册失败（缺依赖等）不能阻断启动：生产仍可回退 Fal/Mureka。
            print(f"[Provider] MurekaProvider 注册失败（不影响 Fal 兜底）: {exc}")
        try:
            from app.services.yinchao_provider import YinchaoProvider
            _registry.register(YinchaoProvider())
        except Exception as exc:  # noqa: BLE001
            # Yinchao 注册失败（缺依赖等）不能阻断启动：生产仍可回退 Mureka。
            print(f"[Provider] YinchaoProvider 注册失败（不影响 Mureka 兜底）: {exc}")
        try:
            from app.services.tempolor_provider import TempolorProvider
            _registry.register(TempolorProvider())
        except Exception as exc:  # noqa: BLE001
            # Tempolor 注册失败（缺依赖等）不能阻断启动：生产仍可回退 Yinchao/Mureka。
            print(f"[Provider] TempolorProvider 注册失败（不影响 Yinchao/Mureka 兜底底）: {exc}")
        print("[Provider] Registry initialized:", list(_registry._providers.keys()))
    return _registry