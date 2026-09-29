# Melovar 生产部署指令（阿里云 ECS）

> 本文所有路径、端口、镜像 ID、资源数字均为 **2026-09-29 实测值**，非推测。
> 目标环境不是 Render；`render.yaml` 已过期，禁止按它操作。

---

## 0. 环境事实（实测基线）

| 项 | 实测值 |
|---|---|
| 主机 | `ssh melovar-ecs` → `47.88.16.83`，用户 `admin`，密钥 `~/.ssh/melovar_ecs` |
| 规格 | 2 vCPU / RAM 1613 MB（available 670 MB）/ **Swap 2047 MB（0 已用）** |
| 磁盘 | `/dev/vda3` 40 G，已用 29 G，**可用 8.8 G**（77%） |
| Docker | 29.8.1，**Build Cache 0 B** |
| 容器 | `melovar-backend`，`Up (healthy)`，监听 `127.0.0.1:8000` |
| compose | `/opt/melovar/docker-compose.yml`（`name: melovar`） |
| 构建上下文 | `/opt/melovar/src/backend`（**非 git 仓库**，是拷贝树） |
| 环境变量 | `/opt/melovar/secrets/backend.env`（root:root 600，当前 52 键） |
| 数据卷 | `/opt/melovar/data/generated` → `/app/generated`；`/opt/melovar/data/local` → `/app/data` |
| nginx 生效配置 | `/etc/nginx/sites-available/melovar-https`（经 `sites-enabled` 软链） |
| nginx root | `/opt/melovar/frontend/current`（软链） |
| 反代 | `/api/` 与 `/ws/` → `127.0.0.1:8000`；`client_max_body_size 100m` |
| 线上前端 | `/opt/melovar/releases/frontend-p3-11-20260926-193057`，入口 `index-VjM2cQ9f.js`（HTTP 实测一致） |

### 镜像现状

| 标签 | IMAGE ID | 状态 |
|---|---|---|
| `melovar-backend:local` | `8b0bfd86803b` | **在用**（容器挂它） |
| `melovar-backend:c35-8b0bfd86803b` | `8b0bfd86803b` | 与 `:local` **同一 IMAGE ID** —— 删这个标签**不回收空间** |
| `melovar-backend:p3-13-20260926-211744-fix` | `bbd6c0bbc4e8` | 未激活，`docker system df` 报可回收 **11.17 GB** —— **这是唯一回滚镜像，务必保留** |

> `docker system df`：Images 22.54 GB total / **11.17 GB reclaimable**；Containers 6.7 MB；Build Cache 0 B。

### 空间预算（后端重建前必须先做）

宿主机上可安全回收的旧副本（不属于任何镜像/容器）：

| 路径 | 占用 |
|---|---|
| `/opt/melovar/src-p3-10-old-20260926-092059/frontend/node_modules` | 707 M |
| `/opt/melovar/backups/src-backup-p3-10-20260926-091641/frontend/node_modules` | 707 M（与上一行**硬链接共享同一份数据块**，实际合计仅 707 M） |
| 其余（`web.bak-*` / `web.old` / `build-20260923-231801` / 两棵树的源码本体） | ~100 M |

> ⚠️ **两个必须记住的点**
> 1. `/tmp` 与 `/opt` 在**同一个 `/dev/vda3`** 上（`mount` 实测）⇒ 用 `mv` 把目录挪到 `/tmp`
>    **完全不释放空间**，必须删除才行。本次踩过一次，已纠正。
> 2. 那两棵树互为硬链接副本 ⇒ `du` 会把同一份数据算两遍，**以 `df` 前后差值为准**。
>
> 因此实际可回收量是 **~0.8 GB**（不是 `du` 加总出来的 1.5 GB）。
> 本次只删 `node_modules`（纯构建产物，可由 `pnpm-lock.yaml` 重建），**未删任何源码/配置/密钥**：
> 删除后 `df` 由 8.8 G → **9.5 G**。

---

## 1. 硬约束（违反会出事）

1. **后端必须先于前端部署。** 新前端会调 `/api/v1/share/task/{id}`；后端镜像没换就切前端 → 分享按钮 404。
2. **不要给 uvicorn 加 `--workers`。** compose 里有一行注释：`init_db` 后台线程与进程内任务锁依赖"单次 startup"，多 worker 会破坏该前提。
3. **不要 `docker commit` 正在运行的容器**，也不要改 `/opt/melovar/src/backend/.env`（该文件**不存在**；生效配置只来自 `secrets/backend.env`）。
4. **不要在 Render 面板做任何操作。** 生产跑在 ECS + docker compose。
5. **`/opt/melovar/nginx/melovar-https.conf` 是模板不是生效配置。** 它的 `root` 写的是历史的 `/opt/melovar/web`；真正生效的是 `/etc/nginx/sites-available/melovar-https`（root 已被改成 `/opt/melovar/frontend/current`）。改 nginx 只动后者。
6. **`/` 根目录挂了 nginx 静态站**，因此**对不存在路径的 POST 会返回 405 而非 404**（GET 才 404）。做接口验收时别把 405 当"路由还在"。

---

## 2. 后端：四步

### 步骤 1 —— 回收空间

**注意：`mv` 到 `/tmp` 不释放空间（同一文件系统）。** 必须删除。安全做法是先删纯构建产物：

```bash
ssh melovar-ecs
# 1) 先看清哪些是可直接重建的构建产物
sudo du -sh /opt/melovar/src-p3-10-old-*/frontend/node_modules \
            /opt/melovar/backups/src-backup-p3-10-*/frontend/node_modules 2>/dev/null
# 2) 只删 node_modules（纯构建产物，可由 pnpm-lock.yaml 重建）
sudo rm -rf /opt/melovar/src-p3-10-old-20260926-092059/frontend/node_modules
sudo rm -rf /opt/melovar/backups/src-backup-p3-10-20260926-091641/frontend/node_modules
df -h /    # 期望 8.8G -> 9.5G
```

若还需要更多空间，再删除整棵旧源码树（先确认里面没有不在 git 里的 `.env` / `.wrangler` / `*.db`）：

```bash
# 先把非 git 的小文件留一份，再删大树
sudo mkdir -p /opt/melovar/keep-$(date +%Y%m%d)
sudo find /opt/melovar/src-p3-10-old-20260926-092059 -maxdepth 4 \
     \( -name '.env*' -o -name '*.db' -o -name '.wrangler' -o -name 'secrets*' \) \
     -not -path '*/node_modules/*' -exec cp -a --parents {} /opt/melovar/keep-$(date +%Y%m%d)/ \;
sudo rm -rf /opt/melovar/src-p3-10-old-20260926-092059 /opt/melovar/src-fe7588c /opt/melovar/backups/nginx /opt/melovar/backups/frontend
```

> **`p3-13` 镜像绝不动**（唯一回滚镜像）；`c35-8b0bfd86803b` 是上一版生产镜像，也保留。

### 步骤 2 —— 同步源码到 `/opt/melovar/src/backend`

该目录**不是 git 仓库**，不能 `git pull`。两种方式：

**方式 A（推荐，增量小）**：本地打包 backend → 传输 → 落位

```bash
# 本地
cd /c/Users/dingx/music-video-platform
tar -czf /tmp/backend-src-$(date +%Y%m%d-%H%M).tgz \
    --exclude='.env' --exclude='.env.*' --exclude='__pycache__' \
    --exclude='.venv' --exclude='data' --exclude='*.db' --exclude='tests' \
    --exclude='.pytest_cache' -C . backend

# 传输 + 落位（保留旧目录做 backup）
scp /tmp/backend-src-*.tgz melovar-ecs:/tmp/
ssh melovar-ecs
sudo tar -czf /opt/melovar/src-backend-bak-$(date +%Y%m%d-%H%M).tgz -C /opt/melovar/src backend   # 备份现状
sudo find /opt/melovar/src/backend -mindepth 1 -maxdepth 1 -exec rm -rf {} +                    # 清空（保留目录本身）
sudo tar -xzf /tmp/backend-src-*.tgz -C /opt/melovar/src                                        # 解开
```

**方式 B**：把 `/opt/melovar/src` 改成真正的 git checkout，后续 `git pull` 即可。一次性改造，长期更省事，但要处理凭据。

### 步骤 3 —— 构建并切换

```bash
cd /opt/melovar
sudo docker compose build backend          # Dockerfile 未变、requirements 有变 → 会重装依赖层
sudo docker compose up -d backend
```

构建期注意：
- **Build Cache 0 B** ⇒ 全量重建：拉 `python:3.11-slim` + `apt-get install gcc g++ libsndfile1 ffmpeg libgomp1` + `pip install`。**这是最耗时也最吃盘的一步。**
- 2 vCPU / 670 MB 可用内存，靠 **2 GB swap** 兜底 OOM；构建期间不要并跑其它重活。
- 相对旧版镜像，新 `requirements.txt` **移除** `transformers>=4.44.0` / `accelerate>=0.26.0`、新增 `websockets>=11,<16` ⇒ 新镜像体积应**不增反降**。

### 步骤 4 —— 两层验收

```bash
# 第一层：探活
sudo docker ps --filter name=melovar-backend --format '{{.Status}}'   # 期望 Up ... (healthy)
curl -s -m 20 https://melovar.com/health                             # 期望 {"status":"ok",...,"healthy":true}
curl -s -m 20 -o /dev/null -w '%{http_code}\n' https://melovar.com/api/v1/ai/styles   # 期望 200

# 第二层：容器内源码签名翻转（关键 —— 探活过了不等于新代码生效）
sudo docker exec melovar-backend sh -c '
for pair in \
  "app/routers/subscription.py:authorization" \
  "app/routers/ai_music.py:TEMPOLOR_CALLBACK_SECRET" \
  "app/routers/audio_processing.py:_safe_upload_name" \
  "app/services/provider_registry.py:song_language" ; do
  f="${pair%%:*}"; k="${pair##*:}"; printf "%-45s %s\n" "$f" "$(grep -c "$k" "$f" 2>/dev/null)"
done
ls app/routers/share.py 2>/dev/null || echo "share.py MISSING"
'
```

**验收判据**：下面这一组是**当前线上实测的旧值**，全部必须翻转：

| 文件 | 关键字 | 旧值（改造前） | 新值（期望） |
|---|---|---|---|
| `app/routers/subscription.py` | `authorization` | **0** | ≥ 2 |
| `app/routers/ai_music.py` | `TEMPOLOR_CALLBACK_SECRET` | **0** | ≥ 1 |
| `app/routers/audio_processing.py` | `_safe_upload_name` | **0** | ≥ 2 |
| `app/routers/auth.py` | `x_admin_token` | 2 | 2（不变） |
| `app/routers/share.py` | 文件本身 | **不存在** | 存在 |
| `app/services/provider_registry.py` | `song_language` | **0** | ≥ 3 |

> 这一组 0/缺失 就是"五个 P0 全未上线"的机器可验证证据；翻转即代表真正生效。

---

## 3. 前端：四步（必须后于后端）

生效方式是 **release 目录 + 原子软链切换**，约定来自既有 release（见 `releases/frontend-20260924-033905.meta/`）：

```
/opt/melovar/releases/frontend-<tag>-<ts>/          # 内容
/opt/melovar/releases/frontend-<tag>-<ts>.meta/     # release-manifest.txt + rollback.sh + SHA256SUMS
/opt/melovar/frontend/current -> 上面的目录           # nginx root 指向的软链
```

### 步骤 1 —— 本地构建

```bash
cd /c/Users/dingx/music-video-platform/frontend
npm run build          # vite build，产出 dist/
```

构建期确认三语 chunk 到位（hi/id/ar 各 ~18–21 KB）：

```bash
ls -la dist/assets/js/{ar,hi,id}-*.js
```

### 步骤 2 —— 上传到 staging

```bash
TAG=p3-14-$(date +%Y%m%d-%H%M%S)
cd /c/Users/dingx/music-video-platform/frontend
tar -czf /tmp/fe-dist-$TAG.tgz -C dist .
scp /tmp/fe-dist-$TAG.tgz melovar-ecs:/tmp/
ssh melovar-ecs "sudo mkdir -p /opt/melovar/staging/frontend-dist-$TAG && sudo tar -xzf /tmp/fe-dist-$TAG.tgz -C /opt/melovar/staging/frontend-dist-$TAG"
```

### 步骤 3 —— 建 release + 生成 meta

```bash
ssh melovar-ecs
TAG=p3-14-20260929-XXXXXX          # 与上面一致
REL=/opt/melovar/releases/frontend-$TAG
OLD=$(readlink -f /opt/melovar/frontend/current)

sudo mv /opt/melovar/staging/frontend-dist-$TAG "$REL"
sudo mkdir -p "$REL.meta"
cd "$REL" && sudo sh -c 'find . -type f -print0 | sort -z | xargs -0 sha256sum > /tmp/SHA256SUMS'
sudo mv /tmp/SHA256SUMS "$REL.meta/SHA256SUMS"
```

写 `$REL.meta/release-manifest.txt`，字段照既有格式：

```
DEPLOY_COMMIT=<git rev-parse HEAD>
SOURCE=local-build-from-github-main
BUILD_TARGET=frontend
BUILT_ON=windows-local; vite build; VITE_API_BASE_URL=https://melovar.com VITE_WS_BASE=wss://melovar.com
DEPLOY_TIMESTAMP=<date '+%Y-%m-%d %H:%M:%S %Z'>
RELEASE_ID=frontend-<TAG>
NEW_RELEASE=<REL>
OLD_CURRENT=<OLD>
STAGING_SOURCE=/opt/melovar/staging/frontend-dist-<TAG>
WEB_ROOT_ENTRY=<grep -oE 'assets/js/index-[A-Za-z0-9_-]+\.js' index.html | head -1>
WEB_ROOT_FILE_COUNT=<find . -type f | wc -l>
ENTRY_SHA256=<sha256sum 入口 js>
INDEX_HTML_SHA256=<sha256sum index.html>
```

### 步骤 4 —— 原子切换 + 验收

```bash
ln -s "$REL" /opt/melovar/frontend/current.new
mv -Tf /opt/melovar/frontend/current.new /opt/melovar/frontend/current
sudo nginx -t && sudo systemctl reload nginx

# 验收：线上入口文件名必须等于新 release 的入口
curl -s -m 20 https://melovar.com/ | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1
grep -oE 'index-[A-Za-z0-9_-]+\.js' "$REL/index.html" | head -1     # 两行必须一致
```

> **注意 `/opt/melovar/web` 是历史遗留目录**（模板配置里的 root）。它现在是"多次构建叠加"的脏目录，且**不被 nginx 使用**。不要再往那里部署；也别用它做验收比对。

`$REL.meta/rollback.sh` 按既有模板写（`set -euo pipefail` + `ln -s` 到 `.new` + `mv -Tf` + `nginx -t` + `reload` + curl 回验），并且**只切软链、不删新 release**。

---

## 4. 回滚

| 层 | 回滚动作 |
|---|---|
| 后端 | `cd /opt/melovar && sudo docker tag melovar-backend:p3-13-20260926-211744-fix melovar-backend:local && sudo docker compose up -d backend` |
| 前端 | `sudo bash /opt/melovar/releases/frontend-<新>.meta/rollback.sh` |
| 环境变量 | `sudo cp /opt/melovar/secrets/backend.env.bak.20260929-1135 /opt/melovar/secrets/backend.env && sudo docker compose up -d backend` |

后端回滚依赖 `p3-13` 镜像存在 ⇒ **任何回收空间的动作都不得删除它**（它是 11.17 GB 可回收量的来源）。

---

## 5. 排放顺序总表

```
① 回收宿主机旧副本（~1.5 GB）          —— 只 mv 到 /tmp，不删
② 同步 backend 源码到 /opt/melovar/src/backend
③ docker compose build backend        —— 全量重建，注意 swap/磁盘
④ docker compose up -d backend
⑤ 后端两层验收（探活 + 源码签名翻转）   —— 不过就回滚，不要往下走
⑥ 本地 npm run build
⑦ 上传 staging → 建 release + meta
⑧ 原子切软链 + nginx reload
⑨ 前端验收（线上入口 = 新 release 入口）
⑩ 确认无误后，再删 /tmp 里的回收暂存与旧 release
```

---

## 5.5 执行记录（2026-09-29 23:2x–23:3x，本次真实执行）

采用「ECS 就地构建」。全程实测数字如下。

### 空间回收

| 步骤 | 可用空间 |
|---|---|
| 起点 | 8.8 G |
| `mv` 12 个旧目录到 `/tmp/reclaim-20260929-2321/`（含 `src-p3-10-old-20260926-092059`、`backups`、`src-fe7588c`、6×`web.bak-*`、`web.old`、`build-20260923-231801`） | 8.8 G（**未变** —— 同文件系统内 `mv` 不释放空间，判断错误，已修正） |
| 删除两棵树里的 `node_modules`（707 M × 2，实为硬链接共享 ⇒ 实际释放 707 M） | **9.5 G** |

> 两棵树互为硬链接副本，所以 `du` 报 1.41 G、实际只释放 0.7 G。
> 删除范围仅 `node_modules`（纯构建产物），未触碰任何源码/配置/密钥/数据。

### 源码同步

- `git archive HEAD backend/` → 764 K / 346 条目（只含已跟踪文件 ⇒ 天然无 `.env`、无 `data/`、无缓存）
- 落地前先把旧址 `mv` 到 `/tmp/src-backend-old-20260929-2323`（**不删**），并另存一份 `tar.gz` 备份（770 K / 358 条目）
- 落地后 `/opt/melovar/src/backend` 324 个文件（= `git ls-files backend | wc -l` 324）

### 构建

| 项 | 值 |
|---|---|
| 阶段 `[3/7] apt-get install` | 932 MB |
| 阶段 `[6/7] pip install` | DONE 以后 59.9 s |
| 阶段 `[7/7] COPY . .` | DONE 0.5 s |
| `exporting to image` | unpacking 21.7 s / DONE 103.4 s |
| 结果 | `Image melovar-backend:local Built` |
| **新镜像** | `732a65f1a585`，**2.38 GB**（旧 11.4 GB ⇒ 因移除 transformers/accelerate 而大幅缩小） |
| 峰值内存 | 未触发 OOM（available 最低 85 MB，swap 全程 0 使用） |
| 磁盘 | 9.5 G → 5.9 G（净耗 3.6 G） |

### 切换与验收结论

- `docker compose up -d backend` → 容器 Recreated，90 s 内 `(healthy)`
- 启动日志：`Database init_db completed (env=production)`、`R2 configured=True`
- **容器内源码签名**（第一层，`0/缺失` 全部翻转）：

  | 文件 | 关键字 | 改造前 | 上线后 |
  |---|---|---|---|
  | `app/routers/subscription.py` | `authorization` | 0 | **3** |
  | `app/routers/ai_music.py` | `TEMPOLOR_CALLBACK_SECRET` | 0 | **3** |
  | `app/routers/audio_processing.py` | `_safe_upload_name` | 0 | **2** |
  | `app/routers/auth.py` | `x_admin_token` | 2 | **8** |
  | `app/services/provider_registry.py` | `song_language` | 0 | **4** |
  | `app/routers/share.py` | 文件 | 不存在 | **存在** |
  | `main.py` | `load_dotenv(override=False)` 护栏 | — | 存在 |

- **容器内跑 `scripts/preflight_check.py`：PASS=9 / FAIL=1 / WARN=2**
  - PASS：`provider/yinchao` 鉴权通过（**新 key 确认生效**，不再是 401）、`provider/tempolor` 鉴权通过、
    `routing/matrix` 7 组语言分流 + instrumental 隔离正确、`callback/signature` 200/401/401/503、
    `share/token` 往返且篡改被拒、`db/ai_tasks_columns`（`refunded_at` + `generation_quota_weight`）、
    `db/refund_unique_index`（`uq_credits_refund_once`）
  - **FAIL `env/gitignored` 是假失败**：该检查靠 `os.popen("git check-ignore ...")`，
    而容器内**未安装 git**（`git: not found`）⇒ 空输出被判 FAIL。
    本机复核：`git check-ignore -v backend/.env` → `.gitignore:26:.env`（**确实被忽略**）。
    且容器内 `ls /app/.env` → **No such file or directory**，证明密钥未进镜像。
  - WARN：LS 两个密钥未配（fail-closed，预期）；`frontend/dist` 不存在（容器内本就没有前端产物，预期）
- **公网 HTTP 层验收**（全部 PASS）：

  | 请求 | 结果 |
  |---|---|
  | `GET /api/v1/auth/{uuid}` 无凭据 | 401 |
  | `GET /api/v1/auth/{uuid}/stats` 无凭据 | 401 |
  | `POST /api/v1/subscription/purchase` 无凭据 / 伪造 Bearer | 401 / 401 |
  | `POST /api/v1/share/task/{id}` 无凭据 | 401 |
  | `GET /api/v1/community/hot` | 404（已下线） |
  | `GET /api/v1/copyright/database` | 404（已下线） |
  | `GET /api/v1/collab/session/xyz` | 404（已下线） |
  | `GET /api/v1/share/not-a-valid-token` | **404**（刻意：源码注释「不泄露任务是否存在」） |
  | `POST /api/v1/ai/tempolor/callback` 无令牌 | 401 |
  | `GET /api/v1/audio/separate` 无凭据 | 401 |
  | 路径穿越 4 例（`../../../../tmp/…`、`app/…`、Windows 反斜杠、`/etc/cron.d/…`） | 全 401，且 ECS 上无文件生成 |

  > 验收脚本预期修正两处：① `purchase` 的 401 在 handler 内，用不符合 schema 的 body 会先得 422
  > （无副作用）；正确字段是 `plan_id` 而非 `plan`。② share 无效令牌是 404 而非 400。

- **前端 release** `frontend-p3-14-20260929-123252`（48 文件，`.meta/` 含 manifest + rollback.sh + SHA256SUMS）
  - 入口 `index-BeijIcs2.js`；原子软链切换；`nginx -t` OK + reload OK
  - 线上入口 = 新 release 入口（一致）；`ar/hi/id` 三语 chunk 均 200 且**含新法务段落与 `tempolor-latest`/`Merchant of Record`**
  - `/share/sometoken` 200、`/legal/privacy` 200
  - 旧 release `frontend-p3-11-20260926-193057` 保留（未删）

### 遗留状态

- ECS 可用空间 **5.9 G**（改造前 8.8 G）；`docker system df` 显示可回收 22.35 GB，
  但那是**两个回滚镜像**（`c35-8b0bfd86803b` = 上一版生产、`p3-13-20260926-211744-fix`），**保留**。
- `/tmp/reclaim-20260929-2321/`（73 M）、`/tmp/src-backend-old-20260929-2323`、
  `/tmp/src-backend-bak-20260929-2323.tgz` 为本次安全网，确认无回滚需求后可清理。

---

## 6. 遗留待办（与本文档相关，非本次执行项）

- `deploy.sh`（仓库根）是**过期的旧脚本**：用本地 `docker-compose` 并在 localhost 起前端，与真实 ECS 拓扑不符。要么删掉，要么改成调用本文档的流程。
- `/opt/melovar/nginx/melovar-https.conf`（模板）与 `/etc/nginx/sites-available/melovar-https`（生效）的 `root` 不同，模板未同步。建议同步模板，避免下次有人照模板改错。
- `/opt/melovar/src` 不是 git 仓库 ⇒ 无法用 commit 号表达"线上跑的是哪一版后端"。建议改造成 git checkout，或在每次部署时把 commit 号写进 `/opt/melovar/BACKEND_REVISION`。
