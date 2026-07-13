/**
 * AI 特效工具 (P3-2)
 * 精简版：KISS + DRY
 */

import React, { useState, useCallback } from 'react';
import { Upload, Button, Space, Input, Select, Progress, message } from 'antd';
import { UploadOutlined, PlayCircleOutlined, DownloadOutlined } from '@ant-design/icons';

const { TextArea } = Input;
const { Option } = Select;

interface VideoGenResult {
  task_id: string;
  status: 'processing' | 'completed' | 'failed';
  video_url?: string;
  error?: string;
}

export const AIEffectsTool: React.FC = () => {
  const [mode, setMode] = useState<'video' | 'inpaint' | 'bg-remove'>('video');
  const [uploading, setUploading] = useState(false);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [prompt, setPrompt] = useState('');
  const [motionScore, setMotionScore] = useState(5);
  const [duration, setDuration] = useState(4);
  const [result, setResult] = useState<VideoGenResult | null>(null);
  const [progress, setProgress] = useState(0);

  // 生成视频
  const handleGenerate = useCallback(async () => {
    if (!imageUrl) {
      message.error('请先上传图片');
      return;
    }

    setUploading(true);
    setResult({ task_id: '', status: 'processing' });
    setProgress(0);

    try {
      const res = await fetch('/api/v1/ai-effects/video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_url: imageUrl,
          prompt,
          motion_score: motionScore,
          duration,
          aspect_ratio: '16:9',
        }),
      });

      const data = await res.json();
      if (data.success) {
        setResult({ task_id: data.task_id, status: 'processing' });
        message.success('任务已提交，正在生成...');
        pollStatus(data.task_id);
      } else {
        setResult({ task_id: '', status: 'failed', error: '提交失败' });
        message.error('提交失败');
      }
    } catch {
      setResult({ task_id: '', status: 'failed', error: '网络错误' });
      message.error('网络错误，请重试');
    } finally {
      setUploading(false);
    }
  }, [imageUrl, prompt, motionScore, duration]);

  // 轮询状态
  const pollStatus = useCallback(async (taskId: string) => {
    const poll = async () => {
      try {
        const res = await fetch(`/api/v1/ai-effects/status/${taskId}`);
        const data = await res.json();

        if (data.success) {
          const { status, output_url, progress } = data.data;
          setProgress(progress || 0);

          if (status === 'completed') {
            setResult({ task_id: taskId, status: 'completed', video_url: output_url });
            message.success('生成成功！');
          } else if (status === 'failed') {
            setResult({ task_id: taskId, status: 'failed', error: data.data.error });
            message.error('生成失败');
          } else {
            setTimeout(poll, 3000);
          }
        } else {
          setTimeout(poll, 3000);
        }
      } catch {
        setTimeout(poll, 3000);
      }
    };
    poll();
  }, []);

  return (
    <div style={{ padding: '24px' }}>
      <h2>🎬 AI 特效</h2>
      <p>使用 RunwayML AI 生成视频、扩图、背景移除</p>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* 模式选择 */}
        <Select value={mode} onChange={setMode} style={{ width: '100%' }} size="large">
          <Option value="video">🎬 图生视频 (Motion Brush)</Option>
          <Option value="inpaint">🖼️ AI 扩图/修复</Option>
          <Option value="bg-remove">✂️ 背景移除</Option>
        </Select>

        {/* 图片上传 */}
        <Upload
          customRequest={({ file, onSuccess }) => {
            const reader = new FileReader();
            reader.onload = e => setImageUrl(e.target?.result as string);
            reader.readAsDataURL(file);
            onSuccess?.(null);
          }}
          accept="image/*"
          showUploadList={false}
          disabled={uploading}
        >
          <Button icon={<UploadOutlined />}>上传图片</Button>
        </Upload>

        {imageUrl && <div><h4>预览</h4><img src={imageUrl} alt="Preview" style={{ maxWidth: '400px', maxHeight: '300px' }} /></div>}

        {/* 参数配置 */}
        {mode === 'video' && (
          <>
            <TextArea
              placeholder="描述想要的运动效果 (可选)"
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              rows={3}
              maxLength={500}
            />
            <div>
              <label>运动强度：{motionScore}</label>
              <input type="range" min="1" max="10" value={motionScore} onChange={e => setMotionScore(Number(e.target.value))} style={{ width: '100%' }} />
            </div>
            <div>
              <label>视频时长：{duration}秒</label>
              <Select value={duration} onChange={setDuration} style={{ width: '150px', marginLeft: '10px' }}>
                <Option value={4}>4 秒</Option>
                <Option value={8}>8 秒</Option>
                <Option value={12}>12 秒</Option>
              </Select>
            </div>
          </>
        )}

        {/* 生成按钮 */}
        <Button type="primary" size="large" onClick={handleGenerate} loading={uploading} icon={<PlayCircleOutlined />} disabled={!imageUrl}>
          {mode === 'video' ? '生成视频' : mode === 'inpaint' ? 'AI 扩图' : '移除背景'}
        </Button>

        {/* 进度和结果 */}
        {result?.status === 'processing' && <div><h4>生成中...</h4><Progress percent={progress} status="active" /></div>}
        {result?.status === 'completed' && result.video_url && (
          <div>
            <h4>生成成功!</h4>
            <video src={result.video_url} controls style={{ maxWidth: '600px', maxHeight: '400px' }} />
            <div style={{ marginTop: '12px' }}>
              <Button icon={<DownloadOutlined />} onClick={() => {
                const a = document.createElement('a');
                a.href = result.video_url!;
                a.download = 'ai-video.mp4';
                a.click();
              }}>下载视频</Button>
            </div>
          </div>
        )}
        {result?.status === 'failed' && <div style={{ color: 'red' }}>❌ 生成失败：{result.error}</div>}

        {/* 使用说明 */}
        <div style={{ marginTop: '24px', padding: '16px', background: '#f5f5f5', borderRadius: '8px' }}>
          <h4>💡 使用说明</h4>
          <ul>
            <li>图生视频：上传图片，描述运动效果，AI 生成 4-12 秒视频</li>
            <li>AI 扩图：需要上传遮罩图片 (白色区域为修复区域)</li>
            <li>背景移除：自动移除图片背景，输出透明 PNG</li>
            <li>费用：RunwayML API, $0.35/秒 (图生视频), $0.05/张 (扩图)</li>
          </ul>
        </div>
      </Space>
    </div>
  );
};

export default AIEffectsTool;