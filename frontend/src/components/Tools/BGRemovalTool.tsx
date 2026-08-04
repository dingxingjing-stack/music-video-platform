/**
 * 智能抠图组件 (P1-7)
 * 
 * 功能: 上传图片 - 抠图 - 预览 - 下载
 */

import React, { useState, useCallback } from 'react';
import { Upload, Image, Button, Space, message, Alert } from 'antd';
import { UploadOutlined } from '@ant-design/icons';

export const BGRemovalTool: React.FC = () => {
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
        message.success('抠图成功！');
      } else {
        message.error(`抠图失败：${result.error}`);
      }
    } catch (error) {
      message.error('网络错误，请重试');
    } finally {
      setUploading(false);
    }

    return false;
  }, []);

  return (
    <div style={{ padding: '24px' }}>
      <h2>智能抠图</h2>
      <p>一键移除图片背景，支持人物/产品/通用场景</p>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Upload
          customRequest={({ file }) => handleRemoveBG(file as File)}
          accept="image/*"
          showUploadList={false}
          disabled={uploading}
        >
          <Button type="primary" icon={<UploadOutlined />} loading={uploading}>
            上传图片
          </Button>
        </Upload>

        {(previewUrl || resultUrl) && (
          <Space size="large">
            {previewUrl && (
              <div>
                <h4>原图</h4>
                <Image src={previewUrl} alt="Original" style={{ maxWidth: '400px', maxHeight: '400px' }} />
              </div>
            )}
            {resultUrl && (
              <div>
                <h4>抠图结果</h4>
                <Image src={resultUrl} alt="No BG" style={{ maxWidth: '400px', maxHeight: '400px' }} />
                <div style={{ marginTop: '12px' }}>
                  <Button type="primary" onClick={() => {
                    const a = document.createElement('a');
                    a.href = resultUrl;
                    a.download = 'no_bg.png';
                    a.click();
                  }}>
                    下载结果
                  </Button>
                </div>
              </div>
            )}
          </Space>
        )}

        <Alert
          message="使用说明"
          description="支持 PNG/JPG/WebP。使用 Remove.bg API (精准) 或本地 rembg 库 (免费)"
          type="info"
          showIcon
        />
      </Space>
    </div>
  );
};

export default BGRemovalTool;