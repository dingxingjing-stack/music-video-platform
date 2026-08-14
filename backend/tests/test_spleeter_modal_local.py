"""spleeter_modal 本地静态/单元测试（不触碰真实 Modal / 权重）。

通过 sys.modules 注入假 modal，验证：
  1. App 名、注册函数名、镜像 Python 版本与 env（SPLEETER_MODEL_PATH）
  2. 固定依赖版本（spleeter==2.4.2，tensorflow==2.12.1），容器不含 torch/demucs
  3. 卷名与 ACE-Step App 保持一致（共享数据卷/模型卷）
  4. 独立 App 的语义约束：不向 web 容器注入 spleeter/tensorflow
"""

import importlib
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "spleeter_modal.py"


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
        self.pip_packages: list[tuple[str, ...]] = []
        self.apt_packages: list[str] = []

    @classmethod
    def debian_slim(cls, python_version: str | None = None):
        return cls(python_version=python_version)

    def apt_install(self, *pkgs: str):
        self.apt_packages.extend(pkgs)
        return self

    def run_commands(self, *cmds: str):
        return self

    def pip_install(self, *pkgs: str, **kwargs):
        self.pip_packages.append(pkgs)
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
def spleeter_modal_module(modal_module):
    return importlib.import_module("spleeter_modal")


def test_app_name_and_registry(spleeter_modal_module):
    assert spleeter_modal_module._APP.name == "avireon-music-platform-spleeter"
    registered = set(spleeter_modal_module._APP.registry)
    assert "separate_audio" in registered
    assert "preload_models" in registered


def test_image_python_and_env(spleeter_modal_module):
    assert spleeter_modal_module._IMAGE.python_version == "3.11"
    envs = spleeter_modal_module._IMAGE.envs
    assert envs["SPLEETER_MODEL_PATH"] == "/models/spleeter"


def test_fixed_versions(spleeter_modal_module):
    all_pkgs = set()
    for group in spleeter_modal_module._IMAGE.pip_packages:
        all_pkgs.update(group)
    assert "spleeter==2.4.2" in all_pkgs
    assert "tensorflow==2.12.1" in all_pkgs


def test_volume_names_match_shared(spleeter_modal_module):
    assert spleeter_modal_module._DATA_VOLUME.name == "avireon-music-platform-data-v1"
    assert spleeter_modal_module._MODEL_VOLUME.name == "avireon-music-platform-models-v1"


def test_no_forbidden_tokens_in_source():
    src = _MODULE_PATH.read_text(encoding="utf-8")
    forbidden = [
        "import torch",  # 独立 App 不装 PyTorch（避免与 TensorFlow 冲突）
        "import demucs",  # 四轨分离不再依赖 Demucs
        "from demucs",
        "MusicgenForConditionalGeneration",
    ]
    for token in forbidden:
        assert token not in src, f"spleeter_modal 源码仍包含被禁止 token: {token!r}"
    assert "Separator" in src
    assert "spleeter:4stems" in src