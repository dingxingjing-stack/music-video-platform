@echo off
REM Quick Start Script for Music Video Platform v2.0 (Windows)
REM Usage: deploy.bat [dev]

set MODE=%1
if "%MODE%"=="" set MODE=dev

echo 🚀 Deploying Music Video Platform v2.0 in %MODE% mode...

if "%MODE%"=="prod" (
    echo 📦 Building Docker image...
    docker-compose build

    echo 🔧 Starting services...
    docker-compose up -d

    echo ⏳ Waiting for services to start...
    timeout /t 10 /nobreak

    echo 🧪 Health check...
    curl -f http://localhost:8000/api/v1/ai/styles
    if errorlevel 1 exit /b 1

    echo ✅ Production deployment complete!
    echo    Frontend: http://localhost
    echo    Backend:  http://localhost:8000
    echo    API Docs: http://localhost:8000/docs
) else (
    echo 📦 Installing frontend dependencies...
    cd frontend
    call npm install

    echo 📦 Installing backend dependencies...
    cd ..\backend
    call pip install -r requirements.txt

    echo 🎵 Starting backend (port 8000)...
    cd ..
    start "Backend" cmd /k "uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000"

    echo 🎨 Starting frontend (port 3000)...
    cd frontend
    start "Frontend" cmd /k "npm run dev"

    echo.
    echo ✅ Development mode started!
    echo    Frontend: http://localhost:3000
    echo    Backend:  http://localhost:8000
    echo    API Docs: http://localhost:8000/docs
    echo.
    echo Close the terminal windows to stop services
)