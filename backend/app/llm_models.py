"""Pydantic request/response models for LLM endpoints."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: str = Field(..., description="Role: system, user, or assistant")
    content: str = Field(..., description="Message content")


class LLMRequest(BaseModel):
    messages: List[LLMMessage] = Field(..., description="Conversation messages")
    provider: str = Field("auto", description="Provider: auto, nvidia, gemini")
    model: Optional[str] = Field(None, description="Specific model name")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1, le=8192)
    stream: bool = Field(False, description="Stream response as SSE")


class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str
    error: Optional[str] = None  # 调试用：所有 provider 失败时的最后错误