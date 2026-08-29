# 4-stem 可行性最终对比报告

> 基于已完成的三项真实隔离验证 POC（未重新运行，数据来自各模型独立 JSON 报告）。
> 测试音频：`poc_3m30s.wav`（210s / 44100Hz / 2ch）。

## 模型与验证环境

| 模型 | 架构 / 格式 | 验证环境 |
|---|---|---|
| MDX-Net (`UVR_MDXNET_9482.onnx`) | MDX-Net, ONNX, 28.3MB | 本机 CPU (16.8GB RAM) |
| MDX23C (`MDX23C-8KFFT-InstVoc_HQ.ckpt`) | MDX23C TFC-TDF, 427.3MB | Modal GPU A10G |
| Mega 53 (`mvsep_mega_model_bs_roformer_53_stems_v1.ckpt`) | BS-RoFormer, 1368.9MB | Modal GPU A10G |

## 统一指标对比

| 指标 | MDX-Net | MDX23C | Mega 53 |
|---|---|---|---|
| 原生 4-stem (vocals/drums/bass/other) | ❌ | ❌ | ❌ |
| 实际输出 stems | 2 (vocals/instrumental) | 2 (vocals/instrumental) | 53 细粒度 |
| 需后处理才能得 4-stem | 是（缺 drums/bass/other 源） | 是（缺 drums/bass/other 源） | 是（无 other、vocals 拆分） |
| stems 求和还原原曲 | ✅ | ✅ | ❌（官方声明不求和、含重叠） |
| 模型大小 | 28.3MB | 427.3MB | 1368.9MB |
| 模型加载时间 | 3.7s | 1.5s (GPU) | 12.8s (GPU) |
| 3:30 推理时间 | 54.8s | 61.2s | 49.4s |
| GPU VRAM 峰值 | N/A (CPU) | 2.6GB reserved | 10.6GB reserved |
| RAM 峰值 | 1660MB | 4799MB | 12100MB |
| 输出文件数 / 总大小 | 2 / 74.1MB | 2 / 74.1MB | 53 / 3926.7MB |
| GPU/CPU 要求 | CPU 即可 | 需 GPU（本机 CPU 加载超时） | 需 ≥16GB VRAM 级 GPU |
| 3:30 稳定性 | ✅ | ✅ | ✅ |
| 适合生产 | ❌ | ❌ | ❌ |
| 值得进入 Stage 2 | ❌ | ❌ | ❌ |

## 4-stem 判定（严格区分）

| 模型 | 输出多 stem | 输出 4 目标 stem | 原生独立 4-stem | 后处理聚合 4-stem |
|---|---|---|---|---|
| MDX-Net | ✅ | ❌ | ❌ | 不可行（无 drums/bass/other 源） |
| MDX23C | ✅ | ❌ | ❌ | 不可行（同上） |
| Mega 53 | ✅ (53) | ❌ | ❌ | 技术上可拼，但非原生、stems 不求和且重叠，质量低于专项模型，按项目规则禁止伪装为原生 |

> 项目硬性要求：**只有原生输出 `vocals + drums + bass + other` 才算满足 4-stem**。禁止将多 stem 人为相加/聚合后标记为原生 4-stem。

## 最终生产决策

- **A. 现有模型可直接进 production？** ❌ 否。三者均非原生独立 4-stem。
- **B. 明确结论：** 当前没有合格的真 4-stem 模型，**不进入 Stage 2 集成**。
- **C. production separation 状态：** **保持不变**——继续使用现有 2-stem MDX-Net 实现，不做替换或扩展。
- **D. 下一阶段筛选条件：**
  1. 架构必须**原生输出 exactly 4 stems**：vocals / drums / bass / other
  2. 首选 **Demucs v4 系**（`htdemucs` / `htdemucs_ft` / `htdemucs_6s` / `htdemucs_ft_6s`，BSD-3，原生 4-stem，无需后处理）
  3. 模型须能在框架内置清单或官方 hash/配置直接加载（不修改框架代码）
  4. 模型 <1GB；加载时间尽量短（CPU 可跑，或 GPU 显存 <8GB）
  5. 3:30 推理 <2 分钟；RSS 峰值 <3GB（贴合生产容器）
  6. stems 无重叠或可求和还原，需书面确认
  7. 许可证优先 MIT/BSD/Apache；B 级候选需数据来源书面确认

## 建议下一步

用同一 3:30 音频对候选 Demucs v4 模型做**隔离 POC**（加载/推理/VRAM/RAM/输出规格/稳定性），与 MDX-Net baseline 对比后再评估集成（集成前先出方案，不直接改现有 separation 代码）。

---
数据来源：`poc_4stem_report.json`、`mdx23c_modal_gpu_report.json`、`mega53_modal_gpu_report.json`；本报告与三份单模型报告均为独立文件，未覆盖或修改任何已有报告。