"""生产部署前自动校验（只读，不部署）。

对 backend/deploy_bundle/ 执行：
  1. 输出 bundle 文件清单（manifest）
  2. 校验禁止文件缺失（tests/docs/scripts/POC/独立 GPU App/未批准新服务/*.db/.env 等）
  3. import 完整性：在临时副本中独立 import main，必须成功
  4. provider 默认 = modal_ace_step 且 gpu = L40S
  5. HF fallback 仍禁止 SoundHelix/mock 音频
  6. generation_cost_logs migration 正常（独立副本建表）
  7. 生产 GPU App（ace_step_modal.py）配置未变：gpu=L40S / max_containers=1 / 无 keep_warm

全部通过退出码 0；任一失败退出码 1 并打印失败项。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE = os.path.join(BACKEND, "deploy_bundle")

FAILED = []


def check(name: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def read(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


PROBE = r"""
import os
import sys
import sqlite3
import tempfile

sys.path.insert(0, os.getcwd())
import main  # 必须可导入
from app.services.provider_registry import get_provider_registry as registry
p = registry().select()
assert p.name == "modal_ace_step", p.name
assert p.gpu == "L40S", p.gpu
from app.routers.ai_music import _try_hf_ace_step_fallback  # fallback 存在
from app.services import task_store
db = os.path.join(tempfile.mkdtemp(), "beta.db")
task_store._DB_PATH = db
task_store._DB_DIR = os.path.dirname(db)
task_store._get_conn().close()
conn = sqlite3.connect(db)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
conn.close()
assert "generation_cost_logs" in tables, tables
assert "ai_tasks" in tables, tables
assert "task_locks" in tables, tables
print("PROBE_OK provider=%s gpu=%s tables=%s" % (p.name, p.gpu, sorted(tables)))
"""


def main() -> int:
    if not os.path.isdir(BUNDLE):
        print("[FAIL] deploy_bundle/ 不存在，请先运行 python scripts/build_deploy_bundle.py")
        return 1

    # ── 1. bundle 清单 ──
    manifest = []
    mpath = os.path.join(BUNDLE, "manifest.json")
    if os.path.exists(mpath):
        manifest = json.loads(read(mpath)).get("files", [])
    else:
        manifest = [os.path.relpath(os.path.join(r, f), BUNDLE).replace("\\", "/")
                    for r, _, fs in os.walk(BUNDLE) for f in fs]
    print(f"=== bundle 文件清单（{len(manifest)} 个）===")
    for f in sorted(manifest):
        print("  ", f)

    # ── 2. 禁止文件缺失检查 ──
    forbidden_files = (
        "asr_client.py", "tts_client.py", "voice_clone_task.py",
        "ace_step_modal.py", "spleeter_modal.py", "musicgen_modal.py", "gpt_sovits_modal.py",
    )
    forbidden_dirs = ("tests", "docs", "scripts", "poc", "__pycache__", "voice_models")
    violations = []
    for rel in manifest:
        parts = rel.split("/")
        if any(p in forbidden_dirs for p in parts[:-1]):
            violations.append(f"禁止目录 {rel}")
        base = parts[-1]
        if base in forbidden_files:
            violations.append(f"禁止文件 {rel}")
        if base in (".env", ".envrc", "secrets.json", "secrets.local.json"):
            violations.append(f"禁止文件 {rel}")
        if any(base.endswith(e) for e in (".db", ".wav", ".mp3", ".pyc", ".log")):
            violations.append(f"禁止扩展名 {rel}")
    check("2. bundle 不含禁止文件/目录", not violations, "; ".join(violations[:12]))

    new_services = ("app/services/asr_client", "app/services/tts_client",
                    "app/services/voice_clone_task", "app/services/separation")
    bad = [m for m in manifest if m.startswith(new_services)]
    check("未批准新服务未进入 bundle", not bad, "; ".join(bad))

    bad = [m for m in manifest if m.startswith(("scripts/", "tests/", "docs/"))]
    check("scripts/tests/docs 未进入 bundle", not bad, "; ".join(bad))

    # ── 3/4/6. 临时副本 import 验证 ──
    tmp = tempfile.mkdtemp(prefix="predeploy_")
    try:
        for rel in manifest:
            src = os.path.join(BUNDLE, rel.replace("/", os.sep))
            dst = os.path.join(tmp, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        with open(os.path.join(tmp, ".env"), "w", encoding="utf-8") as fh:
            fh.write("")
        with open(os.path.join(tmp, "probe.py"), "w", encoding="utf-8") as fh:
            fh.write(PROBE)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, "probe.py"], cwd=tmp,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        out = (r.stdout or "") + (r.stderr or "")
        tail = out.strip().splitlines()[-1] if out.strip() else ""
        check("3. bundle import 完整性（独立副本 import main）", r.returncode == 0, tail)
        check("4. provider 默认 modal_ace_step / gpu=L40S",
              r.returncode == 0 and "PROBE_OK" in (r.stdout or ""))
        check("6. generation_cost_logs migration（独立副本建表）",
              r.returncode == 0 and "generation_cost_logs" in (r.stdout or ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ── 5. HF fallback 禁 mock/SoundHelix ──
    src = read(os.path.join(BUNDLE, "app/routers/ai_music.py"))
    no_mock_ref = "MOCK_AUDIO_URL" not in src and "soundhelix.com/examples" not in src
    rejects_soundhelix = "soundhelix.com" in src
    has_fallback = "_try_hf_ace_step_fallback" in src
    check("5. HF fallback 禁 SoundHelix/mock（无 mock 引用 + 显式拒绝 soundhelix）",
          no_mock_ref and rejects_soundhelix and has_fallback,
          "no_mock=%s reject=%s has_fn=%s" % (no_mock_ref, rejects_soundhelix, has_fallback))

    # ── 7. 生产 GPU App 配置未变 ──
    gpufile = os.path.join(BACKEND, "ace_step_modal.py")
    gsrc = read(gpufile)
    ok_gpu = 'gpu="L40S"' in gsrc
    ok_containers = "max_containers=1" in gsrc
    ok_nowarm = "keep_warm" not in gsrc.replace("无 keep_warm", "")
    check("7. 生产 GPU App 未变（gpu=L40S / max_containers=1 / 无 keep_warm）",
          ok_gpu and ok_containers and ok_nowarm,
          f"gpu={ok_gpu} containers={ok_containers} no_warm={ok_nowarm}")

    print()
    if FAILED:
        print("=== 校验未通过：%d 项 ===" % len(FAILED))
        for f in FAILED:
            print("  -", f)
        return 1
    print("=== 全部通过，可以进入部署审批 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())