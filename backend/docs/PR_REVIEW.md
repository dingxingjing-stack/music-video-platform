# Pull Request: 强化 BaseInferenceService 重试与冷启动处理

## 📋 变更概述

| 项目 | 详情 |
|---|---|
| **仓库** | music-video-platform |
| **模块** | `app/services/inference/` |
| **涉及文件** | `base.py`, `gradio_mixins.py` |
| **测试文件** | `test_inference_retry.py`（新增）, `tests/test_inference.py`（更新） |
| **测试通过率** | 53 / 53 (100%) |

---

## 🔍 变更背景

### 问题描述

在原有实现中，`GradioSpaceMixin._submit_gradio_prediction()` 内部使用 `try/except` 吞掉了所有网络异常（`httpx.ConnectError`、`httpx.ReadTimeout`），并统一返回 `{"_sleeping": True}`。这导致：

1. **网络异常无法被基类捕获** — `BaseInferenceService.predict()` 的 `except httpx.ConnectError` 分支永远不会被执行，因为异常在 mixin 层就被静默消化了。
2. **重试策略不完整** — 只有冷启动重试（`_do_submit` 返回 `None`）生效，网络层重试形同虚设。
3. **无法区分故障类型** — 真正的网络连接失败和正常的冷启动被混为一谈，日志缺乏结构化信息。

### 目标

将网络异常的**决策权**交还给 `BaseInferenceService.predict()`，由其统一执行双层指数退避重试策略。

---

## 🛠 关键代码修改点

### 1. `gradio_mixins.py` — 异常冒泡

**修改前：**
```python
async def _submit_gradio_prediction(...):
    try:
        resp = await client.post(...)
        ...
    except httpx.ConnectError:
        return {"_sleeping": True}   # ❌ 吞掉异常
    except httpx.ReadTimeout:
        return {"_sleeping": True}   # ❌ 吞掉异常
    except Exception as exc:
        return {"_error": ...}
```

**修改后：**
```python
async def _submit_gradio_prediction(...):
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(...)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 503:
            return {"_sleeping": True}  # ✅ 仅 503 表示冷启动
        resp.raise_for_status()         # ✅ 其他异常自然冒泡
```

关键变化：
- 移除顶层 `try/except`，让 `httpx` 原生异常直接向上抛出
- 仅保留 503 的特殊处理（Space 主动报告休眠状态）
- 非 200/503 响应通过 `raise_for_status()` 转为 `HTTPStatusError` 冒泡

### 2. `base.py` — predict() 双层重试循环增强

**新增：`max_network_retries` 上限保护**
```python
except httpx.ConnectError as exc:
    net_attempt += 1
    if net_attempt > self.retry_config.max_network_retries:
        return self._make_failed_result(...)  # ✅ 防止无限重试
```

**新增：`event_url` 初始化 + 兜底检查**
```python
event_url: Optional[str] = None  # ✅ 避免 UnboundLocalError
...
if event_url is None:
    return self._make_failed_result(...)  # ✅ 兜底 FAILED
```

**新增：`_report()` 覆盖所有 FAILED 返回路径**
```python
# 所有 FAILED 返回路径统一先调用 _report() 再 return
failed = self._make_failed_result(...)
await self._report(failed)
return failed
```

### 3. 结构化冷启动日志

```python
# 人类可读
logger.info("[task-xxx] Cold-start detected, Space sleeping. Attempt 1/3, next wait 60s")

# 机器可读（供 ELK/Datadog 等解析）
logger.info("task_id=xxx event=cold_start attempt=1 max_attempts=3 wait_seconds=60.0")
```

---

## ✅ 测试场景验证结果

### 独立重试测试 (`test_inference_retry.py`)

| # | 测试场景 | 验证内容 | 结果 |
|---|---|---|---|
| 1 | `ConnectError` 连续 3 次 | 指数退避 (1ms→2ms→4ms) + `FAILED` + `NETWORK_RETRY_EXHAUSTED` | ✅ PASS |
| 2 | `ConnectError` 后恢复 | 2 次失败后第 3 次成功 → 进入轮询 → `COMPLETED` | ✅ PASS |
| 3 | 冷启动 `None` 3 次 | 60s→120s→240s 退避 + `COLD_START_EXHAUSTED` | ✅ PASS |
| 4 | 冷启动后恢复 | 2 次 `None` 后返回 URL → 轮询成功 → `COMPLETED` | ✅ PASS |
| 5 | 混合故障 | `ConnectError` → `None` → `None` → 成功 | ✅ PASS |

### 回归测试 (`tests/test_inference.py`)

| 类别 | 用例数 | 通过数 | 备注 |
|---|---|---|---|
| Factory 创建 | 15 | 15 | 含别名映射、缓存、广播注入 |
| 预测契约 | 7 | 7 | 含缺失参数校验 |
| 冷启动流程 | 6 | 6 | 含结构化错误码验证 |
| 结果契约 | 8 | 8 | 含 `to_dict`、向后兼容 |
| 错误分类 | 5 | 5 | 含 `PoolTimeout` 修复 |
| 重试配置 | 3 | 3 | 含边界值 capped |
| 注册表/别名 | 3 | 3 | — |
| 取消 | 1 | 1 | — |
| **总计** | **48** | **48** | **0 回归** |

---

## 📊 生产稳定性影响

### 正面影响

1. **消除静默失败** — 网络异常不再被吞掉，重试策略真正生效
2. **可观测性提升** — 结构化日志支持自动化告警和故障定位
3. **防御性编程** — 所有重试耗尽路径统一返回 `PredictResult(Failed)`，永不抛异常中断进程
4. **上限保护** — `max_network_retries` 防止无限重试导致的资源泄漏

### 潜在风险

1. **冷启动等待时间较长** — 默认 60s→120s→240s，单次任务最长等待 420s。可通过 `RetryConfig` 调优或 `max_wait` 参数控制。
2. **广播回调增加** — 每个重试节点都会触发 `_report()`，WebSocket 连接数多时需关注广播性能。

### 向后兼容性

- ✅ 所有公开 API 签名未变
- ✅ 子类 `_build_payload` / `_do_submit` / `_parse_response` 契约未变
- ✅ `PredictResult` 新增字段均有默认值
- ✅ `GradioSpaceMixin.__init__` MRO 链未变

---

## 📝  reviewer 注意事项

- `gradio_mixins.py` 的 `_submit_gradio_prediction` 现在是**裸调用**，不再有内部 `try/except`
- 所有 `FAILED` 返回路径均已添加 `_report()` 调用，确保前端能收到最终状态
- `max_network_retries` 参数现在在 `predict()` 中被实际检查（此前虽定义但未使用）
