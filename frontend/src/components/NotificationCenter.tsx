/**
 * NotificationCenter - 通知中心组件
 * 
 * 功能:
 * - 显示通知列表
 * - 实时 WebSocket 推送
 * - 未读计数徽章
 * - 分类筛选 (全部/点赞/收藏/关注/系统)
 * - 标记已读/删除
 */

import { useState, useEffect, useCallback, useRef } from 'react';

interface Notification {
  id: string;
  user_id: string;
  type: string;
  title: string;
  content: string;
  related_id?: string;
  sender_id?: string;
  sender_name?: string;
  is_read: boolean;
  created_at: string;
}

interface Props {
  userId: string;
  onClose: () => void;
}

const TYPE_ICONS: Record<string, string> = {
  like: '👍',
  favorite: '⭐',
  follow: '👤',
  comment: '💬',
  system: '🔔',
  collab_invite: '🤝',
  copyright_alert: '⚠️'
};

const TYPE_LABELS: Record<string, string> = {
  like: '点赞',
  favorite: '收藏',
  follow: '关注',
  comment: '评论',
  system: '系统',
  collab_invite: '协作邀请',
  copyright_alert: '版权提醒'
};

export function NotificationCenter({ userId, onClose }: Props) {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'unread' | 'like' | 'favorite' | 'follow'>('all');
  const [unreadCount, setUnreadCount] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);

  // 加载通知列表
  const loadNotifications = useCallback(async () => {
    try {
      const params = new URLSearchParams({ user_id: userId });
      if (filter === 'unread') params.append('unread_only', 'true');
      if (filter !== 'all' && filter !== 'unread') params.append('type_filter', filter);
      
      const response = await fetch(`/api/v1/notifications?${params}`);
      const data = await response.json();
      setNotifications(data);
    } catch (error) {
      console.error('加载通知失败:', error);
    } finally {
      setLoading(false);
    }
  }, [userId, filter]);

  // 加载未读计数
  const loadUnreadCount = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/notifications/unread/count?user_id=${userId}`);
      const data = await response.json();
      setUnreadCount(data.unread_count);
    } catch (error) {
      console.error('加载未读计数失败:', error);
    }
  }, [userId]);

  // 标记已读
  const markAsRead = useCallback(async (notifId: string) => {
    try {
      await fetch(`/api/v1/notifications/${notifId}/read`, { method: 'PUT' });
      setNotifications(prev => prev.map(n => 
        n.id === notifId ? { ...n, is_read: true } : n
      ));
      loadUnreadCount();
    } catch (error) {
      console.error('标记已读失败:', error);
    }
  }, [loadUnreadCount]);

  // 删除通知
  const deleteNotification = useCallback(async (notifId: string) => {
    try {
      await fetch(`/api/v1/notifications/${notifId}`, { method: 'DELETE' });
      setNotifications(prev => prev.filter(n => n.id !== notifId));
      loadUnreadCount();
    } catch (error) {
      console.error('删除通知失败:', error);
    }
  }, [loadUnreadCount]);

  // 全部已读
  const markAllAsRead = useCallback(async () => {
    try {
      await fetch(`/api/v1/notifications/read-all?user_id=${userId}`, { method: 'PUT' });
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch (error) {
      console.error('全部已读失败:', error);
    }
  }, [userId]);

  // WebSocket 实时推送
  useEffect(() => {
    if (!userId) return;

    const ws = new WebSocket(`ws://${window.location.hostname}:8001/ws/notifications/${userId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('通知 WebSocket 已连接');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'init') {
        setUnreadCount(data.unread_count);
      } else {
        // 新通知推送
        setNotifications(prev => [data, ...prev]);
        setUnreadCount(prev => prev + 1);
        
        // 浏览器通知 (如果需要)
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification(data.title, {
            body: data.content,
            icon: '/logo.png'
          });
        }
      }
    };

    ws.onclose = () => {
      console.log('通知 WebSocket 已断开');
      // 3 秒后重连
      setTimeout(() => loadNotifications(), 3000);
    };

    return () => {
      ws.close();
    };
  }, [userId, loadNotifications]);

  // 初始加载
  useEffect(() => {
    loadNotifications();
    loadUnreadCount();
  }, [userId, filter, loadNotifications, loadUnreadCount]);

  // 请求浏览器通知权限
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, []);

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    
    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes}分钟前`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}小时前`;
    const days = Math.floor(hours / 24);
    return `${days}天前`;
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="w-[600px] max-h-[80vh] bg-[#1e1e1e] rounded-xl border border-[#2a2a2a] overflow-hidden flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-[#2a2a2a]">
          <div>
            <h2 className="text-lg font-bold text-[#e0e0e0]">🔔 通知中心</h2>
            <p className="text-xs text-[#777777]">
              {unreadCount > 0 ? `${unreadCount} 条未读` : '全部已读'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {unreadCount > 0 && (
              <button
                onClick={markAllAsRead}
                className="text-xs text-orange-500 hover:text-orange-400 transition"
              >
                全部已读
              </button>
            )}
            <button
              onClick={onClose}
              className="text-[#777777] hover:text-white transition"
            >
              ✕
            </button>
          </div>
        </div>

        {/* 筛选器 */}
        <div className="flex items-center gap-2 p-3 border-b border-[#2a2a2a]">
          {[
            { key: 'all', label: '全部' },
            { key: 'unread', label: '未读' },
            { key: 'like', label: '👍 点赞' },
            { key: 'favorite', label: '⭐ 收藏' },
            { key: 'follow', label: '👤 关注' }
          ].map(item => (
            <button
              key={item.key}
              onClick={() => setFilter(item.key as typeof filter)}
              className={`px-3 py-1.5 text-sm rounded-lg transition ${
                filter === item.key
                  ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white'
                  : 'bg-[#2a2a2a] text-[#777777] hover:text-white'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* 通知列表 */}
        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="p-8 text-center text-[#777777]">加载中...</div>
          ) : notifications.length === 0 ? (
            <div className="p-8 text-center text-[#777777]">
              🎉 暂无通知
            </div>
          ) : (
            <div className="divide-y divide-[#2a2a2a]">
              {notifications.map(notif => (
                <div
                  key={notif.id}
                  className={`p-4 hover:bg-[#252525] transition ${
                    !notif.is_read ? 'bg-[#1f2530]' : ''
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="text-2xl">{TYPE_ICONS[notif.type] || '🔔'}</div>
                    <div className="flex-1">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="font-medium text-[#e0e0e0]">{notif.title}</h3>
                          <p className="text-sm text-[#999999] mt-1">{notif.content}</p>
                          {notif.sender_name && (
                            <p className="text-xs text-[#777777] mt-1">
                              来自：{notif.sender_name}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-[#555555]">
                            {formatTime(notif.created_at)}
                          </span>
                          {!notif.is_read && (
                            <button
                              onClick={() => markAsRead(notif.id)}
                              className="text-xs text-orange-500 hover:text-orange-400"
                            >
                              标记已读
                            </button>
                          )}
                          <button
                            onClick={() => deleteNotification(notif.id)}
                            className="text-xs text-[#555555] hover:text-red-500"
                          >
                            ✕
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}