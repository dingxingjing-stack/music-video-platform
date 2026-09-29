#!/usr/bin/env python3
"""i18n key-parity report —— 只读，不写任何文件。

把 en.json 作为基准，统计每个目标语言：
  - translated   : key 存在，且值不为空、且不等于英文原文（= 真译文）
  - untranslated : key 缺失，或值仍等于英文（= 运行时回退英文，gap 可见）
  - coverage     : translated / en 叶子 key 总数

用法：
    cd frontend && python src/i18n/parity_check.py
或直接运行本文件（基准目录自动定位，不依赖当前工作目录）。

设计说明（为什么不整份复制 en.json）：
  缺失的 key 会由 useTranslation.ts 的 en fallback 兜住；若把英文复制进去，
  <html lang="hi"> 会挂着英文正文 —— 搜索引擎按印地语索引、屏幕阅读器选错发音，
  且再也看不出哪些没译。所以"未译"必须是可见指标，而不是被占位文件藏起来。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
BASE = "en"
TARGETS = ["hi", "id", "ar"]
PREVIEW = 5  # 每种语言打印多少条"待译"样例


def load(name: str) -> dict:
    """加载 locale JSON；文件不存在直接报明确错误（不静默跳过）。"""
    path = LOCALES_DIR / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"[parity] 缺少 locale 文件：{path}")
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[parity] {path.name} 不是合法 JSON：{exc}")


def leaves(obj: dict, prefix: str = ""):
    """递归展开嵌套 dict，产出 (点分 key, 叶子值)。"""
    for key, value in obj.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from leaves(value, full)
        else:
            yield full, value


def main() -> int:
    en_keys = dict(leaves(load(BASE)))
    total = len(en_keys)

    print(f"i18n parity report — 基准 {BASE}.json（{total} 个叶子 key）")
    print("=" * 64)
    print(f"{'locale':<8}{'translated':>12}{'untranslated':>14}{'coverage':>11}")
    print("-" * 64)

    for loc in TARGETS:
        cur = dict(leaves(load(loc)))
        translated = 0
        pending: list[str] = []

        for key, en_value in en_keys.items():
            value = cur.get(key)
            # 只認「非空字符串 且 不等于英文原文」为真译文
            if isinstance(value, str) and value.strip() and value != en_value:
                translated += 1
            else:
                pending.append(key)

        missing = total - translated
        pct = (translated / total * 100) if total else 0.0
        print(f"{loc:<8}{translated:>12}{missing:>14}{pct:>10.1f}%")

        if pending:
            preview = ", ".join(pending[:PREVIEW])
            more = "" if len(pending) <= PREVIEW else f" （共 {len(pending)} 条）"
            print(f"         待译样例: {preview}{more}")

    print("=" * 64)
    print("说明：缺失或仍为英文的 key 会在运行时回退 en.json —— 这是预期行为。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
