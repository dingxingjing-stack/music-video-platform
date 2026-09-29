"""音潮 V4.0 最大时长测试脚本（独立测试，非生产代码）。

结论先行（本脚本只做只读能力核 + 安全探测，默认不触发生成）：
- generate 端点 POST /api/v1/song/generate 必需字段 = {model, task_type}；可选 prompt/n。
  → **没有 duration / max_duration / audio_duration 参数**（已通过 422 校验实测确认）。
- extend 端点 POST /api/v1/song/extend 存在（GET→405 证明是 POST 路由），必需字段 = {model}。
  → 其它字段（引用的歌曲 id / 续写时长）未在 422 里暴露，官方未公开 schema。

因此：
- 无法「指定 120/180/240/300 秒」—— generate 不接受 duration 参数，本脚本不会伪造。
- 真实最大时长只能通过「生成后观察 duration」或「extend 后观察 duration」获得，
  二者都会产生费用，默认不执行；需要时显式用 --run 触发（仅 1 次生成 + 1 次 extend）。

用法：
  python test_yinchao_max_duration.py           # 只读能力核（不花钱）
  python test_yinchao_max_duration.py --run      # 真实跑 1 次生成 + 1 次 extend（**会扣费**）
"""
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
import requests

KEY = os.getenv("YINCHAO_API_KEY", "")
BASE = (os.getenv("YINCHAO_API_BASE_URL", "") or "https://open.yinchaoyongxian.com").rstrip("/")
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

POLL_INTERVAL = 3
POLL_TIMEOUT = 180


def mask(k):
    if not k:
        return "EMPTY"
    k = str(k)
    return f"len={len(k)} prefix={k[:2]}... suffix=...{k[-2:]}"


def capability_report():
    """只读能力核：不发任何生成请求，只做路由存在性 + 422 schema 探测。"""
    print("=== 音潮 V4.0 能力核（只读，不产生费用）===")
    print("KEY:", "已配置" if KEY else "未配置", "|", mask(KEY))
    print("BASE:", BASE)

    # 路由存在性（GET 405 = 存在但 POST-only；404 = 不存在）
    for path in ("/api/v1/song/generate", "/api/v1/song/extend", "/api/v1/song/continue", "/api/v1/song/expand"):
        try:
            r = requests.get(BASE + path, timeout=15)
            code = r.status_code
        except Exception as e:
            code = f"ERR {type(e).__name__}"
        verdict = "存在(POST-only)" if code == 405 else ("存在" if code != 404 else "不存在(404)")
        print(f"  GET {path} -> {code}  [{verdict}]")

    # schema 探测：空 body → 422 暴露必需字段
    for path in ("/api/v1/song/generate", "/api/v1/song/extend"):
        try:
            r = requests.post(BASE + path, headers=H, json={}, timeout=30)
            print(f"  POST {path} 空body -> {r.status_code}  {r.text[:300]}")
        except Exception as e:
            print(f"  POST {path} 异常: {type(e).__name__}")

    print("\n结论：generate 无 duration 参数；extend 端点存在但 schema 未公开。")
    print("指定 120/180/240/300 秒：不可行（不伪造参数）。")


def poll_task(task_id, label):
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        try:
            q = requests.get(f"{BASE}/api/v1/task/query", params={"task_id": task_id}, headers=H, timeout=30)
        except Exception as e:
            print(f"  [{label}] query 网络错误: {type(e).__name__}")
            continue
        qd = q.json() if q.content else {}
        choices = qd.get("choices") if isinstance(qd, dict) else None
        status = None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            status = choices[0].get("status")
        if status in ("done", "fail", "failed", "error", "cancel", "cancelled"):
            return status, qd
    return "timeout", {}


def run_once():
    """真实跑 1 次生成 + 1 次 extend（**会扣费**，仅在显式 --run 时执行）。"""
    print("=== 真实最小测试（1 生成 + 1 extend，会扣费）===")
    # 1) 生成
    payload = {"model": "v4.0", "task_type": "normal", "prompt": "一首轻快的中文流行歌曲，夏日海边，女声", "n": 1}
    r = requests.post(f"{BASE}/api/v1/song/generate", headers=H, json=payload, timeout=60)
    print("[gen] HTTP", r.status_code)
    if r.status_code != 200:
        print("[gen] body:", r.text[:500])
        return
    d = r.json()
    task_id = d.get("id")
    choice = (d.get("choices") or [{}])[0] if isinstance(d.get("choices"), list) else {}
    choice_id = choice.get("id")
    print(f"[gen] task_id={task_id} choice_id={choice_id}")

    st, qd = poll_task(task_id, "gen")
    choices = qd.get("choices") or [{}]
    c0 = choices[0] if choices and isinstance(choices[0], dict) else {}
    dur1 = c0.get("duration")
    audio1 = c0.get("audio_url")
    print(f"[gen] 终态={st} duration={dur1} audio_url={'Y' if audio1 else 'N'}")

    if st != "done" or not audio1:
        print("[gen] 未成功，不继续 extend")
        return

    # 2) extend（尝试；schema 未公开，这里按 model + 引用歌曲字段保守构造）
    ext_payload = {
        "model": "v4.0",
        "task_id": task_id,
        "choice_id": choice_id,
    }
    r2 = requests.post(f"{BASE}/api/v1/song/extend", headers=H, json=ext_payload, timeout=60)
    print("[ext] HTTP", r2.status_code)
    print("[ext] body:", r2.text[:600])
    if r2.status_code != 200:
        print("[ext] 失败，停止（extend 字段名未确认，需人工核对）")
        return
    d2 = r2.json()
    tid2 = d2.get("id") or d2.get("task_id")
    print(f"[ext] task_id={tid2}")
    st2, qd2 = poll_task(tid2, "ext")
    ch2 = (qd2.get("choices") or [{}])[0] if isinstance(qd2.get("choices"), list) else {}
    print(f"[ext] 终态={st2} duration={ch2.get('duration')} audio_url={'Y' if ch2.get('audio_url') else 'N'}")


def probe_extend_schema():
    """零费用探测 /song/extend 的字段：不带 model（必 422），所有候选字段给错误类型，
    FastAPI 会一次性报告「model required」+ 每个真实字段的「expected <type>」，
    而伪造的字段名会被静默忽略 —— 从而在不满足 schema、绝不创建任务的前提下暴露真实 schema。"""
    print("=== /song/extend 字段探测（零费用）===")
    candidates = [
        "task_id", "choice_id", "song_id", "audio_id", "audio_url", "reference_audio",
        "duration", "extend_duration", "seconds", "duration_seconds",
        "prompt", "lyric", "n", "task_type",
    ]
    body = {c: [] for c in candidates}  # 每个候选字段给 list（对任何标量类型都是错误类型）
    body["model"] = None  # 显式给 None，确保 model 被视为"未提供/无值"而触发 422 且绝不往下走
    try:
        r = requests.post(f"{BASE}/api/v1/song/extend", headers=H, json=body, timeout=30)
    except Exception as e:
        print("网络错误:", type(e).__name__, e)
        return
    print("HTTP:", r.status_code)
    print("body:", r.text[:2000])

    # 解析 detail
    real_fields = set()
    try:
        d = r.json()
        detail = d.get("detail")
        if isinstance(detail, list):
            for item in detail:
                loc = item.get("loc")
                if isinstance(loc, (list, tuple)) and len(loc) >= 2 and loc[0] == "body":
                    fname = loc[1]
                    if fname in candidates:
                        real_fields.add(fname)
                        print(f"  真实字段确认: {fname} -> {item.get('type')} ({item.get('msg')})")
                    elif fname == "model":
                        print("  model -> required (expected)")
    except Exception:
        pass

    absent = [c for c in candidates if c not in real_fields]
    print("\n已确认真实字段:", sorted(real_fields))
    print("未出现在 422（= 被忽略的伪造字段，说明不存在或非标量）:", sorted(absent))


def _ffprobe_duration(path):
    import subprocess
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=30)
        v = out.stdout.strip().splitlines()[0]
        return float(v)
    except Exception as e:
        return None


def _download(url, path):
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            if r.status_code != 200:
                return None
            with open(path, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
        return path
    except Exception as e:
        print("  download 异常:", type(e).__name__, str(e)[:200])
        return None


def extend_real():
    """真实 extend 测试（会扣费）：复用之前生成的歌，再调一次 /song/extend。"""
    print("=== 音潮 V4.0 真实 Extend 测试（会扣费）===")
    import tempfile, os as _os
    tmp = tempfile.mkdtemp(prefix="yc_ext_")

    # 复用之前真实生成结果（仍可用，不重新生成）
    prev = {
        "task_id": "f5baca25-100b-443f-be5f-f38e52219b5c",
        "choice_id": "abb07d16-87c2-48df-b8e0-c7123fa48481",
        "audio_url": "https://api-cdn.yinchaoyongxian.com/openapi/public/song/ecd49eab17b6458297f73c0938dd8945.mp3",
        "duration_api": 140.382,
        "size": 5616680,
    }
    print("\n[原始歌曲] 复用之前结果：")
    print("  task_id:", prev["task_id"])
    print("  choice_id:", prev["choice_id"])
    print("  duration(API):", prev["duration_api"], "秒")
    print("  audio_url:", prev["audio_url"])

    # 下载原始 MP3 并用 ffprobe 实测时长
    orig_path = _os.path.join(tmp, "orig.mp3")
    if _download(prev["audio_url"], orig_path):
        d = _ffprobe_duration(orig_path)
        print("  原始 MP3 实测时长:", d, "秒  文件:", _os.path.getsize(orig_path), "bytes")
    else:
        print("  原始 MP3 下载失败（仍继续，用 API duration 作基准）")

    # 真实 extend（仅用已确认字段：model + lyric + n）
    ext_payload = {
        "model": "v4.0",
        "lyric": "夏天的尾声，海风把回忆吹远，我站在岸边，等一个不会回来的浪",
        "n": 1,
    }
    print("\n[extend] POST /api/v1/song/extend  payload keys:", list(ext_payload.keys()))
    r = requests.post(f"{BASE}/api/v1/song/extend", headers=H, json=ext_payload, timeout=60)
    print("[extend] HTTP:", r.status_code)
    print("[extend] body:", r.text[:1500])

    if r.status_code != 200:
        print("[extend] 失败，停止（不继续）")
        return

    d2 = r.json() if r.content else {}
    print("[extend] 返回 keys:", sorted(d2.keys()) if isinstance(d2, dict) else "n/a")
    tid2 = d2.get("id") if isinstance(d2, dict) else None
    print("[extend] task_id:", tid2)

    if not tid2:
        print("[extend] 未返回 task_id，停止")
        return

    st2, qd2 = poll_task(tid2, "extend")
    choices2 = qd2.get("choices") if isinstance(qd2, dict) else None
    c2 = (choices2[0] if isinstance(choices2, list) and choices2 and isinstance(choices2[0], dict) else {})
    print("[extend] 终态:", st2)
    print("[extend] choice keys:", sorted(c2.keys()) if isinstance(c2, dict) else "n/a")
    if isinstance(c2, dict):
        for k in ("id", "audio_url", "pipe_url", "title", "duration", "size", "error", "error_code"):
            if k in c2:
                v = c2[k]
                if k == "lyric_more" or len(str(v)) > 300:
                    v = str(v)[:300] + "..."
                print(f"  {k} = {v}")

    dur2 = c2.get("duration") if isinstance(c2, dict) else None
    audio2 = c2.get("audio_url") if isinstance(c2, dict) else None

    if audio2:
        ext_path = _os.path.join(tmp, "ext.mp3")
        if _download(audio2, ext_path):
            d2_real = _ffprobe_duration(ext_path)
            print("  extend MP3 实测时长:", d2_real, "秒  文件:", _os.path.getsize(ext_path), "bytes")
            if d2_real and prev["duration_api"]:
                print(f"\n=== 时长对比 ===\n原始(API): {prev['duration_api']}s")
                print(f"extend(API): {dur2}")
                print(f"extend(实测): {d2_real}s")
        else:
            print("  extend MP3 下载失败")
    else:
        print("  extend 无 audio_url")

    # 清理
    for fp in (orig_path, _os.path.join(tmp, "ext.mp3")):
        try:
            if _os.path.exists(fp):
                _os.remove(fp)
        except Exception:
            pass


def extend_v35():
    """按官方文档复用 140.382s MP3，用 model=v3.5 + origin_audio(audio_type=audio_url) 扩写一次。
    只做一次真实付费调用；成功后下载 + ffprobe 测量，计算实际增加秒数。"""
    import tempfile, os as _os
    print("=== 音潮 extend（model=v3.5，origin_audio 引用原 MP3，n=1）===")

    prev_url = "https://api-cdn.yinchaoyongxian.com/openapi/public/song/ecd49eab17b6458297f73c0938dd8945.mp3"
    prev_dur = 140.382
    print("原始 MP3 URL:", prev_url)
    print("原始 duration:", prev_dur, "秒")

    payload = {
        "model": "v3.5",
        "origin_audio": {
            "audio_type": "audio_url",
            "audio_url": prev_url,
        },
        "n": 1,
    }
    print("[extend] payload:", json.dumps(payload, ensure_ascii=False)[:400])

    r = requests.post(f"{BASE}/api/v1/song/extend", headers=H, json=payload, timeout=60)
    print("[extend] HTTP:", r.status_code)
    print("[extend] body:", r.text[:1500])
    if r.status_code != 200:
        print("[extend] 失败，停止")
        return

    d2 = r.json() if r.content else {}
    tid2 = d2.get("id") if isinstance(d2, dict) else (d2.get("task_id") if isinstance(d2, dict) else None)
    print("[extend] task_id:", tid2)
    if not tid2:
        print("[extend] 未返回 task_id，停止")
        return

    st2, qd2 = poll_task(tid2, "extend")
    print("[extend] 终态:", st2)
    choices2 = (qd2.get("choices") if isinstance(qd2, dict) else None)
    c2 = (choices2[0] if isinstance(choices2, list) and choices2 and isinstance(choices2[0], dict) else {})

    if st2 != "done":
        print("[extend] 未成功，body:", str(qd2)[:800])
        return

    dur2_api = c2.get("duration") if isinstance(c2, dict) else None
    audio2 = c2.get("audio_url") if isinstance(c2, dict) else None
    size2 = c2.get("size") if isinstance(c2, dict) else None
    print("[extend] choice id:", c2.get("id") if isinstance(c2, dict) else None)
    print("[extend] API duration:", dur2_api, "| API size:", size2)
    print("[extend] audio_url:", audio2)

    if not audio2:
        print("[extend] 无 audio_url，停止")
        return

    tmp = tempfile.mkdtemp(prefix="yc_v35_")
    fp = _os.path.join(tmp, "ext_v35.mp3")
    if _download(audio2, fp):
        real_dur = _ffprobe_duration(fp)
        real_size = _os.path.getsize(fp)
        print("\n=== 实测结果 ===")
        print("原始 duration :", prev_dur, "秒")
        print("extend 实测时长 :", real_dur, "秒")
        print("extend 文件大小 :", real_size, "bytes")
        if real_dur:
            added = real_dur - prev_dur
            print("实际增加秒数  :", round(added, 3), "秒")
        try:
            _os.remove(fp)
        except Exception:
            pass
    else:
        print("[extend] 下载失败")


def extend_upload():
    """官方推荐流程：下载 V4.0 MP3 → /api/v1/file/upload(upload_type=extend) → 取 upload_id
    → /api/v1/song/extend(model=v3.5, origin_audio.audio_type=upload_id, audio_content=upload_id, n=1)
    → 轮询 → 下载 → ffprobe 测时长。单次付费。"""
    import tempfile, os as _os
    print("=== 音潮 extend（upload_id 流程, model=v3.5, n=1）===")
    prev_url = "https://api-cdn.yinchaoyongxian.com/openapi/public/song/ecd49eab17b6458297f73c0938dd8945.mp3"
    prev_dur = 140.382
    print("原始 MP3 URL:", prev_url)
    print("原始 duration:", prev_dur, "秒")

    tmp = tempfile.mkdtemp(prefix="yc_up_")
    orig_path = _os.path.join(tmp, "orig.mp3")

    # Step 1: 下载原 MP3
    if not _download(prev_url, orig_path):
        print("[download] 原 MP3 下载失败，停止")
        return
    print("[download] 原 MP3 本地:", orig_path, _os.path.getsize(orig_path), "bytes")

    # Step 2: 上传（第二次：放宽 connect/read 超时，requests 无独立 write timeout）
    print("\n[upload] POST /api/v1/file/upload (multipart: file + upload_type=extend)")
    import time as _t
    _up_start = _t.time()
    with open(orig_path, "rb") as fh:
        try:
            ru = requests.post(
                f"{BASE}/api/v1/file/upload",
                headers={"Authorization": f"Bearer {KEY}"},
                files={"file": ("orig.mp3", fh, "audio/mpeg")},
                data={"upload_type": "extend"},
                timeout=(30, 180),
            )
        except Exception as e:
            _up_end = _t.time()
            print("[upload] 异常类型:", type(e).__name__)
            print("[upload] 异常信息:", repr(e))
            print("[upload] 上传持续秒数:", round(_up_end - _up_start, 2))
            print("[upload] 文件大小:", _os.path.getsize(orig_path), "bytes")
            # 是否有部分数据/响应：requests 异常对象可能含 response
            resp = getattr(e, "response", None)
            print("[upload] 收到服务器 HTTP 响应:", ("YES status=" + str(resp.status_code)) if resp is not None else "NO")
            print("[upload] FAIL，停止")
            return
    _up_end = _t.time()
    print("[upload] 上传持续秒数:", round(_up_end - _up_start, 2))
    print("[upload] HTTP:", ru.status_code)
    print("[upload] body:", ru.text[:1000])
    if ru.status_code != 200:
        print("[upload] 失败，停止")
        return
    ud = ru.json() if ru.content else {}
    upload_id = None
    if isinstance(ud, dict):
        upload_id = ud.get("upload_id") or ud.get("id") or ud.get("file_id")
        if not upload_id and isinstance(ud.get("data"), dict):
            upload_id = ud["data"].get("upload_id")
    print("[upload] upload_id:", upload_id)
    print("[upload] 文件大小:", _os.path.getsize(orig_path), "bytes")
    print("[upload] upload_type: extend")
    if not upload_id:
        print("[upload] 未取到 upload_id，停止")
        return

    # Step 3: extend
    payload = {
        "model": "v3.5",
        "origin_audio": {
            "audio_type": "upload_id",
            "audio_content": upload_id,
        },
        "n": 1,
    }
    print("\n[extend] payload:", json.dumps(payload, ensure_ascii=False)[:400])
    re = requests.post(f"{BASE}/api/v1/song/extend", headers=H, json=payload, timeout=60)
    print("[extend] HTTP:", re.status_code)
    print("[extend] body:", re.text[:1500])
    if re.status_code != 200:
        print("[extend] 失败，停止")
        return
    de = re.json() if re.content else {}
    tid = de.get("id") if isinstance(de, dict) else None
    print("[extend] task_id:", tid)
    if not tid:
        print("[extend] 未返回 task_id，停止")
        return

    # Step 4: 轮询
    st, qd = poll_task(tid, "extend")
    print("[extend] 终态:", st)
    choices = (qd.get("choices") if isinstance(qd, dict) else None)
    c = (choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {})
    if st != "done":
        print("[extend] 未 done，body:", str(qd)[:800])
        return
    dur_api = c.get("duration") if isinstance(c, dict) else None
    audio = c.get("audio_url") if isinstance(c, dict) else None
    size_api = c.get("size") if isinstance(c, dict) else None
    print("[extend] API duration:", dur_api, "| size:", size_api)
    print("[extend] audio_url:", audio)
    if not audio:
        print("[extend] 无 audio_url，停止")
        return

    # Step 5: 下载 + ffprobe
    fp = _os.path.join(tmp, "ext.mp3")
    if _download(audio, fp):
        real_dur = _ffprobe_duration(fp)
        real_size = _os.path.getsize(fp)
        print("\n=== 最终测量 ===")
        print("原始 duration :", prev_dur, "秒")
        print("extend 实测时长 :", real_dur, "秒")
        print("extend 文件大小 :", real_size, "bytes")
        if real_dur:
            print("实际增加秒数 :", round(real_dur - prev_dur, 3), "秒")
    else:
        print("[extend] 下载失败")


if __name__ == "__main__":
    if "--run" in sys.argv:
        run_once()
    elif "--probe-extend" in sys.argv:
        probe_extend_schema()
    elif "--extend-real" in sys.argv:
        extend_real()
    elif "--extend-v35" in sys.argv:
        extend_v35()
    elif "--extend-upload" in sys.argv:
        extend_upload()
    else:
        capability_report()