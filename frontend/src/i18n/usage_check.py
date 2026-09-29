"""只读分析：把 en.json 的全量 key 与「代码里真实引用的 key」做交叉，按命名空间统计覆盖率。

用途：全量 1544 个 key 里混着大量已下线/未完成功能的文案（stems / midi / voice clone /
batch / workflow / 假社区 / 假版权检测 / mock 一键发布…）。盲目补齐它们既浪费翻译预算，
也会把死功能"翻译得更像真的"。先看清哪些 key 真会被渲染，再决定翻什么。

用法： python src/i18n/usage_check.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

LOCALES = Path(__file__).parent / "locales"
SRC = Path(__file__).parent.parent  # frontend/src

# t('a.b') / t("a.b") —— 只取字面量；动态拼接（t(`x.${k}`)）单独统计为 dynamic
LITERAL = re.compile(r"""\bt\(\s*['"]([A-Za-z0-9_.\-]+)['"]""")
DYNAMIC = re.compile(r"""\bt\(\s*`""")


def flatten(obj: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out


def main() -> None:
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    en_flat = flatten(en)

    used: set[str] = set()
    dynamic = 0
    for f in SRC.rglob("*"):
        if f.suffix not in {".ts", ".tsx"} or f.name.endswith(".d.ts"):
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        used.update(LITERAL.findall(text))
        dynamic += len(DYNAMIC.findall(text))

    used_in_en = {k for k in used if k in en_flat}
    ghost = sorted(k for k in used if k not in en_flat)  # 引用了但 en 里没有 → 一定是 en 回退

    print("i18n 实际使用率分析")
    print("=" * 68)
    print(f"en.json 叶子 key 总数        : {len(en_flat)}")
    print(f"代码里字面量引用 key 数      : {len(used)}")
    print(f"  其中 en.json 里存在        : {len(used_in_en)}")
    print(f"  引用了但 en 里缺失(ghost)  : {len(ghost)}")
    print(f"动态拼接 t(`...`) 次数       : {dynamic}")
    print()

    # 按命名空间分组
    def ns(key: str) -> str:
        return key.split(".")[0] if "." in key else key

    by_ns_total: dict[str, int] = defaultdict(int)
    for k in en_flat:
        by_ns_total[ns(k)] += 1
    by_ns_used: dict[str, int] = defaultdict(int)
    for k in used_in_en:
        by_ns_used[ns(k)] += 1

    targets = ["hi", "id", "ar"]
    cov: dict[str, dict[str, int]] = {}
    for loc in targets:
        flat = flatten(json.loads((LOCALES / f"{loc}.json").read_text(encoding="utf-8")))
        cov[loc] = flat

    print(f"{'namespace':<16}{'en总数':>7}{'代码引用':>9}"
          + "".join(f"{l+'已译':>9}" for l in targets)
          + f"{'hi覆盖':>9}")
    print("-" * 68)
    rows = []
    for n in sorted(by_ns_total, key=lambda x: -by_ns_total[x]):
        keys = [k for k in en_flat if ns(k) == n]
        u = by_ns_used.get(n, 0)
        row = [n, len(keys), u]
        for l in targets:
            row.append(sum(1 for k in keys if k in cov[l]))
        rows.append(row)
    for r in sorted(rows, key=lambda r: (-r[2], -r[1])):
        total, used_n, hi_n = r[1], r[2], r[3]
        pct = f"{hi_n / total * 100:.0f}%" if total else "-"
        print(f"{r[0]:<16}{total:>7}{used_n:>9}" + "".join(f"{r[3 + i]:>9}" for i in range(3)) + f"{pct:>9}")

    print()
    # 关键结论：只统计"代码真正会用到"的 key 的三语覆盖
    print("只看「代码真实引用」的 key：")
    for l in targets:
        done = sum(1 for k in used_in_en if k in cov[l])
        print(f"  {l}: {done}/{len(used_in_en)} = {done / len(used_in_en) * 100:.1f}%")
    print(f"  （en 全量口径下：hi {len([k for k in en_flat if k in cov['hi']])}/{len(en_flat)}）")

    if ghost:
        print()
        print(f"ghost key 样例（前 15）：{ghost[:15]}")


if __name__ == "__main__":
    main()
