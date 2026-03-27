/**
 * HydroAgent API Client + SSE Utilities
 */

const BASE_URL = '/api';

// ============================================================
//  REST API helpers
// ============================================================

async function apiGet<T = any>(path: string, params: Record<string, any> = {}): Promise<T> {
  const url = new URL(BASE_URL + path, window.location.origin);
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

async function apiPost<T = any>(path: string, body: Record<string, any> = {}): Promise<T> {
  const res = await fetch(BASE_URL + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API ${path} failed: ${res.status}`);
  }
  return res.json();
}

async function apiDelete<T = any>(path: string): Promise<T> {
  const res = await fetch(BASE_URL + path, { method: 'DELETE' });
  if (!res.ok) throw new Error(`DELETE ${path} failed: ${res.status}`);
  return res.json();
}

async function apiPut<T = any>(path: string, body: Record<string, any> = {}): Promise<T> {
  const res = await fetch(BASE_URL + path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PUT ${path} failed: ${res.status}`);
  return res.json();
}

// ============================================================
//  SSE Chat Stream
// ============================================================

export interface StreamCallbacks {
  onText?: (text: string) => void;
  onToolCall?: (tool: string, args: Record<string, any>) => void;
  onToolResult?: (tool: string, result: any) => void;
  onDone?: () => void;
  onError?: (err: string) => void;
}

/**
 * Stream a chat message and call callbacks for each event.
 */
async function streamChat(conversationId: string, message: string, callbacks: StreamCallbacks = {}) {
  const { onText, onToolCall, onToolResult, onDone, onError } = callbacks;

  try {
    const res = await fetch(`${BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, message }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (onError) onError(err.detail || `请求失败: ${res.status}`);
      return;
    }

    if (!res.body) throw new Error('No response body for SSE');
    
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const dataStr = line.slice(6).trim();
        if (!dataStr) continue;

        try {
          const event = JSON.parse(dataStr);
          switch (event.type) {
            case 'text':
              if (onText) onText(event.content || '');
              break;
            case 'tool_call':
              if (onToolCall) onToolCall(event.tool, event.args || {});
              break;
            case 'tool_result':
              if (onToolResult) onToolResult(event.tool, event.result || '');
              break;
            case 'done':
              if (onDone) onDone();
              return;
          }
        } catch (e) {
          // Ignore parse errors in SSE stream
        }
      }
    }

    if (onDone) onDone();
  } catch (error: any) {
    if (onError) onError(error.message || 'Stream connection error');
  }
}

// ============================================================
//  Specific API endpoints
// ============================================================

export const api = {
  // System
  getStatus: () => apiGet('/status'),

  // Conversations
  listConversations: () => apiGet('/conversations'),
  createConversation: (title = '新对话') => apiPost('/conversations', { title }),
  getConversation: (id: string) => apiGet(`/conversations/${id}`),
  deleteConversation: (id: string) => apiDelete(`/conversations/${id}`),

  // Chat
  streamChat,

  // Sensors
  getCurrentSensors: () => apiGet('/sensors/current'),
  getSensorHistory: (dataType = 'soil_moisture', hours = 24) =>
    apiGet('/sensors/history', { data_type: dataType, hours }),

  // Weather
  getWeather: (city = '北京') => apiGet('/weather', { city }),

  // Irrigation
  getIrrigationStatus: () => apiGet('/irrigation/status'),
  controlIrrigation: (action: 'start' | 'stop', duration = 30) =>
    apiPost('/irrigation/control', { action, duration_minutes: duration }),
  getIrrigationLogs: () => apiGet('/irrigation/logs'),

  // Decisions
  getDecisions: (limit = 20) => apiGet('/decisions', { limit }),

  // Settings
  getSettings: () => apiGet('/settings'),
  updateSettings: (data: Record<string, any>) => apiPut('/settings', data),
};
