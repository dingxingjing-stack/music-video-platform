"""P5-B.8 / P5-B.9：/api/v1/workflow/* 与 /api/v1/batch/* 端点退休守卫。

本文件原用于验证 workflow 四条路径在 mock / real 两种 WORKFLOW_MODE 下的额度预占、
429 拒绝、锁抢占失败与退款路径。P5-B 起这些端点在 HTTP 边界统一返回 410 Gone，
那些路径不再可能经由 HTTP 触达，故保留同名文件、改为端点退休守卫，防止"先返回
started 再在后台失败"的假成功回归。

未删除的部分：`app/services/workflow.py`（WorkflowEngine 及其配额逻辑）与
`app/services/batch_router.py` 中的路由模块本体仍在仓库内，物理清理归 P5-C/P6。
真实生歌链路是 POST /api/v1/ai/generate（Yinchao → TemPolor），与这些端点无关。
"""

from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
    from main import app
except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover
    pytest.skip(f"Skipping retirement tests: {exc}", allow_module_level=True)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("path", ["a", "b", "c", "d"])
def test_workflow_paths_are_retired(client, path):
    """workflow/a~d 必须 410，且不得再创建任务或预占额度。"""
    resp = client.post(
        f"/api/v1/workflow/{path}",
        json={"prompt": "x", "tts_text": "y", "duration": 5.0},
    )
    assert resp.status_code == 410, f"{path} -> {resp.status_code}: {resp.text}"


@pytest.mark.parametrize("path", ["a", "b"])
def test_batch_paths_are_retired(client, path):
    """batch/a|b 原为 self-declared stub（返回 started 但无队列），必须 410。"""
    resp = client.post(
        f"/api/v1/batch/{path}",
        json={"prompts": ["x"], "items": [{"prompt": "x", "tts_text": "y"}]},
    )
    assert resp.status_code == 410, f"{path} -> {resp.status_code}: {resp.text}"


def test_batch_status_is_retired(client):
    """batch/status 原恒返回 queue=0/active=0，必须 410。"""
    resp = client.get("/api/v1/batch/status/any-task-id")
    assert resp.status_code == 410, resp.text
