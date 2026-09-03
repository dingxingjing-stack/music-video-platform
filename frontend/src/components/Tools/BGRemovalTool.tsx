/**
 * 智能抠图组件 (P1-7)
 * 
 * 功能: 上传图片 - 抠图 - 预览 - 下载
 */

import React, { useState, useCallback } from 'react';
import { Upload, Image, Button, Space, message, Alert } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import { useTranslation } from '../../i18n/useTranslation';

export const BGRemovalTool: React.FC = () => {
  const { t } = useTranslation();
  const [uploading, setUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);

  const handleRemoveBG = useCallback(async (file: File) => {
    setUploading(true);
    setPreviewUrl(URL.createObjectURL(file));
    setResultUrl(null);

    const formData = new FormData();
    formData.append('image', file);
    formData.append('type', 'auto');
    formData.append('size', 'full');
    formData.append('format', 'png');

    try {
      const response = await fetch('/api/v1/bg/remove', {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();

      if (result.success) {
        setResultUrl(result.output_url);
        message.success(t('bgremove.success'));
      } else {
        message.error(t('bgremove.failed', { error: result.error }));
      }
    } catch (error) {
      message.error(t('bgremove.networkRetry'));
    } finally {
      setUploading(false);
    }

    return false;
  }, []);

  return (
    <div style={{ padding: '24px' }}>
      <h2>{t('bgremove.title')}</h2>
      <p>{t('bgremove.subtitle')}</p>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Upload
          customRequest={({ file }) => handleRemoveBG(file as File)}
          accept="image/*"
          showUploadList={false}
          disabled={uploading}
        >
          <Button type="primary" icon={<UploadOutlined />} loading={uploading}>
            {t('bgremove.uploadImage')}
          </Button>
        </Upload>

        {(previewUrl || resultUrl) && (
          <Space size="large">
            {previewUrl && (
              <div>
                <h4>{t('bgremove.original')}</h4>
                <Image src={previewUrl} alt="Original" style={{ maxWidth: '400px', maxHeight: '400px' }} />
              </div>
            )}
            {resultUrl && (
              <div>
                <h4>{t('bgremove.result')}</h4>
                <Image src={resultUrl} alt="No BG" style={{ maxWidth: '400px', maxHeight: '400px' }} />
                <div style={{ marginTop: '12px' }}>
                  <Button type="primary" onClick={() => {
                    const a = document.createElement('a');
                    a.href = resultUrl;
                    a.download = 'no_bg.png';
                    a.click();
                  }}>
                    {t('bgremove.download')}
                  </Button>
                </div>
              </div>
            )}
          </Space>
        )}

        <Alert
          message={t('bgremove.howTo')}
          description={t('bgremove.desc')}
          type="info"
          showIcon
        />
      </Space>
    </div>
  );
};

export default BGRemovalTool;