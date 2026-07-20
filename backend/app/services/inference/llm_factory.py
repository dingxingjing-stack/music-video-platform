import os
import asyncio
import logging
import time
import httpx
from typing import AsyncGenerator, Any, Dict, List, Union

logger = logging.getLogger(__name__)


def _enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _extract_text(obj):
    """递归查找响应中的首个非空 text 字段，兼容 Gemini 各种返回结构。"""
    if isinstance(obj, dict):
        text = obj.get("text")
        if isinstance(text, str) and text.strip():
            return text
        for value in obj.values():
            found = _extract_text(value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _extract_text(item)
            if found:
                return found
    return None


# --- 临时方案：默认仅启用 agnes（免费主力，稳定）。 ---
# Gemini / NVIDIA 需显式设置环境变量开启，避免其失败拖垮 LLM 接口：
#   LLM_ENABLE_GEMINI=1   /   LLM_ENABLE_NVIDIA=1
MODELS = {
    "agnes": {
        "base_url": "https://apihub.agnes-ai.com/v1",
        "key": os.getenv("AGNES_API_KEY"),
        "model_default": "agnes-2.0-flash",
        "fmt": "openai",
        "enabled": True,  # 永久主力，始终启用
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key": os.getenv("NVIDIA_API_KEY"),
        "model_default": os.getenv("NVIDIA_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1"),
        "fmt": "openai",
        "enabled": True,  # 默认启用，有密钥则加载
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "key": os.getenv("GEMINI_API_KEY"),
        "model_default": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "fmt": "gemini",
        "enabled": True,  # 默认启用，有密钥则加载
    },
}

# 全部大模型失败时返回的占位文本（不阻断前端流程）
MOCK_FALLBACK_TEXT = os.getenv(
    "LLM_MOCK_FALLBACK",
    "（AI 服务暂时繁忙，这是占位文本。请稍后重试以获取完整生成结果。）",
)


class LLMProviderError(Exception):
    """厂商专属错误，用于区分可降级场景"""
    def __init__(self, provider: str, reason: str, status_code: int = None):
        self.provider = provider
        self.reason = reason
        self.status_code = status_code
        super().__init__(f"[{provider}] {reason}")

class LLMFatalError(LLMProviderError):
    """致命错误：额度耗尽/限流，应跳过该provider，尝试更高优先级"""
    pass


class LLMFactory:
    """Unified LLM client with retry, fallback and concurrency control."""

    def __init__(self):
        self.clients: Dict[str, httpx.AsyncClient] = {}
        for name, conf in MODELS.items():
            if conf.get("enabled") and conf["key"]:
                headers = (
                    {"Authorization": f"Bearer {conf['key']}"}
                    if conf["fmt"] == "openai"
                    else {"x-goog-api-key": conf["key"]}
                )
                self.clients[name] = httpx.AsyncClient(
                    base_url=conf["base_url"],
                    headers=headers,
                    timeout=120.0,
                )
                logger.info("LLM provider loaded: %s (%s)", name, conf["model_default"])
            elif conf.get("enabled") and not conf["key"]:
                logger.warning("LLM provider %s enabled but missing API key, skipped", name)
        if not self.clients:
            logger.error("No LLM provider configured! All calls will return mock fallback.")
        self.sem = asyncio.Semaphore(4)
        # 新降级顺序：agnes → Gemini → NVIDIA → mock（用户确认2026-07-20）
        order = os.getenv("PROVIDER_ORDER", "agnes,gemini,nvidia")
        self.provider_order = [
            p.strip() for p in order.split(",") if p.strip() and p.strip() in self.clients
        ]
        if not self.provider_order:
            self.provider_order = list(self.clients.keys())

    async def call(
        self,
        messages: List[Dict[str, str]],
        provider: str = "auto",
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        **kwargs,
    ) -> Union[str, AsyncGenerator[str, None]]:
        providers = [provider] if provider != "auto" else self.provider_order
        last_err = None

        for idx, prov in enumerate(providers):
            if prov not in self.clients:
                logger.warning("Provider %s not configured, skip", prov)
                continue
            try:
                return await self._call_with_retry(
                    prov, messages, model, temperature, max_tokens, stream, **kwargs
                )
            except LLMFatalError as e:
                last_err = e
                logger.warning("[%s] %s，跳过该模型，尝试前序优先级更高模型", prov, e.reason)
                continue
            except Exception as e:
                last_err = e
                logger.warning("[%s] 调用失败: %s，切换至下一厂商", prov, e)

        raise RuntimeError(f"All providers exhausted. Last error: {last_err}")

    async def generate_safe(
        self,
        messages: List[Dict[str, str]],
        provider: str = "auto",
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        永不抛出：单个/全部大模型失败时返回 mock 占位文本，保证接口返回 200，
        不阻断前端流程。返回 {text, provider, model, mock}。

        Fallback 策略：优先使用显式指定的 provider（若已加载），失败或不可用则
        自动回退到默认顺序中的其余可用 provider（无论前端选 gemini/nvidia 与否，
        只要 agnes 可用就走 agnes）。全部失败才返回 mock。
        """
        order: List[str] = []
        if provider != "auto" and provider in self.clients:
            order.append(provider)
        order += [p for p in self.provider_order if p not in order]
        last_err = None
        for prov in order:
            if prov not in self.clients:
                continue
            try:
                text = await self._call_with_retry(
                    prov, messages, model, temperature, max_tokens, False, **kwargs
                )
                return {
                    "text": text,
                    "provider": prov,
                    "model": model or MODELS[prov]["model_default"],
                    "mock": False,
                }
            except LLMFatalError as e:
                last_err = e
                logger.warning("[%s] %s，跳过该模型，尝试前序优先级更高模型", prov, e.reason)
                continue
            except Exception as e:
                last_err = e
                logger.warning("[%s] generate_safe 调用失败: %s", prov, e)
                continue

        logger.error("All LLM providers failed, returning mock fallback. Last error: %s", last_err)
        return {
            "text": MOCK_FALLBACK_TEXT,
            "provider": "mock",
            "model": "mock",
            "mock": True,
            "error": str(last_err) if last_err else None,
        }

    async def health_check(self) -> Dict[str, Dict[str, Any]]:
        """Check all configured providers."""
        results = {}
        for name in self.clients:
            try:
                model = MODELS[name]["model_default"]
                payload = self._build_payload(name, [{"role": "user", "content": "hi"}], model, 0.1, 10, False)
                url = self._get_endpoint(name, model)
                async with self.sem:
                    resp = await self.clients[name].post(url, json=payload)
                results[name] = {"healthy": resp.status_code == 200, "status": resp.status_code}
            except Exception as exc:
                results[name] = {"healthy": False, "error": str(exc)[:200]}
        return {"providers": results}

    async def _call_with_retry(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
        **kwargs,
    ):
        client = self.clients[provider]
        conf = MODELS[provider]
        model_name = model or conf["model_default"]
        payload = self._build_payload(provider, messages, model_name, temperature, max_tokens, stream, **kwargs)
        url = self._get_endpoint(provider, model_name)
        
        nvidia_last_call_time = 0  # 40RPM避让：记录上次调用时间

        async with self.sem:
            for attempt in range(3):
                try:
                    if stream:
                        return await self._stream_request(client, url, payload, provider)
                    resp = await client.post(url, json=payload)
                    return self._handle_response(provider, resp)
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    
                    # 致命错误：402额度耗尽、429限流 → 跳过该provider，回退前序更高优先级
                    if status == 402:
                        logger.error("[%s] 402 额度/积分耗尽，判定该模型临时不可用，回退调用Agnes免费模型", provider)
                        raise LLMFatalError(provider, "402 额度耗尽", 402)
                    if status == 429:
                        logger.warning("[%s] 429 速率超限，判定该模型临时不可用，回退调用Agnes免费模型", provider)
                        raise LLMFatalError(provider, "429 速率超限", 429)
                    
                    # NVIDIA 40RPM 避让逻辑
                    if provider == "nvidia":
                        now = time.time()
                        elapsed = now - nvidia_last_call_time
                        if elapsed < 1.5:  # 40RPM ≈ 1.5s间隔
                            wait = 1.5 - elapsed
                            logger.info("[%s] 40RPM避让：等待 %.1fs", provider, wait)
                            await asyncio.sleep(wait)
                        nvidia_last_call_time = time.time()
                    
                    # 可重试错误
                    if status in (500, 502, 503, 504):
                        wait = 2 ** attempt + (attempt * 0.1)
                        logger.warning(
                            "[%s] HTTP %s (attempt %d/3), retry in %.1fs",
                            provider, status, attempt + 1, wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        # 其他HTTP错误，转为provider错误
                        raise LLMProviderError(provider, f"HTTP error {status}", status)
                        
                except (httpx.RequestError, asyncio.TimeoutError) as e:
                    wait = 2 ** attempt + (attempt * 0.1)
                    logger.warning(
                        "[%s] Network error: %s (attempt %d/3), retry in %.1fs",
                        provider, e, attempt + 1, wait,
                    )
                    await asyncio.sleep(wait)

        raise RuntimeError(f"{provider} failed after 3 retries")

    def _build_payload(self, provider, messages, model, temperature, max_tokens, stream, **kwargs):
        if MODELS[provider]["fmt"] == "openai":
            return {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream,
                **kwargs,
            }
        if provider == "gemini":
            system_instruction = None
            contents = []
            for m in messages:
                if m["role"] == "system":
                    system_instruction = {"parts": [{"text": m["content"]}]}
                else:
                    role = "user" if m["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": m["content"]}]})
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }
            if system_instruction:
                payload["systemInstruction"] = system_instruction
            return payload
        raise ValueError(f"Unknown provider {provider}")

    def _get_endpoint(self, provider, model):
        if MODELS[provider]["fmt"] == "openai":
            return "/chat/completions"
        if provider == "gemini":
            return f"/models/{model}:generateContent"
        raise ValueError(f"Unknown provider {provider}")

    def _handle_response(self, provider, resp: httpx.Response) -> str:
        resp.raise_for_status()
        data = resp.json()
        if MODELS[provider]["fmt"] == "openai":
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, TypeError, IndexError):
                # 兜底：递归查找任意 text 字段，兼容 NVIDIA 各 NIM 模型返回结构差异
                found = _extract_text(data)
                if found:
                    return found
                raise ValueError(f"OpenAI-format response missing content for {provider}: {data}")
        if provider == "gemini":
            return self._parse_gemini(data)
        raise ValueError(f"Unknown provider {provider}")

    @staticmethod
    def _parse_gemini(data: dict) -> str:
        """
        兼容新版 Gemini 返回体：candidates[].content 结构多样——
        标准 parts[].text、部分代理直出 content.text、甚至嵌套 text。
        任意异常结构（空 candidates / 安全过滤 / 缺字段）均安全降级，
        抛出可读错误交由上层兜底。
        """
        candidates = data.get("candidates") or []
        if not candidates:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            raise RuntimeError(f"Gemini returned no candidates (blockReason={block})")
        content = candidates[0].get("content") or {}
        # 1) 标准：parts[].text
        parts = content.get("parts") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
        if texts:
            return "".join(texts)
        # 2) 部分代理直出 content.text
        if isinstance(content.get("text"), str) and content["text"].strip():
            return content["text"]
        # 3) 递归查找任意 text 字段（兼容未知结构）
        found = _extract_text(candidates[0])
        if found:
            return found
        finish = candidates[0].get("finishReason")
        raise RuntimeError(f"Gemini response missing text (finishReason={finish})")

    async def _stream_request(self, client, url, payload, provider):
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = line[6:]
                if chunk == "[DONE]":
                    break
                import json
                try:
                    j = json.loads(chunk)
                    if MODELS[provider]["fmt"] == "openai":
                        delta = j["choices"][0]["delta"].get("content")
                    else:
                        delta = None
                    if delta:
                        yield delta
                except json.JSONDecodeError:
                    pass

    async def close(self):
        for c in self.clients.values():
            await c.aclose()


llm_factory = LLMFactory()
