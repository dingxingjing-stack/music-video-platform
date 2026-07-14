# Python FastAPI Backend for AI Music Platform
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Render sets PORT env var)
EXPOSE 8000

# Run the application (use $PORT for Render compatibility)
CMD uvicorn main:app --host 0.0.0.0 --port $PORT