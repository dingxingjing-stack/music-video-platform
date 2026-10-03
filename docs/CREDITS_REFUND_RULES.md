# CREDITS_REFUND_RULES.md — Credits 退款规则最终口径（需求文档 v1.0）

- **裁定日期**：2026-10-03
- **性质**：产品需求文档（规则固化）。**本轮未修改任何生产代码**
- **适用范围**：用户协议、帮助文档、FAQ、前台文案、内部成功判定与退款实现

---

## 1. 用户可见规则（对外口径，唯二表述）

> **生成成功：正常消耗 Credits。**
> **生成失败：退还本次生成消耗的 Credits。**

用户协议、帮助文档、FAQ、前台文案中**不得出现**以下表述：

- "240 秒"
- "不足 240 秒退款"
- "必须生成 240 秒"
- "240 秒是退款条件"
- 任何其他形式的时长限制/时长承诺作为退款条件

240 秒属于**内部 generation success criteria**，不是用户侧退款条款，不得把内部实现条件暴露成用户协议中的退款条件。

## 2. 内部成功判定规则（对内，代码保留）

```text
最终生成音频时长 ≥ 240 秒 → generation success → 正常消耗 30 Credits，不退款
最终生成音频时长 < 240 秒 → generation failure → 走既有失败/退款流程，
                            退还本次生成消耗的 Credits
其他生成失败             → generation failure → 同上
```

不得新增第二套退款机制；`<240s` 失败后走 `generation failed → existing failure/refund flow → refund`。

## 3. 现有实现状态（审计结论，2026-10-03 核对）

| 项 | 状态 | 证据 |
|---|---|---|
| 内部 240s 判定 | ✅ 保留，**本轮未修改** | `MIN_AUDIO_DURATION_SECONDS = 240`、`DurationValidationError`、`_enforce_duration_gate`（ai_music.py L478，生产 L412 同源） |
| 失败退款实现 | ✅ 保留，**本轮未修改** | `refund_generation(...)`（13 调用点）+ `refund_generation_credits(...)`（10 调用点），幂等由应用级校验 + Supabase `uq_credits_refund_once` 索引保障 |
| `<240s` 实际退款 | ✅ YES（代码链路证实） | gate raise → except → 恰好一次退款；`test_p6b_c2_duration_gate` + `test_ai_music_flow` 覆盖 |
| **用户可见文案合规** | ✅ **全部合规，无需修改** | ① `i18n/legal/refund.ts`：中" Credits 仅在任务成功时扣减；生成失败不扣 Credits，已扣的会自动退回您的余额"/EN "Credits are deducted only when a task succeeds. A failed generation costs no Credits…" —— 与本口径逐字一致；② `creditsRule`（zh/en）："一次成功的音乐创作消耗 30 Credits" —— 一致；③ 全前端 grep `240`：零用户可见暴露（命中均为内部常量/死组件/Canvas 坐标） |

## 4. 已知遗留（非本轮范围，已另行记录）

- `TrackStudio/AIGeneratePanel.tsx`（未挂载死组件）内 `aiGen.songDuration = "歌曲时长（上限 3 分钟）"` 过时文案 —— A-19 P1-2 死树处置项，随死树决策一并清理；当前用户不可达
- 后续任何新文案/帮助文档/FAQ 落地时，必须按 §1 口径审查

## 5. 生效与变更

- 本口径自 2026-10-03 起生效
- 代码侧（`MIN_AUDIO_DURATION_SECONDS` 等）如需变更，必须另行授权并先做只读影响分析
- 用户可见文案如需新增/修改，须对照 §1 禁止清单审查
