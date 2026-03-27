import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, RefreshCw, Layers } from 'lucide-react';
import { marked } from 'marked';
import { api } from '../api';
import type { StreamCallbacks } from '../api';

export default function AgentChat() {
  const [messages, setMessages] = useState<any[]>([
    { role: 'assistant', content: '您好，我是 HydroAgent，您的水利灌溉 AI 决策模型。您可以要求我分析当前园区指标或控制灌溉流。' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [convId, setConvId] = useState<string | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Scroll to bottom
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages, loading]);

  useEffect(() => {
    api.listConversations().then((res: any) => {
      if (res.conversations && res.conversations.length > 0) {
        setConvId(res.conversations[0].session_id);
        loadHistory(res.conversations[0].session_id);
      } else {
        api.createConversation('新对话').then((c: any) => setConvId(c.conversation.session_id));
      }
    }).catch(console.error);
  }, []);

  const loadHistory = async (id: string) => {
    try {
      const conv = await api.getConversation(id);
      if (conv.messages) {
        setMessages(conv.messages.map((m: any) => ({
          role: m.role,
          content: m.content || '',
          toolCalls: m.tool_calls
        })));
      }
    } catch { }
  };

  const handleSend = async (text: string) => {
    if (!text.trim() || !convId || loading) return;
    setInput('');
    setLoading(true);

    const newMsgs = [...messages, { role: 'user', content: text }, { role: 'assistant', content: '' }];
    setMessages(newMsgs);

    const callbacks: StreamCallbacks = {
      onText: (chunk) => {
        setMessages((prev) => {
          const arr = [...prev];
          arr[arr.length - 1].content += chunk;
          return arr;
        });
      },
      onToolCall: (tool, args) => {
        setMessages((prev) => {
          const arr = [...prev];
          const argStr = Object.values(args).join(', ');
          arr[arr.length - 1].content += `\n\n> 🛠️ **正在调用工具**: \`${tool}(${argStr})\` ... `;
          return arr;
        });
      },
      onToolResult: (_tool, _result) => {
        setMessages((prev) => {
          const arr = [...prev];
          arr[arr.length - 1].content += `✅ *获取完成*\n\n`;
          return arr;
        });
      },
      onDone: () => setLoading(false),
      onError: (err) => {
        setMessages((prev) => {
          const arr = [...prev];
          arr[arr.length - 1].content += `\n\n**系统错误:** ${err}`;
          return arr;
        });
        setLoading(false);
      }
    };

    await api.streamChat(convId, text, callbacks);
  };

  const quickCommands = [
    '分析当前土壤湿度，是否需要开启水阀？',
    '查询今天的气象数据预测。',
    '检查整个传感器网络的状态。'
  ];

  return (
    <div style={{ display: 'flex', gap: '1.5rem', height: 'calc(100vh - 120px)' }}>
      {/* Sidebar */}
      <div className="v-card" style={{ width: '280px', display: 'flex', flexDirection: 'column' }}>
        <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.4rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.8rem' }}>
          <Layers size={18} /> 会话管理
        </h3>
        <button className="v-btn" style={{ width: '100%', marginBottom: '1rem' }} onClick={() => {
          api.createConversation('新对话').then((c: any) => {
            setConvId(c.conversation.session_id);
            setMessages([{ role: 'assistant', content: '新的会话已开始。' }]);
          });
        }}>
          + 新建会话
        </button>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <p style={{ color: 'var(--text-dim)', fontSize: '0.85rem' }}>推荐快捷指令</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
            {quickCommands.map((cmd, idx) => (
              <button key={idx} className="v-btn" style={{ fontSize: '0.8rem', textAlign: 'left', whiteSpace: 'normal', padding: '0.5rem' }} onClick={() => handleSend(cmd)}>
                {cmd}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="v-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '1rem 1.5rem', borderBottom: '1px solid var(--border-color)' }}>
          <div style={{ fontWeight: 600 }}>HydroAgent Core 智能控制台</div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {loading && <RefreshCw size={16} className="spin" color="var(--text-dim)" />}
          </div>
        </div>

        <div ref={chatRef} style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {messages.map((m, idx) => (
            <div key={idx} style={{ display: 'flex', gap: '1rem', flexDirection: m.role === 'user' ? 'row-reverse' : 'row' }}>
              <div style={{ 
                width: 36, height: 36, borderRadius: '50%', backgroundColor: m.role === 'user' ? 'var(--text-main)' : 'var(--card-bg)', border: '1px solid var(--border-color)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', color: m.role === 'user' ? 'var(--bg-color)' : 'var(--text-main)'
              }}>
                {m.role === 'user' ? <User size={18} /> : <Bot size={18} />}
              </div>
              <div style={{ 
                maxWidth: '75%', 
                padding: '1rem', 
                backgroundColor: m.role === 'user' ? 'var(--border-color)' : 'var(--bg-color)',
                borderRadius: '8px',
                border: m.role === 'assistant' ? '1px solid var(--border-color)' : 'none',
                lineHeight: 1.6,
                fontSize: '0.95rem'
              }}>
                <div dangerouslySetInnerHTML={{ __html: marked(m.content) }} className="markdown-body" />
              </div>
            </div>
          ))}
          {loading && messages.length > 0 && messages[messages.length - 1].role === 'user' && (
            <div style={{ display: 'flex', gap: '1rem' }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Bot size={18} />
              </div>
              <div style={{ color: 'var(--text-dim)', paddingTop: '0.5rem' }}>思考中...</div>
            </div>
          )}
        </div>

        <div style={{ padding: '1.2rem', borderTop: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)' }}>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input 
              type="text" 
              className="v-input" 
              style={{ flex: 1 }} 
              placeholder="发送指令给系统..." 
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend(input)}
              disabled={loading}
            />
            <button className="v-btn v-btn-primary" onClick={() => handleSend(input)} disabled={loading || !input.trim()}>
              <Send size={18} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
