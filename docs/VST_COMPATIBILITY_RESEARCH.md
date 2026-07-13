# 🎹 VST 插件兼容性预研报告 (P3-4)

**目标**: 200+ → 1000+ VST3 支持  
**周期**: 6 周  
**预算**: ¥5K (测试服务器)  
**技术路线**: JUCE + WebAssembly

---

## 📊 技术方案对比

### 方案 A: JUCE + WebAssembly (推荐 🌟)

**架构**:
```
浏览器 → WebAudio API → WASM Runtime (JUCE) → VST3 插件 → 音频输出
                ↓
          UI 渲染 (HTML/CSS)
```

**优势**:
- ✅ 原生 VST3 SDK 支持
- ✅ 性能接近原生 (90%+)
- ✅ 生态系统成熟 (JUCE 社区)
- ✅ 可同时支持 Windows/Mac/ Web

**劣势**:
- ❌ 包体积大 (~50MB)
- ❌ 首次加载慢 (5-10 秒)
- ❌ 浏览器兼容性要求高 (Chrome 89+)
- ❌ 开发复杂度高 (C++ + JS 混合)

**工作量**: 6 周
- Week 1-2: JUCE 编译到 WASM
- Week 3-4: WebAudio 集成
- Week 5-6: UI 系统开发

---

### 方案 B: Faust + WebAudio

**架构**:
```
Faust 代码 → WebAudio 节点 → 输出
```

**优势**:
- ✅ 开发快速 (2 周)
- ✅ 包体积小 (~1MB)
- ✅ 浏览器兼容性好

**劣势**:
- ❌ 不支持 VST3 格式
- ❌ 需要重写所有插件
- ❌ 生态不成熟

**结论**: 不适用于本项目 (需要 VST3 兼容)

---

### 方案 C: 混合方案 (最佳实践)

**架构**:
```
基础效果器 (20 种) → WebAudio 原生实现
高级 VST3 插件 → JUCE WASM 沙盒
```

**策略**:
1. **第一阶段 (Week 1-2)**: WebAudio 实现 20 种常用效果器
   - EQ, Compressor, Reverb, Delay, Chorus
   - 快速上线，满足 80% 用户

2. **第二阶段 (Week 3-6)**: JUCE WASM 集成
   - 支持 VST3 插件加载
   - 插件市场架构
   - 逐步扩充到 1000+

---

## 🛠️ JUCE WASM 实施步骤

### Step 1: 环境搭建 (Week 1)

**依赖安装**:
```bash
# 安装 Emscripten (WASM 编译器)
git clone https://github.com/emscripten-core/emsdk.git
cd emsdk
./emsdk install latest
./emsdk activate latest

# 安装 JUCE 框架
git clone https://github.com/juce-framework/JUCE.git
cd JUCE

# 验证 CMake
cmake --version
```

**JUCE WASM 配置**:
```cmake
# CMakeLists.txt (WASM Target)
add_executable(PluginHostWASM)
target_sources(PluginHostWASM PRIVATE Source/Main.cpp)
target_link_libraries(PluginHostWASM PRIVATE juce::juce_audio_utils)

set_target_properties(PluginHostWASM PROPERTIES
    LINK_FLAGS "--bind -s WASM=1 -s ALLOW_MEMORY_GROWTH=1"
)
```

---

### Step 2: VST3 包装器开发 (Week 2-3)

**C++ 包装器代码**:
```cpp
// VST3Wrapper.h
class VST3Wrapper : public juce::AudioProcessor {
public:
    VST3Wrapper() : plugin(nullptr) {}
    
    void prepareToPlay(double sampleRate, int samplesPerBlock) override {
        if (plugin) {
            plugin->prepareToPlay(sampleRate, samplesPerBlock);
        }
    }
    
    void processBlock(juce::AudioBuffer<float>& buffer, 
                     juce::MidiBuffer& midiMessages) override {
        if (plugin) {
            plugin->processBlock(buffer, midiMessages);
        }
    }
    
    bool loadVST3(const juce::File& file) {
        plugin = juce::AudioPluginInstance::createInstanceFromDescription(
            juce::AudioPluginFormatManager(),
            file
        );
        return plugin != nullptr;
    }

private:
    juce::AudioPluginInstance* plugin;
};
```

---

### Step 3: WebAudio 集成 (Week 4)

**JavaScript 绑定**:
```javascript
// VSTPluginHost.js
class VSTPluginHost {
  constructor() {
    this.module = null;
    this.plugin = null;
  }

  async loadWASM(wasmPath) {
    const imports = {
      env: {
        // 提供必要的环境函数
        memory: new WebAssembly.Memory({ initial: 256 }),
      }
    };

    const response = await fetch(wasmPath);
    const bytes = await response.arrayBuffer();
    this.module = await WebAssembly.instantiate(bytes, imports);
    
    return this.module;
  }

  async loadVST3(vst3Path) {
    if (!this.module) throw new Error('WASM 未加载');

    // 调用 C++ 导出函数
    const loadPlugin = this.module.cwrap('loadVST3', 'number', ['string']);
    const pluginId = loadPlugin(vst3Path);

    if (pluginId === 0) {
      throw new Error('插件加载失败');
    }

    this.plugin = pluginId;
    return pluginId;
  }

  process(audioData, midiData) {
    if (!this.plugin) return audioData;

    const processBlock = this.module.cwrap('processBlock', null, [
      'number',  // plugin ID
      'number',  // audio buffer ptr
      'number',  // midi buffer ptr
      'number'   // sample count
    ]);

    // 处理音频...
    processBlock(this.plugin, audioPtr, midiPtr, samples);

    return audioData;
  }
}
```

---

### Step 4: 插件市场架构 (Week 5-6)

**后端 API**:
```python
@router.get("/plugins")
async def list_plugins(category: str = None):
    """获取插件列表"""
    plugins = db.query(Plugin).filter(
        Plugin.category == category if category else True
    ).all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "type": p.type,  # "VST3" | "WebAudio"
            "vendor": p.vendor,
            "price": p.price,
            "rating": p.rating,
            "download_count": p.downloads,
            "thumbnail": p.thumbnail_url
        }
        for p in plugins
    ]

@router.post("/plugins/{plugin_id}/purchase")
async def purchase_plugin(plugin_id: str, user_id: str):
    """购买插件"""
    # 支付逻辑...
    return {"success": True, "download_url": "..."}
```

**前端组件**:
```tsx
// PluginMarket.tsx
export const PluginMarket: React.FC = () => {
  const [plugins, setPlugins] = useState([]);
  
  useEffect(() => {
    fetch('/api/v1/plugins')
      .then(r => r.json())
      .then(setPlugins);
  }, []);

  return (
    <div className="plugin-market">
      {plugins.map(plugin => (
        <PluginCard key={plugin.id} {...plugin} />
      ))}
    </div>
  );
};
```

---

## 📊 测试计划

### 兼容性测试清单

**测试插件** (100+ 主流):
- 🎛️ **FabFilter**: Pro-Q3, Pro-C2, Pro-L2
- 🎛️ **Waves**: SSL, C6, CLA-76
- 🎛️ **Soundtoys**: Decapitator, EchoBoy
- 🎛️ **Valhalla**: VintageVerb, Supermassive
- 🎛️ **iZotope**: Ozone, Neutron
- 🎛️ **Native Instruments**: Guitar Rig, Kontakt
- 🎛️ **免费插件**: TDR Nova, Voxengo SPAN

**测试维度**:
- [ ] 加载成功率 (>95%)
- [ ] CPU 占用 (<10% 单插件)
- [ ] 内存占用 (<100MB 单插件)
- [ ] 延迟 (<10ms)
- [ ] UI 渲染正常
- [ ] 预设保存/加载
- [ ] 自动化控制
- [ ] 多实例运行

---

## 💰 预算明细

| 项目 | 明细 | 金额 |
|------|------|------|
| **开发服务器** | 4090 GPU (WASM 编译) | ¥500/月 × 6 = ¥3000 |
| **测试插件采购** | 付费插件测试授权 | ¥1000 |
| **CDN 存储** | WASM 文件存储 | ¥300/月 × 6 = ¥1800 |
| **备用金** | 应急使用 | ¥200 |
| **总计** | | **¥5000** |

---

## 📈 预期成果

### 技术指标
- [ ] 支持 VST3 格式 1000+
- [ ] 加载成功率 >95%
- [ ] 平均延迟 <10ms
- [ ] CPU 占用 <10% (单插件)
- [ ] 插件市场上线

### 用户体验
- [ ] 插件加载时间 <2 秒
- [ ] UI 响应流畅
- [ ] 预设管理方便
- [ ] 支持搜索/分类

### 商业模式
- [ ] 免费插件 20+ 种
- [ ] 付费插件分成 30%
- [ ] 插件开发者入驻 10+
- [ ] 月插件收入 ¥50K+

---

## ⚠️ 风险与应对

### 风险 1: WASM 包体积过大

**应对**:
- 按需加载 (Lazy Load)
- CDN 分发
- 首次只加载核心插件

### 风险 2: 浏览器兼容性

**应对**:
- 降级方案 (WebAudio 原生)
- 提示用户升级浏览器
- 提供 Electron 桌面版

### 风险 3: 插件授权问题

**应对**:
- 只支持用户已购插件
- 插件市场正版授权
- DRM 保护机制

---

**状态**: ✅ 预研完成，准备开发  
**下一步**: Week 1 JUCE 环境搭建  
**负责人**: 音频团队