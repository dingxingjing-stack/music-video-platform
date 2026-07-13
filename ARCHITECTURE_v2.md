# MV Studio — 功能架构 v2.0 (DAW + AI Hybrid)

## 核心理念
结合 **Cubase 的专业 DAW 功能** + **Suno 的 AI 生成能力**，打造混合式音乐制作平台。

---

## 功能模块总览

```
┌─────────────────────────────────────────────────────────────────┐
│                      NAVIGATION / 导航                          │
│  [首页] [发现 Feed] [我的作品] [工作室] [学习资源]              │
└─────────────────────────────────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────┐ ┌─────────────────┐
│   发现 Feed     │ │  我的作品   │ │   工作室 DAW    │
│  (Suno-style)   │ │  (Project)  │ │  (Cubase-style) │
└─────────────────┘ └─────────────┘ └─────────────────┘
                           │                 │
                           └────────┬────────┘
                                    ▼
                        ┌───────────────────────┐
                        │   AI 生成引擎         │
                        │  - 提示词→歌曲        │
                        │  - 续写/扩展          │
                        │  - 风格迁移           │
                        │  - 歌词生成           │
                        └───────────────────────┘
```

---

## 模块详解

### 1️⃣ 发现 Feed (Community)
**对标**: Suno Discover
- [ ] 无限滚动歌曲卡片
- [ ] 播放/暂停（内嵌播放器）
- [ ] 点赞/收藏/分享
- [ ] 播放计数，喜欢计数
- [ ] 流派筛选，热门标签
- [ ] 翻唱/Remix 入口
- [ ] 创作者主页

### 2️⃣ 我的作品 (Library)
**对标**: Cubase Project Browser + Suno Library
- [ ] 项目/工程文件列表（网格/列表视图）
- [ ] 搜索/筛选（日期，流派，状态）
- [ ] 快速预览（悬停播放）
- [ ] 批量操作（删除，导出，归档）
- [ ] 版本历史（Git-style）

### 3️⃣ 工作室 DAW (核心)
**对标**: Cubase Arrange Window + MixConsole

#### 3.1 多轨编辑器 (Arrangement)
- [x] 单轨 waveform 显示
- [ ] **多轨并行**（音频轨 + MIDI 轨 + 总线）
- [ ] **时间轴缩放**（水平/垂直）
- [ ] **播放头定位**（点击跳转，键盘左右）
- [ ] **Loop 循环区域**设置
- [ ] **Markers 标记**（Verse, Chorus, Bridge）

#### 3.2 音频剪辑 (Audio Editing)
- [ ] **切割工具**（Split at cursor）
- [ ] **裁剪/修剪**（Trim start/end）
- [ ] **淡入淡出**（Fade handles）
- [ ] **交叉淡化**（Crossfade）
- [ ] **弹性音频**（Time-stretch）
- [ ] **音频对齐**（Quantize）
- [ ] **静音/独奏/武装**（M/S/A）

#### 3.3 MIDI 编辑器
- [ ] **钢琴卷帘**（Note 绘制，力度，时值）
- [ ] **乐谱视图**（简谱/五线谱）
- [ ] **鼓编辑器**（Step sequencer）
- [ ] **MIDI 效果器**（Arpeggiator，Chord）
- [ ] **量化**（Quantize）
- [ ] **力度编辑**（Velocities）

#### 3.4 MixConsole 调音台
- [ ] **通道条**（Gain, Pan, M/S）
- [ ] **插入效果**（4 插槽）
- [ ] **发送/返回**（Aux sends）
- [ ] **EQ 三段**（High/Mid/Low）
- [ ] **压缩器**（Threshold, Ratio, Attack, Release）
- [ ] **响度表**（LUFS, Peak）

#### 3.5 效果器链 (FX Rack)
- [ ] **EQ**（8 段参数，频谱分析）
- [ ] **压缩**（VCA, Optical）
- [ ] **混响**（Hall, Plate, Room）
- [ ] **延迟**（Tape, Digital）
- [ ] **调制**（Chorus, Flanger, Phaser）
- [ ] **失真**（Saturation, Bitcrush）
- [ ] **母带**（Limiter, Maximizer）

#### 3.6 自动化 (Automation)
- [ ] **音量自动化**（Draw/read）
- [ ] **声像自动化**
- [ ] **效果参数自动化**
- [ ] **包络跟随**

### 4️⃣ AI 生成引擎
**对标**: Suno Create + Advanced Controls

#### 4.1 基础生成
- [x] 提示词输入
- [x] 风格选择
- [ ] **人声性别**（Male/Female/Both）
- [ ] **排除乐器**（No drums, No bass）
- [ ] **歌曲结构**（Intro-Verse-Chorus-Outro）

#### 4.2 高级控制
- [ ] **Weirdness 滑块**（0-100%）
- [ ] **Style Strength 滑块**
- [ ] **BPM 范围锁定**
- [ ] **调性锁定**（C maj, A min）

#### 4.3 后期 AI 工具
- [ ] **歌词重写**（行级编辑）
- [ ] **段落续写**（Extend from timestamp）
- [ ] **风格迁移**（Change genre）
- [ ] ** tái 混音**（Remix with new elements）
- [ ] **人声替换**（Change singer voice）
- [ ] **扒带**（Extract chords/melody）

### 5️⃣ 导出与分享
- [ ] **单文件导出**（MP3, WAV, FLAC）
- [ ] **分轨导出**（Stems: Vocals, Drums, Bass, Other）
- [ ] **批量导出**（全专辑）
- [ ] **响度标准化**（-14 LUFS for Spotify）
- [ ] **元数据嵌入**（ID3 tags）
- [ ] **直接发布**（到发现 Feed）

### 6️⃣ 学习资源
**对标**: Cubase Learn + Steinberg Tutorials
- [ ] 新手引导（交互式）
- [ ] 视频教学（内嵌）
- [ ] 预设/模板库
- [ ] 快捷键速查表

---

## 技术架构

### 前端 (React + TypeScript)
```
src/
├── components/
│   ├── MultiTrackEditor/      # 多轨时间轴
│   ├── AudioClip/             # 音频片段
│   ├── PianoRoll/             # MIDI 编辑器
│   ├── MixConsole/            # 调音台
│   ├── FXRack/                # 效果器架
│   ├── AutomationLane/        # 自动化轨道
│   ├── Transport/             # 播放控制
│   ├── DiscoveryFeed/         # 发现页
│   └── ProjectBrowser/        # 项目管理
├── hooks/
│   ├── useAudioEngine/        # 音频引擎（WebAudio API）
│   ├── useMIDIInput/          # MIDI 设备支持
│   ├── useAutomation/         # 自动化管理
│   └── useProject/            # 项目状态
├── stores/
│   ├── projectStore.ts        # Zustand: 项目状态
│   ├── audioStore.ts          # WebAudio 上下文
│   └── uiStore.ts             # UI 状态
└── workers/
    ├── audioWorker.ts         # 音频处理（離线程）
    └── renderWorker.ts        # 渲染队列
```

### 后端 (FastAPI)
```
backend/app/
├── routers/
│   ├── projects.py            # 项目 CRUD
│   ├── tracks.py              # 音轨管理
│   ├── export.py              # 导出任务
│   └── community.py           # 社区 feed
├── services/
│   ├── audio_processor.py     # FFmpeg/librosa
│   ├── midi_parser.py         # pretty_midi
│   ├── ai_generator.py        # Mureka/NVAPI
│   └── stem_separator.py      # Demucs
└── models/
    ├── Project.py             # SQLAlchemy ORM
    └── Track.py
```

### 音频引擎
- **播放**: WebAudio API + wavesurfer.js
- **MIDI**: @tonejs/midi + WebMIDI API
- **效果**: TONE.js FX (EQ, Compressor, Reverb)
- **离线程**: AudioWorklet (低延迟处理)

---

## 开发优先级

### Phase 1 (基础 DAW) - 2 周
1. 多轨时间轴（音频轨叠加）
2. 播放头同步，Loop 区域
3. 基础剪辑（切割，裁剪）
4. MixConsole（推子，M/S）

### Phase 2 (MIDI 编辑) - 2 周
1. 钢琴卷帘
2. MIDI 输入（鼠标绘制 + 键盘）
3. 量化，力度编辑
4. VSTi 预览基础音源

### Phase 3 (效果器) - 2 周
1. TONE.js FX 集成
2. 串联效果链
3. EQ + Compressor + Reverb
4. 参数自动化

### Phase 4 (AI 增强) - 2 周
1. 段落续写 API
2. 风格迁移
3. 歌词重写
4. 扒带功能

### Phase 5 (社区 + 导出) - 1 周
1. 发现 Feed
2. 分轨导出
3. 批量处理
4. 发布分享

---

## UI 设计原则

### 配色 (Suno-inspired, original execution)
- **Background**: `#121212` (深灰)
- **Panel**: `#1e1e1e` (中灰)
- **Track BG**: `#2a2a2a` (轨道背景)
- **Waveform**: `#00d4aa` (青绿渐变)
- **MIDI Notes**: `#ff6a95` (粉红)
- **Accent**: `#ff8c42` (橙色渐变)
- **Text Primary**: `#f0f0f0`
- **Text Secondary**: `#a0a0a0`

### 布局
- **顶部**: 全局导航 + 用户菜单
- **左侧**: 项目浏览器/工具箱
- **中央**: 多轨时间轴 + 编辑器
- **底部**: MixConsole 调音台
- **右侧**: 效果器架 + 属性面板

### 交互
- **拖拽**: 轨道重排，片段移动
- **缩放**: 鼠标滚轮（时间轴）
- **快捷键**: Cubase-style (Q 切割，E 裁剪)
- **右键菜单**: 上下文操作

---

## 成功指标

### 功能性
- [ ] 支持 16+ 音频轨并行播放
- [ ] MIDI 输入延迟 < 10ms
- [ ] 实时效果处理无爆音
- [ ] 导出速度 < 1x 实时

### 用户体验
- [ ] 新手 5 分钟内完成第一首歌
- [ ] 专业用户可完成完整混音
- [ ] 移动端基础编辑可用

### 性能
- [ ] 首屏加载 < 3s
- [ ] 工程打开 < 5s (100 轨)
- [ ] 自动保存每 30s

---

**下一步**: 实现 Phase 1 — 多轨时间轴编辑器