# Python FastAPI Backend for AI Music Platform
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libsndfile1 \
    ffmpeg \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Koyeb 无状态：本地磁盘仅临时文件，数据库走 Supabase/R2，无需持久卷（保留 /app/data 仅临时）
RUN mkdir -p /app/data /app/generated

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies (Step 4: modal 已移除)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Koyeb 注入 PORT)
EXPOSE 8000

# 动态 PORT，单 worker 避免 Render 端口扫描竞态
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]