"""gpt_sovits_modal 本地静态/单元测试（不触碰真实 Modal / 权重 / GPU）。

通过 sys.modules 注入假 modal，验证：
  1. App 名、注册函数名、镜像 Python 版本与 env
  2. 锁定官方 repo commit / 权重来源（lj1995/GPT-SoVITS）
  3. 卷名与 ACE-Step/Spleeter App 保持一致（共享数据卷/模型卷）
  4. 推理后端复用官方 api.py（不重写核心）：子进程启动参数指向 /gpt-sovits/api.py
  5. 输出与参考音频目录分离（/root/data/generated vs /root/data/refs）
  6. 源码不包含被禁止的自行推理实现 token
"""

import importlib
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "gpt_sovits_modal.py"


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
        self.run_commands_list: list[tuple[str, ...]] = []

    @classmethod
    def debian_slim(cls, python_version: str | None = None):
        return cls(python_version=python_version)

    def apt_install(self, *pkgs: str):
        self.apt_packages.extend(pkgs)
        return self

    def run_commands(self, *cmds: str):
        self.run_commands_list.append(cmds)
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
def gpt_sovits_modal_module(modal_module):
    return importlib.import_module("gpt_sovits_modal")


def test_app_name_and_registry(gpt_sovits_modal_module):
    assert gpt_sovits_modal_module._APP.name == "avireon-music-platform-gptsovits"
    registered = set(gpt_sovits_modal_module._APP.registry)
    assert "synthesize_cloned" in registered
    assert "preload_models" in registered


def test_image_python_and_env(gpt_sovits_modal_module):
    assert gpt_sovits_modal_module._IMAGE.python_version == "3.11"
    envs = gpt_sovits_modal_module._IMAGE.envs
    assert envs["PYTHONIOENCODING"] == "utf-8"


def test_repo_pinned_commit(gpt_sovits_modal_module):
    assert gpt_sovits_modal_module._REPO_URL == "https://github.com/RVC-Boss/GPT-SoVITS"
    assert len(gpt_sovits_modal_module._REPO_COMMIT) == 40
    cmd_lines = [
        line
        for group in gpt_sovits_modal_module._IMAGE.run_commands_list
        for line in group
    ]
    pinned = any(gpt_sovits_modal_module._REPO_COMMIT in c for c in cmd_lines)
    assert pinned, "镜像构建必须锁定官方 repo commit"


def test_weights_repo_source(gpt_sovits_modal_module):
    assert gpt_sovits_modal_module._WEIGHTS_REPO == "lj1995/GPT-SoVITS"
    src = _MODULE_PATH.read_text(encoding="utf-8")
    assert "License: mit" in src
    assert "snapshot_download" in src


def test_volume_names_match_shared(gpt_sovits_modal_module):
    assert gpt_sovits_modal_module._DATA_VOLUME.name == "avireon-music-platform-data-v1"
    assert gpt_sovits_modal_module._MODEL_VOLUME.name == "avireon-music-platform-models-v1"


def test_ref_and_output_dirs_separate(gpt_sovits_modal_module):
    assert gpt_sovits_modal_module._REF_DIR != gpt_sovits_modal_module._OUT_DIR
    assert gpt_sovits_modal_module._REF_DIR == "/root/data/refs"
    assert gpt_sovits_modal_module._OUT_DIR == "/root/data/generated"


def test_reuses_official_api_not_self_impl(gpt_sovits_modal_module):
    """推理后端必须是官方 api.py 子进程，禁止自行实现推理核心。"""
    src = _MODULE_PATH.read_text(encoding="utf-8")
    assert '"python", "api.py"' in src or "'python', 'api.py'" in src
    assert 'cwd="/gpt-sovits"' in src
    forbidden = [
        "Text2SemanticLightningModule",  # 官方模型类，禁止在本文件重新导入实例化
        "SynthesizerTrn",
        "infer_panel",
        "torch.no_grad",
    ]
    for token in forbidden:
        assert token not in src, f"gpt_sovits_modal 不应自行实现推理核心: {token!r}"


def test_api_payload_matches_official_protocol(gpt_sovits_modal_module):
    """POST 字段必须与官方 api.py 的 / 端点一致。"""
    src = _MODULE_PATH.read_text(encoding="utf-8")
    for key in ("refer_wav_path", "prompt_text", "prompt_language", "text", "text_language"):
        assert f'"{key}"' in src
    assert "resp.status_code != 200" in src
    assert "_DATA_VOLUME.commit()" in src
