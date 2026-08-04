"""
统一密钥读取入口。

读取优先级（从高到低）：
1. 进程环境变量（生产用 Render 环境变量注入、CI 注入等）
2. backend/secrets.local.json（开发本机，不入仓库）
3. backend/secrets.json（fallback，同样不入仓库）

若三层都拿不到：
- required=True  → 抛 RuntimeError，启动即可暴露配置问题
- required=False → 返回 None，由调用方自行处理

设计原则：
- 所有外部 API key / token / DSN 必须通过本模块获取，禁止在业务代码里写 os.getenv(key, "硬编码默认值")
- secrets.local.json 与 secrets.json 均被 .gitignore 屏蔽，永远不会被推送
- 本模块本身不含任何密钥字面值
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
候选文件 = [
    BACKEND_ROOT / "secrets.local.json",
    BACKEND_ROOT / "secrets.json",
]


def _read_secrets_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def load_all() -> dict:
    merged: dict = {}
    for path in 候选文件:
        merged.update(_read_secrets_file(path))
    return merged


def get_secret(key: str, required: bool = False, default: Optional[str] = None) -> Optional[str]:
    value: Optional[str] = os.getenv(key)
    if value:
        return value
    secrets = load_all()
    value = secrets.get(key)
    if value:
        return value
    if required and default is None:
        raise RuntimeError(
            f"[secrets] 缺失必要密钥 '{key}'。"
            f"请在环境变量、backend/secrets.local.json 或 backend/secrets.json 中提供。"
        )
    return default
