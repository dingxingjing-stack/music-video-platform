"""音潮（Yinchao）API 只读/最小生成验证脚本 —— 独立测试，不属于生产代码。

用法：python test_yinchao.py
仅从 backend/.env 读取 YINCHAO_API_KEY / YINCHAO_API_BASE_URL，
不输出完整 API Key。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import requests

KEY = os.getenv("YINCHAO_API_KEY", "")
BASE = (os.getenv("YINCHAO_API_BASE_URL", "") or "https://open.yinchaoyongxian.com").rstrip("/")

def mask(k):
    if not k:
        return "EMPTY"
    k = str(k)
    return f"len={len(k)} prefix={k[:2]}... suffix=...{k[-2:]}"

def main():
    print("=== 音潮 API 测试 ===")
    print("YINCHAO_API_KEY:", "已配置" if KEY else "未配置", "|", mask(KEY))
    print("BASE_URL:", BASE)

    headers = {
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "v4.0",
        "task_type": "normal",
        "prompt": "一首轻快的中文流行歌曲，主题是夏日海边的回忆，女声演唱，现代流行音乐风格",
        "n": 1,
    }

    # 1) 提交生成
    print("\n[1] POST /api/v1/song/generate ...")
    try:
        r = requests.post(f"{BASE}/api/v1/song/generate", headers=headers, json=payload, timeout=60)
    except requests.exceptions.Timeout:
        print("SUBMIT: 网络错误（超时）")
        return
    except Exception as e:
        print(f"SUBMIT: 网络错误 {type(e).__name__}: {e}")
        return

    print("SUBMIT HTTP:", r.status_code)
    body = ""
    try:
        body = r.text
    except Exception:
        pass
    print("SUBMIT body:", body[:800])

    if r.status_code != 200:
        _classify(r.status_code, body)
        return

    # 解析 task_id
    data = {}
    try:
        data = r.json()
    except Exception:
        pass
    task_id = None
    if isinstance(data, dict):
        # 兼容多种可能的字段名
        task_id = (data.get("data", {}) if isinstance(data.get("data"), dict) else {}).get("task_id") \
            or (data.get("data", {}) if isinstance(data.get("data"), dict) else {}).get("taskId") \
            or data.get("task_id") or data.get("taskId") or data.get("id")
    print("task_id:", task_id)

    if not task_id:
        print("RESULT: 提交成功但未返回 task_id，需人工核对返回结构")
        return

    # 2) 轮询
    print("\n[2] 轮询 /api/v1/task/query ...")
    deadline = time.time() + 180
    final = None
    poll = 0
    while time.time() < deadline:
        poll += 1
        try:
            q = requests.get(f"{BASE}/api/v1/task/query", params={"task_id": task_id}, headers=headers, timeout=30)
        except Exception as e:
            print(f"QUERY: 网络错误 {type(e).__name__}: {e}")
            time.sleep(3)
            continue
        qd = {}
        try:
            qd = q.json() if q.content else {}
        except Exception:
            pass
        # 状态可能位于不同层级：顶层 status/state，或 choices[0].status
        inner = qd if isinstance(qd, dict) else {}
        status = None
        if isinstance(inner, dict):
            status = inner.get("status") or inner.get("state") or qd.get("status")
            if not status:
                choices = inner.get("choices")
                if isinstance(choices, list) and choices:
                    c0 = choices[0] if isinstance(choices[0], dict) else {}
                    status = c0.get("status") or c0.get("state")
        print(f"  poll#{poll}: HTTP={q.status_code} status={status}")
        if status in ("done", "success", "succeeded", "completed"):
            final = ("done", inner)
            break
        if status in ("fail", "failed", "error", "cancel", "cancelled"):
            final = ("fail", inner)
            break
        time.sleep(3)

    if final is None:
        print("\nRESULT: 180 秒内未达终态（timeout，需人工再查）")
        print("最后查询 body:", qd if isinstance(qd, dict) else "")
        return

    st_s, final_data = final
    print(f"\n=== 最终状态: {st_s} ===")
    if isinstance(final_data, dict):
        print("final data keys:", sorted(final_data.keys()))
        # 递归打印关键字段（截断过长值，避免刷屏）
        for k in ("audio_url", "audioUrl", "pipe_url", "pipeUrl", "duration", "duration_sec", "title", "model"):
            if k in final_data:
                v = final_data[k]
                print(f"  {k} = {v}")

        # 定位 audio url 与 pipe url
        def _find(keys):
            for k in keys:
                if isinstance(final_data.get(k), str) and final_data.get(k).strip():
                    return final_data[k]
                # 嵌套 data
                inner = final_data.get("data")
                if isinstance(inner, dict) and isinstance(inner.get(k), str) and inner.get(k).strip():
                    return inner[k]
            return None

        audio_url = _find(("audio_url", "audioUrl", "url", "song_url", "songUrl"))
        pipe_url = _find(("pipe_url", "pipeUrl"))
        print("\naudio_url 存在:", bool(audio_url))
        print("audio_url:", audio_url if audio_url else "(无)")
        print("pipe_url 存在:", bool(pipe_url))
        print("pipe_url:", pipe_url if pipe_url else "(无)")

        # audio_url 可访问性（仅 HEAD，不下载不保存）
        if audio_url:
            try:
                hr = requests.head(audio_url, timeout=30, allow_redirects=True)
                print("audio_url HEAD:", hr.status_code, "content-type:", hr.headers.get("content-type"))
            except Exception as e:
                print("audio_url 访问异常:", type(e).__name__, str(e)[:200])

        if st_s == "fail":
            print("错误信息:", final_data.get("error") or final_data.get("message") or final_data.get("errMsg") or "")
    else:
        print("final_data 非 dict:", str(final_data)[:500])


def _classify(status, body):
    print("\n=== 失败分类 ===")
    low = (body or "").lower()
    if status == 401:
        print("判定: A. API Key 无效（401 未授权）")
    elif status == 403:
        print("判定: 地区/权限限制（403）")
    elif status == 402 or ("balance" in low or "credit" in low or "quota" in low or "额度" in body or "余额" in body):
        print("判定: B. 余额不足（402/quota）")
    elif status == 400 or status == 422:
        print("判定: C. 参数错误（400/422）")
    elif status == 429:
        print("判定: 限流（429）")
    elif status >= 500:
        print("判定: D. 服务端错误（5xx）")
    else:
        print(f"判定: E. 其他错误（HTTP {status}）")


if __name__ == "__main__":
    main()