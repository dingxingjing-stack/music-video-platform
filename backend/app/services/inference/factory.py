"""
Inference Service Factory

Creates and configures inference service instances dynamically based on
the requested service type.  Supports broadcast callback injection for
real-time WebSocket progress pushing.

Configuration priority (highest to lowest):
  1. Explicit kwargs passed to create()
  2. Config dict passed to __init__()
  3. Environment variables (e.g. GPT_SOVITS_SPACE_URL)

Usage::

    factory = InferenceServiceFactory(config)
    svc = factory.create("tts", broadcast=my_callback)
    result = await svc.predict(PredictRequest(...))
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .base import BaseInferenceService, BroadcastCallback, PredictRequest, PredictResult, RetryConfig
from .gpt_sovits import GPTSovitsService
from .musicgen import MusicGenService
from .cogvideox import CogVideoXService
from .midi_render import MidiRenderService, create_midi_render_service

logger = logging.getLogger(__name__)

# Service type registry — maps short names to (class, env_prefix)
_SERVICE_REGISTRY: dict[str, tuple[type[BaseInferenceService], str]] = {
    "tts": (GPTSovitsService, "GPT_SOVITS"),
    "music": (MusicGenService, "MUSICGEN"),
    "video": (CogVideoXService, "COGVIDEOX"),
    "midi": (MidiRenderService, "MIDI_RENDER"),
}

# Alias support: allow alternate names to resolve to canonical types
_ALIASES: dict[str, str] = {
    "voice": "tts",
    "audio": "tts",
    "music_gen": "music",
    "text2video": "video",
    "t2v": "video",
    "midi_render": "midi",
}


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""

    def __init__(self, message: str, service_type: str = "", key: str = ""):
        self.message = message
        self.service_type = service_type
        self.key = key
        super().__init__(f"[{service_type}] {message}" if service_type else message)


class InferenceServiceFactory:
    """
    Factory for creating and configuring inference services.

    Each created instance can receive a ``broadcast`` callback that will be
    wired into the service's internal ``_report()`` method, enabling
    real-time progress pushes to connected WebSocket clients.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self._config = config or {}
        self._instances: dict[str, BaseInferenceService] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(
        self,
        service_type: str,
        *,
        space_url: Optional[str] = None,
        api_token: Optional[str] = None,
        fn_index: Optional[int] = None,
        retry_config: Optional[RetryConfig] = None,
        broadcast: Optional[BroadcastCallback] = None,
        http_timeout: Optional[float] = None,
        cache: bool = True,
    ) -> BaseInferenceService:
        """
        Create (or retrieve from cache) an inference service instance.

        Args:
            service_type: One of "tts", "music", "video" (or aliases).
            space_url: Override the HF Space URL.
            api_token: HF API token (for private Spaces).
            fn_index: Gradio function index (0-based).
            retry_config: Custom retry/backoff configuration.
            broadcast: WebSocket progress callback injected into the service.
            http_timeout: Override HTTP read timeout.
            cache: Reuse cached instance if config matches.

        Returns:
            A configured BaseInferenceService subclass instance.

        Raises:
            ConfigError: If required configuration is missing.
        """
        # Resolve aliases
        canonical = _ALIASES.get(service_type.lower(), service_type.lower())
        if canonical not in _SERVICE_REGISTRY:
            available = ", ".join(_SERVICE_REGISTRY.keys())
            raise ConfigError(
                f"Unknown service type '{service_type}'. "
                f"Available: {available}",
                service_type=service_type,
            )

        cls, env_prefix = _SERVICE_REGISTRY[canonical]

        # Resolve configuration
        resolved = self._resolve_config(
            canonical,
            env_prefix=env_prefix,
            space_url=space_url,
            api_token=api_token,
            fn_index=fn_index,
            retry_config=retry_config,
            broadcast=broadcast,
            http_timeout=http_timeout,
        )

        # Cache key based on all resolved parameters
        cache_key = f"{canonical}:{hash(frozenset(resolved.items()))}"

        if cache and cache_key in self._instances:
            cached = self._instances[cache_key]
            if isinstance(cached, cls):
                logger.debug("Reusing cached %s instance", canonical)
                return cached

        instance = cls(**resolved)

        if cache:
            self._instances[cache_key] = instance

        logger.info("Created %s service: %s", canonical, resolved.get("space_url", ""))
        return instance

    def create_all(
        self,
        broadcast: Optional[BroadcastCallback] = None,
    ) -> dict[str, BaseInferenceService]:
        """
        Create all known service instances at once, with broadcast injected.

        Useful for application startup initialization.

        Returns:
            Dict mapping service_type → service instance.
        """
        return {
            stype: self.create(stype, broadcast=broadcast, cache=False)
            for stype in _SERVICE_REGISTRY
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_config(
        self,
        service_type: str,
        *,
        env_prefix: str,
        **overrides: Any,
    ) -> dict[str, Any]:
        """
        Resolve configuration from overrides → config dict → env vars.

        Priority:
          1. Explicit kwarg override
          2. Config dict (self._config[service_type][key])
          3. Environment variable (ENV_PREFIX_KEY_UPPER)
          4. None (optional) / raise (required)
        """
        cfg: dict[str, Any] = {}

        for key in ("space_url", "api_token", "fn_index", "http_timeout"):
            env_key = f"{env_prefix}_{key.upper()}"

            # 1. Explicit override
            if key in overrides and overrides[key] is not None:
                cfg[key] = overrides[key]
            # 2. Config dict
            elif service_type in self._config and key in self._config.get(service_type, {}):
                cfg[key] = self._config[service_type][key]
            # 3. Environment variable
            elif os.getenv(env_key):
                val = os.getenv(env_key, "")
                if key == "fn_index":
                    val = int(val)
                elif key == "http_timeout":
                    val = float(val)
                cfg[key] = val
            # 4. Default
            else:
                if key == "space_url":
                    raise ConfigError(
                        f"Missing required config: {env_key}",
                        service_type=service_type,
                        key=env_key,
                    )
                cfg[key] = None

        # Pass through special overrides
        if overrides.get("retry_config"):
            cfg["retry_config"] = overrides["retry_config"]
        if overrides.get("broadcast") is not None:
            cfg["broadcast"] = overrides["broadcast"]

        return cfg

    def invalidate(self, service_type: Optional[str] = None) -> None:
        """Clear cached instances."""
        if service_type:
            self._instances = {
                k: v for k, v in self._instances.items()
                if self._key_type(k) != service_type
            }
        else:
            self._instances.clear()

    @staticmethod
    def _key_type(cache_key: str) -> str:
        """Extract service type from cache key like 'tts:-12345'."""
        return cache_key.split(":")[0]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_factory: Optional[InferenceServiceFactory] = None


def get_factory(config: Optional[dict[str, Any]] = None) -> InferenceServiceFactory:
    """Get or create the module-level factory singleton."""
    global _default_factory
    if _default_factory is None:
        _default_factory = InferenceServiceFactory(config)
    elif config:
        _default_factory._config.update(config)
    return _default_factory


def reset_factory() -> None:
    """Reset the singleton (useful in tests)."""
    global _default_factory
    _default_factory = None
