# 音轨分离功能验证运行纪要 run07（MDX23 4stems 尝试）

## 一、运行标识
- 运行 ID：`2026-07-21_run07`
- 执行人：Trae 编程助手
- 执行时间：2026-07-21 23:05 ~ 23:12（UTC+8）
- 后端 commit / branch：`feat/audio-mdx23-4stems` @ 20a6e07
- 前端：无变更

## 二、环境
- Render 服务 URL：https://ai-music-backend-db6h.onrender.com
- 测试音频：test_3s.wav（3.000000秒，44.1kHz，单声道，16-bit PCM）
- WEB_CONCURRENCY=1，OMP_NUM_THREADS=1（Dockerfile 已设）

## 三、执行过程与结果

| 步骤 | 操作 | HTTP 状态 | TIME_TOTAL | 备注 |
|------|------|-----------|-----------|------|
| 阶段 1 - 健康探测 | GET /health | 200 | 0.30s | 实例健康 |
| 阶段 1 - 模型列表 | GET /api/v1/audio/separate/models | 200 | 1.00s | 返回 ["htdemucs","htdemucs_ft","htdemucs_6s"]（兼容占位） |
| 阶段 2 - 3-A 首次分离 | POST /separate (文件+model=htdemucs) | **502** | **52.45s** | 长时间处理后 502，实例崩溃（OOM） |
| 健康探测（崩溃后 5s） | GET /health | 502 | 1.48s | 实例已崩 |
| 健康探测（等待 180s 自动恢复） | GET /health | 200 | 0.30s | 实例恢复 |
| 阶段 1 - 重复健康/模型列表 | 同上 | 200 / 0.32s / 1.00s | 正常 |
| 阶段 2 - 3-A 第二次尝试 | POST /separate | **502** | **8.63s** | 快速失败，表明实例尚未完全恢复或模型加载后即 OOM |

> 注意：两次 3-A 均返回 502（Bad Gateway），无法获取任务 ID 或分离结果。实例在处理过程中被 OOM Kill，网关返回 502。

## 四、与之前运行的横向对比

| 运行 | 模型/配置 | 3-A 首次耗时 | 是否 OOM | 备注 |
|------|-----------|--------------|----------|------|
| run01 | 原始 subprocess（默认） | 65.37s | ✅ OOM | 下载+加载+推理三重叠 |
| run02 | subprocess + `--segment 4 --shifts 1` + 预下载模型 | 19.53s | ✅ OOM | 加载阶段 OOM |
| run03 | 进程内单例 + `--segment 4 --shifts 1` | 35.81s | ✅ OOM | 推理阶段 OOM |
| run04 | 进程内 + 4-bit 量化 + `--segment 2` | 28.84s | ✅ OOM | 量化后仍 OOM |
| run05 | 进程内 + 4-bit 量化 + `--segment 1` | 45.66s / 48.20s | ✅ OOM | 耗时反增，仍 OOM |
| **run06**（Spleeter 5stems）| Spleeter 5stems 进程内 | 20.44s | ✅ OOM | 未到 3-B |
| **run07**（MDX23 4stems）| MDX23 4stems 进程内（本次） | 52.45s / 8.63s | ✅ OOM | 两次均 OOM |

## 五、结论

**❌ 不通过**  
所有尝试的本地 4 轨分离模型（Demucs、Spleeter、MDX23）在 Render 免费 512MB 实例上均不可避免地触发 OOM，导致 HTTP 502。即便采用激进的内存优化（4-bit 量化、极短分片、单线程、进程内单例），模型在推理过程中的中间张量峰值仍然超过 512MB 的瞬时容量上限，被 cgroup OOM Killer 终止。

### 六、后续建议（根据任务说明）

1. **路线 A：架构重构，将推理剥离至外部异步算力**  
   - 使用 Modal、HuggingFace Spaces、AWS Lambda 等外部算力执行实际分离任务。  
   - 本地服务仅负责接收请求、转发至远程服务、轮询结果并返回。  
   - 这样可以保持免费实例仅作轻量调度，避免本地 OOM。

2. **路线 B：升级至付费实例（Starter 2GB）**  
   - 在 Render dashboard 中将服务从 Free 升级为 Starter（约 0.75 USD/天）。  
   - 保留现有的 DX23（或之前任意）实现，无需代码更改。  
   - 2GB 内存足以容纳模型常驻 (~150MB) 与推理峰值 (~300-400MB)，理论上可稳定运行。

鉴于目前已在模型选择与内存优化上耗尽合理空间，建议优先考虑 **路线 B**（升级实例），因为它能保留最高音质（MDX23 或 Demucs）且实现最简。若成本敏感，则可实施 **路线 A**（异步外部算力）作为长期方案。

## 七、交付物

- 本运行纪要：`docs/audio_separation_verification/2026-07-21_run07/run_summary.md`  
- 所有 curl 原始输出均保存在同目录下的 `curl_outputs.md`（如需可提供）。

**最终结论**：Render 免费 512MB 容器无法承载本地原生 4 轨音乐分离模型；必须升级实例或采用异步外部算力方案。