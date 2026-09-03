/**
 * {t('aieffects.title')}工具 (P3-2)
 * 精简版：KISS + DRY
 */

import React, { useState, useCallback } from 'react';
import { Upload, Button, Space, Input, Select, Progress, message } from 'antd';
import { UploadOutlined, PlayCircleOutlined, DownloadOutlined } from '@ant-design/icons';
import { useTranslation } from '../../i18n/useTranslation';

const { TextArea } = Input;
const { Option } = Select;

interface VideoGenResult {
  task_id: string;
  status: 'processing' | 'completed' | 'failed';
  video_url?: string;
  error?: string;
}

export const AIEffectsTool: React.FC = () => {
  const { t } = useTranslation();
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
      message.error(t('aieffects.noImage'));
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
        message.success(t('aieffects.submitted'));
        pollStatus(data.task_id);
      } else {
        setResult({ task_id: '', status: 'failed', error: t('aieffects.submitFailed') });
        message.error(t('aieffects.submitFailed'));
      }
    } catch {
      setResult({ task_id: '', status: 'failed', error: t('aieffects.networkError') });
      message.error(t('aieffects.networkRetry'));
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
            message.success(t('aieffects.success'));
          } else if (status === 'failed') {
            setResult({ task_id: taskId, status: 'failed', error: data.data.error });
            message.error(t('aieffects.fail'));
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
      <h2>🎬 {t('aieffects.title')}</h2>
      <p>{t('aieffects.subtitle')}</p>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* 模式选择 */}
        <Select value={mode} onChange={setMode} style={{ width: '100%' }} size="large">
          <Option value="video">{t('aieffects.modeVideo')}</Option>
          <Option value="inpaint">{t('aieffects.modeInpaint')}</Option>
          <Option value="bg-remove">{t('aieffects.modeBgRemove')}</Option>
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
          <Button icon={<UploadOutlined />}>{t('aieffects.uploadImage')}</Button>
        </Upload>

        {imageUrl && <div><h4>{t('aieffects.preview')}</h4><img src={imageUrl} alt="Preview" style={{ maxWidth: '400px', maxHeight: '300px' }} /></div>}

        {/* 参数配置 */}
        {mode === 'video' && (
          <>
            <TextArea
              placeholder={t('aieffects.motionPrompt')}
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              rows={3}
              maxLength={500}
            />
            <div>
              <label>{t('aieffects.motionStrength', { score: motionScore })}</label>
              <input type="range" min="1" max="10" value={motionScore} onChange={e => setMotionScore(Number(e.target.value))} style={{ width: '100%' }} />
            </div>
            <div>
              <label>{t('aieffects.videoDuration', { duration })}</label>
              <Select value={duration} onChange={setDuration} style={{ width: '150px', marginLeft: '10px' }}>
                <Option value={4}>{t('aieffects.dur4')}</Option>
                <Option value={8}>{t('aieffects.dur8')}</Option>
                <Option value={12}>{t('aieffects.dur12')}</Option>
              </Select>
            </div>
          </>
        )}

        {/* 生成按钮 */}
        <Button type="primary" size="large" onClick={handleGenerate} loading={uploading} icon={<PlayCircleOutlined />} disabled={!imageUrl}>
          {mode === 'video' ? t('aieffects.genVideo') : mode === 'inpaint' ? t('aieffects.genInpaint') : t('aieffects.genBgRemove')}
        </Button>

        {/* 进度和结果 */}
        {result?.status === 'processing' && <div><h4>{t('aieffects.processing')}</h4><Progress percent={progress} status="active" /></div>}
        {result?.status === 'completed' && result.video_url && (
          <div>
            <h4>{t('aieffects.successTitle')}</h4>
            <video src={result.video_url} controls style={{ maxWidth: '600px', maxHeight: '400px' }} />
            <div style={{ marginTop: '12px' }}>
              <Button icon={<DownloadOutlined />} onClick={() => {
                const a = document.createElement('a');
                a.href = result.video_url!;
                a.download = 'ai-video.mp4';
                a.click();
              }}>{t('aieffects.downloadVideo')}</Button>
            </div>
          </div>
        )}
        {result?.status === 'failed' && <div style={{ color: 'red' }}>❌ {t('aieffects.failed', { error: result.error })}</div>}

        {/* 使用说明 */}
        <div style={{ marginTop: '24px', padding: '16px', background: '#f5f5f5', borderRadius: '8px' }}>
          <h4>💡 {t('aieffects.howTo')}</h4>
          <ul>
            <li>{t('aieffects.how1')}</li>
            <li>{t('aieffects.how2')}</li>
            <li>{t('aieffects.how3')}</li>
            <li>{t('aieffects.how4')}</li>
          </ul>
        </div>
      </Space>
    </div>
  );
};

export default AIEffectsTool;