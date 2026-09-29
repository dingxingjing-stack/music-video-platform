"""假功能收口验收脚本（只读，不发真实生成请求）。

验证：
  1. main.py 可正常导入（删除重复 import 后未破坏模块）
  2. 三个"假功能"路由已从 OpenAPI 表消失，且 HTTP 返回 404
  3. 保留的路由仍在（social / poyo voice-clone / share / ai_music）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)
paths = set(app.openapi().get("paths", {}).keys())

print("=" * 68)
print("1) OpenAPI 路径表检查")
print("=" * 68)

RETIRED = [
    ("/api/v1/community/hot", "community 假榜单"),
    ("/api/v1/community/new", "community 假榜单"),
    ("/api/v1/collab/session", "collaboration 内存 Mock"),
    ("/api/v1/copyright/scan", "copyright 随机版权结论"),
    ("/api/v1/copyright/database", "copyright 随机版权结论"),
]
KEPT = [
    ("/api/v1/social/feed", "social（SQLite 真实持久化）"),
    ("/api/v1/voice-clone/validate", "poyo voice-clone（诚实 fail-closed 503）"),
    ("/api/v1/share/task/{task_id}", "分享签名令牌"),
]

fail = 0
for p, why in RETIRED:
    ok = p not in paths
    print(f"  [{'PASS' if ok else 'FAIL'}] 已下线 {p:42s} ({why})")
    fail += 0 if ok else 1

print()
for p, why in KEPT:
    ok = p in paths
    print(f"  [{'PASS' if ok else 'FAIL'}] 仍在册 {p:42s} ({why})")
    fail += 0 if ok else 1

print()
print("=" * 68)
print("2) 实际 HTTP 行为（未被其它路由意外兜住）")
print("=" * 68)
print("  注：main.py 在 '/' 挂了 StaticFiles（仅 GET/HEAD），因此对不存在路径的 POST")
print("      会被兜成 405 而非 404。下面用一条哨兵路径测出该基线，再要求已下线路径与之相同。")

# 哨兵：一条保证不存在的路径，测出"未注册路径"的基线状态码
_SENTINEL_POST = "/api/v1/__retired_sentinel_do_not_use__"
base_post = client.request("POST", _SENTINEL_POST, json={}).status_code
base_get = client.request("GET", _SENTINEL_POST).status_code
print(f"  基线：未注册路径 POST -> {base_post} / GET -> {base_get}")
print()

HTTP_CASES = [
    ("GET", "/api/v1/community/hot", base_get),
    ("GET", "/api/v1/copyright/database", base_get),
    ("POST", "/api/v1/collab/session", base_post),
    ("GET", "/api/v1/social/stats/probe-work-id", 200),
    ("POST", "/api/v1/social/like", 401),  # 无 JWT 必须 401（证明 social 仍受 JWT 保护）
    ("POST", "/api/v1/voice-clone/validate", 401),  # 无 JWT 先 401（未到 503 门禁）
]
for method, url, expect in HTTP_CASES:
    r = client.request(method, url, json={} if method == "POST" else None)
    ok = r.status_code == expect
    print(f"  [{'PASS' if ok else 'FAIL'}] {method:4s} {url:38s} -> {r.status_code} (期望 {expect})")
    fail += 0 if ok else 1

print()
print("=" * 68)
print(f"结果：{'全部通过' if fail == 0 else f'{fail} 项不通过'}")
print("=" * 68)
sys.exit(1 if fail else 0)
