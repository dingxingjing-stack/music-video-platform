# Stage 2 第一阶段 POC 报告 — MDX 音乐分离（2026-08-15）

**结论：POC 通过，可进入下一阶段（自动化测试补全 + 4-stem 模型对比 + 路由接入评估）。**

## 1. 目标回顾
按用户批准的 Stage 2 计划，第一阶段只做 **POC**：新增独立分离服务（python-audio-separator 框架 +
UVR_MDXNET_9482 POC 模型），统一接口 `AudioSeparatorService`（MDX 主 + Spleeter fallback），
严格保持 `/api/v1/audio/separate` 契约 `{"success","stems","duration","message"}`，
**不改生产路由、不删 Spleeter、不引入 Demucs/MUSDB18HQ 权重**。

## 2. 新增/修改文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/services/separation/__init__.py` | 新增 | 隔离包 |
| `backend/app/services/separation/base.py` | 新增 | 统一契约 `SeparationResult`、`SeparatorBackend`、`SEPARATION_CONTRACT_KEYS`、轨道语义 |
| `backend/app/services/separation/mdx_separator.py` | 新增 | MDX backend（懒加载、全流程锁串行、超时保护） |
| `backend/app/services/separation/spleeter_separator.py` | 新增 | Spleeter fallback（包装现有 `demucs_service`，不改其代码） |
| `backend/app/services/separation/audio_separator_service.py` | 新增 | 统一门面（MDX 主 → 失败 fallback，含日志与原因） |
| `backend/app/services/separation/models_license_audit.json` | 新增 | 8 个模型的独立许可审计记录 |
| `backend/scripts/poc_mdx_separation.py` | 新增 | POC 脚本（性能/缓存/并发/边界/超时/fallback 探针） |
| `backend/tests/test_separation_service.py` | 新增 | 19 项自动化测试 |
| `backend/docs/audio_separation_verification/2026-08-15_poc_mdx/poc_report.json` | 新增 | POC 实测数据 |
| `backend/data/poc_3m30s.wav`、`poc_test_8s.wav`、`poc_out/*` | 新增 | 测试音频与输出 |
| `backend/data/audio_separator_models/` | 新增 | 模型缓存（UVR_MDXNET_9482.onnx ≈29.8MB） |

**生产代码零改动**：未触碰 `audio_processing.py`、`main.py`、`workflow.py`、`spleeter_modal.py`、
`audio_separation_service.py`（Spleeter 侧）、`inference/demucs.py`、额度/任务系统、前端。

## 3. 依赖变化
- POC/测试环境新增：`audio-separator==0.44.5`（框架，MIT）、`psutil`（仅测内存）。
- 传递依赖：`onnxruntime`、`librosa`、`numpy`、`soundfile` 等已在环境中。
- `backend/requirements.txt` **尚未加入** audio-separator（路由接入阶段再决定正式依赖声明）。

## 4. 测试结果（19/19 通过）
`python -m pytest tests/test_separation_service.py -q` → **19 passed**，覆盖：
API 契约（字段严格一致、不泄露审计元数据）、WAV/MP3/16kHz 单声道输入、空文件/损坏文件/缺失文件、
模型加载失败（ImportError/加载错误）、超时保护、fallback（MDX 失败→Spleeter、禁用时直返、
强制 spleeter backend）、stem 文件存在性、轨道语义诚实（2-stem 如实标记 missing drums/bass）、
duration 一致性、4 线程并发、许可审计记录字段完整性。

## 5. POC 实测（本机 CPU-only，Python 3.12.10）
| 指标 | 结果 |
|---|---|
| 测试音频 | 3:30（210s，44100Hz 立体声） |
| 首次分离（含模型下载+加载） | 58.5s（推理 54.8s） |
| 第二次分离（缓存命中） | 55.4s，**0 新增下载** |
| 4 线程并发（串行锁） | 总 218.1s，**4/4 成功**，无异常 |
| 峰值 RSS | 1660MB，增量 ≈1218MB |
| GPU 显存 | N/A（本机无 GPU，需 Modal 部署阶段实测） |
| 输出 | vocals + instrumental 2 轨（各 ≈37MB） |
| 空/缺失/损坏输入 | 均正常返回 `success=false`，不崩溃 |

**轨道语义**：MDX-Net 为 2-stem，输出 `real_stems=[vocals, instrumental]`、
`derived_stems=[other]`、`missing_stems=[drums, bass]` —— **未虚假填充 4 轨**。

## 6. 发现的问题（均不影响 POC 结论）
1. **Spleeter fallback 在当前本地环境失败**：`'Volume' object has no attribute 'add_local_file'`。
   根因是 `backend/app/services/audio_separation_service.py:122`（既有生产代码）调用 modal 1.5.3
   已移除的 `Volume.add_local_file` API。**这是既有问题，非本次引入**；fallback 机制本身正确
   （MDX 失败→Spleeter→带原因返回）。修复属 Modal 部署/生产环境适配，需另立项（不属 Phase 1）。
2. python-audio-separator 单实例非并发安全（共享 output_dir 写同名文件）→ 已在
   `MdxSeparator.separate()` 用全流程可重入锁串行，4 线程验证通过。

## 7. 许可风险（详见 `models_license_audit.json`）
- **UVR_MDXNET_9482.onnx**：A 级（作者 Anjok07 于 discussion #2307 明确授予商用+随安装包分发，
  需署名）。**用于 POC 通过。**
- MDX23C（ZFTurbo）：A 级（2026-05-10 作者确认代码+权重 MIT）→ 可作对比候选。
- Spleeter：A 级（权重 MIT，Deezer 确认商用）→ fallback 保留。
- Demucs 全部权重、MUSDB18HQ 多轨：**C 级（仅科研）→ 不引入**。
- BS-RoFormer viperx：B/C 级 → 不采用。
- 本次未引入任何 C 级模型。权重许可 ≠ 代码许可，审计记录独立存档。

## 8. 下一步（需用户确认）
1. **自动化测试补全到 30+ 项**：Mock Modal 容器 Spleeter、真实转码 MP3、长音频（>10min）边界。
2. **4-stem 模型对比 POC**：MDX-Net 2-stem + 第二级 kuielab per-stem（drums/bass）vs MDX23C vs
   Mega 53-Stems，同一批测试音频，输出质量/耗时/成本对比后决定（用户批准目标 #7）。
3. **Modal 部署环境验证**：GPU 显存实测、Spleeter fallback 的 modal SDK 适配（需确认范围）。
4. 以上通过后，进入 shadow/灰度路由接入（目标 #13），才修改生产路由。