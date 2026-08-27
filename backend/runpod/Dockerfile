# RunPod Serverless Worker — GPU Smoke Test
FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY backend/runpod/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy root handler (contains module-level runpod.serverless.start)
COPY handler.py .

# RunPod Serverless entrypoint
CMD ["python", "-u", "handler.py"]