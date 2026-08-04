### 命令 1 健康探测（首次）

```
HTTP_STATUS:200
TIME_TOTAL:211.385697s

Response:
{"status":"ok","timestamp":"2026-07-21T17:49:18.829635Z","services":{"tts":{"healthy":true,"message":"Mock tts service ready"},"music":{"healthy":true,"message":"Mock music service ready"},"video":{"healthy":true,"message":"Mock video service ready"}}}

现象：实例刚被唤醒，请求耗时 211 秒；状态码 200；服务以 Mock 模式就绪。
判定：A1 健康检查通过；同时确认实例处于冷启动唤醒状态。
```

### 命令 2 模型列表查询（首次）

```
HTTP_STATUS:200
TIME_TOTAL:0.354212s

Response:
{"models":["htdemucs","htdemucs_ft","htdemucs_6s"],"model_descriptions":{"htdemucs":"高性能混合 Transformer Demucs (推荐)","htdemucs_ft":"微调版 (音质更好，速度慢)","htdemucs_6s":"6 轨分离 (加钢琴/吉他)"}}

现象：返回 3 个模型，无 ["mock"] 降级。
判定：A2 模型列表正确 → demucs 已正确安装、依赖链路完整。
```

### 命令 3-A 首次分离（第 1 次尝试）

```
HTTP_STATUS:502
TIME_TOTAL:5.357962s

Response: Render Bad Gateway HTML 页面
  Request ID: a1ec146ebb43f94d-SEA
  "This service is currently unavailable."

现象：实例刚唤醒未稳定，立即 502；后端未真正处理。
判定：实例未就绪，并非真正分离失败；按中断恢复规则等待恢复。
```

### 命令 1 健康探测（第 1 次失败后立即）

```
HTTP_STATUS:502
TIME_TOTAL:0.453952s

Response: Render Bad Gateway HTML 页面
现象：实例仍然崩溃中。
```

### 命令 1 健康探测（休眠 120 秒后）

```
HTTP_STATUS:502
TIME_TOTAL:1.565146s

Response: Render Bad Gateway HTML 页面
现象：等待 120 秒实例未自动恢复。
```

### 命令 1 健康探测（再休眠 180 秒后）

```
HTTP_STATUS:200
TIME_TOTAL:0.723219s

Response: {"status":"ok","timestamp":"2026-07-21T18:01:50.849939Z","services":{"tts":{"healthy":true,...},"music":{"healthy":true,...},"video":{"healthy":true,...}}}

现象：实例已自动恢复，耗时 0.72 秒（热响应）。
判定：触发【测试中断恢复规则】返回阶段 1 从头重测。
```

### 命令 2 模型列表查询（恢复后）

```
HTTP_STATUS:200
TIME_TOTAL:0.794221s

Response:
{"models":["htdemucs","htdemucs_ft","htdemucs_6s"]}（同首次）

判定：阶段 1 通过，可进入阶段 2。
```

### 命令 3-A 首次分离（第 2 次尝试，恢复后）

```
HTTP_STATUS:502
TIME_TOTAL:65.365341s

Response: Render Bad Gateway HTML 页面
  Request ID: a1ec201469591f86-SEA
  "This service is currently unavailable."

现象：
  - 客户端被占用 65.37 秒后返回 502
  - 健康 ASCII 65 秒 >> 第 1 次的 5 秒
  - 符合后端实际接收请求并开始处理（下载模型 / 加载 torch / 启动 subprocess）
  - 65 秒后突然 502 → 进程被 SIGKILL（典型 OOM 特征，与方案故障 1 描述一致）

判定：
  - 故障 1（OOM 内存溢出）触发，
  - htdemucs 模型 + torch + 推理 tensor 总占用突破 512MB 上限
  - 须按方案【故障 1 长期方案】改造 demucs CLI 参数 + 入口限时长 + Dockerfile 预下载模型
```

### 命令 1 健康探测（命令 3-A OOM 后 10 秒）

```
HTTP_STATUS:502
TIME_TOTAL:0.486375s

Response: Render Bad Gateway HTML 页面
现象：实例已彻底崩溃。
判定：触发【测试中断恢复规则】；鉴于两次 3-A 均告失败且明确为 OOM，不再继续重试；
      按【验收判定标准】A4 / A5 / B1 / B2 / B3 / B4 全红；
      按矩阵最终结论 = ❌ 不通过；纳入 backlog 进入迭代流程。
```
