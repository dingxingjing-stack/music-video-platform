/**
 * MessagingPanel - 私信聊天组件
 * 
 * 功能:
 * - 对话列表
 * - 实时聊天 (WebSocket)
 * - 发送文本/图片消息
 * - 未读计数
 * - 已读状态
 */

import { useState, useEffect, useCallback, useRef } from 'react';

interface Conversation {
  conversation_id: string;
  partner_id: string;
  partner_name?: string;
  last_message: string;
  last_message_time: string;
  unread_count: number;
}

interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  receiver_id: string;
  content: string;
  type: string;
  media_url?: string;
  is_read: boolean;
  created_at: string;
}

interface Props {
  userId: string;
  onClose: () => void;
}

export function MessagingPanel({ userId, onClose }: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedPartner, setSelectedPartner] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 加载对话列表
  const loadConversations = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/messages/conversations?user_id=${userId}`);
      const data = await response.json();
      setConversations(data);
    } catch (error) {
      console.error('加载对话失败:', error);
    }
  }, [userId]);

  // 加载聊天记录
  const loadMessages = useCallback(async (partnerId: string) => {
    setLoading(true);
    try {
      const response = await fetch(
        `/api/v1/messages/conversations/${partnerId}?user_id=${userId}&limit=50`
      );
      const data = await response.json();
      setMessages(data);
      
      // 标记所有消息为已读
      data.forEach((msg: Message) => {
        if (!msg.is_read && msg.receiver_id === userId) {
          fetch(`/api/v1/messages/${msg.id}/read`, { method: 'PUT' });
        }
      });
    } catch (error) {
      console.error('加载消息失败:', error);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  // 发送消息
  const sendMessage = useCallback(async () => {
    if (!newMessage.trim() || !selectedPartner) return;

    try {
      const response = await fetch('/api/v1/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sender_id: userId,
          receiver_id: selectedPartner,
          content: newMessage,
          type: 'text'
        })
      });
      
      const msg = await response.json();
      setMessages(prev => [...prev, msg]);
      setNewMessage('');
      
      // 更新对话列表
      loadConversations();
    } catch (error) {
      console.error('发送消息失败:', error);
    }
  }, [userId, selectedPartner, newMessage, loadConversations]);

  // WebSocket 实时消息
  useEffect(() => {
    if (!userId) return;

    const ws = new WebSocket(`ws://${window.location.hostname}:8001/ws/messages/${userId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('消息 WebSocket 已连接');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'new_message') {
        const msg = data.message;
        // 如果是当前对话的消息
        if (selectedPartner && msg.conversation_id === 
            `conv_${[userId, selectedPartner].sort().join('_')}`) {
          setMessages(prev => [...prev, msg]);
          // 自动标记已读
          if (msg.receiver_id === userId) {
            fetch(`/api/v1/messages/${msg.id}/read`, { method: 'PUT' });
          }
        }
        // 更新对话列表
        loadConversations();
      }
    };

    ws.onclose = () => {
      console.log('消息 WebSocket 已断开');
    };

    return () => {
      ws.close();
    };
  }, [userId, selectedPartner, loadConversations]);

  // 滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 选择对话
  const selectConversation = (partnerId: string) => {
    setSelectedPartner(partnerId);
    loadMessages(partnerId);
  };

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
      <div className="w-[800px] max-h-[80vh] bg-[#1e1e1e] rounded-xl border border-[#2a2a2a] overflow-hidden flex">
        {/* 左侧：对话列表 */}
        <div className="w-80 border-r border-[#2a2a2a] flex flex-col">
          <div className="p-4 border-b border-[#2a2a2a]">
            <h2 className="text-lg font-bold text-[#e0e0e0]">💬 私信</h2>
          </div>
          
          <div className="flex-1 overflow-auto">
            {conversations.length === 0 ? (
              <div className="p-8 text-center text-[#777777]">
                暂无对话
              </div>
            ) : (
              <div className="divide-y divide-[#2a2a2a]">
                {conversations.map(conv => (
                  <button
                    key={conv.conversation_id}
                    onClick={() => selectConversation(conv.partner_id)}
                    className={`w-full p-4 text-left hover:bg-[#252525] transition ${
                      selectedPartner === conv.partner_id ? 'bg-[#252525]' : ''
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-[#e0e0e0] truncate">
                            {conv.partner_name || conv.partner_id}
                          </span>
                          {conv.unread_count > 0 && (
                            <span className="px-2 py-0.5 text-xs bg-orange-500 text-white rounded-full">
                              {conv.unread_count}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-[#777777] truncate mt-1">
                          {conv.last_message}
                        </p>
                      </div>
                      <span className="text-xs text-[#555555]">
                        {formatTime(conv.last_message_time)}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 右侧：聊天窗口 */}
        <div className="flex-1 flex flex-col">
          {!selectedPartner ? (
            <div className="flex-1 flex items-center justify-center text-[#777777]">
              选择一个对话开始聊天
            </div>
          ) : (
            <>
              {/* 聊天头部 */}
              <div className="p-4 border-b border-[#2a2a2a]">
                <h3 className="font-medium text-[#e0e0e0]">
                  {conversations.find(c => c.partner_id === selectedPartner)?.partner_name || selectedPartner}
                </h3>
              </div>

              {/* 消息列表 */}
              <div className="flex-1 overflow-auto p-4 space-y-4">
                {loading ? (
                  <div className="text-center text-[#777777]">加载中...</div>
                ) : messages.length === 0 ? (
                  <div className="text-center text-[#777777]">
                    还没有消息，开始对话吧！
                  </div>
                ) : (
                  messages.map(msg => (
                    <div
                      key={msg.id}
                      className={`flex ${msg.sender_id === userId ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-[70%] p-3 rounded-lg ${
                          msg.sender_id === userId
                            ? 'bg-gradient-to-r from-orange-500 to-pink-500 text-white'
                            : 'bg-[#2a2a2a] text-[#e0e0e0]'
                        }`}
                      >
                        <p className="text-sm">{msg.content}</p>
                        <p className={`text-xs mt-1 ${
                          msg.sender_id === userId ? 'text-white/70' : 'text-[#777777]'
                        }`}>
                          {formatTime(msg.created_at)}
                        </p>
                      </div>
                    </div>
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* 输入框 */}
              <div className="p-4 border-t border-[#2a2a2a]">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={newMessage}
                    onChange={(e) => setNewMessage(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                    placeholder="输入消息..."
                    className="flex-1 bg-[#2a2a2a] text-[#e0e0e0] px-4 py-2 rounded-lg border border-[#2a2a2a] focus:outline-none focus:border-orange-500"
                  />
                  <button
                    onClick={sendMessage}
                    disabled={!newMessage.trim()}
                    className="px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 text-white rounded-lg font-medium hover:from-orange-600 hover:to-pink-600 transition disabled:opacity-50"
                  >
                    发送
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* 关闭按钮 */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-[#777777] hover:text-white transition"
        >
          ✕
        </button>
      </div>
    </div>
  );
}