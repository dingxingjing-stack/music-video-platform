"""P0-4-C Phase 2 — WORKFLOW_MODE 生产 Fail-Closed 测试（T1–T5）。

验证规则：
  production  + WORKFLOW_MODE=mock  -> 校验失败（T1）
  production  + WORKFLOW_MODE 缺失   -> 校验失败（T2）
  production  + WORKFLOW_MODE=real  -> 校验通过（T3）
  test 环境    + WORKFLOW_MODE=mock  -> 放行（pytest 正常）（T4）
  development 环境策略                -> 放行 / 允许 mock（T5）
"""
import os

import pytest

from app.services import workflow_mode


# ───────────── T1: production + mock -> fail ─────────────
def test_t1_production_mock_fails(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("WORKFLOW_MODE", "mock")
    with pytest.raises(RuntimeError, match="WORKFLOW_MODE"):
        workflow_mode.validate_workflow_mode_for_production()


def test_t1b_production_mock_fails_without_env(monkeypatch):
    """不污染 os.environ，直接用显式参数校验同规则。"""
    with pytest.raises(RuntimeError, match="WORKFLOW_MODE"):
        workflow_mode.validate_workflow_mode_for_production(environment="production", workflow_mode="mock")


# ───────────── T2: production + missing -> fail ─────────────
def test_t2_production_missing_fails(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("WORKFLOW_MODE", raising=False)
    with pytest.raises(RuntimeError, match="WORKFLOW_MODE"):
        workflow_mode.validate_workflow_mode_for_production()


def test_t2b_production_missing_fails_whitespace(monkeypatch):
    """显式传空/空白同样视为缺失 -> fail。"""
    with pytest.raises(RuntimeError, match="WORKFLOW_MODE"):
        workflow_mode.validate_workflow_mode_for_production(environment="production", workflow_mode="   ")


# ───────────── T3: production + real -> pass ─────────────
def test_t3_production_real_passes(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("WORKFLOW_MODE", "real")
    # 不抛异常即通过
    assert workflow_mode.validate_workflow_mode_for_production() is None


def test_t3b_production_real_passes_explicit():
    assert workflow_mode.validate_workflow_mode_for_production(environment="production", workflow_mode="real") is None


# ───────────── T4: test 环境 + mock -> 放行 ─────────────
def test_t4_test_mock_allowed(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("WORKFLOW_MODE", "mock")
    assert workflow_mode.validate_workflow_mode_for_production() is None


# ───────────── T5: development 策略 ─────────────
def test_t5_development_environment_strategy(monkeypatch):
    """development：不强制，缺省回落 mock，校验放行（与现有 main.py WORKFLOW_MODE 默认一致）。"""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("WORKFLOW_MODE", raising=False)
    # 运行时读取非生产允许回落 mock —— 与现有 get_workflow_mode 一致
    assert workflow_mode.get_workflow_mode() == "mock"
    assert workflow_mode.validate_workflow_mode_for_production() is None


def test_t5b_development_explicit_real_is_kept_real(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("WORKFLOW_MODE", "real")
    assert workflow_mode.get_workflow_mode() == "real"
    assert workflow_mode.validate_workflow_mode_for_production() is None


# ───────────── 辅助：is_production / production_workflow_mode ─────────────
def test_is_production_true(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert workflow_mode.is_production() is True


def test_is_production_false_by_default(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert workflow_mode.is_production() is False


def test_production_workflow_mode_missing_is_none(monkeypatch):
    monkeypatch.delenv("WORKFLOW_MODE", raising=False)
    assert workflow_mode.production_workflow_mode() is None