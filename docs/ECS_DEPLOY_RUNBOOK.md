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
| `/opt/melovar/src-p3-10-old-20260926-092059` | 726 M |
| `/opt/melovar/backups` | 731 M |
| `/opt/melovar/web*`（6 个 bak + old + 无用的 `web`） | ~22 M |
| `/opt/melovar/src-fe7588c` | 9.1 M |
| **合计** | **≈ 1.49 GB** |

回收后可用空间 ≈ **10.3 GB**。

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

```bash
ssh melovar-ecs
sudo mv /opt/melovar/src-p3-10-old-20260926-092059 /opt/melovar/backups /opt/melovar/web.bak-* /opt/melovar/web.old /opt/melovar/src-fe7588c /tmp/reclaim-$(date +%Y%m%d-%H%M)/
df -h /    # 期望 avail 由 8.8G 变为 ~10.3G
```

> 用 `mv` 到 `/tmp` 而不是 `rm`：确认新版本跑起来后再删。**`p3-13` 镜像绝不动。**

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

## 6. 遗留待办（与本文档相关，非本次执行项）

- `deploy.sh`（仓库根）是**过期的旧脚本**：用本地 `docker-compose` 并在 localhost 起前端，与真实 ECS 拓扑不符。要么删掉，要么改成调用本文档的流程。
- `/opt/melovar/nginx/melovar-https.conf`（模板）与 `/etc/nginx/sites-available/melovar-https`（生效）的 `root` 不同，模板未同步。建议同步模板，避免下次有人照模板改错。
- `/opt/melovar/src` 不是 git 仓库 ⇒ 无法用 commit 号表达"线上跑的是哪一版后端"。建议改造成 git checkout，或在每次部署时把 commit 号写进 `/opt/melovar/BACKEND_REVISION`。
