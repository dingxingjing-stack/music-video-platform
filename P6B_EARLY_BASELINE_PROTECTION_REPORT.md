# P6-B — Early Baseline 保护报告（EARLY_BASELINE_PROTECTION）

- 日期：2026-09-28
- 阶段结论：**`EARLY_BASELINE_ACCEPTED_AND_TAG_PROTECTED`**
- 依据阶段：`EARLY_BASELINE_INDEX_PREVIEW_PASS`（预演）→ `EARLY_BASELINE_ACCEPTED` + `POST_COMMIT_VERIFICATION = PASS` → `EARLY_BASELINE_PROTECTION = PASS`（轻量标签创建与核验）
- 本文件性质：项目进度/基线保护记录。**只新增本文件，未修改任何源码、测试、配置、依赖或生产文件。**

---

## 0. 阶段结论

```text
EARLY_BASELINE_ACCEPTED_AND_TAG_PROTECTED
```

Early Baseline 已被接受，并通过本地轻量标签建立了可检索的基线引用。标签创建未改变 HEAD、真实
`.git/index`、staged 集合或工作区内容。后续工作应以该标签作为基线参照，同时保护所有未提交的
Phase B 及其他工作区内容。

---

## 1. 四类对象必须分开理解（不可混为一谈）

| 对象 | 具体值 | 状态 |
|---|---|---|
| **Early Baseline 提交** | `b31ad3a2f0b1276405c31fff3add4b98206f7f8b`（22 文件 / +3838 −345） | 已验收（`POST_COMMIT_VERIFICATION = PASS`），**未推送远程** |
| **本地轻量标签** | `early-baseline-20260928` → 指向上面那个提交 | 已创建并核验通过；**仅存在于本地仓库，尚未推送远程** |
| **当前 HEAD** | `main` = `404ba4f007ec11dddf7615fff36d07969e700db4`（本文件自己的定向提交，父提交为 Early Baseline `b31ad3a`） | 建标签轮 HEAD 曾为 `b31ad3a`，标签创建未改变它；P6-C 的定向提交使 HEAD 前进一次。HEAD **不等于**仓库全部内容：本文件创建前工作区 107 条（本文件为 `??`，108 条），本文件被提交后回到 107 条，本次快照修订后为 108 条（唯一差异 = ` M P6B_EARLY_BASELINE_PROTECTION_REPORT.md`） |
| **尚未提交的 Phase B 内容** | `continuation_service.py` 的 index blob `8187bf07` + staged 新增文件 `backend/tests/test_phase_b_hf_gate.py`（`d50f8264`） | **不属于**已接受的 Early Baseline，须继续保护，不得被覆盖或误提交 |

补充：`origin/main` 仍为 `eeef9aa13c1a1a1393fad9ad5be40898992e4648`，本地 `main` 领先 3 个提交
（`bb92275` + `b31ad3a` + `404ba4f`，最后一个是本文件的定向提交）。因此**基线提交与标签都还没有成为远端事实**。

---

## 2. Early Baseline 状态

```text
状态                = EARLY_BASELINE_ACCEPTED
POST_COMMIT_VERIFICATION = PASS
提交                = b31ad3a2f0b1276405c31fff3add4b98206f7f8b
                      chore: establish early baseline for AI generation and routing
                      2026-09-28 13:39:42 -0300（author == committer）
父提交              = bb92275793c9149abc88e334d4c8930affa010e7
Tree                = 7bbddfe41b51a921b9baf1642da018d10c3ca698
变更范围            = 22 个文件（15 M + 7 A；无 D、无重命名、无越界文件）
变更统计            = +3838 / -345
```

基线内已包含的关键语义（用于后续阶段判定"哪些工作已经进基线"）：

```text
C2 成品时长硬闸：  DurationValidationError / _measure_final_duration / MIN_AUDIO_DURATION_SECONDS
                   在 commit 内命中 3 / 2 / 3，在父提交内均为 0
C3-1 最小解 A：    state="stitching" 与 state="generating_continuation" 在 commit 内均已归零
                   （统一为既有活跃态 generating，从而复用现有 busy-lock / stale-recovery / refund 机制）
```

---

## 3. 基线标签状态

```text
标签名      = early-baseline-20260928
类型        = Lightweight Tag（git cat-file -t 返回 commit；41B loose ref 文件，未进 packed-refs，无 tag reflog）
指向        = b31ad3a2f0b1276405c31fff3add4b98206f7f8b
创建核验    = PASS（8 项：指向正确 / 类型 lightweight / SHA 全等 / HEAD 未变 /
              真实 index 未变 / staged 未变 / 工作区未变 / 无 push 且无其他 ref 改动）
推送状态    = ★ 尚未推送远程：标签与提交都只存在于本地仓库；本阶段未执行任何 git push
```

后续阶段取用基线 SHA 的方式：

```bash
git rev-parse early-baseline-20260928
```

---

## 4. 工作区保护状态（建标签前后实测一致）

```text
HEAD 未改变（建标签轮）
.git/index 字节与纳秒级 mtime 未改变（建标签轮实测）
                      sha256 = 0b96e726366188f2424f964df5d7e17c9a783058556d148eefe03e73b96bab95
                      mtime  = 2026-09-28 11:24:35.907360400 -0300
                      ★ 重新核验（P6-C3 修订本快照时实测）：index 字节已随 P6-C 对本文件的定向提交
                        （git add + git commit --only）推进为新值，此后本文件的编辑与多次 git status
                        均未再改写它：
                      sha256 = da98f731d0ef7d3eb5ef0873492bd7091012be05a97ceffc2cbeaf3fc520bfd7
                      mtime  = 2026-09-28 14:29:32.355438700 -0300 / size = 81809 B
                      该推进只涉及本文件 ?? → 已跟踪并已提交，23 条 staged 内容零变化；
                      保护性断言以内容层指纹为准（与建标签轮及 P6-C 执行前逐项相同）：
                      git diff --cached --raw sha256 =
                        2e9a1555eb757272704c318dd44659d674cd1a28909830e1fd37ffdcc434c449（23 条逐行未变）
                      git ls-files -s         sha256 =
                        3af6941d4aeaf7aa7f83f8d84e0920d390f8eecd4c45a03ba514dfe29fbd5d1e（全表项未变）
staged 项目            = 23 条，保持不变
未跟踪文件             = 19 项，保持不变
git status --porcelain = 107 行，sorted sha e3b90739d59545647f0c1e23fa33a0bd1be5397d6dd4ec0731301341a47b8b41
                      与建标签前预检记录逐行一致
git diff --check       = 0
14:00 之后工作区文件写入 = 0（新对象数 = 0）
未执行                 = commit / add / reset / restore / stash / push / 部署 / 生产环境操作
```

本文件自身带来的记账变化（预期且已授权）：porcelain 由 **107 → 108**，仅新增
`?? P6B_EARLY_BASELINE_PROTECTION_REPORT.md` 一条；其余 107 条逐行不变。

---

## 5. 重要风险与后续约束（长期有效）

1. 工作区仍有大量未提交内容：**禁止** `git add .`、`git add -A`、`git commit -a` 等批量操作。
2. `continuation_service.py` 在真实 index 中有一份**独立的 Phase B staged 内容**
   （index blob `8187bf07`，既 ≠ 父提交、也 ≠ 基线、也 ≠ 磁盘），它**不属于**已接受的 Early Baseline。
3. `test_phase_b_hf_gate.py` 同样**不属于** Early Baseline（staged 新增，index == 磁盘 `d50f8264`）。
4. 工作区有 **6 个文件磁盘内容 ≠ 基线内容**：`backend/app/routers/ai_music.py`、
   `backend/app/services/continuation_service.py`、`backend/app/services/provider_registry.py`、
   `backend/tests/test_long_duration.py`、`backend/tests/test_mureka_provider.py`、
   `backend/tests/test_p0_security_fixes.py`。这些是基线提交之后的额外修改，磁盘是唯一副本，
   **后续不得误覆盖或丢弃**。
5. ⚠️ **对当前真实 index 执行一次裸 `git commit` 会生成"回退基线"的第二个提交**：
   15 个 staged M 中有 14 个 blob 恰好等于父提交（HEAD→index 净变化 = 23 files, `+655 / −3839`）、
   `continuation_service.py` 会退到不含 C2/C3-1 标记的 `8187bf07`、7 个 `D` 会把基线刚纳入的
   `test_p6b_*` 系列测试取消跟踪，并夹带 `test_phase_b_hf_gate.py`。
   `git diff --cached` 里的大量 M/D 属**预期显示错位**（index 是 11:24 的旧线、HEAD 是 13:39 的新线），
   **不得**用 reset / restore / stash 去"修复"。
6. 此前发现的 porcelain sorted-sha 差异（`5232b145` → `e3b90739`）已稳定记录，且本轮建标签前后
   逐行一致；**不得**将其误判为工作区内容变化（107 行原文已存档于仓库外快照文件，可逐行复核）。

---

## 6. 证据可得性声明（必须如实理解，不得过度表述）

```text
1) 预演阶段的独立临时 index：已无法恢复（.git 下仅存 index 本体；无 index.* 变体；/c/tmp 与会话
   目录内均无该工件；stash = 0）。
2) 最初的 EARLY_BASELINE_INDEX_PREVIEW_PASS 预演报告：未在仓库内落盘为可读文件，仅命中工具侧
   会话日志（.qoder-cn/logs/…），因此"审计范围一致性"只能与既定的 15 M + 7 A 范围逐项比对，
   无法与原报告文本逐条比对。
3) 13:39 那次写操作的原始命令序列无法从日志复原（相关 run 日志内未出现 git add / commit-tree /
   update-ref 记录）。基线的构造方式（从工作区内容另建 index 提交、不触碰真实 index）是
   ★ 基于现有证据的推断（16/22 文件 commit == 磁盘、14/15 个 staged M 的 blob 等于父提交、
   真实 index mtime 11:24 早于提交 13:39 且字节未变），不应描述为"已完整复现"。
```

---

## 7. 命名澄清

仓库根目录另有 `PHASE6_5_BASELINE_CLEANUP_REPORT.md`（2026-09-02，`# Phase 6.5 — Production
Baseline Cleanup Report`），其 "Baseline" 指当时的依赖/镜像清理，**与本文的 Early Baseline
（提交 `b31ad3a` + 标签 `early-baseline-20260928`）是两个不相干的概念**，勿混淆。
另与 GitHub 分支 `p3-13-prod-baseline` 上的生产镜像源码基线（`8191635`）也不同：那一份是
"与生产镜像逐字节 0 差异的可构建源码基线"，本一份是"当前阶段工作树收敛后的提交基线"。

---

## 8. 下一阶段建议（仅建议，本轮不执行）

1. Phase B 若要提交，必须先确定其 index 策略（在独立 `GIT_INDEX_FILE` 上构造，绝不触碰真实
   `.git/index`），否则会触发第 5 节第 5 条的回退风险。
2. 若希望基线成为远端事实，需要单独的推送授权（当前 `origin/main = eeef9aa`，标签亦未推送）。
3. 为防误操作丢对象，可考虑增加仓库外快照（`git bundle` 或 `git clone --mirror`）；本次未执行。
4. C3 剩余债务保持 DEFER：C3-2 provider-level A2A、C3-4 quota weight 与归一化后时长不一致、
   C3-5 R2 孤儿对象与双重上传、C3-6 duration 结构化持久化（需 DDL）、C3-7 duration 错误语义。

---

## 附：本文件创建时的核验基线

```text
HEAD                        = b31ad3a2f0b1276405c31fff3add4b98206f7f8b（本文件创建时）
                              → 404ba4f007ec11dddf7615fff36d07969e700db4（P6-C 定向提交本文件之后）
tags                        = early-baseline-20260928（唯一标签，本地）
refs 总数                    = 18
.git/index sha256           = 0b96e726366188f2424f964df5d7e17c9a783058556d148eefe03e73b96bab95（本文件创建时）
                              → da98f731d0ef7d3eb5ef0873492bd7091012be05a97ceffc2cbeaf3fc520bfd7
                                （P6-C 定向提交之后；23 条 staged 内容未变，内容层指纹见 §4）
porcelain（本文件创建前）    = 107 行，sorted sha e3b90739d59545647f0c1e23fa33a0bd1be5397d6dd4ec0731301341a47b8b41
porcelain（本文件创建后）    = 108 行（唯一差异 = ?? P6B_EARLY_BASELINE_PROTECTION_REPORT.md）
本轮授权写操作               = 1（仅创建本 Markdown 文件）
```
