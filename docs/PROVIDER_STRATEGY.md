# Zyvexo 生产 Provider 策略（Commit 3 声明）

> 本文件为策略声明文档，不修改任何运行时行为。
> Commit 3 仅包含本文档与 `backend/.env.example` 占位变量。

## 1. 最终生产音乐生成 Provider

正式生产环境的 AI 音乐生成只允许两个 Provider：

1. **Yinchao（音潮）** — 第一 Provider
2. **TemPolor（天普大模型）** — 第二 Provider

生产自动模式严格为：

```text
Yinchao → TemPolor → 最终失败 → 退款一次
```

* Yinchao 成功则直接进入后续上传/R2 流程，不再调用 TemPolor。
* Yinchao 失败后自动尝试 TemPolor。
* TemPolor 失败后最终失败，并按既有语义退款一次。
* 每个 Provider 内部的重试次数语义（`MAX_AUTO_RETRIES`）保持不变；
  不在 Provider 内部实现跨 Provider fallback。

## 2. 不进入生产链的 Provider

以下全部不得进入生产音乐生成链（`ENVIRONMENT=production` 下的
`fallback_chain()` / `select()` 默认路径）：

* Mureka
* RunPod
* Fal Stable Audio
* Modal（ACE-Step）
* MusicGen
* CosyVoice
* HF Ace-Step（router 层兜底，生产不使用）

显式 `AI_GENERATION_PROVIDER` 在生产也不得指向上述非策略 Provider；
具体禁选名单与默认选择由后续 Commit 在 `provider_registry.py` 落地。

## 3. 历史代码保留

* 历史 Provider 文件与代码暂时全部保留，不删除任何 Provider 文件。
* 包括但不限于 `mureka_provider.py`、`runpod_client.py`、`fal_client.py`、
  Modal / MusicGen / CosyVoice 相关实现、测试与文档。
* 后续清理（如需）必须由明确的独立 Commit 提出，不得借策略 Commit 顺手删除。

## 4. HF fallback 说明

* 生产不使用 HF Ace-Step fallback。
* HF 相关逻辑（如 `ai_music._try_hf_ace_step_fallback`）在本 Commit 不修改；
  是否在后续 Commit 中移除/门控生产 HF 调用，由后续 Commit 明确说明。

## 5. 缺 Key 处理原则

* 缺少某 Provider 的 API Key 时，不得导致进程启动失败或整链异常。
* 后续链逻辑中应跳过该 Provider（或等价的快速失败后继续下一 Provider），
  具体实现由后续 Commit 落地。
* `YINCHAO_API_KEY` / `TEMPOLOR_API_KEY` 的真实值只填本地 `backend/.env`
  或 Render 等生产环境变量，绝不写入 `backend/.env.example` 与本文档。

## 6. 额度语义边界

* Credits / Reserve / Refund（含 `reserve_generation` / `refund_generation` /
  `credits_service`）逻辑不属于本次 Provider 策略变更。
* 自动模式最终失败后的退款一次语义保持不变，本 Commit 不触碰。

## 7. 本 Commit 范围（Commit 3）

* 允许修改：
  1. `backend/.env.example`（仅补 `YINCHAO_*` / `TEMPOLOR_*` 占位与注释）
  2. `docs/PROVIDER_STRATEGY.md`（本文件）
* 禁止修改：`provider_registry.py`、各 Provider 实现、`ai_music.py`、
  测试文件、Credits / Projects / Auth / Supabase / `database.py` /
  `task_store.py` / 前端 / i18n / VoiceClone / MV / RunPod 部署 / HF 逻辑。
