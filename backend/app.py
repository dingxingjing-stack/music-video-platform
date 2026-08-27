"""
HeartMuLa 3B + HeartCodec - Hugging Face Spaces 入口点

HF Spaces Docker 启动命令: python app.py
- 启动 FastAPI 服务 (端口 7860)
- 初始化 HeartMuLa 本地推理服务
- 提供健康检查端点供 HF Spaces 探针使用
- 支持优雅关闭和模型清理

环境变量配置（在 HF Spaces Settings -> Repository secrets 设置）:
- HF_TOKEN: Hugging Face 读取私有模型权限
- HEARTMULA_LOCAL_ENABLED: "true" (启用本地推理)
- HEARTMULA_MODEL_REPO: "HeartMuLa/HeartMuLa-oss-3B-happy-new-year"
- HEARTCODEC_MODEL_REPO: "HeartMuLa/HeartCodec-oss-20260123"
- HEARTMULA_VERSION: "3B"
- HEARTMULA_LAZY_LOAD: "true"
- R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET: Cloudflare R2 配置
- CDN_BASE_URL: 公网 CDN 域名
"""

import os
import sys
import logging
import asyncio
from contextlib import asynccontextmanager

# 强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 导入 FastAPI 应用
from main import app

# 导入 HeartMuLa 本地服务初始化
from app.services.heartmula_local import (
    initialize_heartmula_local,
    HeartMuLaLocalConfig,
    is_heartmula_local_available,
)
from app.services.heartmula_service import get_heartmula_service


# 启动/关闭生命周期管理
@asynccontextmanager
async def lifespan(app):
    """应用生命周期管理"""
    logger.info("=" * 60)
    logger.info("HeartMuLa 3B + HeartCodec - HF Spaces 启动中...")
    logger.info("=" * 60)
    
    # 打印关键配置
    logger.info(f"Python: {sys.version}")
    logger.info(f"HF_TOKEN: {'已配置' if os.getenv('HF_TOKEN') else '未配置'}")
    logger.info(f"HEARTMULA_LOCAL_ENABLED: {os.getenv('HEARTMULA_LOCAL_ENABLED', 'false')}")
    logger.info(f"HEARTMULA_MODEL_REPO: {os.getenv('HEARTMULA_MODEL_REPO', 'HeartMuLa/HeartMuLa-oss-3B-happy-new-year')}")
    logger.info(f"HEARTCODEC_MODEL_REPO: {os.getenv('HEARTCODEC_MODEL_REPO', 'HeartMuLa/HeartCodec-oss-20260123')}")
    logger.info(f"R2 配置: {'已配置' if os.getenv('R2_ENDPOINT') and os.getenv('R2_ACCESS_KEY_ID') else '未配置'}")
    
    # 检查 GPU
    import torch
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        logger.info(f"GPU: {gpu_name}, VRAM: {vram_gb:.2f} GB")
        logger.info(f"CUDA 版本: {torch.version.cuda}")
    else:
        logger.warning("⚠️ GPU 不可用！本地推理需要 NVIDIA GPU")
    
    # 初始化 HeartMuLa 本地服务（如果启用）
    heartmula_local_enabled = os.getenv("HEARTMULA_LOCAL_ENABLED", "false").lower() in ("1", "true", "yes")
    
    if heartmula_local_enabled:
        if not torch.cuda.is_available():
            logger.error("❌ HEARTMULA_LOCAL_ENABLED=true 但 GPU 不可用，无法启动本地推理")
            logger.error("请检查：Docker --gpus all、基础镜像 CUDA 支持、驱动版本")
            # 不抛异常，让健康检查返回 unhealthy
        else:
            try:
                logger.info("初始化 HeartMuLa 本地推理服务...")
                config = HeartMuLaLocalConfig()
                await initialize_heartmula_local(config)
                logger.info("✅ HeartMuLa 本地推理服务初始化完成")
            except Exception as e:
                logger.exception(f"❌ HeartMuLa 本地服务初始化失败: {e}")
                # 不阻塞启动，让 /health 端点报告错误
    else:
        logger.info("ℹ️ HEARTMULA_LOCAL_ENABLED=false，使用 API 模式（需配置 HEARTMULA_API_KEY）")
    
    # 获取服务实例（触发单例创建）
    service = get_heartmula_service()
    if service:
        logger.info(f"HeartMuLa 服务模式: {service.get_mode()}")
    
    logger.info("=" * 60)
    logger.info("启动完成，服务就绪")
    logger.info("=" * 60)
    
    yield
    
    # 关闭时清理
    logger.info("正在关闭 HeartMuLa 服务...")
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("GPU 缓存已清理")
    except Exception as e:
        logger.warning(f"关闭清理警告: {e}")
    logger.info("服务已关闭")


# 为 HF Spaces 替换 lifespan（FastAPI 0.115+ 支持）
app.router.lifespan_context = lifespan


# 根路径重定向到文档
@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "HeartMuLa 3B + HeartCodec",
        "version": "1.0.0",
        "mode": "local" if os.getenv("HEARTMULA_LOCAL_ENABLED", "false").lower() in ("1", "true", "yes") else "api",
        "docs": "/docs",
        "health": "/health",
        "heartmula": {
            "generate": "/api/v1/heartmula/generate",
            "health": "/api/v1/heartmula/health",
            "memory": "/api/v1/heartmula/memory",
            "info": "/api/v1/heartmula/info",
        },
    }


if __name__ == "__main__":
    import uvicorn
    
    # HF Spaces 使用 PORT 环境变量（默认 7860）
    port = int(os.getenv("PORT", "7860"))
    host = "0.0.0.0"
    
    logger.info(f"启动 uvicorn: {host}:{port}")
    
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        workers=1,  # 单 worker，模型在进程间共享
        log_level="info",
        access_log=True,
    )