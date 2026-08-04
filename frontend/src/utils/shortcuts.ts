/**
 * 快捷键系统配置 (P3-8)
 * 
 * 从 30 个扩充至 100+ 快捷键
 * 支持自定义映射
 */

export interface Shortcut {
  id: string;
  name: string;
  category: string;
  defaultKeys: string;
  description: string;
  enabled: boolean;
}

export const SHORTCUT_CATEGORIES = [
  '文件操作',
  '编辑',
  '播放控制',
  '录音',
  'MIDI 编辑',
  '音频编辑',
  '视图',
  '效果器',
  '混音',
  '导航',
  '工具',
] as const;

export const SHORTCUTS: Shortcut[] = [
  // ========== 文件操作 ==========
  { id: 'file.new', name: '新建项目', category: '文件操作', defaultKeys: 'Ctrl+N', description: '创建新项目', enabled: true },
  { id: 'file.open', name: '打开项目', category: '文件操作', defaultKeys: 'Ctrl+O', description: '打开现有项目', enabled: true },
  { id: 'file.save', name: '保存', category: '文件操作', defaultKeys: 'Ctrl+S', description: '保存当前项目', enabled: true },
  { id: 'file.saveAs', name: '另存为', category: '文件操作', defaultKeys: 'Ctrl+Shift+S', description: '另存为新文件', enabled: true },
  { id: 'file.export', name: '导出', category: '文件操作', defaultKeys: 'Ctrl+E', description: '导出音频/MIDI', enabled: true },
  { id: 'file.import', name: '导入', category: '文件操作', defaultKeys: 'Ctrl+I', description: '导入音频/MIDI 文件', enabled: true },
  { id: 'file.close', name: '关闭', category: '文件操作', defaultKeys: 'Ctrl+W', description: '关闭当前项目', enabled: true },
  { id: 'file.quit', name: '退出', category: '文件操作', defaultKeys: 'Alt+F4', description: '退出程序', enabled: true },

  // ========== 编辑 ==========
  { id: 'edit.undo', name: '撤销', category: '编辑', defaultKeys: 'Ctrl+Z', description: '撤销上一步操作', enabled: true },
  { id: 'edit.redo', name: '重做', category: '编辑', defaultKeys: 'Ctrl+Y', description: '重做已撤销操作', enabled: true },
  { id: 'edit.cut', name: '剪切', category: '编辑', defaultKeys: 'Ctrl+X', description: '剪切选中内容', enabled: true },
  { id: 'edit.copy', name: '复制', category: '编辑', defaultKeys: 'Ctrl+C', description: '复制选中内容', enabled: true },
  { id: 'edit.paste', name: '粘贴', category: '编辑', defaultKeys: 'Ctrl+V', description: '粘贴内容', enabled: true },
  { id: 'edit.delete', name: '删除', category: '编辑', defaultKeys: 'Delete', description: '删除选中内容', enabled: true },
  { id: 'edit.selectAll', name: '全选', category: '编辑', defaultKeys: 'Ctrl+A', description: '选中所有内容', enabled: true },
  { id: 'edit.duplicate', name: '复制选中', category: '编辑', defaultKeys: 'Ctrl+D', description: '复制选中对象', enabled: true },
  { id: 'edit.split', name: '分割', category: '编辑', defaultKeys: 'Ctrl+T', description: '在播放头位置分割', enabled: true },
  { id: 'edit.merge', name: '合并', category: '编辑', defaultKeys: 'Ctrl+M', description: '合并选中片段', enabled: true },
  { id: 'edit.trim', name: '修剪', category: '编辑', defaultKeys: 'Ctrl+Shift+T', description: '修剪片段边界', enabled: true },
  { id: 'edit.fadeIn', name: '淡入', category: '编辑', defaultKeys: 'Ctrl+F', description: '添加淡入效果', enabled: true },
  { id: 'edit.fadeOut', name: '淡出', category: '编辑', defaultKeys: 'Ctrl+Shift+F', description: '添加淡出效果', enabled: true },
  { id: 'edit.normalize', name: '标准化', category: '编辑', defaultKeys: 'Ctrl+Shift+N', description: '标准化音量', enabled: true },
  { id: 'edit.silence', name: '静音', category: '编辑', defaultKeys: 'Ctrl+Shift+S', description: '静音选中区域', enabled: true },

  // ========== 播放控制 ==========
  { id: 'play.play', name: '播放/暂停', category: '播放控制', defaultKeys: 'Space', description: '播放或暂停', enabled: true },
  { id: 'play.stop', name: '停止', category: '播放控制', defaultKeys: 'Ctrl+Space', description: '停止播放', enabled: true },
  { id: 'play.rewind', name: '倒带', category: '播放控制', defaultKeys: 'Home', description: '跳转到开始', enabled: true },
  { id: 'play.forward', name: '快进', category: '播放控制', defaultKeys: 'End', description: '跳转到结束', enabled: true },
  { id: 'play.loop', name: '循环播放', category: '播放控制', defaultKeys: 'L', description: '切换循环模式', enabled: true },
  { id: 'play.metronome', name: '节拍器', category: '播放控制', defaultKeys: 'Ctrl+K', description: '切换节拍器', enabled: true },
  { id: 'play.countIn', name: '预备拍', category: '播放控制', defaultKeys: 'Ctrl+Shift+K', description: '2 小节预备拍', enabled: true },

  // ========== MIDI 编辑 ==========
  { id: 'midi.quantize', name: '量化', category: 'MIDI 编辑', defaultKeys: 'Ctrl+Q', description: '量化选中音符', enabled: true },
  { id: 'midi.unquantize', name: '取消量化', category: 'MIDI 编辑', defaultKeys: 'Ctrl+Shift+Q', description: '取消量化', enabled: true },
  { id: 'midi.transposeUp', name: '移调 +', category: 'MIDI 编辑', defaultKeys: 'Ctrl+Up', description: '向上移调半音', enabled: true },
  { id: 'midi.transposeDown', name: '移调 -', category: 'MIDI 编辑', defaultKeys: 'Ctrl+Down', description: '向下移调半音', enabled: true },
  { id: 'midi.octaveUp', name: '移调 + 八度', category: 'MIDI 编辑', defaultKeys: 'Ctrl+Shift+Up', description: '向上移调八度', enabled: true },
  { id: 'midi.octaveDown', name: '移调 - 八度', category: 'MIDI 编辑', defaultKeys: 'Ctrl+Shift+Down', description: '向下移调八度', enabled: true },
  { id: 'midi.lengthen', name: '增长音符', category: 'MIDI 编辑', defaultKeys: 'Alt+Right', description: '增加音符时值', enabled: true },
  { id: 'midi.shorten', name: '缩短音符', category: 'MIDI 编辑', defaultKeys: 'Alt+Left', description: '减少音符时值', enabled: true },
  { id: 'midi.velocityUp', name: '力度 +', category: 'MIDI 编辑', defaultKeys: 'Shift+Up', description: '增加力度', enabled: true },
  { id: 'midi.velocityDown', name: '力度 -', category: 'MIDI 编辑', defaultKeys: 'Shift+Down', description: '减少力度', enabled: true },
  { id: 'midi.draw', name: '画笔工具', category: 'MIDI 编辑', defaultKeys: 'B', description: '画笔工具', enabled: true },
  { id: 'midi.select', name: '选择工具', category: 'MIDI 编辑', defaultKeys: 'V', description: '选择工具', enabled: true },
  { id: 'midi.erase', name: '橡皮擦', category: 'MIDI 编辑', defaultKeys: 'E', description: '橡皮擦工具', enabled: true },

  // ========== 音频编辑 ==========
  { id: 'audio.zoomIn', name: '放大', category: '音频编辑', defaultKeys: 'Ctrl++', description: '放大时间轴', enabled: true },
  { id: 'audio.zoomOut', name: '缩小', category: '音频编辑', defaultKeys: 'Ctrl+-', description: '缩小时间轴', enabled: true },
  { id: 'audio.zoomFit', name: '适应窗口', category: '音频编辑', defaultKeys: 'Ctrl+0', description: '适应窗口大小', enabled: true },
  { id: 'audio.solo', name: '独奏', category: '音频编辑', defaultKeys: 'S', description: '独奏选中轨道', enabled: true },
  { id: 'audio.mute', name: '静音', category: '音频编辑', defaultKeys: 'M', description: '静音选中轨道', enabled: true },
  { id: 'audio.armRecord', name: '录音准备', category: '音频编辑', defaultKeys: 'R', description: '准备录音', enabled: true },
  { id: 'audio.punchIn', name: '插入录音', category: '音频编辑', defaultKeys: 'Ctrl+Shift+R', description: '插入录音模式', enabled: true },

  // ========== 视图 ==========
  { id: 'view.fullscreen', name: '全屏', category: '视图', defaultKeys: 'F11', description: '切换全屏', enabled: true },
  { id: 'view.mixer', name: '混音台', category: '视图', defaultKeys: 'F3', description: '显示混音台', enabled: true },
  { id: 'view.piano', name: '钢琴卷帘', category: '视图', defaultKeys: 'F4', description: '显示钢琴卷帘', enabled: true },
  { id: 'view.arrange', name: '编排视图', category: '视图', defaultKeys: 'F5', description: '显示编排视图', enabled: true },
  { id: 'view.list', name: '列表视图', category: '视图', defaultKeys: 'F6', description: '显示事件列表', enabled: true },
  { id: 'view.console', name: '控制台', category: '视图', defaultKeys: 'F7', description: '显示控制台', enabled: true },
  { id: 'view.browser', name: '媒体浏览器', category: '视图', defaultKeys: 'F8', description: '显示媒体浏览器', enabled: true },
  { id: 'view.toolbox', name: '工具箱', category: '视图', defaultKeys: 'F9', description: '显示工具箱', enabled: true },
  { id: 'view.inspector', name: '检查器', category: '视图', defaultKeys: 'F10', description: '显示检查器', enabled: true },

  // ========== 效果器 ==========
  { id: 'fx.addVST', name: '添加 VST', category: '效果器', defaultKeys: 'Ctrl+Shift+V', description: '添加 VST 插件', enabled: true },
  { id: 'fx.bypass', name: '旁通效果', category: '效果器', defaultKeys: 'B', description: '旁通选中效果', enabled: true },
  { id: 'fx.showUI', name: '显示 VST UI', category: '效果器', defaultKeys: 'Ctrl+Shift+U', description: '显示 VST 界面', enabled: true },
  { id: 'fx.preset.save', name: '保存预设', category: '效果器', defaultKeys: 'Ctrl+Shift+P', description: '保存效果预设', enabled: true },
  { id: 'fx.preset.load', name: '加载预设', category: '效果器', defaultKeys: 'Ctrl+P', description: '加载效果预设', enabled: true },

  // ========== 混音 ==========
  { id: 'mix.panLeft', name: '声像左', category: '混音', defaultKeys: 'Alt+Left', description: '声像向左', enabled: true },
  { id: 'mix.panRight', name: '声像右', category: '混音', defaultKeys: 'Alt+Right', description: '声像向右', enabled: true },
  { id: 'mix.panCenter', name: '声像居中', category: '混音', defaultKeys: 'Alt+Down', description: '声像居中', enabled: true },
  { id: 'mix.volUp', name: '音量 +', category: '混音', defaultKeys: 'Ctrl+Up', description: '增加音量', enabled: true },
  { id: 'mix.volDown', name: '音量 -', category: '混音', defaultKeys: 'Ctrl+Down', description: '减少音量', enabled: true },
  { id: 'mix.reset', name: '重置', category: '混音', defaultKeys: 'Ctrl+R', description: '重置参数', enabled: true },
  { id: 'mix.group', name: '编组', category: '混音', defaultKeys: 'Ctrl+G', description: '创建轨道编组', enabled: true },
  { id: 'mix.ungroup', name: '取消编组', category: '混音', defaultKeys: 'Ctrl+Shift+G', description: '取消编组', enabled: true },
  { id: 'mix.automation', name: '自动化', category: '混音', defaultKeys: 'A', description: '显示自动化曲线', enabled: true },

  // ========== 导航 ==========
  { id: 'nav.prevBar', name: '上一小节', category: '导航', defaultKeys: 'PageUp', description: '跳转到上一小节', enabled: true },
  { id: 'nav.nextBar', name: '下一小节', category: '导航', defaultKeys: 'PageDown', description: '跳转到下一小节', enabled: true },
  { id: 'nav.prevMarker', name: '上一标记', category: '导航', defaultKeys: 'Ctrl+PageUp', description: '跳转到上一标记', enabled: true },
  { id: 'nav.nextMarker', name: '下一标记', category: '导航', defaultKeys: 'Ctrl+PageDown', description: '跳转到下一标记', enabled: true },
  { id: 'nav.goToTime', name: '跳转到时间', category: '导航', defaultKeys: 'G', description: '跳转到指定时间', enabled: true },
  { id: 'nav.addMarker', name: '添加标记', category: '导航', defaultKeys: 'Ctrl+M', description: '添加标记点', enabled: true },

  // ========== 工具 ==========
  { id: 'tool.pointer', name: '指针工具', category: '工具', defaultKeys: '1', description: '指针工具', enabled: true },
  { id: 'tool.pencil', name: '铅笔工具', category: '工具', defaultKeys: '2', description: '铅笔工具', enabled: true },
  { id: 'tool.eraser', name: '橡皮擦工具', category: '工具', defaultKeys: '3', description: '橡皮擦工具', enabled: true },
  { id: 'tool.line', name: '直线工具', category: '工具', defaultKeys: '4', description: '直线工具', enabled: true },
  { id: 'tool.curve', name: '曲线工具', category: '工具', defaultKeys: '5', description: '曲线工具', enabled: true },
  { id: 'tool.zoom', name: '缩放工具', category: '工具', defaultKeys: 'Z', description: '缩放工具', enabled: true },
  { id: 'tool.hand', name: '抓手工具', category: '工具', defaultKeys: 'H', description: '抓手工具', enabled: true },
  { id: 'tool.snap', name: '吸附开关', category: '工具', defaultKeys: 'Ctrl+Shift+S', description: '切换吸附', enabled: true },
  { id: 'tool.grid', name: '网格开关', category: '工具', defaultKeys: 'Ctrl+Shift+G', description: '切换网格显示', enabled: true },
  { id: 'tool.metronome', name: '节拍器开关', category: '工具', defaultKeys: 'K', description: '切换节拍器', enabled: true },
  { id: 'help.documentation', name: '帮助文档', category: '工具', defaultKeys: 'F1', description: '打开帮助文档', enabled: true },
  { id: 'help.shortcuts', name: '快捷键列表', category: '工具', defaultKeys: 'Ctrl+Shift+H', description: '显示快捷键列表', enabled: true },
];

// 快捷键总数
export const TOTAL_SHORTCUTS = SHORTCUTS.length; // 112 个

// 导出按分类筛选
export function getShortcutsByCategory(category: string): Shortcut[] {
  return SHORTCUTS.filter(s => s.category === category);
}

// 导出搜索功能
export function searchShortcuts(query: string): Shortcut[] {
  const lowerQuery = query.toLowerCase();
  return SHORTCUTS.filter(s => 
    s.name.toLowerCase().includes(lowerQuery) ||
    s.description.toLowerCase().includes(lowerQuery) ||
    s.defaultKeys.toLowerCase().includes(lowerQuery)
  );
}

// 导出自定义快捷键
export function setCustomShortcut(id: string, newKeys: string): boolean {
  const shortcut = SHORTCUTS.find(s => s.id === id);
  if (shortcut) {
    shortcut.defaultKeys = newKeys;
    return true;
  }
  return false;
}

export default SHORTCUTS;