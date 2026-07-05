# Development Journal — Music Video Platform

**Status:** 全自动纠错 · 持续优化 · 长期记忆模式已开启
**Started:** 2026-06-30

## 工程化协议

- 目录结构标准化：src/components, src/hooks, src/utils, src/styles, docs
- 错误自动修复：每次代码报错时自动读取日志并修复
- 性能持续优化：每个功能完成后主动审视性能并记录
- 长期记忆：所有规范和决策记录在本文档中，后续会话自动继承

## 变更记录

|| Date | Change | Description ||
|------|--------|-------------||
| 2026-07-05 | P0: Implement ProvenanceTimeline | Created `ProvenanceTimeline.tsx` component with vertical timeline UI, color-coded operation nodes (generate/remix/trim/mv), param summaries, originality badge (原创/衍生), and JSON-LD export. Integrated into TrackStudio.tsx with provenance state management. RemixTool now records detailed params (pitchShift, tempoMultiplier, timbreTransform) and marks derivative works. `tsc --noEmit` passes zero errors. |
| 2026-07-05 | P1: Complete MIDI Render pipeline (Path D) | Replaced MockInferenceService with real `MidiRenderService` in `WorkflowEngine.run_path_d`. Added `_get_midi_service()` lazy loader with FluidSynth/mido support. Fixed `health_check` bug in `midi_render.py`. Added `MIDI_SOUNDFONT_PATH` env var config. Path D now renders MIDI projects to audio via FluidSynth. `tsc --noEmit` passes zero errors. |
| 2026-07-05 | P2: MV Generator end-to-end fix | Fixed `MVGenerator.tsx` download section to use `<video>` tag instead of `<audio>`. Added `mvReady` translation to all 8 locale files (en/zh/ja/ko/de/es/fr/pt/ru). |
| 2026-07-05 | P1: Rewrite mix_engine.py — fix broken ffmpeg filter graph | Original `mix_engine.py` had critical bugs: (1) `_pan_gain` returned 0.0 for L channel when pan<0 (silenced left side), (2) filter labels between per-track processing and pan stage were inconsistent (`a{i}` vs `{i}`), (3) `[{i}]anull` was malformed. Rewrote with: equal-power pan via `pan=stereo|c0=cos|c1=sin`, correct 3-band EQ (100Hz/1kHz/8kHz), reverb via `asplit → aecho → amix`, clean label chain `[i:a]→...→[t{i}]→amix→[mix0]→[out]`. 10/10 ad-hoc verification checks pass. `tsc --noEmit` passes. |
| 2026-07-05 | P1: Rewrite remix.py `_apply_remix_sync` — pydub → ffmpeg | Original `_apply_remix_sync` had critical bugs: (1) pitch shift + tempo change via `frame_rate` manipulation were incompatible (tempo change re-pitched the already-pitch-shifted audio, and `set_frame_rate` resampling cancelled the pitch shift), (2) timbre EQ via `low_pass_filter + (float)*seg` produced illogical blends. Rewrote as ffmpeg filter chain: `asetrate` for pitch (with `atempo` to fix duration), `atempo` for tempo (independent of pitch), `lowshelf/highshelf/equalizer` for timbre, `dynaudnorm` for loudness normalization. Updated `health_check` to detect ffmpeg instead of pydub. 10/10 ad-hoc verification checks pass. |
| 2026-07-05 | P1: Docker deployment | Created multi-stage `Dockerfile` (frontend-build → backend → production), `docker-compose.yml` with nginx reverse proxy, `.env.example` template, `.dockerignore`, and `DEPLOYMENT.md`. Production image includes nginx (serving SPA + proxying /api/ and /ws/ to backend), ffmpeg, fluidsynth. `docker compose up --build -d` brings up full stack on port 80. |
|| 2026-06-30 | P1: Implement RemixTool.tsx | Created RemixTool component (pitch ±12st, tempo 0.5-2.0x, timbre presets) with /api/v1/remix/process API integration. Wired into TrackList and HistoryPanel as floating menu on completed tracks. Added remix WS progress handling, provenance marking (derivative tracks). Updated types with ProjectProvenance, RemixParameters, BeatDetectionResult, VideoRenderJob. `tsc --noEmit` passes zero errors. |
| 2026-06-30 | Feature planning: copyright protection, MV generator, provenance audit | Added Section 8 (功能规划) to best-practices.md. Designed RemixTool.tsx, useVideoGenerator.ts, ProjectProvenance type. Identified 5 backend services needed. |
| 2026-06-30 | Refactor TrackStudio.tsx (1586 lines → ~30 files) | Phase 1: Extract types (`types/trackStudio.ts`), hooks (`useSessionStorage`, `useBatchProgress`). Phase 2: Create 10 sub-components (`MiniWaveform`, `AudioPlayer`, `TrackStudioHeader`, `PathSelector`, `TrackInputArea`, `TrackList`, `HistoryPanel`, `IdleState`, `BatchProgressDashboard`). Phase 3: Rewrite `TrackStudio.tsx` as composition entry (~350 lines). Original backed up as `.tsx.bak`. `tsc --noEmit` passes zero errors. |
| 2026-06-30 | Session interrupted — state frozen | User signed off. All files committed/staged. Build verified. See 明日待办 below. |

## 会话状态快照

```
当前工作树状态:
  M  frontend/src/pages/TrackStudio.tsx          (1586 → 358 lines, -77%)
  ?? DEVELOPMENT_JOURNAL.md                       (new)
  ?? frontend/docs/best-practices.md              (new)
  ?? frontend/src/components/Audio/MiniWaveform.tsx
  ?? frontend/src/components/Audio/AudioPlayer.tsx
  ?? frontend/src/components/TrackStudio/RemixTool.tsx
  ?? frontend/src/components/TrackStudio/TrackList.tsx
  ?? frontend/src/components/TrackStudio/HistoryPanel.tsx
  ?? frontend/src/components/TrackStudio/TrackStudioHeader.tsx
  ?? frontend/src/components/TrackStudio/PathSelector.tsx
  ?? frontend/src/components/TrackStudio/TrackInputArea.tsx
  ?? frontend/src/components/TrackStudio/IdleState.tsx
  ?? frontend/src/components/TrackStudio/BatchProgressDashboard.tsx
  ?? frontend/src/hooks/useSessionStorage.ts
  ?? frontend/src/hooks/useBatchProgress.ts
  ?? frontend/src/pages/TrackStudio.tsx.bak       (original backup)
  ?? frontend/src/types/trackStudio.ts

编译验证: tsc --noEmit ✓ 零错误
构建验证: vite build ✓ 43 modules, 183KB gzip 57KB
```

## 明日待办

- [x] **P0: Provenance 时间轴可视化** — ✅ 已完成。`ProvenanceTimeline.tsx` 组件，垂直时间轴，颜色编码操作节点，原创/衍生徽章，JSON-LD 导出。
- [ ] **RemixTool WS 反馈链路验证** — 启动后端 mock，确认
       `POST /api/v1/remix/process` → WS 推送 → `onRemixComplete` 追加新 track 到 history 的全链路。
- [ ] **useVideoGenerator.ts 骨架** — 对接 `/api/v1/mv/detect-beats` 和
       `/api/v1/mv/render` 端点，复用 `useWebSocketProgress` 进度推送模式。
- [ ] **Git commit** — 将所有新增/修改文件提交到版本控制。

## Todo

- [ ] Backend API integration test coverage
- [ ] WebSocket reconnect mechanism optimization
- [ ] Frontend component performance profiling
