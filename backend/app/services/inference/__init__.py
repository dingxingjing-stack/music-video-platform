"""Inference service package — open-source AI models on HF Spaces."""

from .base import (
    BaseInferenceService,
    BroadcastCallback,
    DEFAULT_RETRY_CONFIG,
    ErrorCategory,
    PredictRequest,
    PredictResult,
    RetryConfig,
    TaskProgress,
    TaskStatus,
    _classify_http_error,
)
from .gpt_sovits import GPTSovitsService
from .musicgen import MusicGenService
from .cogvideox import CogVideoXService
from .gradio_mixins import GradioSpaceMixin
from .factory import (
    InferenceServiceFactory,
    ConfigError,
    get_factory,
    reset_factory,
)

__all__ = [
    # Base types
    "BaseInferenceService",
    "BroadcastCallback",
    "DEFAULT_RETRY_CONFIG",
    "ErrorCategory",
    "PredictRequest",
    "PredictResult",
    "RetryConfig",
    "TaskProgress",
    "TaskStatus",
    "_classify_http_error",
    # Concrete services
    "GPTSovitsService",
    "MusicGenService",
    "CogVideoXService",
    # Mixin
    "GradioSpaceMixin",
    # Factory
    "InferenceServiceFactory",
    "ConfigError",
    "get_factory",
    "reset_factory",
]
