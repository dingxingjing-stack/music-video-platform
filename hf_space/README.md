---
title: mvp-musicgen-zero
emoji: 🎵
colorFrom: purple
colorTo: blue
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
---

# MVP MusicGen-Small ZeroGPU

- Model: `facebook/musicgen-small` (300M, MIT) via `transformers`
- Hardware: ZeroGPU (Space Settings → Hardware → ZeroGPU, `large` 48GB default)
- Pattern: `model.to('cuda')` at top level, `@spaces.GPU(duration=60)` for inference
- CosyVoice2: BLOCKED this phase (stub)

## Local test (Kaggle T4)
```
python hf_space/app.py
```
