# ---- Stage 1: Build frontend ----
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ .
RUN npx tsc --noEmit && npm run build

# ---- Stage 2: Backend ----
FROM python:3.12-slim AS backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fluidsynth \
    libfluidsynth3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir .

COPY backend/ ./

# ---- Stage 3: Production ----
FROM python:3.12-slim AS production

LABEL maintainer="music-video-platform"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fluidsynth \
    libfluidsynth3 \
    nginx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy frontend build artifacts
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# Copy backend
COPY --from=backend /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY backend/ /app/backend

# Create results dir
RUN mkdir -p /app/results

# Nginx config for serving frontend + proxying backend
RUN cat > /etc/nginx/sites-available/default <<'NGINX'
server {
    listen 80;
    server_name _;

    # Serve frontend static files
    location / {
        root /app/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Proxy API to backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # Proxy WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 300s;
    }

    # Serve results (generated audio/video)
    location /results/ {
        alias /app/results/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
NGINX

EXPOSE 80

CMD ["sh", "-c", \
    "uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 2 & \
     nginx -g 'daemon off;'"]
