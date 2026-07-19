import { notification } from 'antd';
import { useEffect } from 'react';

export const ToastContainer = () => {
  useEffect(() => {
    // 配置 notification 的全局配置
    notification.config({
      placement: 'bottomRight',
      duration: 3,
      maxCount: 3,
    });
  }, []);

  return null;
};