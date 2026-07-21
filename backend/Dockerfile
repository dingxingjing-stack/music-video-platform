# Python FastAPI Backend for AI Music Platform
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set TORCH_HOME to persist model cache across restarts
ENV TORCH_HOME=/app/.torch
# Limit OpenMP threads to 1 to reduce memory pressure
ENV OMP_NUM_THREADS=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libsndfile1 \
    ffmpeg \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download htdemucs model during build to avoid runtime download
# and fix model cache path for Render restarts
RUN mkdir -p /app/.torch && \
    python -c "from demucs.pretrained import get_model; get_model('htdemucs')"

# Copy application code
COPY . .

# Expose port (Render sets PORT env var)
EXPOSE 8000

# Run the application (use $PORT for Render compatibility)
CMD uvicorn main:app --host 0.0.0.0 --port $PORT