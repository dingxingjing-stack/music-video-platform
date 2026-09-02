# PHASE 7.5 — Production Connectivity Recovery Audit

**Date:** 2026-08-17
**Type:** READ-ONLY infrastructure audit (no production code/config modified)
**Scope:** Verify why the deployed gateway (`music-api-gateway.dingxingjing.workers.dev`) cannot reach the real backend, and classify the failure for remediation.

---

## 1. Executive Summary

| Component | Status |
|---|---|
| Gateway Worker (`music-api-gateway`) | **DEPLOYED & RUNNING** (3 versions, 2026-07-13) |
| Worker DNS | ✅ Resolves |
| Worker R2 binding (`BUCKET`) | ✅ Working (returns gateway.js `{"error":"File not found"}` for missing key) |
| Worker **API_BASE_URL binding** | ❌ **`http://localhost:8002`** ← **ROOT CAUSE** |
| Backend on Render (`ai-music-backend-8e85.onrender.com`) | ❌ **404 + `x-render-routing: no-server`** (service not present) |
| Frontend Pages (`music-video-platform.pages.dev`) | ✅ Deployed (1 week ago, git-integrated) |
| R2 bucket `music-audio-storage` | ✅ Exists (created 2026-07-13) |
| Modal ACE-Step app | ✅ Deployed (`avireon-music-platform-acestep`, 2026-08-13) |
| Modal Spleeter app | ⚠️ **NOT FOUND in app list** (see §5) |
| Modal `music-audio-storage` / models volume | ⚠️ `ace-step`, `hf` dirs only — **no `spleeter` dir** (models never preloaded via Modal) |

**E2E verdict:** NOT EXECUTABLE / BLOCKED BY CONFIGURATION. The gateway worker runs and forwards traffic, but its `API_BASE_URL` points at the dev-only value `http://localhost:8002`, which Cloudflare refuses to proxy → 403 / error 1003. The intended Render backend itself is also not deployed (`no-server`). Both halves of the chain are broken.

---

## 2. Evidence Chain

### 2.1 Gateway is alive and forwarding (not a Cloudflare edge block)

| Probe | Result | Interpretation |
|---|---|---|
| `GET /api/v1/r2/download/nonexistent.mp3` | `{"error":"File not found"}` | R2 branch of gateway.js runs → worker deployed & code live |
| `GET /api/v1/ai/limits` (POST `/api/v1/ai/generate`) | HTTP 403, **with** `Access-Control-Allow-Origin: *` + `Access-Control-Allow-Credentials: true` | 403 carries gateway.js success-forward CORS headers → the 403 is **returned by the upstream**, not a Cloudflare edge rejection of the worker |
| `GET https://ai-music-backend-8e85.onrender.com/` + `/health` | HTTP 404, header `x-render-routing: no-server`, **no** CORS headers | Render has **no server** behind that hostname; also proves gateway origin ≠ onrender (headers differ) |
| `POST /api/v1/ai/generate` w/ JSON body | HTTP 403, CORS headers present | consistent with worker forwarding to its configured origin |

### 2.2 Worker bindings read from Cloudflare API (authoritative)

Query: `GET /accounts/{acct}/workers/scripts/music-api-gateway/settings`

```json
"bindings": [
  { "name": "API_BASE_URL", "type": "plain_text", "text": "http://localhost:8002" },
  { "name": "BUCKET",        "type": "r2_bucket",   "bucket_name": "music-audio-storage" },
  { "name": "CORS_ORIGIN",   "type": "plain_text", "text": "*" },
  { "name": "RATE_LIMIT",    "type": "plain_text", "text": "100" }
]
```

**Root cause:** `API_BASE_URL = "http://localhost:8002"` is the **development** value (see `wrangler.workers.toml:7`). It was deployed as-is via `wrangler deploy workers/gateway.js --name music-api-gateway` (per `docs/CLOUDFLARE_DEPLOYMENT.md`), with no `--var API_BASE_URL=...` override. Cloudflare Workers cannot fetch `localhost:8002` from the sandbox → upstream unreachable → gateway surfaces 403 / error 1003 ("Direct IP access not allowed").

### 2.3 Deployment topology (as actually deployed)

- Root `wrangler.toml` = **Pages** project (`name = "music-video-platform"`, `pages_build_output_dir = "frontend/dist"`, `API_BASE_URL = onrender`). Not used for the Worker deployment.
- `wrangler.workers.toml` = **Workers** config (`name = "music-api-gateway"`, `main = "workers/gateway.js"`, `API_BASE_URL = "http://localhost:8002"`). This is the file whose vars were actually bound.
- `workers/wrangler.cdn.toml` = `zyvexo-cdn` (R2 CDN), separate.
- Cloudflare account: `b8743fc421303345b81bce87d3b10742` (dingxingjing@gmail.com), 3 worker versions, compatibility_date `2026-07-13`.
- `wrangler pages project list` → `music-video-platform` exists (git provider, modified ~1 week ago).
- `wrangler r2 bucket list` → `music-audio-storage` exists.
- No Pages Functions (`functions/` and `frontend/dist/_worker.js` absent).

---

## 3. Failure Classification

| # | Layer | Finding | Severity |
|---|---|---|---|
| 1 | **Worker → Backend** | `API_BASE_URL = http://localhost:8002` (dev value deployed) | 🔴 **BLOCKER** |
| 2 | **Backend deployment** | Render hostname returns `404 + x-render-routing: no-server`; no service running | 🔴 **BLOCKER** |
| 3 | **Modal Spleeter app** | `avireon-music-platform-spleeter` **absent** from `modal app list`; models volume lacks `spleeter/` | 🟠 **HIGH** (stems path breaks at runtime) |
| 4 | **Modal ACE-Step** | `avireon-music-platform-acestep` deployed 2026-08-13 | ✅ OK |
| 5 | Frontend → gateway | Build resolves to `music-api-gateway.dingxingjing.workers.dev` (Phase 6.5) | ✅ OK |

**Root-cause statement:** The gateway worker is healthy and forwarding, but was deployed against a dev-only origin. Fixing the binding alone is insufficient — the Render backend must also be re-deployed (or the origin switched to the live Modal/web backend).

---

## 4. Remediation Plan (proposed, not executed — read-only phase)

1. **Redeploy backend.** Decide canonical backend host:
   - Preferred: the onrender hostname once the service is re-created, **or**
   - the Modal web endpoint if web containers are intended as origin.
   - Verify `/health` returns 200 before wiring.
2. **Re-bind gateway var:**
   - `wrangler deploy workers/gateway.js --name music-api-gateway --var API_BASE_URL:https://<canonical-backend>` (wrangler v4 syntax) or `--var API_BASE_URL=https://...`.
   - Re-verify: `GET <gateway>/api/v1/ai/limits` should no longer 403; CORS headers should still be present.
3. **Modal Spleeter:** confirm/re-deploy `spleeter_modal.py` and run `preload_models()` so `spleeter/` weights exist in `avireon-music-platform-models-v1`.
4. **Re-run Phase 7 E2E checklist** (gateway reachability, limits, budget, music flow, R2 upload/private-read) once origin answers.

---

## 5. Modal Inventory (as of 2026-08-17)

| App | State | Deployed |
|---|---|---|
| avireon-ai-music-platform | deployed | 2026-08-01 |
| avireon-ai-music | deployed | 2026-08-02 |
| avireon-music-platform | deployed | 2026-08-04 |
| avireon-music-platform-musicgen | deployed | 2026-08-04 |
| avireon-music-platform-acestep | deployed | 2026-08-13 |
| lyrics-llm-qwen25 | deployed | 2026-08-16 |
| **avireon-music-platform-spleeter** | **⚠️ not listed** | — |

Models volume `avireon-music-platform-models-v1` contains only `ace-step/` and `hf/`.

---

## 6. Conclusion

**Phase 7.5 = COMPLETE — VERDICT: BLOCKED BY CONFIGURATION (two independent breakages).**

The failure is **not** a worker-runtime or Cloudflare-edge issue; it is a **configuration/deployment gap**:

1. Worker `API_BASE_URL` points at `http://localhost:8002` (dev value) — must be re-bound to a reachable origin.
2. The intended Render backend is not deployed (`no-server`).
3. Modal Spleeter app + preloaded models are missing.

E2E cannot pass until origin + binding are corrected. No production files were modified during this audit.
