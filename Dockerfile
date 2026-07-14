# Music Video Platform Frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm install --frozen-lockfile

# Copy source code
COPY frontend/ ./

# Build
RUN npm run build

# Production stage - Backend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements
COPY backend/requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./app/

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./static

# Set environment variables
ENV PYTHONPATH=/app
ENV FRONTEND_BUILD_PATH=./static

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]