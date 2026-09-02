"""
Avireon AI Music Platform — Modal Cloud 部署脚本
兼容 modal 1.5.3，仅使用 add_local_file / pip_install / asgi_app。
"""
import os

import modal
from modal import App, Image, asgi_app

# ══════════════════════════════════════════════════════════════════════════════
FILE_LIST = [
    # ---- 根目录 ----
    "run.py",
    # ---- backend ----
    "backend/main.py",
    "backend/pyproject.toml",
    "backend/requirements.txt",
    # ---- backend/app ----
    "backend/app/__init__.py",
    "backend/app/llm_models.py",
    "backend/app/websocket_manager.py",
    # ---- backend/app/core ----
    "backend/app/core/secrets.py",
    # ---- backend/app/db ----
    "backend/app/db/postgres.py",
    # ---- backend/app/middleware ----
    "backend/app/middleware/privacy.py",
    # ---- backend/app/routers ----
    "backend/app/routers/__init__.py",
    "backend/app/routers/ai_lyrics.py",
    "backend/app/routers/ai_music.py",
    "backend/app/routers/asset_store.py",
    "backend/app/routers/audio_processing.py",
    "backend/app/routers/audio_quality.py",
    "backend/app/routers/auth.py",
    "backend/app/routers/beta.py",
    "backend/app/routers/bg_removal.py",
    "backend/app/routers/cdn_upload.py",
    "backend/app/routers/chord_track.py",
    "backend/app/routers/collaboration.py",
    "backend/app/routers/community.py",
    "backend/app/routers/comping.py",
    "backend/app/routers/copyright.py",
    "backend/app/routers/feedback.py",
    "backend/app/routers/gemini_ai_music.py",
    "backend/app/routers/hf_music.py",
    "backend/app/routers/lyrics_rhyme.py",
    "backend/app/routers/messages.py",
    "backend/app/routers/notifications.py",
    "backend/app/routers/one_click_publish.py",
    "backend/app/routers/pitch_correction.py",
    "backend/app/routers/remix_engine.py",
    "backend/app/routers/rhythm_analysis.py",
    "backend/app/routers/runway_ml.py",
    "backend/app/routers/social.py",
    "backend/app/routers/song_continuation.py",
    "backend/app/routers/songs.py",
    "backend/app/routers/stems_export.py",
    "backend/app/routers/subscription.py",
    "backend/app/routers/subtitle_recognition.py",
    "backend/app/routers/time_stretch.py",
    "backend/app/routers/ugc.py",
    "backend/app/routers/voice_clone.py",
    "backend/app/routers/voice_cloning.py",
    # ---- backend/app/services ----
    "backend/app/services/__init__.py",
    "backend/app/services/agnes_music_service.py",
    "backend/app/services/audio_enhancement.py",
    "backend/app/services/audio_export.py",
    "backend/app/services/audio_post_processor.py",
    "backend/app/services/audio_router.py",
    "backend/app/services/audio_separation_service.py",
    "backend/app/services/audio_trim.py",
    "backend/app/services/batch_queue.py",
    "backend/app/services/batch_router.py",
    "backend/app/services/beat_detector.py",
    "backend/app/services/beta_service.py",
    "backend/app/services/bg_removal.py",
    "backend/app/services/bilibili_service.py",
    "backend/app/services/cache_service.py",
    "backend/app/services/cdn_uploader.py",
    "backend/app/services/chord_track_service.py",
    "backend/app/services/community_service.py",
    "backend/app/services/comping_service.py",
    "backend/app/services/copyright_check.py",
    "backend/app/services/dmca_router.py",
    "backend/app/services/external_services.py",
    "backend/app/services/feedback_service.py",
    "backend/app/services/ffmpeg_utils.py",
    "backend/app/services/gemini_music_service.py",
    "backend/app/services/hf_music_service.py",
    "backend/app/services/lyric_service.py",
    "backend/app/services/lyrics_rhyme_ai.py",
    "backend/app/services/mastering_service.py",
    "backend/app/services/mix_engine.py",
    "backend/app/services/mureka_service.py",
    "backend/app/services/mv_router.py",
    "backend/app/services/nv_music_service.py",
    "backend/app/services/pitch_correction_service.py",
    "backend/app/services/prompt_enhancer.py",
    "backend/app/services/remix_engine_service.py",
    "backend/app/services/runway_ml.py",
    "backend/app/services/runway_ml_test.py",
    "backend/app/services/sqlite_service.py",
    "backend/app/services/stems_export_service.py",
    "backend/app/services/supabase_service.py",
    "backend/app/services/task_handlers.py",
    "backend/app/services/tiktok_service.py",
    "backend/app/services/time_stretch_service.py",
    "backend/app/services/user_router.py",
    "backend/app/services/vocal_enhancer.py",
    "backend/app/services/voice_clone_service.py",
    "backend/app/services/voice_cloning_service.py",
    "backend/app/services/watermark.py",
    "backend/app/services/workflow.py",
    "backend/app/services/workflow_router.py",
    "backend/app/services/youtube_service.py",
    # ---- backend/app/services/inference ----
    "backend/app/services/inference/__init__.py",
    "backend/app/services/inference/base.py",
    "backend/app/services/inference/cogvideox.py",
    "backend/app/services/inference/demucs.py",
    "backend/app/services/inference/factory.py",
    "backend/app/services/inference/gpt_sovits.py",
    "backend/app/services/inference/gradio_mixins.py",
    "backend/app/services/inference/llm_factory.py",
    "backend/app/services/inference/midi_render.py",
    "backend/app/services/inference/mock.py",
    "backend/app/services/inference/mureka.py",
    "backend/app/services/inference/musicgen.py",
    "backend/app/services/inference/remix.py",
    # ---- backend/scripts ----
    "backend/scripts/beta_schema.sql",
    "backend/scripts/daily_credit_reset.py",
    "backend/scripts/test_one_click_publish.py",
    # ---- backend/tests ----
    "backend/tests/__init__.py",
    "backend/tests/test_demucs.py",
    "backend/tests/test_e2e_integration.py",
    "backend/tests/test_inference.py",
    "backend/tests/test_mix_engine.py",
    "backend/tests/test_real_service.py",
    "backend/tests/test_services.py",
    "backend/tests/test_websocket.py",
]

# ══════════════════════════════════════════════════════════════════════════════
image = Image.debian_slim(python_version="3.12").run_commands(
    "apt-get update -qq && apt-get install -y -qq libsndfile1 ffmpeg && rm -rf /var/lib/apt/lists/*"
)

image = image.pip_install(
    "fastapi==0.115.0",
    "uvicorn[standard]==0.30.6",
    "python-dotenv==1.0.1",
    "pydantic==2.11.7",
    "email-validator==2.3.0",
    "supabase==2.31.0",
    "boto3==1.35.0",
    "aiohttp==3.10.5",
    "httpx==0.27.2",
    "numpy>=1.26.4,<2.0",
    "scipy==1.14.1",
    "librosa==0.10.2",
    "python-multipart==0.0.20",
    "pypinyin==0.52.0",
    "sqlalchemy==2.0.35",
    "sentry-sdk[fastapi,sqlalchemy]==2.42.0",
    "demucs>=4.0.0",
    "soundfile>=0.12.1",
    "pydub>=0.25.1",
    "psycopg2-binary",
)

_local_root = os.path.dirname(os.path.abspath(__file__))
for rel_path in FILE_LIST:
    local_full = os.path.join(_local_root, rel_path)
    if not os.path.isfile(local_full):
        raise FileNotFoundError(f"FILE_LIST missing: {rel_path}")
    image = image.add_local_file(local_full, "/root/" + rel_path)

# ══════════════════════════════════════════════════════════════════════════════
# 持久化 Volume（SQLite beta.db + WAL）
data_volume = modal.Volume.from_name("music-platform-data", create_if_missing=True)

app = App("avireon-ai-music-platform")


@app.function(
    image=image,
    volumes={"/root/backend/data": data_volume},
    secrets=[
        modal.Secret.from_name("avireon-secrets"),
        modal.Secret.from_name("avireon-config"),
        modal.Secret.from_name("r2-storage-config"),
        modal.Secret.from_name("hf-token"),
        modal.Secret.from_name("agnes-key"),
    ],
    max_containers=1,
    scaledown_window=600,
)
@asgi_app()
def fastapi_endpoint():
    """
    所有初始化代码均在此函数内部执行，全局作用域不加载任何 backend 模块。
    """
    import sys as _sys
    from pathlib import Path

    # [改动1] sys.path 插入在函数体内
    _sys.path.insert(0, "/root")
    _sys.path.insert(0, "/root/backend")

    # [改动2] 写 .env 并 load_dotenv，保证 backend.main 导入前环境已就绪
    # 生产环境从 Modal Secrets 读取，不再硬编码 Mock 模式
    env_path = Path("/root/.env")
    env_lines = [
        "# Auto-generated by modal_server.py - production reads from Modal Secrets",
        f"WORKFLOW_MODE={os.getenv('WORKFLOW_MODE', 'real')}",
        f"TTS_BACKEND_MODE={os.getenv('TTS_BACKEND_MODE', 'real')}",
        f"TTS_FORCE_MOCK={os.getenv('TTS_FORCE_MOCK', 'false')}",
        f"MUSIC_FORCE_MOCK={os.getenv('MUSIC_FORCE_MOCK', 'false')}",
        f"VIDEO_FORCE_MOCK={os.getenv('VIDEO_FORCE_MOCK', 'false')}",
    ]
    env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    # [改动3] 明确用文件路径调用 load_dotenv，避免默认查找当前目录
    import dotenv
    dotenv.load_dotenv(env_path)

    # [改动4] 刷新 importlib 缓存，确保 Python 能识别新加入 sys.path 的 /root/backend 下的 app 包
    import importlib
    importlib.invalidate_caches()

    # [改动5] Mock fallback：backend/main.py 期望的 results 目录
    (Path("/root/backend") / "results").mkdir(parents=True, exist_ok=True)

    # [改动6] 延迟导入 backend.main（返回 ASGI 兼容的 FastAPI 实例）
    import traceback as _tb
    try:
        import backend.main as _bm
        return _bm.app
    except Exception:
        # 打印完整追踪到 stderr，Modal 会自动捕获并显示在日志中
        _tb.print_exc()
        # 返回一个最小 FastAPI 实例作为降级方案，确保 Modal 不报 invalid function call
        from fastapi import FastAPI as _FastAPI
        _fallback = _FastAPI()
        @_fallback.get("/")
        def _root():
            return {"error": "backend.main import failed — check Modal logs"}
        @_fallback.get("/health")
        def _health():
            return {"status": "degraded"}
        return _fallback