# Python FastAPI Backend for AI Music Platform
FROM python:3.11-slim

# Set working directory
WORKDIR /app

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

# Pre-download MDX23 model during build
# so runtime does not block on network downloads.
# This bakes the model weights into the image.
RUN mkdir -p /app/.cache && \
    python -c "import mdx23; mdx23.pretrained.get_model('mdx23')"

# Copy application code
COPY . .

# Expose port (Render sets PORT env var)
EXPOSE 8000

# Run the application (use $PORT for Render compatibility)
CMD uvicorn main:app --host 0.0.0.0 --port $PORT