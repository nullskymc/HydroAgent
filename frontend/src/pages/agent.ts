import { api } from '../api';
import { marked } from 'marked';

let currentSessionId: string | null = null;
let isGenerating = false;

// Interface for global variables
declare global {
  interface Window {
    _deleteConversation: (id: string, e: Event) => void;
  }
}

export async function render(): Promise<void> {
  const app = document.getElementById('app');
  const tpl = document.getElementById('tpl-agent') as HTMLTemplateElement;
  if (!app || !tpl) return;
  
  app.innerHTML = '';
  app.appendChild(tpl.content.cloneNode(true));

  // Bind UI elements
  const btnNew = document.getElementById('btn-new-conversation');
  const btnClear = document.getElementById('btn-clear-chat');
  const btnSend = document.getElementById('btn-send');
  const chatInput = document.getElementById('chat-input') as HTMLTextAreaElement;
  
  if (btnNew) btnNew.addEventListener('click', () => createNewConversation());
  if (btnClear) btnClear.addEventListener('click', () => {
    if (confirm('确定清空当前会话？')) {
      if (currentSessionId) {
        api.deleteConversation(currentSessionId).then(() => createNewConversation());
      }
    }
  });

  // Handle chat input
  if (chatInput) {
    chatInput.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    // Auto-resize textarea
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });
  }

  if (btnSend) btnSend.addEventListener('click', sendMessage);

  // Quick Prompts & Commands
  document.querySelectorAll('.qprompt, .qcmd').forEach(btn => {
    btn.addEventListener('click', () => {
      const msg = (btn as HTMLElement).dataset.msg;
      if (msg) sendDirectMessage(msg);
    });
  });

  // Expose delete to window for onclick
  window._deleteConversation = deleteConversation;

  // Initialize
  await loadConversations();

  // Check pending message from Dashboard
  const pendingMsg = sessionStorage.getItem('pendingMsg');
  if (pendingMsg) {
    sessionStorage.removeItem('pendingMsg');
    setTimeout(() => sendDirectMessage(pendingMsg), 500);
  }
}

async function loadConversations(): Promise<void> {
  try {
    const res: any = await api.listConversations();
    const convs = res.conversations || [];
    renderSidebar(convs);

    if (convs.length > 0) {
      if (!currentSessionId || !convs.find((c: any) => c.session_id === currentSessionId)) {
        loadSession(convs[0].session_id);
      } else {
        highlightSidebarPath(currentSessionId);
      }
    } else {
      await createNewConversation();
    }
  } catch (e) {
    console.error('Failed to load conversations:', e);
  }
}

function renderSidebar(convs: any[]): void {
  const list = document.getElementById('conversation-list');
  if (!list) return;

  if (convs.length === 0) {
    list.innerHTML = '<div class="conv-loading">暂无对话记录</div>';
    return;
  }

  list.innerHTML = convs.map(c => {
    const date = new Date(c.updated_at || c.created_at).toLocaleString('zh-CN', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
    return `
      <div class="conv-item" data-id="${c.session_id}" onclick="document.dispatchEvent(new CustomEvent('loadSession', {detail: '${c.session_id}'}))">
        <div class="conv-icon">💬</div>
        <div class="conv-info">
          <div class="conv-title" title="${c.title}">${c.title}</div>
          <div class="conv-meta">${date} · ${c.message_count}条</div>
        </div>
        <button class="conv-delete" onclick="window._deleteConversation('${c.session_id}', event)" title="删除">🗑️</button>
      </div>
    `;
  }).join('');

  // Add event listener for dynamic loaded items
  document.addEventListener('loadSession', ((e: CustomEvent) => {
    if (!isGenerating && e.detail !== currentSessionId) {
      loadSession(e.detail);
    }
  }) as EventListener);
}

function highlightSidebarPath(id: string): void {
  document.querySelectorAll('.conv-item').forEach(el => {
    if ((el as HTMLElement).dataset.id === id) {
      el.classList.add('active');
    } else {
      el.classList.remove('active');
    }
  });
}

async function createNewConversation(): Promise<void> {
  if (isGenerating) return;
  try {
    const res: any = await api.createConversation();
    currentSessionId = res.conversation.session_id;
    await loadConversations();
    clearMessagesArea();
    document.getElementById('chat-title')!.textContent = '新对话';
  } catch (e) {
    console.error('Failed to create new conversation:', e);
  }
}

async function loadSession(id: string): Promise<void> {
  if (isGenerating) return;
  try {
    const res: any = await api.getConversation(id);
    currentSessionId = id;
    highlightSidebarPath(id);
    
    document.getElementById('chat-title')!.textContent = res.conversation.title;
    
    const msgContainer = document.getElementById('chat-messages');
    if (!msgContainer) return;
    
    if (res.messages && res.messages.length > 0) {
      msgContainer.innerHTML = '';
      res.messages.forEach((m: any) => {
        if (m.role === 'user') {
          appendUserMessage(m.content);
        } else if (m.role === 'assistant') {
          appendAssistantMessage(m.content, m.tool_calls);
        }
      });
      scrollToBottom();
    } else {
      clearMessagesArea();
    }
  } catch (e) {
    console.error('Failed to load session:', e);
  }
}

async function deleteConversation(id: string, e: Event): Promise<void> {
  e.stopPropagation();
  if (!confirm('确定删除这个对话会话吗？')) return;
  
  try {
    await api.deleteConversation(id);
    if (currentSessionId === id) {
      currentSessionId = null;
    }
    loadConversations();
  } catch (err) {
    console.error('Delete failed:', err);
  }
}

function clearMessagesArea(): void {
  const container = document.getElementById('chat-messages');
  if (container) {
    container.innerHTML = `
      <div class="welcome-message">
        <div class="welcome-icon">🌊</div>
        <h3>你好，我是 HydroAgent</h3>
        <p>你的水利灌溉 AI 智能助手</p>
        <div class="welcome-tips">
          <span class="tip">💡 试试：「分析当前土壤湿度，需要灌溉吗？」</span>
        </div>
      </div>
    `;
  }
}

async function sendDirectMessage(text: string): Promise<void> {
  if (isGenerating || !text.trim()) return;
  const input = document.getElementById('chat-input') as HTMLTextAreaElement;
  if (input) input.value = text;
  sendMessage();
}

async function sendMessage(): Promise<void> {
  if (isGenerating || !currentSessionId) return;
  
  const input = document.getElementById('chat-input') as HTMLTextAreaElement;
  const btn = document.getElementById('btn-send') as HTMLButtonElement;
  if (!input || !btn) return;
  
  const text = input.value.trim();
  if (!text) return;

  // UI Setup
  isGenerating = true;
  input.value = '';
  input.style.height = 'auto';
  input.disabled = true;
  btn.disabled = true;
  
  // Remove welcome msg if present
  const welcome = document.querySelector('.welcome-message');
  if (welcome) welcome.remove();

  // Show User Message
  appendUserMessage(text);
  
  // Show Loading Bubble
  const loadingId = 'loading-' + Date.now();
  appendTypingIndicator(loadingId);
  scrollToBottom();

  let assistantContent = '';
  let activeToolCard: HTMLElement | null = null;
  let activeToolBody: HTMLElement | null = null;
  
  try {
    await api.streamChat(currentSessionId, text, {
      onText: (chunk) => {
        // Remove typing indicator on first text chunk
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();
        
        // Find or create assistant bubble
        let contentEl = document.getElementById('assistant-active-content');
        if (!contentEl) {
          contentEl = appendEmptyAssistantMessage();
        }
        
        assistantContent += chunk;
        if (contentEl) {
          contentEl.innerHTML = marked.parse(assistantContent) as string;
        }
        scrollToBottom();
      },
      onToolCall: (toolName, toolArgs) => {
        // Remove typing indicator if exists
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();
        
        // Prepare tool card
        const card = document.createElement('div');
        card.className = 'tool-call-card';
        card.innerHTML = `
          <div class="tool-call-header">
            <span class="tool-call-icon">🛠️</span>
            <span class="tool-call-name">${toolName}</span>
            <span class="tool-call-status running">运行中</span>
          </div>
          <div class="tool-call-body">${JSON.stringify(toolArgs, null, 2)}</div>
        `;
        
        const container = document.getElementById('chat-messages');
        if (container) container.appendChild(card);
        
        activeToolCard = card;
        activeToolBody = card.querySelector('.tool-call-body');
        scrollToBottom();
      },
      onToolResult: (toolName, resultStr) => {
        if (activeToolCard && activeToolBody) {
          const statusEl = activeToolCard.querySelector('.tool-call-status');
          if (statusEl) {
            statusEl.className = 'tool-call-status done';
            statusEl.textContent = '已完成';
          }
          activeToolBody.textContent += `\n\n>> [${toolName}] 结果:\n${resultStr}`;
        }
        
        // Re-add typing indicator for the follow-up text
        appendTypingIndicator(loadingId);
        scrollToBottom();
      },
      onDone: () => {
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();
        
        // Remove active ID tag
        const contentEl = document.getElementById('assistant-active-content');
        if (contentEl) contentEl.removeAttribute('id');
        
        finishGeneration();
        loadConversations(); // refresh title if it was first message
      },
      onError: (err) => {
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();
        
        appendAssistantMessage('❌ 发生错误: ' + err);
        finishGeneration();
      }
    });
  } catch (err: any) {
    const loader = document.getElementById(loadingId);
    if (loader) loader.remove();
    appendAssistantMessage('❌ 连接错误: ' + err.message);
    finishGeneration();
  }
}

function finishGeneration(): void {
  isGenerating = false;
  const input = document.getElementById('chat-input') as HTMLTextAreaElement;
  const btn = document.getElementById('btn-send') as HTMLButtonElement;
  if (input) {
    input.disabled = false;
    input.focus();
  }
  if (btn) btn.disabled = false;
}

function appendUserMessage(text: string): void {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  const div = document.createElement('div');
  div.className = 'message message-user';
  div.innerHTML = `
    <div class="message-avatar">👤</div>
    <div class="message-content">${escapeHTML(text)}</div>
  `;
  container.appendChild(div);
}

function appendEmptyAssistantMessage(): HTMLElement {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'message message-assistant';
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-content" id="assistant-active-content"></div>
  `;
  container?.appendChild(div);
  return div.querySelector('.message-content')!;
}

function appendAssistantMessage(text: string, toolsUsed?: string[]): void {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  
  let toolsHtml = '';
  if (toolsUsed && toolsUsed.length > 0) {
    toolsHtml = `<div style="margin-bottom:8px">` + 
      toolsUsed.map(t => `<span class="tool-badge mr-1">🛠️ ${t}</span>`).join(' ') + 
      `</div>`;
  }
  
  const div = document.createElement('div');
  div.className = 'message message-assistant';
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-content">
      ${toolsHtml}
      ${marked.parse(text)}
    </div>
  `;
  container.appendChild(div);
}

function appendTypingIndicator(id: string): void {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  const div = document.createElement('div');
  div.id = id;
  div.className = 'message message-assistant';
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-content">
      <div class="typing-indicator">
        <div class="dot"></div><div class="dot"></div><div class="dot"></div>
      </div>
    </div>
  `;
  container.appendChild(div);
}

function scrollToBottom(): void {
  const container = document.getElementById('chat-messages');
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

function escapeHTML(str: string): string {
  return str.replace(/[&<>'"]/g, 
    tag => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;',
      "'": '&#39;', '"': '&quot;'
    }[tag] || tag)
  );
}
