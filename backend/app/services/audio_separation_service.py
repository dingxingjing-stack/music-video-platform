"""
音频分离服务 - 异步网关客户端
不再负责本地模型推理，仅作为远端 HF Worker 的 HTTP 客户端

注意：
- Render 实例不再加载任何 AI 模型（彻底避免 512MB OOM）
- 所有推理转移至 HuggingFace Spaces（16GB 免费容器）
- 鉴权：使用 X-API-Key 头部进行密钥校验
"""

import asyncio
import base64
from typing import Dict, Optional

import httpx

from app.core.config import get_settings

settings = get_settings()
HF_WORKER_URL = settings.HF_WORKER_URL.rstrip("/")
HF_WORKER_API_KEY = settings.HF_WORKER_API_KEY

# 重要：HF 免费层可能在冷启动时需 30 秒+，故读至 300 秒
HF_HTTP_TIMEOUT = httpx.Timeout(30.0, read=300.0)


class DemucsService:
    """
    占位类（保留旧 import 路径，实际功能为 HTTP 客户端）
    """

    async def call_hf_worker(
        self,
        original_url: str,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ) -> Dict[str, bytes]:
        """
        调用 HF Worker 进行分离，返回 4 轨 WAV bytes

        参数：
            original_url: Supabase 上的原始音频公开 URL
            max_retries: 最多重试次数（包含“休眠唤醒”场景）
            retry_delay: 重试间隔（秒）

        流程：
            1. 下载原始音频 bytes
            2. POST 至 HF Worker /separate （multipart form，带 X-API-Key）
            3. 返回 JSON -> 取 stems (base64) 解码为 bytes

        抛出：
            RuntimeError（网络错误、鉴权错误、HF 返回 failed）
        """
        if not HF_WORKER_URL or not HF_WORKER_API_KEY:
            raise RuntimeError("环境变量 HF_WORKER_URL / HF_WORKER_API_KEY 未配置")

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=HF_HTTP_TIMEOUT) as client:
                    # 1. 下载原始音频
                    print(f"[HF-Client] 下载原始音频: {original_url}")
                    orig_resp = await client.get(original_url)
                    if orig_resp.status_code != 200:
                        raise RuntimeError(f"下载原始音频失败: {orig_resp.status_code}")
                    orig_bytes = orig_resp.content
                    file_name = original_url.split("/")[-1] or "audio.wav"
                    mime = orig_resp.headers.get("content-type") or "audio/wav"

                    # 2. POST 至 HF Worker
                    print(f"[HF-Client] 调用 HF Worker {HF_WORKER_URL}/separate (第 {attempt} 次)")
                    resp = await client.post(
                        f"{HF_WORKER_URL}/separate",
                        files={"file": (file_name, orig_bytes, mime)},
                        headers={"X-API-Key": HF_WORKER_API_KEY},
                    )
                    if resp.status_code != 200:
                        raise RuntimeError(f"HF Worker 返回 {resp.status_code}: {resp.text[:200]}")

                    data = resp.json()
                    if not data.get("success"):
                        raise RuntimeError(f"HF 分离失败: {data.get('message', '')}")

                    # 3. 解码 base64 为 bytes
                    stems_b64 = data.get("stems", {})
                    stems_bytes: Dict[str, bytes] = {}
                    for name in ["vocals", "drums", "bass", "other"]:
                        b64_str = stems_b64.get(name)
                        if not b64_str:
                            raise RuntimeError(f"HF 响应中缺少 {name} 轨道")
                        stems_bytes[name] = base64.b64decode(b64_str)

                    print(f"[HF-Client] ✅ 收到 {len(stems_bytes)} 个轨道")
                    return stems_bytes

            except (httpx.TimeoutException, httpx.ConnectError, RuntimeError) as e:
                msg = str(e)
                if attempt >= max_retries:
                    raise RuntimeError(f"重试 {max_retries} 次后仍失败: {msg}")
                print(f"[HF-Client] ⚠️ 第 {attempt} 次失败: {msg}, {retry_delay}s 后重试")
                await asyncio.sleep(retry_delay)
            except Exception as e:
                raise RuntimeError(f"HF Worker 调用异常: {e}")

    # === 保留以兼容旧调用 ===
    def get_available_models(self):
        return ["htdemucs", "htdemucs_ft", "htdemucs_6s"]


# 全局实例
demucs_service = DemucsService()
