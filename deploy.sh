#!/bin/bash
# Quick Deploy Script for Music Video Platform v2.0
# Usage: ./deploy.sh [dev|prod]

set -e

MODE=${1:-dev}
echo "🚀 Deploying Music Video Platform v2.0 in $MODE mode..."

if [ "$MODE" = "prod" ]; then
    echo "📦 Building Docker image..."
    docker-compose build

    echo "🔧 Starting services..."
    docker-compose up -d

    echo "⏳ Waiting for services to start..."
    sleep 10

    echo "🧪 Health check..."
    curl -f http://localhost:8000/api/v1/ai/styles || exit 1

    echo "✅ Production deployment complete!"
    echo "   Frontend: http://localhost"
    echo "   Backend:  http://localhost:8000"
    echo "   API Docs: http://localhost:8000/docs"

else
    echo "📦 Installing frontend dependencies..."
    cd frontend
    npm install

    echo "📦 Installing backend dependencies..."
    cd ../backend
    pip install -r requirements.txt

    echo "🎵 Starting backend (port 8000)..."
    cd ..
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!

    echo "🎨 Starting frontend (port 3000)..."
    cd frontend
    npm run dev &
    FRONTEND_PID=$!

    echo ""
    echo "✅ Development mode started!"
    echo "   Frontend: http://localhost:3000"
    echo "   Backend:  http://localhost:8000"
    echo "   API Docs: http://localhost:8000/docs"
    echo ""
    echo "Press Ctrl+C to stop all services"

    wait $BACKEND_PID $FRONTEND_PID
fi