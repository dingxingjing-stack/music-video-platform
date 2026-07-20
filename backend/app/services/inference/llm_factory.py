import os
import asyncio
import logging
import httpx
from typing import AsyncGenerator, Any, Dict, List, Union

logger = logging.getLogger(__name__)

MODELS = {
    "agnes": {
        "base_url": "https://apihub.agnes-ai.com/v1",
        "key": os.getenv("AGNES_API_KEY"),
        "model_default": "agnes-2.0-flash",
        "fmt": "openai",
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key": os.getenv("NVIDIA_API_KEY"),
        "model_default": "nvidia/nemotron-3-ultra",
        "fmt": "openai",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "key": os.getenv("GEMINI_API_KEY"),
        "model_default": "gemini-2.5-flash",
        "fmt": "gemini",
    },
}


class LLMFactory:
    """Unified LLM client with retry, fallback and concurrency control."""

    def __init__(self):
        self.clients: Dict[str, httpx.AsyncClient] = {}
        for name, conf in MODELS.items():
            if conf["key"]:
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
        self.sem = asyncio.Semaphore(4)
        order = os.getenv("PROVIDER_ORDER", "agnes,gemini")
        self.provider_order = [p.strip() for p in order.split(",") if p.strip()]

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
            except Exception as e:
                last_err = e
                logger.warning("[%s] attempt failed: %s", prov, e)
                if idx == len(providers) - 1:
                    break
                logger.info("Falling back to next provider...")

        raise RuntimeError(f"All providers exhausted. Last error: {last_err}")

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

        async with self.sem:
            for attempt in range(3):
                try:
                    if stream:
                        return await self._stream_request(client, url, payload, provider)
                    resp = await client.post(url, json=payload)
                    return self._handle_response(provider, resp)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code not in (429, 500, 502, 503, 504):
                        raise
                    wait = 2 ** attempt + (attempt * 0.1)
                    logger.warning(
                        "[%s] HTTP %s (attempt %d/3), retry in %.1fs",
                        provider, e.response.status_code, attempt + 1, wait,
                    )
                    await asyncio.sleep(wait)
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
            return data["choices"][0]["message"]["content"]
        if provider == "gemini":
            return data["candidates"][0]["content"]["parts"][0]["text"]
        raise ValueError(f"Unknown provider {provider}")

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