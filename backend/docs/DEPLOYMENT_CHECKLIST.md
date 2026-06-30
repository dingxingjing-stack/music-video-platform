# 生产环境部署清单 — Inference Service 重试强化

> **版本**: v2.0  
> **部署日期**: 2026-06-27  
> **负责人**: 运维团队 / 后端开发  
> **回滚方案**: 见文末

---

## 一、部署前检查

### 1.1 代码与依赖

- [ ] 确认 `base.py` 和 `gradio_mixins.py` 已合并最新代码
- [ ] 确认 `test_inference_retry.py` 和 `tests/test_inference.py` 全部 53 项通过
- [ ] 确认 `pyproject.toml` 中 `asyncio_mode = "auto"` 已设置
- [ ] 确认已安装依赖：
  ```bash
  pip install httpx pytest pytest-asyncio
  ```

### 1.2 环境变量检查

| 变量名 | 必填 | 说明 | 默认值 | 验证命令 |
|---|---|---|---|---|
| `GPT_SOVITS_SPACE_URL` | ✅ | GPT-SoVITS TTS 服务的 HF Space URL | — | `echo $GPT_SOVITS_SPACE_URL` |
| `MUSICGEN_SPACE_URL` | ✅ | MusicGen 的 HF Space URL | — | `echo $MUSICGEN_SPACE_URL` |
| `COGVIDEOX_SPACE_URL` | ✅ | CogVideoX 的 HF Space URL | — | `echo $COGVIDEOX_SPACE_URL` |
| `GPT_SOVITS_API_TOKEN` | ⚠️ | HF API Token（私有 Space 必需） | 无 | `echo $GPT_SOVITS_API_TOKEN \| wc -c` |
| `MUSICGEN_API_TOKEN` | ⚠️ | MusicGen API Token | 无 | — |
| `COGVIDEOX_API_TOKEN` | ⚠️ | CogVideoX API Token | 无 | — |

**验证脚本：**
```bash
#!/bin/bash
# pre_deploy_check.sh
set -euo pipefail

echo "=== 环境变量检查 ==="
for var in GPT_SOVITS_SPACE_URL MUSICGEN_SPACE_URL COGVIDEOX_SPACE_URL; do
    if [ -z "${!var:-}" ]; then
        echo "❌ 缺失: $var"
        exit 1
    fi
    echo "✅ $var = ${!var}"
done

echo ""
echo "=== 端口检查 ==="
ss -tlnp | grep -E ':(8000|8080)' || echo "⚠️ 未检测到监听端口（预期内）"

echo ""
echo "=== Python 版本 ==="
python --version

echo ""
echo "=== 依赖检查 ==="
python -c "import httpx; print(f'httpx {httpx.__version__}')"
python -c "import pytest; print(f'pytest {pytest.__version__}')"
```

### 1.3 健康检查端点

- [ ] 确认 HF Space 可访问性：
  ```bash
  curl -s -o /dev/null -w "%{http_code}" https://<space-url>.hf.space/health
  # 预期: 200 (健康) 或 503 (休眠，属正常)
  ```
- [ ] 确认 API Token 有效：
  ```bash
  curl -s -H "Authorization: Bearer $GPT_SOVITS_API_TOKEN" \
    https://<space-url>.hf.space/api/predict \
    -d '{"session_hash":"test","event_data":[],"fn_index":0}'
  ```

---

## 二、监控告警配置

### 2.1 关键日志模式

以下结构化日志项应配置为监控指标：

| 日志模式 | 级别 | 告警阈值 | 说明 |
|---|---|---|---|
| `event=cold_start` | INFO | 连续出现 > 5 次/分钟 | Space 频繁休眠，考虑预热 |
| `event=network_retry` | INFO | 连续出现 > 10 次/分钟 | 网络不稳定，检查 HF Space 区域 |
| `event=read_timeout` | INFO | 连续出现 > 3 次/分钟 | 推理耗时过长，检查 GPU 负载 |
| `event=http_5xx` | WARNING | 任意出现 | HF Space 服务端错误 |
| `event=permanent_error` | ERROR | 任意出现 | 4xx 客户端错误，需排查输入 |
| `event=unknown_transient` | ERROR | 任意出现 | 未知异常，需人工介入 |
| `event=network_retry` + `NETWORK_RETRY_EXHAUSTED` | ERROR | 任意出现 | 网络重试耗尽，任务失败 |
| `event=cold_start` + `COLD_START_EXHAUSTED` | ERROR | 任意出现 | 冷启动重试耗尽 |
| `event=permanent_error` + `PERMANENT_ERROR` | ERROR | 任意出现 | 永久错误，不重试 |

### 2.2 Prometheus 指标建议

```yaml
# 推荐新增的 metrics
inference_retry_total{service_type="tts|music|video", error_type="connect_error|read_timeout|cold_start"}
inference_cold_start_duration_seconds{service_type="tts|music|video"}
inference_task_status_total{service_type="tts|music|video", status="completed|failed|cancelled"}
inference_poll_timeout_total{service_type="tts|music|video"}
```

### 2.3 Grafana 看板面板

| 面板名称 | 查询 | 用途 |
|---|---|---|
| 任务成功率 | `rate(inference_task_status_total{status="completed"}[5m])` | 整体健康度 |
| 冷启动频率 | `rate(inference_retry_total{error_type="cold_start"}[5m])` | Space 休眠频率 |
| 网络错误率 | `rate(inference_retry_total{error_type="connect_error"}[5m])` | 网络稳定性 |
| 平均重试次数 | `histogram_quantile(0.95, ...)` | 重试压力 |
| 超时任务数 | `rate(inference_poll_timeout_total[5m])` | 轮询超时 |

---

## 三、部署步骤

### 3.1 灰度发布

```bash
# Step 1: 部署到 staging 环境
cd /path/to/music-video-platform/backend
export PATH="/c/Users/dingx/AppData/Local/Programs/Python/Python312:$PATH"

# 运行完整测试套件
python -m pytest test_inference_retry.py tests/test_inference.py -v

# Step 2: 重启 staging 服务
systemctl restart inference-service-staging
# 或
docker compose -f docker-compose.staging.yml up -d

# Step 3: 执行烟雾测试（见第四节）
```

### 3.2 生产发布

```bash
# Step 4: 滚动更新生产实例
kubectl rollout restart deployment/inference-service
# 或
docker compose -f docker-compose.prod.yml up -d --no-deps inference-service

# Step 5: 观察日志 5 分钟
tail -f /var/log/inference-service/app.log | grep -E "event=|FAILED"
```

---

## 四、发布后烟雾测试

按顺序执行以下检查，全部通过方可视为部署成功：

### 4.1 服务可达性

```bash
# 1. 确认服务进程存活
curl -s http://localhost:8000/health | jq .
# 预期: {"status": "ok"}

# 2. 确认工厂能创建所有服务实例
curl -s http://localhost:8000/api/v1/services | jq '.types'
# 预期: ["tts", "music", "video"]
```

### 4.2 健康检查

```bash
# 3. 验证 HF Space 连通性
curl -s http://localhost:8000/api/v1/health/tts
# 预期: {"healthy": true/false, "message": "..."}

# 4. 验证冷启动检测
curl -s http://localhost:8000/api/v1/health/music
# 若返回 503 → 正常（Space 休眠，下次请求会触发冷启动）
```

### 4.3 端到端预测

```bash
# 5. TTS 短文本合成（快速验证）
curl -X POST http://localhost:8000/api/v1/predict/tts \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "smoke-tts-001",
    "text": "测试",
    "reference_audio": "<base64_encoded_wav>",
    "language": "zh"
  }'
# 预期: {"task_id": "smoke-tts-001", "status": "pending"}

# 6. 轮询 TTS 结果
curl -s http://localhost:8000/api/v1/tasks/smoke-tts-001 | jq '.status'
# 预期: "completed"（约 1-3 分钟内）

# 7. Music 短片段生成
curl -X POST http://localhost:8000/api/v1/predict/music \
  -H "Content-Type: application/json" \
  -d '{"task_id": "smoke-music-001", "prompt": "test", "duration": 5.0}'
# 预期: {"task_id": "smoke-music-001", "status": "pending"}

# 8. 验证广播回调（WebSocket）
# 连接 ws://localhost:8000/ws/tasks 并观察进度推送
# 预期: 收到 PENDING → LOADING → RUNNING → COMPLETED 序列
```

### 4.4 故障注入验证（可选）

```bash
# 9. 故意发送无效请求，验证 FAILED 封装
curl -X POST http://localhost:8000/api/v1/predict/tts \
  -H "Content-Type: application/json" \
  -d '{"task_id": "smoke-fail-001", "text": "no-audio"}'
# 预期: 返回 FAILED + 结构化 error 消息，进程不崩溃
```

---

## 五、回滚方案

### 5.1 一键回滚

```bash
# Kubernetes
kubectl rollout undo deployment/inference-service

# Docker Compose
docker compose -f docker-compose.prod.yml up -d --no-deps inference-service
# （假设使用了镜像标签管理版本）

# 直接部署
git checkout <previous-commit-hash>
pip install -r requirements.txt
systemctl restart inference-service
```

### 5.2 回滚触发条件

- [ ] TTS/Music/Video 预测成功率下降 > 5%
- [ ] 冷启动重试日志量超过基线 3 倍
- [ ] WebSocket 广播回调超时率上升
- [ ] 任何未处理的异常导致进程退出

### 5.3 回滚后验证

执行第四节「烟雾测试」的全部步骤，确认服务恢复到稳定状态。

---

## 六、部署后观察期

| 时间 | 检查项 | 负责人 |
|---|---|---|
| +5 min | 服务进程存活、健康检查通过 | 自动 |
| +15 min | 冷启动日志频率、网络重试计数 | 运维 |
| +30 min | 端到端预测成功率 | QA |
| +1 hr | Grafana 看板数据、异常告警 | 运维 |
| +4 hr | 全量任务成功率趋势 | 后端 |
| +24 hr | 长期稳定性确认，关闭观察模式 | 全员 |
