"""
音频后置处理 - 音质增强

功能:
- EQ 均衡器 (增强低频/高频)
- 动态压缩 (控制动态范围)
- 混响 (增加空间感)
- 响度标准化 (LUFS 标准化)

使用 librosa 和 soundfile 处理
"""

import numpy as np
import librosa
import soundfile as sf
import tempfile
import os
from typing import Optional, Tuple


class AudioPostProcessor:
    """音频后置处理器"""
    
    def __init__(self):
        self.sample_rate = 44100  # 标准 CD 质量
    
    def process(self, 
                input_audio_path: str,
                output_path: Optional[str] = None,
                eq_enhance: bool = True,
                compression: bool = True,
                reverb: bool = False,
                loudness_normalization: bool = True,
                target_loudness: float = -14.0  # Spotify 标准
                ) -> str:
        """
        处理音频文件
        
        Args:
            input_audio_path: 输入音频路径
            output_path: 输出路径 (默认临时文件)
            eq_enhance: 启用 EQ 增强
            compression: 启用压缩
            reverb: 添加混响
            loudness_normalization: 响度标准化
        
        Returns:
            处理后音频文件路径
        """
        # 1. 加载音频
        print(f"[后处理] 加载音频：{input_audio_path}")
        y, sr = librosa.load(input_audio_path, sr=self.sample_rate, mono=False)
        
        # 如果是立体声，分离处理
        if len(y.shape) == 1:
            y = np.expand_dims(y, axis=0)
            is_mono = True
        else:
            is_mono = False
        
        print(f"[后处理] 采样率：{sr}, 声道：{y.shape[0]}, 时长：{y.shape[1]/sr:.2f}s")
        
        # 2. EQ 增强
        if eq_enhance:
            y = self._apply_eq(y, sr)
            print("[后处理] ✅ EQ 增强 applied")
        
        # 3. 动态压缩
        if compression:
            y = self._apply_compression(y)
            print("[后处理] ✅ 压缩 applied")
        
        # 4. 混响
        if reverb:
            y = self._apply_reverb(y, sr)
            print("[后处理] ✅ 混响 applied")
        
        # 5. 响度标准化
        if loudness_normalization:
            y = self._normalize_loudness(y,str(target_loudness))
            print(f"[后处理] ✅ 响度标准化 to {target_loudness} LUFS")
        
        # 6. 保存
        if output_path is None:
            # 创建临时文件
            temp_fd, output_path = tempfile.mkstemp(suffix='_enhanced.wav')
            os.close(temp_fd)
        
        # 转回 int16
        y_int16 = (y * 32767).astype(np.int16)
        
        sf.write(output_path, y_int16.T, sr)
        print(f"[后处理] ✅ 保存：{output_path}")
        
        return output_path
    
    def _apply_eq(self, y: np.ndarray, sr: int) -> np.ndarray:
        """
        EQ 均衡器增强
        
        增强策略:
        - 低频 (+2dB @ 100Hz): 增强 bass/808
        - 中低频 (+1dB @ 400Hz): 增加温暖感
        - 高频 (+2dB @ 10kHz): 增加 air/清晰度
        """
        # 简单的三频段 EQ
        from scipy import signal
        
        # 低频增强 (100Hz, +2dB)
        b_low, a_low = signal.butter(4, 100/(sr/2), btype='low')
        low_freq = signal.filtfilt(b_low, a_low, y.T).T
        y = y + low_freq * 0.26  # +2dB
        
        # 高频增强 (10kHz, +2dB)
        b_high, a_high = signal.butter(4, 10000/(sr/2), btype='high')
        high_freq = signal.filtfilt(b_high, a_high, y.T).T
        y = y + high_freq * 0.26  # +2dB
        
        return y
    
    def _apply_compression(self, y: np.ndarray, 
                           threshold: float = 0.6,
                           ratio: float = 3.0,
                           attack: float = 0.005,
                           release: float = 0.1) -> np.ndarray:
        """
        动态压缩器
        
        控制动态范围，让整体响度更均匀
        """
        # 简单压缩器实现
        y_compressed = np.zeros_like(y)
        
        for i in range(y.shape[0]):  # 每个声道
            for j in range(y.shape[1]):
                sample = abs(y[i, j])
                
                if sample > threshold:
                    # 超过阈值，按比例压缩
                    excess = sample - threshold
                    compressed = threshold + excess / ratio
                    y_compressed[i, j] = np.sign(y[i, j]) * compressed
                else:
                    y_compressed[i, j] = y[i, j]
        
        #  makeup gain (补偿增益)
        make_up_gain = 1.3  # ~+2dB
        y_compressed = y_compressed * make_up_gain
        
        # 限制器 (防止削波)
        y_compressed = np.clip(y_compressed, -0.95, 0.95)
        
        return y_compressed
    
    def _apply_reverb(self, y: np.ndarray, sr: int, 
                      room_size: float = 0.5,
                      damping: float = 0.5,
                      wet_level: float = 0.3) -> np.ndarray:
        """
        混响效果
        
        增加空间感，让声音更自然
        """
        # 简化的混响实现 (实际应使用卷积混响)
        from scipy import signal
        
        # 创建简单的脉冲响应
        impulse_length = int(sr * 2)  # 2 秒
        impulse = np.zeros(impulse_length)
        impulse[0] = 1.0
        
        # 添加随机反射 (模拟房间)
        num_reflections = 20
        for _ in range(num_reflections):
            delay = int(np.random.uniform(0.01, 1.5) * sr)  # 10ms - 1.5s
            if delay < impulse_length:
                impulse[delay] = np.random.uniform(-0.3, 0.3) * (1 - room_size)
        
        # 应用阻尼
        damping_filter = np.exp(-np.linspace(0, damping * 10, impulse_length))
        impulse = impulse * damping_filter
        
        # 卷积混响
        y_reverb = np.zeros_like(y)
        for i in range(y.shape[0]):
            dry = y[i]
            wet = signal.fftconvolve(y[i], impulse, mode='full')[:len(y[i])]
            y_reverb[i] = dry * (1 - wet_level) + wet * wet_level
        
        return y_reverb
    
    def _normalize_loudness(self, y: np.ndarray, target_db: str) -> np.ndarray:
        """
        响度标准化
        
        目标：-14 LUFS (Spotify/YouTube 标准)
        """
        # 计算当前响度 (简化版 - 实际应用 pyawap 或 loudness 库)
        # 这里使用 RMS 近似
        rms = np.sqrt(np.mean(y ** 2))
        current_db = 20 * np.log10(rms + 1e-10)
        
        # 计算需要调整的增益
        target_db_float = float(target_db) if isinstance(target_db, str) else target_db
        delta_db = target_db_float - current_db
        
        # 应用增益
        gain_multiplier = 10 ** (delta_db / 20)
        y_normalized = y * gain_multiplier
        
        # 限制器防止削波
        y_normalized = np.clip(y_normalized, -0.95, 0.95)
        
        return y_normalized


# ========== 快捷函数 ==========

def enhance_audio(input_path: str, output_path: Optional[str] = None) -> str:
    """快捷：对音频文件进行完整后处理"""
    processor = AudioPostProcessor()
    return processor.process(
        input音频_path=input_path,
        输出路径=output_path,
        eq_enhance=True,
        compression=True,
        reverb=False,  # 根据风格决定是否添加
        loudness_normalization=True
    )


# 全局实例
audio_processor = AudioPostProcessor()