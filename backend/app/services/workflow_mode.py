"""
WORKFLOW_MODE 生产 Fail-Closed 校验 — P0-4-C

背景：
- workflow router（/api/v1/workflow/a|b|c|d）依据 `WORKFLOW_MODE` 决定是否走真实 HF Space
  服务（real）还是被裁剪的模拟服务（mock）。
- 生产（ENVIRONMENT=production）若允许 `WORKFLOW_MODE=mock` 或缺失时启动，会导致
  真实业务路由以 mock 模式运行：跳过 quota 预留、返回假音频/不调用真实 provider —— 属 P0 风险。

设计原则（复用项目现有环境机制，不新建 ENVIRONMENT 之外的变量）：
- 权威环境标识 = `ENVIRONMENT`（database.py 已有：默认 development，production 时强制 PostgreSQL）。
- 本项目已有同类 validate_production() 惯用法（r2_config.validate_production）：
  生产下对关键配置校验失败即 raise RuntimeError 拒绝启动。本函数沿用同一风格。

规则：
- production + WORKFLOW_MODE == "real"        → 允许（正常生产）
- production + WORKFLOW_MODE == "mock"        → 启动失败（RuntimeError）
- production + WORKFLOW_MODE 缺失/为空         → 启动失败（RuntimeError），禁止回落 mock
- development / test（ENVIRONMENT != production）→ 不强制（允许 mock，供单元/集成测试与本地开发）
"""
from __future__ import annotations

import os


def is_production() -> bool:
    """项目既定的环境判定：ENVIRONMENT=production 即生产。默认 development。"""
    return (os.getenv("ENVIRONMENT") or "development").lower() == "production"


def production_workflow_mode() -> str | None:
    """生产应从环境读取 WORKFLOW_MODE 的原始值（缺失回 None，绝不隐式默认 mock）。"""
    raw = os.getenv("WORKFLOW_MODE")
    return raw.strip().lower() if raw and raw.strip() else None


def validate_workflow_mode_for_production(
    environment: str | None = None,
    workflow_mode: str | None = None,
) -> None:
    """
    生产环境 Fail-Closed 校验：WORKFLOW_MODE 必须显式为 real。

    接受显式参数（便于单测，不污染 os.environ）：
      - environment: 覆盖读取的 ENVIRONMENT（默认从 os.environ 读取）
      - workflow_mode: 覆盖读取的 WORKFLOW_MODE（默认从 os.environ 读取，缺失=None）

    只有 production 才强制；development/test 一律放行。
    """
    env = (environment or os.getenv("ENVIRONMENT") or "development").lower()
    # 非生产：不强制（test/development 允许 mock）
    if env != "production":
        return
    # 生产：FAIL-CLOSED
    mode = workflow_mode if workflow_mode is not None else production_workflow_mode()
    if mode != "real":
        raise RuntimeError(
            "[workflow_mode] ENVIRONMENT=production 但 WORKFLOW_MODE 不是 'real' "
            f"(当前 {mode!r})。生产禁止以 mock/缺失模式启动：必须显式设置 WORKFLOW_MODE=real。"
        )


def get_workflow_mode(workflow_mode: str | None = None) -> str:
    """
    运行时统一读取 WORKFLOW_MODE（非生产允许回落 mock）。
    供 workflow_router 等消费方使用，保证单一读取来源。
    """
    if workflow_mode is not None:
        return workflow_mode.strip().lower()
    return (os.getenv("WORKFLOW_MODE") or "mock").lower()