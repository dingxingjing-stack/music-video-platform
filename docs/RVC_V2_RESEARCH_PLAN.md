# 🎤 RVC v2 人声优化预研计划

**目标**: 人声音质从 6.5 → 8.0/10 (+1.5 分)  
**对标**: Suno v4.5 (7.2/10) → **超越**  
**周期**: 4-6 周  
**预算**: ¥3,000 (GPU 云服务器 + 数据集)

---

## 📊 现状分析

### 当前人声问题 (P0+P1 后)

| 问题 | 严重度 | 现状评分 | 目标评分 |
|------|--------|----------|----------|
| **人声自然度** | 🔴 高 | 6.0/10 | 8.5/10 |
| **情感表达** | 🔴 高 | 6.0/10 | 8.0/10 |
| **咬字清晰度** | 🟡 中 | 6.5/10 | 8.0/10 |
| **音色一致性** | 🟡 中 | 7.0/10 | 8.5/10 |
| **高音表现** | 🟢 低 | 7.0/10 | 8.0/10 |
| **气息噪音** | 🟡 中 | 6.0/10 | 8.0/10 |

**综合**: 6.5/10 → **目标 8.0/10** (+1.5 分)

---

## 🔬 技术方案对比

### 方案 A: RVC v2 (Retrieval-based Voice Conversion)

**优势**:
- ✅ 开源免费 (MIT License)
- ✅ 只需 10 分钟训练数据
- ✅ 支持实时推理 (<100ms)
- ✅ 音色转换质量高
- ✅ 社区活跃 (GitHub 15k+ stars)

**劣势**:
- ❌ 需要 GPU 训练
- ❌ 中文优化不足
- ❌ 需要调参经验

**成本**:
- 训练：¥500 (AutoDL 4090, 20h)
- 推理：¥0 (本地 CPU 可跑)
- 数据：¥500 (购买优质人声数据集)
- **总计**: ¥1,000

**预期提升**: +1.2 分

---

### 方案 B: So-VITS-SVC

**优势**:
- ✅ 音色还原度极高
- ✅ 支持多说话人
- ✅ 中文社区支持好

**劣势**:
- ❌ 训练数据需求大 (30min+)
- ❌ 推理速度慢
- ❌ 显存占用高

**成本**: ¥1,500

**预期提升**: +1.0 分

---

### 方案 C: 商业 API (Azure Speech / ElevenLabs)

**优势**:
- ✅ 质量稳定
- ✅ 无需训练
- ✅ 多语言支持

**劣势**:
- ❌ 成本高 ($0.02-0.15/分钟)
- ❌ 依赖外部
- ❌ 无法定制音色

**成本**: ¥10,000/年

**预期提升**: +1.5 分

---

### 方案 D: 混合方案 (推荐 🌟)

**策略**: RVC v2 + 后处理链

```
用户输入 → Mureka AI 生成 → RVC v2 优化 → 后处理链 → 输出
                                  ↓
                          (De-esser + EQ + 压缩 + 混响)
```

**优势**:
- ✅ RVC v2 负责音色优化
- ✅ 后处理链解决气息/清晰度
- ✅ 成本可控
- ✅ 质量可超越 Suno

**成本**: ¥1,500 (RVC + 后处理)

**预期提升**: **+1.5 分**

---

## 🛠️ RVC v2 实施步骤

### Step 1: 环境搭建 (Week 1)

```bash
# 1. 克隆 RVC v2 仓库
git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git
cd Retrieval-based-Voice-Conversion-WebUI

# 2. 安装依赖
pip install -r requirements.txt

# 3. 下载预训练模型
# 从 HuggingFace 下载:
# - pretrained_v2/*.pth
# - rmvpe/*.pt
```

**验收标准**:
- [ ] WebUI 可 normal 启动
- [ ] 可加载预训练模型
- [ ] 推理测试通过

---

### Step 2: 数据集准备 (Week 1-2)

**数据要求**:
- 时长：10-30 分钟
- 格式：44.1kHz, WAV,  mono
- 质量：无背景音乐，清晰人声
- 内容：覆盖不同音高/情绪

**数据来源**:
1. **购买商业数据集** (¥500)
   - 中文女声/男声数据集
   - 包含多情绪/多音高

2. **自行录制** (¥0)
   - 专业录音棚：¥300/h × 2h = ¥600
   - 自家录音设备：¥0

3. **开源数据集** (¥0)
   - AISHELL-3 (中文 TTS)
   - WenetSpeech (中文语音)
   - LibriTTS (英文，参考用)

**数据处理流程**:
```bash
# 1. 切片 (10 秒一段)
python tools/slicer.py --input raw/ --output sliced/

# 2. 降噪
python tools/denoise.py --input sliced/ --output cleaned/

# 3. 音量标准化
python tools/normalize.py --input cleaned/ --output final/

# 4. 训练/验证划分
python tools/split.py --input final/ --train-ratio 0.9
```

---

### Step 3: 模型训练 (Week 2-3)

**训练配置 (4090 GPU)**:

```
Epoch: 100
Batch Size: 4
Learning Rate: 1e-4
GPU: RTX 4090 (24GB)
预计时间：15-20 小时
成本：¥2.5/h × 20h = ¥50 (AutoDL)
```

**训练流程**:
```bash
# 1. 特征提取
python tools/extract_f0.py --input data/train/

# 2. 提取 latent
python tools/extract_latent.py --input data/train/

# 3. 训练模型
python train.py \
  --exp_name "chinese_pop_female" \
  --batch_size 4 \
  --epochs 100 \
  --data_dir data/train/
```

**监控指标**:
- Total Loss (<0.5)
- F0 Loss (<0.3)
- Timbre Loss (<0.4)

**验收标准**:
- [ ] Loss 收敛到目标值
- [ ] 主观听测 >8.0/10
- [ ] 推理速度 <100ms

---

### Step 4: 后处理链开发 (Week 3-4)

**处理链结构**:
```
RVC 输出 → De-esser → EQ → 压缩 → 混响 → limiter → 最终输出
```

#### 4.1 De-esser (去齿音)

```python
def de_esser(audio, threshold=6000, ratio=0.5):
    """
    去除 s/sh/ch 等齿音
    参数:
      threshold: 频率阈值 (Hz)
      ratio: 压缩比
    """
    # 实现：多段压缩或动态 EQ
    pass
```

**预期提升**: 人声自然度 +0.2 分

#### 4.2 EQ (频率均衡)

```python
def vocal_eq(audio):
    """
    人声 EQ 曲线:
    - 200-400Hz: +2dB (温暖感)
    - 1-3kHz: +3dB (清晰度)
    - 5-8kHz: -2dB (去齿音残留)
    - 10kHz+: +1dB (空气感)
    """
    pass
```

**预期提升**: 清晰度 +0.3 分

#### 4.3 压缩 (动态控制)

```python
def vocal_compressor(audio, threshold=-18, ratio=4, attack=5, release=50):
    """
    人声压缩:
    - Threshold: -18dB
    - Ratio: 4:1
    - Attack: 5ms
    - Release: 50ms
    """
    pass
```

**预期提升**: 动态稳定性 +0.2 分

#### 4.4 混响 (空间感)

```python
def vocal_reverb(audio, room_size=0.3, decay=1.2, wet=0.15):
    """
    人声混响:
    - Room Size: 0.3 (小房间)
    - Decay: 1.2s
    - Wet/Dry: 15%
    """
    pass
```

**预期提升**: 空间感 +0.2 分

#### 4.5 Limiter (响度最大化)

```python
def limiter(audio, ceiling=-1.0):
    """
    限制器：防止削波
    Ceiling: -1.0 dBTP
    """
    pass
```

**预期提升**: 响度一致性 +0.1 分

---

### Step 5: 集成与测试 (Week 4-5)

**集成架构**:
```
用户请求
  ↓
Mureka API (基础生成)
  ↓
RVC v2 (音色优化)
  ↓
后处理链 (De-esser → EQ → 压缩 → 混响 → limiter)
  ↓
CDN 上传
  ↓
返回 URL
```

**API 端点**:
```python
@router.post("/optimize-vocal")
async def optimize_vocal(audio_url: str, preset: str = "pop_female"):
    """
    人声优化端点
    
    参数:
      audio_url: 原始音频 URL
      preset: 预设 (pop_female/rock_male/etc)
    
    返回:
      optimized_url: 优化后音频 URL
      processing_time: 处理时间 (秒)
      quality_score: 质量评分 (0-10)
    """
```

**A/B 测试**:
- Group A: Mureka 原声 (6.5/10)
- Group B: RVC v2 + 后处理 (目标 8.0/10)

**验收标准**:
- [ ] 盲测评分 >8.0/10
- [ ] 处理时间 <10 秒
- [ ] 用户满意度 >90%

---

## 📊 预算明细

| 项目 | 数量 | 单价 | 总价 |
|------|------|------|------|
| **GPU 云训练** | 20h | ¥2.5/h | ¥50 |
| **人声数据集** | 1 套 | ¥500 | ¥500 |
| **录音设备** | 1 套 | ¥400 | ¥400 |
| **后处理插件** | 5 个 | ¥100 | ¥500 |
| **A/B 测试** | 1000 用户 | ¥0.5 | ¥500 |
| **预留** | - | - | ¥1,050 |
| **总计** | - | - | **¥3,000** |

---

## 📈 预期收益

### 音质提升

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| 人声自然度 | 6.0 | 8.5 | +2.5 |
| 情感表达 | 6.0 | 8.0 | +2.0 |
| 咬字清晰度 | 6.5 | 8.0 | +1.5 |
| 音色一致性 | 7.0 | 8.5 | +1.5 |
| 高音表现 | 7.0 | 8.0 | +1.0 |
| 气息噪音 | 6.0 | 8.0 | +2.0 |
| **综合** | **6.5** | **8.0** | **+1.5** |

### 商业价值

- **用户留存**: +30% (音质是核心体验)
- **付费转化**: +20% (专业用户愿意为音质付费)
- **口碑传播**: +50% (用户自发推荐)
- **竞品差距**: 从 -0.7 分 → **+0.8 分** (反超 Suno)

---

## ⚠️ 风险与应对

### 风险 1: RVC v2 训练失败

**原因**: 数据质量差/超参设置错误  
**应对**: 
- 准备 3 套数据集备选
- 先小规模测试 (10 分钟数据)
- 请教 RVC 社区 (GitHub Issues/Discord)

### 风险 2: 推理速度太慢

**原因**: CPU 优化不足  
**应对**:
- 使用 ONNX Runtime 加速
- 量化模型 (FP32 → INT8)
- 必要时上 GPU 推理 (¥0.5/小时)

### 风险 3: 中文效果不佳

**原因**: RVC v2 主要针对英文训练  
**应对**:
- 使用中文数据集 fine-tune
- 后处理链专门针对中文优化
- 必要时切换到中文优化的 So-VITS-SVC

---

## 📅 时间表

| 周次 | 任务 | 交付物 | 负责人 |
|------|------|--------|--------|
| **Week 1** | 环境搭建 + 数据集 | 可运行的 RVC 环境 | 技术团队 |
| **Week 2** | 数据预处理 + 训练启动 | 清洗后的数据集 | 技术团队 |
| **Week 3** | 模型训练 + 初步测试 | 初版 RVC 模型 | 技术团队 |
| **Week 4** | 后处理链开发 | De-esser/EQ/ 压缩/混响 | 音频团队 |
| **Week 5** | 系统集成 + A/B 测试 | 完整 pipeline + 测试报告 | 全体 |
| **Week 6** | 优化 + 上线 | 生产环境部署 | 运维团队 |

---

## ✅ 验收标准

### 技术指标
- [ ] 盲测评分 ≥8.0/10
- [ ] 处理时间 ≤10 秒
- [ ] 音色相似度 ≥90%
- [ ] 推理延迟 ≤100ms (GPU) 或 ≤500ms (CPU)

### 用户体验
- [ ] A/B 测试：B 组 (RVC) 满意度 >90%
- [ ] 用户反馈：80% 认为"音质明显提升"
- [ ] 留存率：+20%

### 商业指标
- [ ] 付费转化：+15%
- [ ] 用户推荐率：+30%
- [ ] 竞品对比：音质反超 Suno v4.5

---

## 🔗 参考资源

- **RVC v2 GitHub**: https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI
- **HuggingFace 模型**: https://huggingface.co/wada-ero/RVC
- **AutoDL GPU 租赁**: https://www.autodl.com/
- **中文语音数据集**: https://www.aishelltech.com/kysjcp
- **后处理插件**: https://github.com/ kihlkwon/Audio-Processing

---

**状态**: ✅ 预研启动  
**预算**: ¥3,000  
**周期**: 6 周  
**目标**: 人声 6.5 → 8.0/10 (+1.5 分)  
**预期**: 反超 Suno v4.5 (7.2/10)