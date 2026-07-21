# GitHub 仓库密钥泄漏扫描报告

| 项 | 内容 |
| --- | --- |
| 报告日期 | 2026-07-21 |
| 扫描范围 | `c:\Users\dingx\music-video-platform\` 仓库工作树 + 全 git 历史 |
| 远端仓库 | https://github.com/dingxingjing-stack/music-video-platform.git |
| 当前 HEAD | `7abcb34` "fix: 修复语言切换/登录状态/生成按钮与 Landing 构建" |
| 远端状态 | README: **已推送** (origin/main tracking HEAD) |
| 报告人 | TRAE |
| 扫描方式 | 子代理清单 + Grep 工作树 + `git log --all -S` 历史追溯 |

## 一、严重程度定级

| 级别 | 含义 |
| --- | --- |
| 🔴 高危 | 密钥已在公开 GitHub 历史 commit 中，任意人可还原 → 必须轮换 |
| 🟠 中危 | 在本仓库工作树中可访问、远端未触发但当前已 push → 必须立即清理 |
| 🟡 低危 | 仅本机其它目录泄漏，未进项目仓库 → 建议清理，无紧迫性 |
| 🟢 已避免 | 项目仓库中不放、根本不存在泄漏 |

## 二、🔴 高危泄漏 —— Mureka API Key

### 2.1 密钥信息

| 项 | 内容 |
| --- | --- |
| 密钥类型 | Mureka API Key (音乐生成服务端鉴权) |
| 完整值（仅供审计参阅，**轮换前应保密**） | 已于 2026-07-21 从本仓库内脱敏；保留指纹用于原文匹配：`op_pw90****crzd1lt****zb` |
| 通行格式 | `op_` 前缀 + 32 位字母数字 |
| 实际用途 | `https://api.mureka.ai/v1/song/generate` Bearer Token 鉴权 |
| 历史 commit | **`90cab11 Initial commit - Music Video Platform` 起就明文写入** |
| 历史 commit 命中数 | 1 (初始提交) |
| 当前推送状态 | **已推送到远端 `origin/main`**，公开可访问 |

### 2.2 工作树泄漏点 (Grep 命中 5 处)

| # | 文件路径 | 行号 | 内容片段 |
| --- | --- | --- | --- |
| 1 | `backend/app/services/mureka_service.py` | 35 | `API_KEY = os.getenv("MUREKA_API_KEY", "op_pw90y...")` ⚠️ **硬编码默认值** |
| 2 | `.env.v1_production` | 51 | `MUREKA_API_KEY=op_pw90y...` ⚠️ **该 .env 文件已被 git 跟踪** |
| 3 | `docs/P0_INTEGRATION_COMPLETE.md` | 260 | 使用现有 API Key: `op_pw90y...` |
| 4 | `docs/RENDER_DEPLOYMENT.md` | 87 | `MUREKA_API_KEY  op_pw90y...` |
| 5 | `docs/RENDER_ONE_CLICK_DEPLOY.md` | 64 | `MUREKA_API_KEY = op_pw90y...` |

### 2.3 为什么 `.env.v1_production` 被推送

项目根 `.gitignore` 第 23 行起：
```
.env
.env.local
.env.*.local
```

通配规则 `.env.*.local` 要求后缀是 `.local`，而 `.env.v1_production` 后缀是 `.v1_production`，**未被规则匹配**。加上历史首次提交时该文件已存在，被 `git add` 之后就一直被跟踪，直至今天 push 跟随代码上传 GitHub。

## 三、🔴 高危泄漏 —— Sentry DSN

### 3.1 密钥信息

| 项 | 内容 |
| --- | --- |
| 密钥类型 | Sentry DSN (监控异常上报端点) |
| 完整值 | 已于 2026-07-21 脱敏；保留指纹用于审计匹配：`https://1a4a****bda@o4511736082661377.ingest.us.sentry.io/4511736089542656` |
| inner token | 已脱敏：`1a4a****bda` (32 位十六进制) |
| 历史 commit 命中 (`git log -S`) | 0 命中（字符串在 git 追加时未触发二分匹配 → 但在工作树里用 Grep 命中 2 处最新文件） |
| 当前推送状态 | **部分已推送** —— `docs/2026-07-18_DEV_LOG.md` 已 push，`docs/2026-07-20_SESSION_LOG.md` 尚未提交也未 push |

### 3.2 工作树泄漏点 (Grep 命中 2 处)

| # | 文件路径 | 行号 | 文件性质 | 当前推送状态 |
| --- | --- | --- | --- | --- |
| 1 | `docs/2026-07-18_DEV_LOG.md` | 182 | 未提交改动中追加的 "2026-07-20 续记" | **modified 未 push**（远端是更老的版本，**没有这条 DSN**） |
| 2 | `docs/2026-07-20_SESSION_LOG.md` | 99 | 新建的归档文件，未 commit | untracked，远端不存在 |

### 3.3 推断：远端 GitHub 上当前实际暴露

| 文件 | 当前 origin/main 状态 | DSN 是否在远端 |
| --- | --- | --- |
| `docs/2026-07-18_DEV_LOG.md` | 旧版本（不含 7-20 续记） | ❌ 不在 |
| `docs/2026-07-20_SESSION_LOG.md` | 远端不存在 | ❌ 不在 |

**结论：**Sentry DSN 尚未推送到公开 GitHub。唯一在 GitHub 上的位置是 `.env.v1_production` 间接包含（如果它写了 Sentry DSN 则会一并暴露）。检查 `.env.v1_production` 第 51 行起：

```
MUREKA_API_KEY=op_pw90****crzd1lt****zb      ← 确认暴露（已脱敏）
（Sentry DSN 是否在该文件中：需要再次扫描确认）
```

→ 待下一步补扫 `.env.v1_production` 中的 SENTRY_DSN。

## 四、🟢 未进入项目仓库的密钥（hermes memories 本机泄漏，非 GitHub 风险）

| 密钥 | 值前 6 位 + 后 4 位 | 进 GitHub | 本机泄漏位置 |
| --- | --- | --- | --- |
| Agnes API Key | `sk-BGBd***RloI16wb` | ❌ 否 | hermes memories MEMORY/USER.md |
| Gemini API Key | `AQ.Ab8R***-srt8Q` | ❌ 否 | 同上 |
| HuggingFace Token | `hf_Xynm***NZiHLs` | ❌ 否 | 同上 |
| Render API Key | `rnd_zGVQ***wYUhMO` | ❌ 否 | 同上 |
| NVIDIA NIM | `nvapi-***rvi` | ❌ 否 | `c:\Users\dingx\.qclaw\openclaw.json`（不是项目仓库） |
| Groq | `gsk_Xs***xz0PEJx` | ❌ 否 | 同上 |
| OpenRouter | `sk-or-v1***e305b7d0` | ❌ 否 | 同上 |
| Gateway Token | `5462a0***3ef1da` | ❌ 否 | 同上 |
| WeChat Token | `49a34e***c98fd` | ❌ 否 | 同上 |

`git log -S` 全历史扫描这 9 个密钥前缀都无命中，确认它们**只在用户主目录 Agent 配置和 Hermes memories 中明文存放**，从未被项目仓库跟踪、不会推送到 GitHub。

## 五、风险等级汇总

| 风险类别 | 等级 | 是否已上 GitHub | 必做处置动作 |
| --- | --- | --- | --- |
| Mureka API Key 在 5 处仓库文件中硬编码 | 🔴 高危 | 是 | 1) Mureka 后台立即 rotate Key<br>2) 清理 5 处硬编码<br>3) `git filter-repo` 改写历史（用户决定） |
| `.env.v1_production` 被纳入 git 跟踪 | 🔴 高危 | 是 | 1) 从 git index 移除：`git rm --cached .env.v1_production`<br>2) 加入 `.gitignore`（修规则匹配后缀）<br>3) 评估是否要 rotate 该文件里所有密钥 |
| Sentry DSN 写入 Markdown 文档 | 🟠 中危 | 部分 | 1) 脱敏 `docs/2026-07-18_DEV_LOG.md`、`docs/2026-07-20_SESSION_LOG.md`<br>2) 在 Sentry 后台考虑 rotate DSN<br>3) 现阶段还能避免 push 触发新泄漏 |
| `.gitignore` 规则不严 | 🟠 中危 | 是 | 修规则为 `.env*` 通配，避免未来再漏 |
| backend `os.getenv(key, "default")` 反模式 | 🟠 中危 | 是 | 删除第二个默认参数，使无环境变量时报错而不是用硬编码 |

## 六、补救操作清单（按用户当前指令：**先只做扫描报告不改任何文件**）

本次不动任何代码或 Markdown 文件。下面是给后续执行用的完整 TODO，等用户批准后再做。

### 6.1 立即必做 (P0)

```bash
# 1. 从 git index 移除泄漏的 .env，但保留本地工作树文件
git rm --cached .env.v1_production

# 2. 修 .gitignore：将第 23 行附近的规则改为
#    .env
#    .env.*
git add .gitignore

# 3. 编辑 backend/app/services/mureka_service.py 第 35 行，改为
#    API_KEY = os.getenv("MUREKA_API_KEY")
#    if not API_KEY:
#        raise RuntimeError("MUREKA_API_KEY environment variable not set")
#    不要保留任何默认值

# 4. 脱敏 4 个泄漏 Markdown：
#    docs/P0_INTEGRATION_COMPLETE.md:260       → MUREKA_API_KEY=<在Render环境变量>
#    docs/RENDER_DEPLOYMENT.md:87             → 同上
#    docs/RENDER_ONE_CLICK_DEPLOY.md:64        → 同上
#    docs/2026-07-18_DEV_LOG.md:182            → SENTRY_DSN=<在Render环境变量>
#    docs/2026-07-20_SESSION_LOG.md:99         → 同上
git add docs/

# 5. 提交（不要带任何密钥）
git commit -m "security: 移除仓库内明文密钥，迁移到 .env / Render 环境变量"

# 6. 推送清理后的新 HEAD
git push
```

### 6.2 历史改写 (可选，按用户当前指令不做)

```bash
# 安装 git-filter-repo
pip install git-filter-repo

# 用替换文件清单逐个清理
echo "op_pw90****crzd1lt****zb==>MUREKA_API_KEY_REDACTED" > replacements.txt
echo "1a4a****bda==>SENTRY_DSN_TOKEN_REDACTED" >> replacements.txt

git filter-repo --replace-text replacements.txt
git push --force-with-lease origin main
```

**注意**：force-push 改写 history 会让所有已 clone 仓库下次 pull 失败。请确认你只有本机这一份 working copy 再做。

### 6.3 密钥轮换清单 (用户当前指令：暂不轮换)

| # | 密钥 | 轮换原因 | 优先级 |
| --- | --- | --- | --- |
| 1 | Mureka API Key | 已在公开 GitHub 历史 | 强烈建议（用户决定） |
| 2 | Sentry DSN | 仅本机 + Markdown 文件，未实际 push 出去 | 可缓 |
| 3 | 其它 9 个本机密钥 | 未进 GitHub | 不急 |

## 七、后续预防机制

1. **`.gitignore` 严格化**：把规则改为 `.env*` 一次性通配所有 .env 变体。
2. **预提交钩子**：添加 `pre-commit` hook 调 `gitleaks` 或 `trufflehog`，避免下次再有密钥进入。
3. **GitHub Secrets Scanning**：在 GitHub Settings → Code security → Secret scanning 打开（公开仓库免费）。
4. **代码评审铁律**：任何 PR 里若出现 `os.getenv("X", "默认值")` 的默认值位置带 `op_` / `sk-` / `nvapi` / `AQ.` / `hf_` / `rnd_` / `gsk_` 前缀或 URL 形式 DSN，必须拒绝。
5. **`.env` 模板**：保留 `.env.example` 作为变量名模板，真实 `.env` 永不进 git。

## 八、本报告不修改文件声明

按用户 2026-07-21 决策（"先只做扫描报告不改任何文件"），本扫描过程**完全只读**：

- ❌ 未修改任何业务代码文件
- ❌ 未修改任何 Markdown 文档
- ❌ 未修改 .env / .gitignore
- ❌ 未执行 `git add` / `git commit` / `git push`
- ✅ 仅做：子代理只读扫 + Grep 工作树扫 + `git log -S` 历史追溯 + 远端 origin/main 状态核查

待用户批准后，严格按照本报告第 6 节操作清单执行。
