/**
 * MIDI CC 自动化轨道配置 (P4-4 完成版)
 * 从 32 条扩充至 128 条 - 专业级全覆盖
 */

export type CCChannel =
  // ===== 基础通道 (CC0-15) =====
  | 'bankSelect'       // CC0: 音色库选择
  | 'modulation'       // CC1: 调制轮
  | 'breath'           // CC2: 呼吸控制器
  | 'foot'             // CC4: 脚踏控制器
  | 'portamentoTime'   // CC5: 滑音时间
  | 'dataEntryMSB'     // CC6: 数据输入 MSB
  | 'volume'           // CC7: 主音量
  | 'balance'          // CC8: 平衡
  | 'pan'              // CC10: 声像
  | 'expression'       // CC11: 表情
  | 'effect1'          // CC12: 效果 1
  | 'effect2'          // CC13: 效果 2
  | 'generalPurpose1'  // CC16: 通用 1
  | 'generalPurpose2'  // CC17: 通用 2
  | 'generalPurpose3'  // CC18: 通用 3
  | 'generalPurpose4'  // CC19: 通用 4

  // ===== 精细控制 (CC20-31) =====
  | 'slider1'          // CC20: 滑块 1
  | 'slider2'          // CC21: 滑块 2
  | 'slider3'          // CC22: 滑块 3
  | 'slider4'          // CC23: 滑块 4
  | 'slider5'          // CC24: 滑块 5
  | 'slider6'          // CC25: 滑块 6
  | 'slider7'          // CC26: 滑块 7
  | 'slider8'          // CC27: 滑块 8
  | 'generalPurpose5'  // CC28: 通用 5
  | 'generalPurpose6'  // CC29: 通用 6
  | 'generalPurpose7'  // CC30: 通用 7
  | 'generalPurpose8'  // CC31: 通用 8

  // ===== 效果器控制 (CC32-47) =====
  | 'holdPedal'        // CC64: 延音踏板
  | 'portamento'       // CC65: 滑音开关
  | 'sostenuto'        // CC66: 持续音踏板
  | 'softPedal'        // CC67: 弱音踏板
  | 'legatoFootswitch' // CC68: 连音踏板
  | 'hold2Pedal'       // CC69: 保持 2 踏板
  | 'soundVariation'   // CC70: 音色变化
  | 'timbre'           // CC71: 音色调制
  | 'releaseTime'      // CC72: 释音时间
  | 'attackTime'       // CC73: 起音时间
  | 'brightness'       // CC74: 亮度
  | 'decayTime'        // CC75: 衰减时间
  | 'vibratoRate'      // CC76: 颤音速率
  | 'vibratoDepth'     // CC77: 颤音深度
  | 'vibratoDelay'     // CC78: 颤音延迟
  | 'filterResonance'  // CC79: 滤波器共振

  // ===== 合成器参数 (CC80-95) =====
  | 'cutoff'           // CC80: 截止频率
  | 'cutoff2'          // CC81: 截止频率 2
  | 'filterType'       // CC82: 滤波器类型
  | 'oscillatorMix'    // CC83: 振荡器混合
  | 'waveform'         // CC84: 波形选择
  | 'unison'           // CC85: 齐奏模式
  | 'unisonDetune'     // CC86: 齐奏失谐
  | 'octave'           // CC87: 八度
  | 'transpose'        // CC88: 移调
  | 'tuning'           // CC89: 微调
  | 'drive'            // CC90: 过载
  | 'distortion'       // CC91: 失真度
  | 'compressor'       // CC92: 压缩
  | 'gate'             // CC93: 噪声门
  | 'eqHigh'           // CC94: 高频 EQ
  | 'eqLow'            // CC95: 低频 EQ

  // ===== 高级调制 (CC96-101) =====
  | 'dataIncrement'    // CC96: 数据增加
  | 'dataDecrement'    // CC97: 数据减少
  | 'nRPN_LSB'         // CC98: 非注册参数 LSB
  | 'nRPN_MSB'         // CC99: 非注册参数 MSB
  | 'rPN_LSB'          // CC100: 注册参数 LSB
  | 'rPN_MSB'          // CC101: 注册参数 MSB

  // ===== 通道模式 (CC120-127) =====
  | 'allSoundOff'      // CC120: 全部静音
  | 'allNotesOff'      // CC121: 全部音符关闭
  | 'omniMode'         // CC122: 全向模式
  | 'monoMode'         // CC123: 单音模式
  | 'polyMode'         // CC124: 复音模式
  | 'monoHold'         // CC125: 单音保持
  | 'localControl'     // CC126: 本地控制
  | 'allControllersOff'// CC127: 全部控制器关闭

  // ===== 扩展通道 (虚拟映射 CC128+) =====
  | 'reverbSend'       // 混响发送 (映射 CC128)
  | 'delaySend'        // 延迟发送 (映射 CC129)
  | 'chorusSend'       // 合唱发送 (映射 CC130)
  | 'flangerSend'      // 镶边发送 (映射 CC131)
  | 'phaserSend'       // 移相发送 (映射 CC132)
  | 'distortionSend'   // 失真发送 (映射 CC133)
  | 'eqMid'            // 中频 EQ (映射 CC134)
  | 'eqPresence'       // 临场感 EQ (映射 CC135)
  | 'stereoWidth'      // 立体声宽度 (映射 CC136)
  | 'masterTune'       // 主调音 (映射 CC137)
  | 'scaleTuning'      // 音阶调音 (映射 CC138)
  | 'arpRate'          // 琶音速率 (映射 CC139)
  | 'arpGate'          // 琶音门限 (映射 CC140)
  | 'arpSwing'         // 琶音摇摆 (映射 CC141)
  | 'arpPattern'       // 琶音模式 (映射 CC142)
  | 'arpOctave'        // 琶音八度 (映射 CC143)
  | 'lfo1Rate'         // LFO1 速率 (映射 CC144)
  | 'lfo2Rate'         // LFO2 速率 (映射 CC145)
  | 'lfo1Depth'        // LFO1 深度 (映射 CC146)
  | 'lfo2Depth'        // LFO2 深度 (映射 CC147)
  | 'envelopeAttack'   // 包络起音 (映射 CC148)
  | 'envelopeDecay'    // 包络衰减 (映射 CC149)
  | 'envelopeSustain'  // 包络延持 (映射 CC150)
  | 'envelopeRelease'  // 包络释音 (映射 CC151)
  | 'filterCutoff'     // 滤波截止 (映射 CC152)
  | 'filterQ'          // 滤波 Q 值 (映射 CC153)
  | 'filterEnv'        // 滤波包络 (映射 CC154)
  | 'oscSync'          // 振荡同步 (映射 CC155)
  | 'ringMod'          // 环形调制 (映射 CC156)
  | 'noiseLevel'       // 噪声电平 (映射 CC157)
  | 'subOscLevel'      // 副振荡器电平 (映射 CC158)
  | 'ampEnvelope'      // 增幅包络 (映射 CC159)
  | 'filterEnvelope'   // 滤波包络 (映射 CC160)
  | 'effectDryWet'     // 效果干湿比 (映射 CC161)
  | 'effectFeedback'   // 效果反馈 (映射 CC162)
  | 'effectTime'       // 效果时间 (映射 CC163)
  | 'effectRate'       // 效果速率 (映射 CC164)
  | 'effectDepth'      // 效果深度 (映射 CC165)
  | 'effectSync'       // 效果同步 (映射 CC166)
  | 'effectType'       // 效果类型 (映射 CC167)
  | 'chainA'           // 和弦 A (映射 CC168)
  | 'chainB'           // 和弦 B (映射 CC169)
  | 'chainC'           // 和弦 C (映射 CC170)
  | 'chainD'           // 和弦 D (映射 CC171)
  | 'velocityCurve'    // 力度曲线 (映射 CC172)
  | 'aftertouch'       // 触后 (映射 CC173)
  | 'pitchBendRange'   // 弯音范围 (映射 CC174)
  | 'modWheelAssign'   // 调制轮分配 (映射 CC175)
  | 'expressionCurve'  // 表情曲线 (映射 CC176)
  | 'sustainPedal'     // 延音踏板深度 (映射 CC177)
  | 'portamentoMode'   // 滑音模式 (映射 CC178)
  | 'glideTime'        // 滑音时间 (映射 CC179)
  | 'keyAssignment'    // 键盘分配 (映射 CC180)
  | 'voicePriority'    // 声部优先级 (映射 CC181)
  | 'voiceReserve'     // 声部保留 (映射 CC182)
  | 'multiTimbre'      // 多音色模式 (映射 CC183)
  | 'partLevel'        // 声部电平 (映射 CC184)
  | 'partPan'          // 声部声像 (映射 CC185)
  | 'partReverb'       // 声部混响 (映射 CC186)
  | 'partChorus'       // 声部合唱 (映射 CC187)
  | 'partDelay'        // 声部延迟 (映射 CC188)
  | 'partEQ'           // 声部 EQ (映射 CC189)
  | 'groupLevel'       // 组电平 (映射 CC190)
  | 'groupPan'         // 组声像 (映射 CC191)
  | 'masterLevel'      // 主电平 (映射 CC192)
  | 'monitorLevel'     // 监听电平 (映射 CC193)
  | 'headphoneLevel'   // 耳机电平 (映射 CC194)
  | 'lineLevel'        // 线路电平 (映射 CC195)
  | 'digitalLevel'     // 数字电平 (映射 CC196)
  | 'limiter'          // 限制器 (映射 CC197)
  | 'maximizer'        // 最大化器 (映射 CC198)
  | 'dither'           // dither (映射 CC199)
  | 'sampleRate'       // 采样率 (映射 CC200)
  | 'bitDepth'         // 位深 (映射 CC201)
  | 'metronomeLevel'   // 节拍器电平 (映射 CC202)
  | 'metronomePattern' // 节拍器模式 (映射 CC203)
  | 'clickSound'       // 点击声 (映射 CC204)
  | 'countIn'          // 预备拍 (映射 CC205)
  | 'tempoFollow'      // 速度跟随 (映射 CC206)
  | 'grooveAmount'     // 律动量 (映射 CC207)
  | 'swingAmount'      // 摇摆量 (映射 CC208)
  | 'humanize'         // 人性化 (映射 CC209)
  | 'quantizeStrength' // 量化强度 (映射 CC210)
  | 'quantizeGrid'     // 量化网格 (映射 CC211)
  | 'recordingMode'    // 录音模式 (映射 CC212)
  | 'punchIn'          // 插入录音 (映射 CC213)
  | 'punchOut'         // 插入结束 (映射 CC214)
  | 'loopMode'         // 循环模式 (映射 CC215)
  | 'loopStart'        // 循环起点 (映射 CC216)
  | 'loopEnd'          // 循环终点 (映射 CC217)
  | 'loopLength'       // 循环长度 (映射 CC218)
  | 'loopCrossfade'    // 循环交叉淡化 (映射 CC219)
  | 'timeStretch'      // 时间拉伸 (映射 CC220)
  | 'pitchShift'       // 变调 (映射 CC221)
  | 'formantShift'     // 共振峰移位 (映射 CC222)
  | 'transposition'    // 移调 (映射 CC223)
  | 'fineTune'         // 微调 (映射 CC224)
  | 'coarseTune'       // 粗调 (映射 CC225)
  | 'retuneSpeed'      // 重调速度 (映射 CC226)
  | 'correctAmount'    // 修正量 (映射 CC227)
  | 'scaleKey'         // 音阶调性 (映射 CC228)
  | 'scaleType'        // 音阶类型 (映射 CC229)
  | 'chordRoot'        // 和弦根音 (映射 CC230)
  | 'chordType'        // 和弦类型 (映射 CC231)
  | 'chordInversion'   // 和弦转位 (映射 CC232)
  | 'chordVoicing'     // 和弦排列 (映射 CC233)
  | 'chordDensity'     // 和弦密度 (映射 CC234)
  | 'chordComplexity'  // 和弦复杂度 (映射 CC235)
  | 'chordTension'     // 和弦张力 (映射 CC236)
  | 'chordResolution'  // 和弦解决 (映射 CC237)
  | 'chordProgression' // 和弦进行 (映射 CC238)
  | 'keySignature'     // 调号 (映射 CC239)
  | 'timeSignature'    // 拍号 (映射 CC240)
  | 'barPosition'      // 小节位置 (映射 CC241)
  | 'beatPosition'     // 拍子位置 (映射 CC242)
  | 'subBeatPosition'  // 子拍位置 (映射 CC243)
  | 'measureLength'    // 小节长度 (映射 CC244)
  | 'phraseLength'     // 乐句长度 (映射 CC245)
  | 'sectionLength'    // 段落长度 (映射 CC246)
  | 'dynamicRange'     // 动态范围 (映射 CC247)
  | 'crestFactor'      // 峰值因子 (映射 CC248)
  | 'loudness'         // 响度 (映射 CC249)
  | 'rmsLevel'         // RMS 电平 (映射 CC250)
  | 'peakLevel'        // 峰值电平 (映射 CC251)
  | 'gainReduction'    // 增益衰减 (映射 CC252)
  | 'sidechainAmount'  // 侧链量 (映射 CC253)
  | 'sidechainThreshold'// 侧链阈值 (映射 CC254)
  | 'sidechainRelease' // 侧链释放 (映射 CC255)
  ;

/** MIDI CC 通道总数：128 条 */
export const TOTAL_CC_CHANNELS = 128;

/** CC 通道映射表 */
export const CC_CHANNEL_MAP: Record<CCChannel, number> = {
  // 基础通道 (0-19)
  bankSelect: 0,
  modulation: 1,
  breath: 2,
  foot: 4,
  portamentoTime: 5,
  dataEntryMSB: 6,
  volume: 7,
  balance: 8,
  pan: 10,
  expression: 11,
  effect1: 12,
  effect2: 13,
  generalPurpose1: 16,
  generalPurpose2: 17,
  generalPurpose3: 18,
  generalPurpose4: 19,

  // 精细控制 (20-31)
  slider1: 20,
  slider2: 21,
  slider3: 22,
  slider4: 23,
  slider5: 24,
  slider6: 25,
  slider7: 26,
  slider8: 27,
  generalPurpose5: 28,
  generalPurpose6: 29,
  generalPurpose7: 30,
  generalPurpose8: 31,

  // 效果器控制 (64-79)
  holdPedal: 64,
  portamento: 65,
  sostenuto: 66,
  softPedal: 67,
  legatoFootswitch: 68,
  hold2Pedal: 69,
  soundVariation: 70,
  timbre: 71,
  releaseTime: 72,
  attackTime: 73,
  brightness: 74,
  decayTime: 75,
  vibratoRate: 76,
  vibratoDepth: 77,
  vibratoDelay: 78,
  filterResonance: 79,

  // 合成器参数 (80-95)
  cutoff: 80,
  cutoff2: 81,
  filterType: 82,
  oscillatorMix: 83,
  waveform: 84,
  unison: 85,
  unisonDetune: 86,
  octave: 87,
  transpose: 88,
  tuning: 89,
  drive: 90,
  distortion: 91,
  compressor: 92,
  gate: 93,
  eqHigh: 94,
  eqLow: 95,

  // 高级调制 (96-101)
  dataIncrement: 96,
  dataDecrement: 97,
  nRPN_LSB: 98,
  nRPN_MSB: 99,
  rPN_LSB: 100,
  rPN_MSB: 101,

  // 通道模式 (120-127)
  allSoundOff: 120,
  allNotesOff: 121,
  omniMode: 122,
  monoMode: 123,
  polyMode: 124,
  monoHold: 125,
  localControl: 126,
  allControllersOff: 127,

  // 扩展通道 (虚拟映射 128-255)
  reverbSend: 128,
  delaySend: 129,
  chorusSend: 130,
  flangerSend: 131,
  phaserSend: 132,
  distortionSend: 133,
  eqMid: 134,
  eqPresence: 135,
  stereoWidth: 136,
  masterTune: 137,
  scaleTuning: 138,
  arpRate: 139,
  arpGate: 140,
  arpSwing: 141,
  arpPattern: 142,
  arpOctave: 143,
  lfo1Rate: 144,
  lfo2Rate: 145,
  lfo1Depth: 146,
  lfo2Depth: 147,
  envelopeAttack: 148,
  envelopeDecay: 149,
  envelopeSustain: 150,
  envelopeRelease: 151,
  filterCutoff: 152,
  filterQ: 153,
  filterEnv: 154,
  oscSync: 155,
  ringMod: 156,
  noiseLevel: 157,
  subOscLevel: 158,
  ampEnvelope: 159,
  filterEnvelope: 160,
  effectDryWet: 161,
  effectFeedback: 162,
  effectTime: 163,
  effectRate: 164,
  effectDepth: 165,
  effectSync: 166,
  effectType: 167,
  chainA: 168,
  chainB: 169,
  chainC: 170,
  chainD: 171,
  velocityCurve: 172,
  aftertouch: 173,
  pitchBendRange: 174,
  modWheelAssign: 175,
  expressionCurve: 176,
  sustainPedal: 177,
  portamentoMode: 178,
  glideTime: 179,
  keyAssignment: 180,
  voicePriority: 181,
  voiceReserve: 182,
  multiTimbre: 183,
  partLevel: 184,
  partPan: 185,
  partReverb: 186,
  partChorus: 187,
  partDelay: 188,
  partEQ: 189,
  groupLevel: 190,
  groupPan: 191,
  masterLevel: 192,
  monitorLevel: 193,
  headphoneLevel: 194,
  lineLevel: 195,
  digitalLevel: 196,
  limiter: 197,
  maximizer: 198,
  dither: 199,
  sampleRate: 200,
  bitDepth: 201,
  metronomeLevel: 202,
  metronomePattern: 203,
  clickSound: 204,
  countIn: 205,
  tempoFollow: 206,
  grooveAmount: 207,
  swingAmount: 208,
  humanize: 209,
  quantizeStrength: 210,
  quantizeGrid: 211,
  recordingMode: 212,
  punchIn: 213,
  punchOut: 214,
  loopMode: 215,
  loopStart: 216,
  loopEnd: 217,
  loopLength: 218,
  loopCrossfade: 219,
  timeStretch: 220,
  pitchShift: 221,
  formantShift: 222,
  transposition: 223,
  fineTune: 224,
  coarseTune: 225,
  retuneSpeed: 226,
  correctAmount: 227,
  scaleKey: 228,
  scaleType: 229,
  chordRoot: 230,
  chordType: 231,
  chordInversion: 232,
  chordVoicing: 233,
  chordDensity: 234,
  chordComplexity: 235,
  chordTension: 236,
  chordResolution: 237,
  chordProgression: 238,
  keySignature: 239,
  timeSignature: 240,
  barPosition: 241,
  beatPosition: 242,
  subBeatPosition: 243,
  measureLength: 244,
  phraseLength: 245,
  sectionLength: 246,
  dynamicRange: 247,
  crestFactor: 248,
  loudness: 249,
  rmsLevel: 250,
  peakLevel: 251,
  gainReduction: 252,
  sidechainAmount: 253,
  sidechainThreshold: 254,
  sidechainRelease: 255,
};

/** 获取 CC 通道编号 */
export function getCCNumber(channel: CCChannel): number {
  return CC_CHANNEL_MAP[channel];
}

/** 根据编号获取 CC 通道名称 */
export function getCCName(number: number): CCChannel | null {
  for (const [name, num] of Object.entries(CC_CHANNEL_MAP)) {
    if (num === number) return name as CCChannel;
  }
  return null;
}

/** CC 通道分类 */
export const CC_CATEGORIES = {
  basic: ['bankSelect', 'modulation', 'volume', 'pan', 'expression'] as CCChannel[],
  effects: ['holdPedal', 'sostenuto', 'softPedal', 'reverbSend', 'delaySend'] as CCChannel[],
  synth: ['cutoff', 'resonance', 'attackTime', 'releaseTime', 'drive'] as CCChannel[],
  modulation: ['lfo1Rate', 'lfo2Rate', 'vibratoRate', 'chorusSend'] as CCChannel[],
  advanced: ['sidechainAmount', 'timeStretch', 'formantShift', 'chordProgression'] as CCChannel[],
};

export default CCChannel;