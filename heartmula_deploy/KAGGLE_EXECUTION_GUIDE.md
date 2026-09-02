# HeartMuLa Kaggle 部署验证执行指南

## 前置条件
- Kaggle 账号，已启用 GPU（T4 或更高）
- Hugging Face Token（用于下载 HeartMuLa 模型，需在 Kaggle Secrets 中配置 `HF_TOKEN`）

---

## 步骤 1：创建笔记本并配置

1. 打开 [Kaggle](https://www.kaggle.com/code) → New Notebook
2. 设置 **GPU: T4**（右侧 Accelerator 选择 GPU T4 x2 或 x1）
3. 在 **Settings → Secrets** 添加：
   - `HF_TOKEN` = 你的 Hugging Face Token（需有权限访问 HeartMuLa/HeartMuLa-oss-3B 和 HeartMuLa/HeartCodec-oss）

---

## 步骤 2：克隆仓库并运行完整部署（推荐）

在笔记本单元格中运行：

```python
!git clone https://github.com/dingxingjing-stack/music-video-platform.git /kaggle/working/music-video-platform
%cd /kaggle/working/music-video-platform
!python heartmula_deploy/kaggle_setup.py
```

**预期输出**：
```
============================================================
HeartMuLa Kaggle 自动部署
============================================================
============================================================
步骤 1: 环境检查
============================================================
Python: 3.10.x
PyTorch: 2.x.x+cu121
CUDA: True
GPU: Tesla T4
VRAM: 15.00 GB
工作目录: /kaggle/working/music-video-platform

============================================================
步骤 2: Clone HeartLib 官方仓库
============================================================
$ git clone --depth 1 https://github.com/HeartMuLa/heartlib.git /kaggle/working/heartlib
✓ /kaggle/working/heartlib/pyproject.toml
✓ /kaggle/working/heartlib/README.md
✓ /kaggle/working/heartlib/src/heartlib/__init__.py
✓ /kaggle/working/heartlib/src/heartlib/heartmula
✓ /kaggle/working/heartlib/src/heartlib/heartcodec
✓ /kaggle/working/heartlib/src/heartlib/pipelines
HeartLib 源码位置: /kaggle/working/heartlib/src/heartlib

============================================================
步骤 3: 安装隔离依赖 (pip --target)
============================================================
...
依赖安装完成: /kaggle/working/heartmula_env

============================================================
步骤 4: 验证导入 (强制路径优先)
============================================================
sys.path 前5: ['/kaggle/working/heartmula_env', '/kaggle/working/heartlib/src', ...]
transformers = 4.57.0
tokenizers = 0.22.1
huggingface_hub = 0.34.4
heartlib.__file__ = /kaggle/working/heartlib/src/heartlib/__init__.py
✓ 正确指向: /kaggle/working/heartlib/src/heartlib/__init__.py
✓ 所有子模块导入成功

============================================================
步骤 5: 下载模型权重
============================================================
下载 HeartMuLa-oss-3B -> /kaggle/working/pretrained/HeartMuLa-oss-3B
✓ /kaggle/working/pretrained/HeartMuLa-oss-3B/tokenizer.json
✓ /kaggle/working/pretrained/HeartMuLa-oss-3B/gen_config.json
下载 HeartCodec-oss -> /kaggle/working/pretrained/HeartCodec-oss
✓ /kaggle/working/pretrained/HeartCodec-oss/config.json

============================================================
步骤 6: 最小音乐生成测试
============================================================
设备: cuda
加载 HeartMuLa...
✓ HeartMuLa 加载成功
加载 HeartCodec...
✓ HeartCodec 加载成功
执行生成测试...
✓ 生成测试通过

============================================================
🎉 所有步骤完成!
============================================================
```

---

## 步骤 3：运行独立生成测试（可选，验证 WAV 输出）

如果步骤 2 成功，运行独立生成脚本：

```python
%cd /kaggle/working/music-video-platform
!python heartmula_deploy/kaggle_generate.py
```

**预期输出**：
- 生成 10 秒钢琴旋律 WAV 文件
- 保存至 `/kaggle/working/generated_test.wav`
- 打印音频形状、时长、采样率

---

## 步骤 4：手动单元格执行（调试用）

若自动脚本失败，用 `kaggle_notebook_cells.py` 中的 5 个单元格逐步执行：

| 单元格 | 内容 | 验证点 |
|--------|------|--------|
| 1 | Clone HeartLib + 结构验证 | 仓库结构完整 |
| 2 | `pip install --target` 隔离依赖 | 版本锁定正确 |
| 3 | `sys.path` 强制优先 + 导入验证 | transformers/tokenizers/hf-hub 版本匹配，heartlib 从正确路径加载 |
| 4 | `snapshot_download` 模型权重 | tokenizer.json, gen_config.json, config.json 存在 |
| 5 | GPU 加载模型 + 生成测试 | HeartMuLa/HeartCodec 加载成功，显存占用正常 |

---

## 常见问题排查

### 1. `transformers` 版本不匹配
```
AssertionError: transformers = 4.xx.x != 4.57.0
```
**原因**：Kaggle 基础镜像自带新版 transformers  
**修复**：单元格 2 中 `--no-deps` 已阻止依赖升级，若仍冲突，在单元格 3 前加：
```python
!pip uninstall -y transformers tokenizers huggingface_hub
!pip install --target /kaggle/working/heartmula_env --no-deps transformers==4.57.0 tokenizers==0.22.1 huggingface-hub==0.34.4
```

### 2. `heartlib` 从错误路径加载
```
AssertionError: 路径错误: /opt/conda/lib/python3.10/site-packages/heartlib/__init__.py != /kaggle/working/heartlib/src/heartlib/__init__.py
```
**原因**：`sys.path` 插入顺序不对  
**修复**：确保 `sys.path.insert(0, "/kaggle/working/heartmula_env")` 和 `sys.path.insert(0, "/kaggle/working/heartlib/src")` 在 **所有 import 之前** 执行

### 3. 模型下载 401/403
```
RepositoryNotFoundError: 401 Client Error
```
**原因**：HF_TOKEN 未配置或无权限  
**修复**：Kaggle Secrets 添加 `HF_TOKEN`，且 Token 需有 HeartMuLa 仓库读取权限

### 4. GPU 显存不足 (OOM)
```
RuntimeError: CUDA out of memory
```
**原因**：T4 16GB 显存可能不足加载两个模型  
**缓解**：
- 单元格 5 中加载后立即 `torch.cuda.empty_cache()`
- 或使用 `device_map="auto"` 让 accelerate 自动分层
- 若仍 OOM，需申请更大 GPU（A100）

### 5. `MusicGenerationPipeline` 不存在
```
ModuleNotFoundError: No module named 'heartlib.pipelines.MusicGenerationPipeline'
```
**原因**：HeartLib 版本差异，Pipeline 类名不同  
**修复**：查看 `heartlib.pipelines.__all__` 或源码确认实际类名，调整 `kaggle_generate.py` 第 37 行导入

---

## 验证清单（全部 ✅ 即通过）

| 检查项 | 通过标准 |
|--------|----------|
| 环境检查 | CUDA=True, GPU=T4, VRAM≥15GB |
| HeartLib Clone | 6 个关键路径全 ✓ |
| 依赖安装 | 无报错，版本锁定 |
| 导入验证 | 3 个版本断言通过，heartlib 指向 `/kaggle/working/heartlib/src/heartlib` |
| 模型下载 | 3 个关键文件全 ✓ |
| 模型加载 | HeartMuLa + HeartCodec 无报错，显存占用 < 14GB |
| 生成测试 | 产出 WAV 文件，时长约 10s，采样率 44100 |

---

## 成功后的产物

```
/kaggle/working/
├── heartlib/                 # HeartLib 源码
├── heartmula_env/            # 隔离依赖
├── pretrained/
│   ├── HeartMuLa-oss-3B/     # ~6GB
│   └── HeartCodec-oss/       # ~1GB
├── generated_test.wav        # 生成测试音频
└── music-video-platform/     # 仓库副本
```

---

## 下一步（验证通过后）

1. 将 `generated_test.wav` 下载本地试听
2. 根据实际 API 调整 `kaggle_generate.py` 生成参数
3. 考虑将生成逻辑集成到主平台后端（Modal/Render）