"""ace_step_modal 本地静态/单元测试（B2 验证，不触碰真实 Modal / GPU）。

通过 sys.modules 注入假 modal 与假 acestep，验证：
  1. App 名、注册函数名、镜像 env（ACESTEP_CHECKPOINTS_DIR）
  2. 源码不再出现旧缺陷（错误 repo ID、裸 transformers 推理、mock 关键词）
  3. duration 钳制与 GenerationParams/GenerationConfig 构造契约
"""

import importlib
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "ace_step_modal.py"


class _FakeVolume:
    def __init__(self, name: str = "", create_if_missing: bool = True):
        self.name = name
        self.create_if_missing = create_if_missing

    @classmethod
    def from_name(cls, name: str, create_if_missing: bool = True):
        return cls(name=name, create_if_missing=create_if_missing)

    def commit(self) -> None:
        pass


class _FakeImage:
    def __init__(self, python_version: str | None = None):
        self.python_version = python_version
        self.envs: dict[str, str] = {}

    @classmethod
    def debian_slim(cls, python_version: str | None = None):
        return cls(python_version=python_version)

    def apt_install(self, *pkgs: str):
        return self

    def run_commands(self, *cmds: str):
        return self

    def pip_install(self, *pkgs: str, **kwargs):
        return self

    def env(self, mapping: dict[str, str]):
        self.envs.update(mapping)
        return self


class _FakeApp:
    def __init__(self, name: str):
        self.name = name
        self.registry: list[str] = []

    def function(self, *args, **kwargs):
        def decorator(fn):
            self.registry.append(fn.__name__)
            return fn

        return decorator


class _FakeModal:
    App = _FakeApp
    Volume = _FakeVolume
    Image = _FakeImage

    @staticmethod
    def concurrent(**kwargs):
        def decorator(fn):
            return fn

        return decorator


@pytest.fixture(scope="module")
def modal_module():
    fake = _FakeModal()
    sys.modules["modal"] = fake
    yield fake
    sys.modules.pop("modal", None)


@pytest.fixture(scope="module")
def ace_step_modal_module(modal_module):
    return importlib.import_module("ace_step_modal")


def test_app_name_and_registry(ace_step_modal_module):
    assert ace_step_modal_module._APP.name == "avireon-music-platform-acestep"
    registered = set(ace_step_modal_module._APP.registry)
    assert "generate_full_song" in registered
    assert "separate_audio" in registered
    assert "preload_models" in registered


def test_image_env_checkpoints_dir(ace_step_modal_module):
    envs = ace_step_modal_module._IMAGE.envs
    assert envs["ACESTEP_CHECKPOINTS_DIR"] == "/models/ace-step"
    assert envs["ACESTEP_INIT_LLM"] == "true"


def test_volume_names(ace_step_modal_module):
    assert ace_step_modal_module._DATA_VOLUME.name == "avireon-music-platform-data-v1"
    assert ace_step_modal_module._MODEL_VOLUME.name == "avireon-music-platform-models-v1"


def test_no_legacy_defects_in_source():
    src = _MODULE_PATH.read_text(encoding="utf-8")
    forbidden = [
        "ace-step/acestep-v15-turbo",  # 不存在的错误 repo ID（401）
        "AutoProcessor.from_pretrained",  # 旧的非官方推理 API 具体调用
        "AutoModelForCausalLM.from_pretrained",
        "diT.generate(",
        "lm=lm",
        "soundhelix",
        "SoundHelix",
        "MOCK_AUDIO_URL",
        "MusicgenForConditionalGeneration",  # MusicGen 无关（防御）
    ]
    for token in forbidden:
        assert token not in src, f"源码仍包含被禁止的旧缺陷 token: {token!r}"
    # 官方模型/API 必须出现
    assert "ACE-Step/Ace-Step1.5" in src or "acestep-v15-turbo" in src
    assert "generate_music" in src
    assert "GenerationParams" in src
    assert "AceStepHandler" in src
    assert "LLMHandler" in src


def test_clamp_duration(ace_step_modal_module):
    clamp = ace_step_modal_module._clamp_duration
    assert clamp(30) == 30
    assert clamp(120) == 120
    assert clamp(180) == 180
    assert clamp(0) == 180
    assert clamp(-5) == 180
    assert clamp(5) == 10
    assert clamp(700) == 600
    assert clamp(None) == 180


def test_generation_params_contract(monkeypatch):
    captured = {}

    class FakeGenerationParams:
        def __init__(self, **kwargs):
            captured["params"] = kwargs

    import types

    acestep = types.ModuleType("acestep")
    inference_mod = types.ModuleType("acestep.inference")
    inference_mod.GenerationParams = FakeGenerationParams
    acestep.inference = inference_mod
    monkeypatch.setitem(sys.modules, "acestep", acestep)
    monkeypatch.setitem(sys.modules, "acestep.inference", inference_mod)

    module = importlib.import_module("ace_step_modal")
    module._build_generation_params("test prompt", "some lyrics", 120)
    assert captured["params"]["caption"] == "test prompt"
    assert captured["params"]["lyrics"] == "some lyrics"
    assert captured["params"]["instrumental"] is False
    assert captured["params"]["duration"] == 120.0
    assert captured["params"]["thinking"] is True

    module._build_generation_params("p", "", 60)
    assert captured["params"]["lyrics"] == ""
    assert captured["params"]["instrumental"] is True
    assert captured["params"]["duration"] == 60.0


def test_generation_config_contract(monkeypatch):
    captured = {}

    class FakeGenerationConfig:
        def __init__(self, **kwargs):
            captured["config"] = kwargs

    import types

    acestep = types.ModuleType("acestep")
    inference_mod = types.ModuleType("acestep.inference")
    inference_mod.GenerationConfig = FakeGenerationConfig
    acestep.inference = inference_mod
    monkeypatch.setitem(sys.modules, "acestep", acestep)
    monkeypatch.setitem(sys.modules, "acestep.inference", inference_mod)

    module = importlib.import_module("ace_step_modal")
    module._build_generation_config()
    assert captured["config"]["batch_size"] == 1
    assert captured["config"]["audio_format"] == "wav"
    assert captured["config"]["use_random_seed"] is True