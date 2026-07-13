/**
 * CopyrightCheckPanel - 版权检测组件
 * 
 * 功能:
 * - 上传音频文件进行版权检测
 * - 显示匹配结果
 * - 风险评估报告
 * - 相似度可视化
 */

import { useState, useCallback } from 'react';

interface Match {
  match_id: string;
  reference_track_id: string;
  reference_track_name: string;
  similarity_score: number;
  risk_level: 'clear' | 'low' | 'medium' | 'high' | 'critical';
  match_segments: any[];
}

interface CopyrightReport {
  report_id: string;
  audio_filename: string;
  total_duration: number;
  matches: Match[];
  overall_risk: string;
  risk_score: number;
  recommendations: string[];
  is_clear_for_use: boolean;
}

export default function CopyrightCheckPanel() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [report, setReport] = useState<CopyrightReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const API_BASE = 'http://localhost:8001/api/v1/copyright';

  // 分析音频文件
  const analyzeAudio = useCallback(async (file: File) => {
    setIsAnalyzing(true);
    setError(null);
    setReport(null);

    try {
      const formData = new FormData();
      formData.append('audio_file', file);

      const res = await fetch(`${API_BASE}/analyze`, {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || '分析失败');
      }

      const data: CopyrightReport = await res.json();
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '分析失败，请重试');
    } finally {
      setIsAnalyzing(false);
    }
  }, []);

  // 处理文件上传
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);

    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('audio/')) {
      analyzeAudio(file);
    } else {
      setError('请上传音频文件');
    }
  }, [analyzeAudio]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      analyzeAudio(file);
    }
  }, [analyzeAudio]);

  // 获取风险等级颜色
  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'clear': return 'text-green-500';
      case 'low': return 'text-blue-500';
      case 'medium': return 'text-yellow-500';
      case 'high': return 'text-orange-500';
      case 'critical': return 'text-red-500';
      default: return 'text-gray-500';
    }
  };

  // 获取风险等级图标
  const getRiskIcon = (risk: string) => {
    switch (risk) {
      case 'clear': return '✅';
      case 'low': return 'ℹ️';
      case 'medium': return '⚠️';
      case 'high': return '⚠️';
      case 'critical': return '❌';
      default: return '❓';
    }
  };

  // 渲染匹配结果
  const renderMatches = () => {
    if (!report || report.matches.length === 0) {
      return (
        <div className="text-center py-8 text-[#777777]">
          <div className="text-4xl mb-2">🎉</div>
          <div className="text-lg font-medium text-white">未发现版权风险</div>
          <div className="text-sm mt-2">可以放心使用这首作品</div>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <h3 className="text-lg font-bold text-white">
          发现 {report.matches.length} 个相似作品
        </h3>
        
        {report.matches.map((match, index) => (
          <div 
            key={match.match_id}
            className="p-4 bg-[#1a1a1a] rounded-lg border-l-4"
            style={{
              borderColor: match.risk_level === 'critical' ? '#FF0000' :
                          match.risk_level === 'high' ? '#FF6B00' :
                          match.risk_level === 'medium' ? '#FFD700' : '#4ECDC4'
            }}
          >
            <div className="flex items-center justify-between mb-2">
              <div>
                <div className="text-white font-medium">
                  {match.reference_track_name}
                </div>
                <div className="text-xs text-[#777777]">
                  ID: {match.reference_track_id}
                </div>
              </div>
              <div className={`text-2xl font-bold ${getRiskColor(match.risk_level)}`}>
                {match.similarity_score * 100}%
              </div>
            </div>
            
            <div className="w-full bg-[#2a2a2a] rounded-full h-2 mb-2">
              <div 
                className={`h-2 rounded-full ${
                  match.risk_level === 'critical' ? 'bg-red-500' :
                  match.risk_level === 'high' ? 'bg-orange-500' :
                  match.risk_level === 'medium' ? 'bg-yellow-500' : 'bg-blue-500'
                }`}
                style={{ width: `${match.similarity_score * 100}%` }}
              />
            </div>
            
            <div className="flex items-center gap-2 text-sm">
              <span className={getRiskColor(match.risk_level)}>
                {getRiskIcon(match.risk_level)}
                <span className="ml-1 capitalize">{match.risk_level}</span>
              </span>
              <span className="text-[#777777]">
                相似度：{(match.similarity_score * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        ))}
      </div>
    );
  };

  // 主渲染
  return (
    <div className="p-6 bg-[#1a1a1a] rounded-lg space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">版权检测</h2>
        {report && (
          <button
            onClick={() => setReport(null)}
            className="text-sm text-[#777777] hover:text-white"
          >
            清除报告
          </button>
        )}
      </div>

      {/* 上传区域 */}
      {!report && !isAnalyzing && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`
            border-2 border-dashed rounded-lg p-8 text-center transition
            ${dragOver ? 'border-orange-500 bg-orange-500/10' : 'border-[#333] hover:border-[#444]'}
          `}
        >
          <div className="text-4xl mb-4">🎵</div>
          <div className="text-lg font-medium text-white mb-2">
            拖拽音频文件到此处
          </div>
          <div className="text-sm text-[#777777] mb-4">
            支持 MP3, WAV, FLAC, M4A 格式
          </div>
          <label className="inline-block">
            <span className="px-6 py-2 bg-gradient-to-r from-orange-500 to-pink-500 text-white rounded cursor-pointer hover:opacity-90 transition">
              选择文件
            </span>
            <input
              type="file"
              accept="audio/*"
              onChange={handleFileSelect}
              className="hidden"
            />
          </label>
        </div>
      )}

      {/* 分析中 */}
      {isAnalyzing && (
        <div className="text-center py-12">
          <div className="text-4xl mb-4">🔍</div>
          <div className="text-lg font-medium text-white mb-2">
            正在分析音频...
          </div>
          <div className="text-sm text-[#777777]">
            提取指纹并比对版权数据库
          </div>
          <div className="mt-6 flex justify-center">
            <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin" />
          </div>
        </div>
      )}

      {/* 错误 */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500 rounded-lg">
          <div className="text-red-500 font-medium">❌ {error}</div>
        </div>
      )}

      {/* 报告 */}
      {report && !isAnalyzing && (
        <div className="space-y-6">
          {/* 总体评估 */}
          <div className={`p-4 rounded-lg ${
            report.is_clear_for_use ? 'bg-green-500/10 border border-green-500' :
            report.overall_risk === 'critical' ? 'bg-red-500/10 border border-red-500' :
            'bg-yellow-500/10 border border-yellow-500'
          }`}>
            <div className="flex items-center gap-3 mb-2">
              <span className="text-2xl">{getRiskIcon(report.overall_risk)}</span>
              <div>
                <div className={`text-lg font-bold ${getRiskColor(report.overall_risk)}`}>
                  {report.overall_risk === 'clear' ? '版权安全' : 
                   report.overall_risk === 'low' ? '低风险' :
                   report.overall_risk === 'medium' ? '中等风险' :
                   report.overall_risk === 'high' ? '高风险' : '极高风险'}
                </div>
                <div className="text-sm text-[#777777]">
                  风险评分：{report.risk_score.toFixed(1)} / 100
                </div>
              </div>
            </div>
            
            {report.is_clear_for_use && (
              <div className="text-green-500 text-sm mt-2">
                ✅ 可以放心使用该作品
              </div>
            )}
            
            {!report.is_clear_for_use && (
              <div className="text-orange-500 text-sm mt-2">
                ⚠️ 建议重新编曲或获取授权
              </div>
            )}
          </div>

          {/* 建议 */}
          {report.recommendations.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-lg font-bold text-white">检测建议</h3>
              {report.recommendations.map((rec, i) => (
                <div key={i} className="p-3 bg-[#1a1a1a] rounded text-sm text-white">
                  {rec}
                </div>
              ))}
            </div>
          )}

          {/* 匹配结果 */}
          {renderMatches()}

          {/* 文件信息 */}
          <div className="pt-4 border-t border-[#333]">
            <div className="text-sm text-[#777777]">
              <div>文件名：{report.audio_filename}</div>
              <div>时长：{report.total_duration.toFixed(2)} 秒</div>
              <div>报告 ID: {report.report_id}</div>
            </div>
          </div>
        </div>
      )}

      {/* 说明 */}
      {!report && !isAnalyzing && (
        <div className="text-xs text-[#777777] space-y-2">
          <div className="font-medium text-white">检测原理:</div>
          <div>• 提取音频指纹 (MFCC 特征 + 频谱峰值)</div>
          <div>• 与百万级版权曲库比对</div>
          <div>• 计算相似度并评估风险</div>
          <div>• 生成详细检测报告</div>
        </div>
      )}
    </div>
  );
}