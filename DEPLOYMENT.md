# Deployment Guide

## Quick Start with Docker

```bash
# 1. Copy env template
cp .env.example .env
# Edit .env with your HF Spaces URLs and API tokens

# 2. Build and run
docker compose up --build -d

# 3. Access
# Frontend: http://localhost
# API docs: http://localhost/docs
```

## Development Setup (without Docker)

### Backend
```bash
cd backend
pip install -e ".[dev]"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKFLOW_MODE` | `mock` | `mock` or `real` |
| `TTS_BACKEND_MODE` | `mock` | `mock` or `real` |
| `MUSICGEN_SPACE_URL` | | HF Space URL for music generation |
| `TTS_SPACE_URL` | | HF Space URL for TTS |
| `DEMUCS_SPACE_URL` | | HF Space URL for stem separation |
| `MIDI_SOUNDFONT_PATH` | `/usr/share/sounds/sf2/FluidR3_GM.sf2` | SoundFont for MIDI rendering |
| `NVIDIA_LLM_API_KEY` | | NVIDIA NIM API key |
| `GOOGLE_GENERATIVE_AI_API_KEY` | | Gemini API key |

## Architecture

```
Nginx (:80)
├── /          → frontend/dist (SPA)
├── /api/      → backend FastAPI (REST)
├── /ws/       → backend FastAPI (WebSocket)
└── /results/  → mounted volume (audio/video files)
```

## Services

- **Frontend**: Vite + React + TypeScript (static SPA)
- **Backend**: FastAPI + Uvicorn (ASGI)
- **ML Services**: MusicGen, GPT-SoVITS, CogVideoX via HF Spaces
- **Local Processing**: FluidSynth (MIDI), ffmpeg (mix/render)
