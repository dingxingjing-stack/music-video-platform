"""
人声质量优化器

功能:
1. De-essing (去齿音) - 去除 s/sh/ch 等刺耳高频
2. 人声 EQ - 温暖感提升 (200-400Hz) + 空气感 (10kHz+)
3. 混响 - 空间感 (Hall/Plate/Room)
4. 和声 - 丰富度 (双轨/三轨叠录模拟)
5. 压缩 - 人声动态控制

目标：让人声从"可用"提升至"专业级"听感
"""

import numpy as np
from scipy import signal
from scipy.fft import fft, ifft
from typing import Dict, Optional
import librosa


class VocalEnhancer:
    """人声增强器"""
    
    def __init__(self, sample_rate: int = 44100):
        self.sr = sample_rate
    
    def de_ess(self, audio: np.ndarray, threshold_db: float = -20.0, freq_range: tuple = (5000, 8000)) -> np.ndarray:
        """
        De-essing 去齿音
        
        原理：压缩特定频段 (5-8kHz) 的动态，减少 s/sh/ch 等齿音
        
        Args:
            audio: 音频信号
            threshold_db: 触发阈值 (dB)
            freq_range: 齿音频段 (Hz)
        
        Returns:
            处理后的音频
        """
        # 1. 设计带通滤波器提取齿音频段
        nyquist = self.sr / 2
        low = freq_range[0] / nyquist
        high = freq_range[1] / nyquist
        b, a = signal.butter(4, [low, high], btype='band')
        
        # 2. 提取齿音成分
        sibilant = signal.filtfilt(b, a, audio)
        
        # 3. 检测超过阈值的齿音
        rms = np.sqrt(np.convolve(sibilant**2, np.ones(1024)/1024, mode='same'))
        threshold = 10 ** (threshold_db / 20)
        
        # 4. 动态压缩齿音
        gain_reduction = np.ones_like(audio)
        over_threshold = rms > threshold
        gain_reduction[over_threshold] = threshold / rms[over_threshold]
        
        # 5. 应用增益衰减到原始信号
        enhanced = audio.copy()
        enhanced -= sibilant * (1 - gain_reduction)
        
        return enhanced
    
    def vocal_eq(self, audio: np.ndarray) -> np.ndarray:
        """
        人声 EQ 优化
        
        - 提升 200-400Hz: 温暖感
        - 提升 2-5kHz: 存在感
        - 提升 10kHz+: 空气感
        - 削减 300-500Hz: 减少浑浊
        
        Returns:
            处理后的音频
        """
        # 使用 FFT 进行频域处理
        spectrum = fft(audio)
        freqs = np.fft.fftfreq(len(audio), 1/self.sr)
        
        # 创建 EQ 曲线
        eq_curve = np.ones_like(spectrum)
        
        # 1. 温暖感提升 (200-400Hz, +3dB)
        mask = (np.abs(freqs) >= 200) & (np.abs(freqs) <= 400)
        eq_curve[mask] *= 10 ** (3 / 20)
        
        # 2. 浑浊削减 (300-500Hz, -2dB)
        mask = (np.abs(freqs) >= 300) & (np.abs(freqs) <= 500)
        eq_curve[mask] *= 10 ** (-2 / 20)
        
        # 3. 存在感提升 (2-5kHz, +4dB)
        mask = (np.abs(freqs) >= 2000) & (np.abs(freqs) <= 5000)
        eq_curve[mask] *= 10 ** (4 / 20)
        
        # 4. 空气感提升 (10kHz+, +6dB)
        mask = np.abs(freqs) >= 10000
        eq_curve[mask] *= 10 ** (6 / 20)
        
        # 5. 低切 (80Hz 以下，去除低频噪音)
        mask = np.abs(freqs) < 80
        eq_curve[mask] *= np.abs(freqs[mask]) / 80
        
        # 应用 EQ
        enhanced_spectrum = spectrum * eq_curve
        return np.real(ifft(enhanced_spectrum))
    
    def add_reverb(self, audio: np.ndarray, room_size: float = 0.5, wet_level: float = 0.2) -> np.ndarray:
        """
        添加混响 (空间感)
        
        Args:
            audio: 干声
            room_size: 房间大小 (0-1, 0=小房间，1=大厅)
            wet_level: 湿声比例 (0-1, 0=干声，1=全混响)
        
        Returns:
            混响后的音频
        """
        # 简化的混响实现 (实际应使用卷积混响)
        # 使用多个延迟模拟早期反射
        
        dry = audio
        wet = np.zeros_like(audio)
        
        # 早期反射点 (延迟时间 ms, 增益)
        early_reflections = [
            (23, 0.3),
            (42, 0.25),
            (67, 0.2),
            (89, 0.15),
            (112, 0.1),
        ]
        
        # 添加早期反射
        for delay_ms, gain in early_reflections:
            delay_samples = int(delay_ms * self.sr / 1000)
            if delay_samples < len(audio):
                wet[delay_samples:] += audio[:-delay_samples] * gain
        
        # 添加衰减
        wet *= room_size * wet_level
        
        return dry + wet
    
    def add_harmony(self, audio: np.ndarray, voices: int = 2, detune_cents: int = 10) -> np.ndarray:
        """
        添加和声 (丰富度)
        
        原理：复制人声并轻微变调，模拟多轨叠录
        
        Args:
            audio: 主人声
            voices: 和声数量 (1=双轨，2=三轨)
            detune_cents: 失谐量 (cents, 1 半音=100 cents)
        
        Returns:
            带和声的音频
        """
        output = audio.copy()
        
        for i in range(voices):
            # 计算变调比例 (±detune cents)
            direction = 1 if i % 2 == 0 else -1
            cents = detune_cents * (i // 2 + 1) * direction
            ratio = 2 ** (cents / 1200)
            
            # 简单的变调通过重采样实现
            new_length = int(len(audio) * ratio)
            if ratio > 1:
                resampled = np.interp(
                    np.linspace(0, len(audio), new_length),
                    np.linspace(0, len(audio), len(audio)),
                    audio
                )[:len(audio)]
            else:
                resampled = np.interp(
                    np.linspace(0, len(audio) * ratio, len(audio)),
                    np.arange(len(audio) * ratio),
                    np.pad(audio, (0, int(len(audio) * (1 - ratio))))
                )
            
            # 混合和声 (较低音量)
            output += resampled * (0.3 / (i + 1))
        
        return output
    
    def vocal_compressor(self, audio: np.ndarray, threshold_db: float = -18.0, ratio: float = 4.0, attack_ms: float = 10.0, release_ms: float = 100.0) -> np.ndarray:
        """
        人声压缩器
        
        控制动态范围，让人声更靠前、更稳定
        
        Args:
            threshold_db: 阈值 (dB)
            ratio: 压缩比 (4:1 等人声常用)
            attack_ms: 启动时间 (ms)
            release_ms: 释放时间 (ms)
        
        Returns:
            压缩后的音频
        """
        # 计算 RMS 包络
        frame_size = int(self.sr * 0.03)  # 30ms
        hop_size = int(self.sr * 0.01)    # 10ms
        
        rms = []
        for i in range(0, len(audio) - frame_size, hop_size):
            frame = audio[i:i+frame_size]
            rms.append(np.sqrt(np.mean(frame**2)))
        
        rms = np.array(rms)
        
        # 转换为 dB
        rms_db = 20 * np.log10(rms + 1e-10)
        
        # 计算增益衰减
        gain_reduction = np.zeros_like(rms_db)
        over_threshold = rms_db > threshold_db
        gain_reduction[over_threshold] = (rms_db[over_threshold] - threshold_db) * (1 - 1/ratio)
        
        # 平滑增益变化 (避免爆音)
        attack_samples = int(attack_ms * self.sr / 1000)
        release_samples = int(release_ms * self.sr / 1000)
        
        # 应用增益衰减
        enhanced = audio.copy()
        for i, gr in enumerate(gain_reduction):
            start = i * hop_size
            end = min(start + frame_size, len(audio))
            gain = 10 ** (-gr / 20)
            enhanced[start:end] *= gain
        
        return enhanced
    
    def enhance(self, audio: np.ndarray, settings: Optional[Dict] = None) -> np.ndarray:
        """
        完整人声增强流程
        
        Args:
            audio: 原始人声
            settings: 可选的自定义设置
        
        Returns:
            增强后的人声
        """
        if settings is None:
            settings = {
                'de_ess': True,
                'eq': True,
                'compression': True,
                'reverb': True,
                'harmony': False,  # 默认不加和声 (太人工)
            }
        
        result = audio.copy()
        
        # 1. De-essing
        if settings.get('de_ess'):
            result = self.de_ess(result)
        
        # 2. EQ
        if settings.get('eq'):
            result = self.vocal_eq(result)
        
        # 3. 压缩
        if settings.get('compression'):
            result = self.vocal_compressor(result)
        
        # 4. 混响
        if settings.get('reverb'):
            result = self.add_reverb(result, room_size=0.4, wet_level=0.15)
        
        # 5. 和声 (可选)
        if settings.get('harmony'):
            result = self.add_harmony(result, voices=1, detune_cents=8)
        
        # 6. 限幅 (防止削波)
        max_val = np.max(np.abs(result))
        if max_val > 0.95:
            result *= 0.95 / max_val
        
        return result


# 全局实例
vocal_enhancer = VocalEnhancer()