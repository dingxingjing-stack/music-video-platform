"""RunPod Serverless 入口文件 — 仓库根目录入口，供 RunPod 静态分析发现。

真实 Worker 实现位于 backend/runpod/handler.py。
"""

import sys
import os

# 将 backend 目录加入 Python 路径，使 backend.runpod.handler 可导入
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

# 导入真实 handler
from backend.runpod.handler import handler  # type: ignore

import runpod
runpod.serverless.start({"handler": handler})