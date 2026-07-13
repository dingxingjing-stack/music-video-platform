/**
 * CollaborationPanel - 协作编辑面板
 * 
 * 功能:
 * - 创建/加入协作会话
 * - 显示在线成员列表
 * - 实时光标同步
 * - 权限管理
 * - 操作历史记录
 */

import { useState, useEffect, useCallback, useRef } from 'react';

interface Member {
  user_id: string;
  username: string;
  role: 'viewer' | 'editor' | 'admin';
  color: string;
  cursor_position?: number;
  joined_at: string;
}

interface Operation {
  id: string;
  user_id: string;
  operation: 'add' | 'remove' | 'update' | 'cursor';
  target: string;
  data: any;
  timestamp: string;
}

interface CollaborationPanelProps {
  projectId: string;
  userId: string;
  username: string;
}

export default function CollaborationPanel({ 
  projectId, 
  userId, 
  username 
}: CollaborationPanelProps) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [isCreator, setIsCreator] = useState(false);
  const [myRole, setMyRole] = useState<'viewer' | 'editor' | 'admin'>('viewer');
  const [operations, setOperations] = useState<Operation[]>([]);
  const [cursorPos, setCursorPos] = useState<number>(0);
  const wsRef = useRef<WebSocket | null>(null);

  const API_BASE = 'http://localhost:8001/api/v1/collab';

  // 创建协作会话
  const createSession = async () => {
    try {
      const res = await fetch(`${API_BASE}/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          created_by: userId,
          username: username
        })
      });
      
      const data = await res.json();
      setSessionId(data.id);
      setIsCreator(true);
      setMyRole('admin');
      setMembers(data.members);
      
      // 连接 WebSocket
      connectWebSocket(data.id);
    } catch (error) {
      console.error('创建会话失败:', error);
    }
  };

  // 加入协作会话
  const joinSession = async (sid: string) => {
    try {
      const res = await fetch(`${API_BASE}/session/${sid}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          username: username,
          role: 'viewer'
        })
      });
      
      const data = await res.json();
      if (data.success) {
        setSessionId(sid);
        setMembers(data.session.members);
        setMyRole('viewer');
        
        // 连接 WebSocket
        connectWebSocket(sid);
      }
    } catch (error) {
      console.error('加入会话失败:', error);
    }
  };

  // 连接 WebSocket
  const connectWebSocket = (sid: string) => {
    const ws = new WebSocket(`ws://localhost:8001/ws/collab/${sid}`);
    
    ws.onopen = () => {
      console.log('WebSocket 已连接');
      // 发送加入消息
      ws.send(JSON.stringify({
        type: 'join',
        data: { user_id: userId, username: username }
      }));
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      handleWebSocketMessage(message);
    };

    ws.onclose = () => {
      console.log('WebSocket 已断开');
      wsRef.current = null;
    };

    ws.onerror = (error) => {
      console.error('WebSocket 错误:', error);
    };

    wsRef.current = ws;
  };

  // 处理 WebSocket 消息
  const handleWebSocketMessage = useCallback((message: any) => {
    const { type, data } = message;

    switch (type) {
      case 'joined':
        setMembers(data.members);
        console.log('已加入协作会话，在线人数:', data.members.length);
        break;

      case 'user_joined':
        setMembers(prev => [...prev, {
          user_id: data.user_id,
          username: data.username,
          role: 'viewer',
          color: data.color,
          joined_at: new Date().toISOString()
        }]);
        console.log(`${data.username} 加入了协作`);
        break;

      case 'user_left':
        setMembers(prev => prev.filter(m => m.user_id !== data.user_id));
        console.log(`${data.username} 离开了协作`);
        break;

      case 'operation':
        // 接收其他成员的操作
        setOperations(prev => [...prev.slice(-49), {
          id: data.operation_id || Date.now().toString(),
          user_id: data.user_id,
          operation: data.operation,
          target: data.target,
          data: data.data,
          timestamp: new Date().toISOString()
        }]);
        
        // TODO: 应用操作到本地状态
        // applyRemoteOperation(data);
        break;

      case 'cursor_move':
        // 更新其他成员的 cursor 位置
        setMembers(prev => prev.map(m => 
          m.user_id === data.user_id 
            ? { ...m, cursor_position: data.position }
            : m
        ));
        break;

      case 'operation_ack':
        console.log('操作已确认，版本:', data.version);
        break;

      case 'sync_required':
        console.log('需要重新同步，当前版本:', data.current_version);
        // TODO: 请求全量同步
        break;

      case 'error':
        console.error('协作错误:', data.message);
        break;
    }
  }, []);

  // 发送操作
  const sendOperation = useCallback((operation: string, target: string, data: any) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('WebSocket 未连接');
      return;
    }

    wsRef.current.send(JSON.stringify({
      type: 'operation',
      data: {
        operation,
        target,
        data,
        version: 0 // TODO: 从本地状态获取
      }
    }));
  }, []);

  // 发送 cursor 位置
  const sendCursor = useCallback((position: number) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }

    wsRef.current.send(JSON.stringify({
      type: 'cursor',
      data: { position }
    }));
  }, []);

  // 离开会话
  const leaveSession = async () => {
    if (sessionId) {
      try {
        await fetch(`${API_BASE}/session/${sessionId}/leave`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId })
        });
      } catch (error) {
        console.error('离开会话失败:', error);
      }
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setSessionId(null);
    setMembers([]);
    setOperations([]);
    setIsCreator(false);
    setMyRole('viewer');
  };

  // 清理
  useEffect(() => {
    return () => {
      leaveSession();
    };
  }, []);

  // 监听 cursor 位置变化
  useEffect(() => {
    if (sessionId && myRole !== 'viewer') {
      sendCursor(cursorPos);
    }
  }, [sessionId, cursorPos, myRole, sendCursor]);

  // 获取我的会话列表
  const getMySessions = async () => {
    try {
      const res = await fetch(`${API_BASE}/sessions?user_id=${userId}`);
      const data = await res.json();
      return data.sessions;
    } catch (error) {
      console.error('获取会话列表失败:', error);
      return [];
    }
  };

  // 渲染成员列表
  const renderMemberList = () => {
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-white">在线成员 ({members.length})</h3>
        {members.map(member => (
          <div 
            key={member.user_id}
            className="flex items-center gap-2 p-2 rounded bg-[#1a1a1a]"
          >
            <div 
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: member.color }}
            />
            <span className="text-sm text-white flex-1">{member.username}</span>
            <span className="text-xs text-[#777777] capitalize">{member.role}</span>
            {member.user_id === userId && (
              <span className="text-xs text-[#FF6B6B]">(我)</span>
            )}
          </div>
        ))}
      </div>
    );
  };

  // 渲染操作历史
  const renderOperationHistory = () => {
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-white">操作历史</h3>
        <div className="max-h-48 overflow-y-auto space-y-1">
          {operations.slice(-10).reverse().map((op, i) => (
            <div key={op.id} className="text-xs text-[#777777]">
              <span>{op.user_id === userId ? '你' : '他人'}</span>
              <span className="mx-1">{op.operation}</span>
              <span>{op.target}</span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  // 主渲染
  if (!sessionId) {
    return (
      <div className="p-4 bg-[#1a1a1a] rounded-lg">
        <h2 className="text-lg font-bold text-white mb-4">协作编辑</h2>
        <p className="text-sm text-[#777777] mb-4">
          创建或加入协作会话，与他人实时协同编辑音乐项目
        </p>
        <div className="space-y-2">
          <button
            onClick={createSession}
            className="w-full px-4 py-2 bg-gradient-to-r from-orange-500 to-pink-500 text-white rounded hover:opacity-90 transition"
          >
            创建协作会话
          </button>
          <div className="text-xs text-[#777777] text-center">或</div>
          <input
            type="text"
            placeholder="输入会话 ID 加入"
            className="w-full px-3 py-2 bg-[#2a2a2a] text-white rounded text-sm border border-[#333]"
            onKeyDown={async (e) => {
              if (e.key === 'Enter') {
                await joinSession(e.currentTarget.value);
              }
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 bg-[#1a1a1a] rounded-lg space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white">协作编辑中</h2>
        <button
          onClick={leaveSession}
          className="text-xs text-[#777777] hover:text-white"
        >
          离开
        </button>
      </div>

      <div className="text-xs text-[#777777]">
        会话 ID: <span className="text-white font-mono">{sessionId}</span>
      </div>

      <div className="flex items-center gap-2">
        <div 
          className="w-3 h-3 rounded-full bg-green-500"
          title="在线"
        />
        <span className="text-sm text-white">
          {members.length} 人在线
        </span>
      </div>

      {renderMemberList()}
      {renderOperationHistory()}

      {myRole === 'viewer' && (
        <div className="text-xs text-yellow-500 bg-yellow-500/10 p-2 rounded">
          ⚠️ 当前为查看模式，无法编辑
        </div>
      )}

      {/* 测试用操作按钮 */}
      {myRole !== 'viewer' && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-white">测试操作</h3>
          <button
            onClick={() => sendOperation('add', 'track', { name: '新轨道', id: Date.now() })}
            className="w-full px-3 py-1.5 bg-[#2a2a2a] text-white text-sm rounded hover:bg-[#333]"
          >
            添加轨道
          </button>
          <input
            type="range"
            min="0"
            max="100"
            value={cursorPos}
            onChange={(e) => setCursorPos(Number(e.target.value))}
            className="w-full"
          />
          <div className="text-xs text-[#777777]">
            Cursor: {cursorPos}
          </div>
        </div>
      )}
    </div>
  );
}