/**
 * VST 插件管理器组件
 * 
 * 功能:
 * - 扫描/加载插件
 * - 插件列表显示
 * - 插件实例管理
 * - 预设系统
 * - 参数自动化编辑
 */

import { useState, useEffect } from 'react';
import { VSTHost } from '../utils/VSTHost';
import { PluginInfo, LoadedPlugin } from '../types/vst';

interface Props {
  onPluginLoad?: (plugin: LoadedPlugin) => void;
  maxInserts?: number;
}

export function VSTPluginManager({ onPluginLoad, maxInserts = 8 }: Props) {
  const [host] = useState(() => new VSTHost());
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loadedPlugins, setLoadedPlugins] = useState<LoadedPlugin[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [selectedPlugin, setSelectedPlugin] = useState<PluginInfo | null>(null);
  const [selectedInstance, setSelectedInstance] = useState<LoadedPlugin | null>(null);
  const [showPluginUI, setShowPluginUI] = useState(false);

  // 初始化
  useEffect(() => {
    host.initialize();
    scanPlugins();

    return () => {
      host.dispose();
    };
  }, []);

  // 扫描插件
  const scanPlugins = async () => {
    setIsScanning(true);
    
    // 模拟插件扫描
    // 实际实现需要扫描预定义的 WASM 插件路径
    const mockPlugins: PluginInfo[] = [
      {
        id: 'vst-eq-1',
        name: 'Pro-Q 3',
        vendor: 'FabFilter',
        version: '3.0',
        type: 'effect',
        category: 'EQ',
        description: '专业均衡器',
        parameters: [
          { id: 'freq', name: 'Frequency', value: 0.5, minValue: 20, maxValue: 20000, defaultValue: 1000, type: 'continuous', unit: 'Hz' },
          { id: 'gain', name: 'Gain', value: 0.5, minValue: -18, maxValue: 18, defaultValue: 0, type: 'continuous', unit: 'dB' },
          { id: 'q', name: 'Q', value: 0.5, minValue: 0.1, maxValue: 10, defaultValue: 1, type: 'continuous', unit: '' }
        ],
        presetCount: 50,
        hasUI: true,
        uiWidth: 800,
        uiHeight: 500
      },
      {
        id: 'vst-comp-1',
        name: 'SSL G-Master',
        vendor: 'Waves',
        version: '1.0',
        type: 'effect',
        category: 'Compressor',
        description: '总线压缩器',
        parameters: [
          { id: 'threshold', name: 'Threshold', value: 0.5, minValue: -30, maxValue: 0, defaultValue: -10, type: 'continuous', unit: 'dB' },
          { id: 'ratio', name: 'Ratio', value: 0.5, minValue: 1, maxValue: 10, defaultValue: 4, type: 'discrete', unit: ':1', steps: 10 },
          { id: 'attack', name: 'Attack', value: 0.5, minValue: 0.1, maxValue: 100, defaultValue: 10, type: 'continuous', unit: 'ms' }
        ],
        presetCount: 30,
        hasUI: true,
        uiWidth: 600,
        uiHeight: 400
      },
      {
        id: 'vst-reverb-1',
        name: 'VintageVerb',
        vendor: 'Valhalla',
        version: '1.0',
        type: 'effect',
        category: 'Reverb',
        description: '经典混响',
        parameters: [
          { id: 'decay', name: 'Decay', value: 0.5, minValue: 0.1, maxValue: 10, defaultValue: 2, type: 'continuous', unit: 's' },
          { id: 'mix', name: 'Mix', value: 0.5, minValue: 0, maxValue: 100, defaultValue: 30, type: 'continuous', unit: '%' },
          { id: 'preDelay', name: 'Pre Delay', value: 0.5, minValue: 0, maxValue: 200, defaultValue: 20, type: 'continuous', unit: 'ms' }
        ],
        presetCount: 100,
        hasUI: true,
        uiWidth: 700,
        uiHeight: 450
      },
      {
        id: 'vst-synth-1',
        name: 'Serum',
        vendor: 'Xfer Records',
        version: '1.3',
        type: 'instrument',
        category: 'Synth',
        description: '波表合成器',
        parameters: [
          { id: 'osc1', name: 'Oscillator 1', value: 0.5, minValue: 0, maxValue: 1, defaultValue: 0.5, type: 'continuous', unit: '' },
          { id: 'filter', name: 'Filter Cutoff', value: 0.5, minValue: 20, maxValue: 20000, defaultValue: 5000, type: 'continuous', unit: 'Hz' },
          { id: 'lfo', name: 'LFO Rate', value: 0.5, minValue: 0.1, maxValue: 20, defaultValue: 2, type: 'continuous', unit: 'Hz' }
        ],
        presetCount: 500,
        hasUI: true,
        uiWidth: 900,
        uiHeight: 600
      }
    ];

    // 模拟延迟
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    setPlugins(mockPlugins);
    setIsScanning(false);
    console.log(`[VSTManager] 扫描完成，找到 ${mockPlugins.length} 个插件`);
  };

  // 加载插件实例
  const loadPluginInstance = (pluginId: string) => {
    const instance = host.createInstance(pluginId);
    if (instance) {
      setLoadedPlugins(prev => [...prev, instance]);
      onPluginLoad?.(instance);
      setSelectedInstance(instance);
      console.log(`[VSTManager] 加载实例：${instance.instanceId}`);
    }
  };

  // 设置参数
  const setParameter = (instanceId: string, paramId: string, value: number) => {
    host.setParameter(instanceId, paramId, value);
    
    // 更新本地状态
    setLoadedPlugins(prev =>
      prev.map(p =>
        p.instanceId === instanceId
          ? { ...p, parameters: { ...p.parameters, [paramId]: value } }
          : p
      )
    );
  };

  // 加载预设
  const loadPreset = (instanceId: string, presetIndex: number) => {
    const success = host.loadPreset(instanceId, presetIndex);
    if (success) {
      console.log('[VSTManager] 预设已加载');
    }
  };

  // 保存预设
  const savePreset = async () => {
    if (!selectedInstance) return;
    
    const name = prompt('预设名称:');
    if (!name) return;

    const preset = host.saveUserPreset(selectedInstance.instanceId, name);
    if (preset) {
      console.log(`[VSTManager] 预设已保存：${preset.name}`);
      alert(`预设 "${preset.name}" 已保存!`);
    }
  };

  // 移除插件
  const removePlugin = (instanceId: string) => {
    host.disconnect(instanceId);
    setLoadedPlugins(prev => prev.filter(p => p.instanceId !== instanceId));
    if (selectedInstance?.instanceId === instanceId) {
      setSelectedInstance(null);
    }
  };

  return (
    <div className="bg-gray-900 rounded-lg p-4 h-full flex flex-col">
      {/* 头部 */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-white font-bold text-lg">VST 插件管理器</h3>
        <button
          onClick={scanPlugins}
          disabled={isScanning}
          className="px-3 py-1.5 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-600 text-white text-sm rounded transition"
        >
          {isScanning ? '扫描中...' : '扫描插件'}
        </button>
      </div>

      <div className="flex-1 grid grid-cols-2 gap-4 overflow-hidden">
        {/* 左侧：可用插件列表 */}
        <div className="bg-gray-800 rounded p-3 overflow-y-auto">
          <h4 className="text-gray-300 text-sm font-semibold mb-2">可用插件 ({plugins.length})</h4>
          
          {plugins.map(plugin => (
            <div
              key={plugin.id}
              onClick={() => {
                setSelectedPlugin(plugin);
                loadPluginInstance(plugin.id);
              }}
              className={`p-2 mb-2 rounded cursor-pointer transition ${
                selectedPlugin?.id === plugin.id
                  ? 'bg-orange-500'
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            >
              <div className="text-white text-sm font-medium">{plugin.name}</div>
              <div className="text-gray-400 text-xs">{plugin.vendor} · {plugin.category}</div>
            </div>
          ))}

          {plugins.length === 0 && !isScanning && (
            <div className="text-gray-500 text-sm text-center py-8">
              点击"扫描插件"加载可用的 VST 插件
            </div>
          )}
        </div>

        {/* 右侧：已加载插件 */}
        <div className="bg-gray-800 rounded p-3 overflow-y-auto">
          <h4 className="text-gray-300 text-sm font-semibold mb-2">
            已加载插件 ({loadedPlugins.length}/{maxInserts})
          </h4>
          
          {loadedPlugins.map(plugin => (
            <div
              key={plugin.instanceId}
              onClick={() => {
                setSelectedInstance(plugin);
                setShowPluginUI(false);
              }}
              className={`p-2 mb-2 rounded cursor-pointer transition ${
                selectedInstance?.instanceId === plugin.instanceId
                  ? 'bg-orange-500'
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-white text-sm font-medium">{plugin.name}</div>
                  <div className="text-gray-400 text-xs">Slot {loadedPlugins.indexOf(plugin) + 1}</div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    loadPreset(plugin.instanceId, 0);
                                    setShowPluginUI(true);
                                    setSelectedInstance(plugin);
                                  }}
                    className="px-2 py-1 bg-gray-600 hover:bg-gray-500 text-white text-xs rounded"
                  >
                    UI
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      removePlugin(plugin.instanceId);
                    }}
                    className="px-2 py-1 bg-red-600 hover:bg-red-500 text-white text-xs rounded"
                  >
                    ✕
                  </button>
                </div>
              </div>
            </div>
          ))}

          {loadedPlugins.length === 0 && (
            <div className="text-gray-500 text-sm text-center py-8">
              点击左侧插件添加到轨道
            </div>
          )}
        </div>
      </div>

      {/* 底部：参数面板 */}
      {selectedInstance && (
        <div className="mt-4 bg-gray-800 rounded p-3">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-white font-semibold">
              {selectedInstance.name} - 参数
            </h4>
            <div className="flex gap-2">
              <button
                onClick={savePreset}
                className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded"
              >
                保存预设
              </button>
              <button
                onClick={() => setShowPluginUI(true)}
                className="px-3 py-1 bg-purple-600 hover:bg-purple-500 text-white text-xs rounded"
              >
                打开界面
              </button>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 max-h-32 overflow-y-auto">
            {Object.entries((selectedInstance as any).parameters).slice(0, 6).map(([paramId, value]) => (
              <div key={paramId} className="bg-gray-700 rounded p-2">
                <label className="text-gray-300 text-xs block mb-1">
                  {paramId.toUpperCase()}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={value}
                  onChange={(e) =>
                    setParameter(selectedInstance.instanceId, paramId, parseFloat(e.target.value))
                  }
                  className="w-full"
                />
                <div className="text-gray-400 text-xs text-right">
                  {(value * 100).toFixed(0)}%
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 插件 UI 模态框 */}
      {showPluginUI && selectedInstance && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-4 max-w-4xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-white font-bold text-xl">{selectedInstance.name}</h3>
              <button
                onClick={() => setShowPluginUI(false)}
                className="text-gray-400 hover:text-white text-2xl"
              >
                ✕
              </button>
            </div>
            
            <div className="bg-gray-900 rounded p-4 aspect-video flex items-center justify-center">
              <div className="text-gray-500 text-center">
                <div className="text-4xl mb-4">🎛️</div>
                <div className="text-lg">插件界面</div>
                <div className="text-sm mt-2">
                  实际部署时会渲染插件的 WebAssembly UI
                </div>
                <div className="text-xs mt-4 text-gray-600">
                  尺寸：{(selectedInstance as any).id === 'vst-synth-1' ? '900x600' : '800x500'}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}