# Inference Service API — Frontend Integration Guide

## Overview

The Inference Service API provides two communication channels:

| Channel | Method | Purpose |
|---------|--------|---------|
| **REST** | `POST /api/v1/predict/{service_type}` | Submit inference task, receive final result |
| **WebSocket** | `ws://host/ws/progress/{task_id}` | Subscribe to real-time progress updates |

Both channels work together: submit a task via REST, then listen on the returned `task_id` via WebSocket for live progress.

---

## 1. Submit a Prediction Task

### Endpoint

```
POST /api/v1/predict/{service_type}
Content-Type: application/json
```

### Service Types

| Type | Description | Required Fields |
|------|-------------|-----------------|
| `tts` | Voice synthesis (GPT-SoVITS) | `reference_audio` (base64 WAV), `text`, `language` |
| `music` | Music generation (MusicGen) | `prompt`, `duration` |
| `video` | Video generation (CogVideoX) | `prompt` |
| `mock` | Simulated task (for testing) | `duration`, `tick_interval` |

### Request Examples

#### TTS (Voice Synthesis)

```json
POST /api/v1/predict/tts
{
  "task_id": "my-task-001",
  "text": "你好世界",
  "language": "zh",
  "reference_audio": "<base64-encoded-wav-bytes>"
}
```

#### Music Generation

```json
POST /api/v1/predict/music
{
  "task_id": "music-001",
  "prompt": "upbeat jazz piano",
  "duration": 30.0
}
```

#### Mock (Testing)

```json
POST /api/v1/predict/mock
{
  "task_id": "mock-001",
  "duration": 10.0,
  "tick_interval": 1.0
}
```

### Response (REST)

```json
{
  "task_id": "my-task-001",
  "status": "completed",
  "progress": 100,
  "message": "Done!",
  "result_url": "https://.../output.wav",
  "metadata": {
    "service_type": "tts"
  },
  "updated_at": 1719580000.0
}
```

> **Note:** The REST response returns the **final** result. For real-time progress, use WebSocket.

---

## 2. Subscribe to Real-Time Progress (WebSocket)

### Connection

```javascript
const taskId = "my-task-001";
const ws = new WebSocket(`ws://localhost:8000/ws/progress/${taskId}`);
```

### Message Flow

```
Client                          Server
  │                               │
  │── CONNECT /ws/progress/{id} ──▶│
  │◄══ SUBSCRIBED ────────────────│  (connection stays open)
  │                               │
  │◄══ {status:pending, progress:0} ──  Phase 0
  │◄══ {status:loading, progress:10} ─── Phase 1
  │◄══ {status:running, progress:50} ─── Phase 2 (repeated)
  │◄══ {status:completed, progress:100} ─ Final
  │                               │
  │── CLOSE ──────────────────────▶│
```

### WebSocket Message Format

Each message is a JSON object matching `PredictResult.to_dict()`:

```json
{
  "task_id": "my-task-001",
  "status": "running",
  "progress": 50,
  "message": "Inference in progress... (50%)",
  "result_url": null,
  "error": null,
  "error_code": null,
  "retryable": false,
  "last_attempt": 0,
  "metadata": {
    "service_type": "tts"
  },
  "updated_at": 1719580000.0
}
```

### Status Values

| Status | Progress | Meaning |
|--------|----------|---------|
| `pending` | 0 | Task queued, waiting to start |
| `loading` | 0–40 | Space cold-start / model loading into VRAM |
| `running` | 20–95 | Inference in progress (progress increases) |
| `completed` | 100 | Task finished successfully — `result_url` populated |
| `failed` | 0 | Task failed — `error` and `error_code` populated |
| `cancelled` | 0 | Task was cancelled by user |

### Terminal States

A task is **complete** when `status` is one of:
- `completed` — success, check `result_url` for download
- `failed` — error, check `error` and `error_code`
- `cancelled` — user-initiated

After a terminal state, no more messages will arrive on the WebSocket.

### JavaScript Integration Example

```javascript
function createTaskAndMonitor(serviceType, body) {
  // Step 1: Submit task via REST
  return fetch(`/api/v1/predict/${serviceType}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  .then(r => r.json())
  .then(result => {
    const taskId = result.task_id;

    // Step 2: Connect WebSocket for live progress
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(`ws://localhost:8000/ws/progress/${taskId}`);

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        console.log(`[${msg.status}] ${msg.progress}% — ${msg.message}`);

        if (msg.status === 'completed') {
          ws.close();
          resolve(msg);  // Final result with result_url
        } else if (msg.status === 'failed') {
          ws.close();
          reject(new Error(msg.error));
        }
      };

      ws.onerror = () => reject(new Error('WebSocket error'));
      ws.onclose = () => {};  // Clean close handled above
    });
  });
}

// Usage:
createTaskAndMonitor('tts', {
  text: '你好世界',
  language: 'zh',
  reference_audio: '<base64-wav>',
});
```

---

## 3. Additional Endpoints

### Task Status (REST)

```
GET /api/v1/tasks/{task_id}
```

Returns subscriber count and active task list:

```json
{
  "task_id": "my-task-001",
  "subscribers": 2,
  "active_tasks": ["my-task-001", "other-task"]
}
```

### Health Check

```
GET /health
```

```json
{
  "status": "ok",
  "timestamp": "2025-06-28T12:00:00.000Z",
  "services": {
    "tts": { "healthy": true, "message": "Space is healthy" },
    "music": { "healthy": true, "message": "Space is healthy" },
    "video": { "healthy": true, "message": "Space is healthy" }
  }
}
```

### API Root

```
GET /
```

```json
{
  "name": "Inference Service API",
  "version": "2.0.0",
  "docs": "/docs",
  "health": "/health",
  "predict": "/api/v1/predict/{tts|music|video|mock}",
  "websocket": "/ws/progress/{task_id}",
  "mock_run": "/api/v1/mock/run"
}
```

---

## 4. Error Handling

| HTTP Status | Condition |
|-------------|-----------|
| 400 | Unknown service type or invalid request |
| 422 | Malformed JSON body |
| 500 | Prediction error (service crashed) |
| 503 | Service unavailable (factory failed to create) |

WebSocket messages carry structured errors:

```json
{
  "status": "failed",
  "progress": 0,
  "error": "Event polling timed out",
  "error_code": "POLL_TIMEOUT",
  "retryable": true,
  "last_attempt": 10
}
```

---

## 5. Quick Reference

| Action | Method | Endpoint |
|--------|--------|----------|
| Submit TTS | `POST` | `/api/v1/predict/tts` |
| Submit Music | `POST` | `/api/v1/predict/music` |
| Submit Video | `POST` | `/api/v1/predict/video` |
| Submit Mock | `POST` | `/api/v1/predict/mock` |
| Listen progress | `WS` | `ws://host/ws/progress/{task_id}` |
| Check task info | `GET` | `/api/v1/tasks/{task_id}` |
| Health check | `GET` | `/health` |
| Interactive docs | Browser | `/docs` |
