/**
 * useWebSocketProgress — React hook for real-time task progress via WebSocket.
 *
 * Features:
 *   - Auto-connect when taskId is provided
 *   - Auto-reconnect with exponential backoff (max 5 retries)
 *   - Clean disconnect on unmount (no memory leaks)
 *   - Unified state: { status, progress, message, resultUrl, elapsedTime, error, connected }
 *
 * Usage:
 *   const { status, progress, message, elapsedTime } = useWebSocketProgress(taskId);
 */

import { useRef, useReducer, useEffect, useCallback } from 'react';

// ── Types ──────────────────────────────────────────────────────────────────

export interface ProgressState {
  status: string;
  progress: number;
  message: string;
  resultUrl: string | null;
  elapsedTime: number | null;  // seconds from task start to completion
  error: string | null;
  connected: boolean;
}

type Action =
  | { type: 'CONNECT' }
  | { type: 'DISCONNECT' }
  | { type: 'UPDATE'; payload: Partial<ProgressState> }
  | { type: 'ERROR'; payload: string }
  | { type: 'RESET' };

// ── Constants ──────────────────────────────────────────────────────────────

const WS_BASE =
  import.meta.env.DEV && window.location.protocol === 'http:'
    ? `ws://${window.location.host}`
    : 'ws://localhost:8000';
const MAX_RETRIES = 5;
const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30_000;

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled']);

const initialState: ProgressState = {
  status: '',
  progress: 0,
  message: '',
  resultUrl: null,
  elapsedTime: null,
  error: null,
  connected: false,
};

// ── Reducer ────────────────────────────────────────────────────────────────

function reducer(state: ProgressState, action: Action): ProgressState {
  switch (action.type) {
    case 'CONNECT':
      return { ...state, connected: true, error: null };
    case 'DISCONNECT':
      return { ...state, connected: false };
    case 'UPDATE':
      return { ...state, ...action.payload };
    case 'ERROR':
      return { ...state, error: action.payload, connected: false };
    case 'RESET':
      return { ...initialState, connected: state.connected };
    default:
      return state;
  }
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useWebSocketProgress(taskId: string | null) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectingRef = useRef(false);
  const taskIdRef = useRef(taskId);

  // Keep ref in sync with prop
  taskIdRef.current = taskId;

  // ── Core connect function (stable identity via refs) ───────────────────
  const connect = useCallback(() => {
    const currentTaskId = taskIdRef.current;
    if (!currentTaskId) return;

    // Close existing connection
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    const ws = new WebSocket(`${WS_BASE}/ws/progress/${currentTaskId}`);
    wsRef.current = ws;

    // UI feedback for reconnecting
    if (reconnectingRef.current) {
      dispatch({
        type: 'UPDATE',
        payload: {
          message: `Reconnecting... (${retryCountRef.current}/${MAX_RETRIES})`,
        },
      });
    }

    dispatch({ type: 'CONNECT' });

    ws.onopen = () => {
      retryCountRef.current = 0;
      backoffRef.current = INITIAL_BACKOFF_MS;
      reconnectingRef.current = false;
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as Record<string, unknown>;
        const status = String(msg.status ?? '');
        const progress = Number(msg.progress ?? 0);

        // Extract elapsed_time if present in the message
        const elapsedTime = msg.elapsed_time !== undefined
          ? Number(msg.elapsed_time)
          : null;

        dispatch({
          type: 'UPDATE',
          payload: {
            status,
            progress,
            message: String(msg.message ?? ''),
            resultUrl: msg.result_url ? String(msg.result_url) : null,
            elapsedTime: elapsedTime ?? state.elapsedTime,
          },
        });

        // Terminal state → stop reconnecting
        if (TERMINAL_STATUSES.has(status)) {
          reconnectingRef.current = false;
        }
      } catch {
        dispatch({
          type: 'ERROR',
          payload: 'Failed to parse WebSocket message',
        });
      }
    };

    ws.onerror = () => {
      // onerror is always followed by onclose in the WebSocket spec
    };

    ws.onclose = () => {
      // Don't reconnect for terminal states or intentional closes
      if (!reconnectingRef.current) {
        dispatch({ type: 'DISCONNECT' });
        return;
      }

      // Attempt reconnect with exponential backoff
      if (retryCountRef.current < MAX_RETRIES) {
        retryCountRef.current += 1;
        dispatch({
          type: 'UPDATE',
          payload: {
            message: `Reconnecting... (${retryCountRef.current}/${MAX_RETRIES})`,
          },
        });
        timerRef.current = setTimeout(() => {
          connect();
        }, backoffRef.current);
        // Exponential backoff with cap
        backoffRef.current = Math.min(
          backoffRef.current * 2,
          MAX_BACKOFF_MS,
        );
      } else {
        dispatch({
          type: 'ERROR',
          payload: `Failed to reconnect after ${MAX_RETRIES} attempts`,
        });
      }
    };
  }, []); // Stable — reads everything from refs

  // ── Lifecycle: connect/disconnect on taskId change ─────────────────────
  useEffect(() => {
    if (!taskId) return;

    reconnectingRef.current = true;
    connect();

    // Cleanup on unmount or taskId change
    return () => {
      reconnectingRef.current = false;
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [taskId, connect]);

  return state;
}
