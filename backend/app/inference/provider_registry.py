from abc import ABC, abstractmethod
import os
import httpx
from typing import Dict, Any

class BaseInferenceProvider(ABC):
    @abstractmethod
    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        pass

class MockProvider(BaseInferenceProvider):
    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"result":"mock_ok","payload":payload}

class RunPodProvider(BaseInferenceProvider):
    def __init__(self):
        self.api_key = os.getenv("RUNPOD_API_KEY")
        self.endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID")
        if not self.api_key or not self.endpoint_id:
            raise RuntimeError("RunPod env missing: RUNPOD_API_KEY / RUNPOD_ENDPOINT_ID")
        self.base_url = f"https://api.runpod.ai/v2/{self.endpoint_id}/run"

    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        body = {"input": payload}
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(self.base_url, json=body, headers=headers)
            r.raise_for_status()
            return r.json()


def get_provider(provider_name:str) -> BaseInferenceProvider:
    registry = {
        "mock": MockProvider,
        "runpod": RunPodProvider
    }
    cls = registry.get(provider_name.lower())
    if cls is None:
        raise ValueError(f"unknown provider {provider_name}")
    return cls()
