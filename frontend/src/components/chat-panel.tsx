'use client'

import { useEffect, useRef, useState, useTransition } from 'react'
import { Bot, MessageSquarePlus, Trash2 } from 'lucide-react'
import { ChatMessage, ConversationDetail, ConversationSummary, StreamEvent } from '@/lib/types'
import { cn, formatDateTime, parseJsonSafe } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge, StatusDot } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'

type LocalMessage = ChatMessage & { localId: string }

function createLocalId() {
  return Math.random().toString(36).slice(2, 10)
}

function eventToToolText(event: StreamEvent) {
  if (event.type === 'tool_call') {
    return `调用工具: ${event.tool || event.content || '未知工具'}`
  }
  if (event.type === 'tool_result') {
    return `工具结果已返回`
  }
  return null
}

export function ChatPanel({
  initialConversations,
  initialActiveConversation,
}: {
  initialConversations: ConversationSummary[]
  initialActiveConversation: ConversationDetail | null
}) {
  const [conversations, setConversations] = useState(initialConversations)
  const [activeConversation, setActiveConversation] = useState<ConversationDetail | null>(initialActiveConversation)
  const [messages, setMessages] = useState<LocalMessage[]>(
    (initialActiveConversation?.messages || []).map((message) => ({
      ...message,
      localId: createLocalId(),
    })),
  )
  const [input, setInput] = useState('')
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const node = composerRef.current
    if (!node) return

    node.style.height = '0px'
    node.style.height = `${Math.min(Math.max(node.scrollHeight, 72), 220)}px`
  }, [input])

  async function loadConversation(sessionId: string) {
    const response = await fetch(`/api/conversations/${sessionId}`)
    if (!response.ok) {
      throw new Error(await response.text())
    }

    const detail = (await response.json()) as ConversationDetail
    setActiveConversation(detail)
    setMessages(
      detail.messages.map((message) => ({
        ...message,
        localId: createLocalId(),
      })),
    )
    return detail
  }

  async function createConversation() {
    const response = await fetch('/api/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: '新对话' }),
    })
    const payload = await response.json()
    const conversation = payload.conversation as ConversationSummary
    setConversations((current) => [conversation, ...current])
    return loadConversation(conversation.session_id)
  }

  async function deleteConversation(sessionId: string) {
    await fetch(`/api/conversations/${sessionId}`, { method: 'DELETE' })
    const nextConversations = conversations.filter((item) => item.session_id !== sessionId)
    setConversations(nextConversations)
    if (activeConversation?.conversation.session_id === sessionId) {
      setActiveConversation(null)
      setMessages([])
      if (nextConversations[0]) {
        await loadConversation(nextConversations[0].session_id)
      }
    }
  }

  async function submitMessage() {
    if (!input.trim()) return

    setError(null)
    const messageText = input.trim()
    setInput('')

    let conversationId = activeConversation?.conversation.session_id
    if (!conversationId) {
      const detail = await createConversation()
      conversationId = detail?.conversation.session_id
    }

    if (!conversationId) {
      throw new Error('会话创建失败')
    }

    const userMessage: LocalMessage = {
      role: 'user',
      content: messageText,
      localId: createLocalId(),
    }
    const assistantMessage: LocalMessage = {
      role: 'assistant',
      content: '',
      localId: createLocalId(),
    }

    setMessages((current) => [...current, userMessage, assistantMessage])

    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: conversationId,
        message: messageText,
      }),
    })

    if (!response.ok || !response.body) {
      throw new Error(await response.text())
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() || ''

      for (const chunk of chunks) {
        const line = chunk
          .split('\n')
          .find((item) => item.startsWith('data: '))

        if (!line) continue

        const payload = parseJsonSafe<StreamEvent>(line.slice(6), { type: 'error', content: '流式数据解析失败' })
        if (payload.type === 'text') {
          setMessages((current) =>
            current.map((item) =>
              item.localId === assistantMessage.localId
                ? { ...item, content: `${item.content || ''}${payload.content}` }
                : item,
            ),
          )
        } else if (payload.type === 'error') {
          setError(payload.content)
        } else if (payload.type !== 'done') {
          const toolText = eventToToolText(payload)
          if (toolText) {
            setMessages((current) => [
              ...current,
              { role: 'tool', content: toolText, localId: createLocalId() },
            ])
          }
        }
      }
    }

    await loadConversation(conversationId)
    const refreshed = await fetch('/api/conversations')
    const refreshedData = await refreshed.json()
    setConversations(refreshedData.conversations || [])
  }

  return (
    <div className="chat-workspace">
      <aside className="chat-sidebar">
        <div className="chat-sidebar-surface">
          <div className="chat-sidebar-header">
            <div className="chat-sidebar-copy">
              <p className="eyebrow">会话历史</p>
              <h2>智能体对话</h2>
            </div>
            <Button
              size="icon"
              variant="secondary"
              onClick={() =>
                startTransition(async () => {
                  await createConversation()
                })
              }
            >
              <MessageSquarePlus size={16} />
            </Button>
          </div>
          <div className="conversation-list">
            {conversations.length === 0 ? (
              <div className="conversation-empty">
                <p className="inline-muted">暂无历史会话</p>
                <p className="inline-muted">点击右上角按钮快速创建新对话。</p>
              </div>
            ) : null}
            {conversations.map((conversation) => (
              <button
                key={conversation.session_id}
                className={`conversation-item ${
                  activeConversation?.conversation.session_id === conversation.session_id ? 'conversation-item-active' : ''
                }`}
                onClick={() =>
                  startTransition(async () => {
                    await loadConversation(conversation.session_id)
                  })
                }
              >
                <div className="conversation-item-main">
                  <strong>{conversation.title}</strong>
                  <p>{conversation.message_count} 条消息</p>
                </div>
                <span>{formatDateTime(conversation.updated_at)}</span>
              </button>
            ))}
          </div>
        </div>
      </aside>

      <section className="chat-canvas">
        <div className="chat-thread-bar">
          <div className="chat-header-copy">
            <p className="eyebrow">HydroAgent Chat</p>
            <div className="chat-header-main">
              <h2>{activeConversation?.conversation.title || '新对话'}</h2>
              <div className="chat-header-meta">
                <Badge><StatusDot tone="success" /> 流式</Badge>
                <Badge>FastAPI SSE</Badge>
              </div>
            </div>
            <p className="inline-muted">围绕灌溉状态、执行策略与传感器网络发起会话。</p>
          </div>
          {activeConversation ? (
            <Button
              size="icon"
              variant="ghost"
              className="chat-delete-button"
              onClick={() =>
                startTransition(async () => {
                  await deleteConversation(activeConversation.conversation.session_id)
                })
              }
            >
              <Trash2 size={16} />
            </Button>
          ) : null}
        </div>

        <div className="chat-stream" ref={scrollRef}>
          <div className={cn('chat-stream-inner', messages.length === 0 && 'chat-stream-inner-empty')}>
            {messages.length === 0 ? (
              <div className="empty-state chat-empty-state">
                <Bot size={28} />
                <h3>让 HydroAgent 解释当前灌溉状态</h3>
                <p>例如：现在是否应该浇水？过去 24 小时湿度趋势如何？</p>
              </div>
            ) : (
              messages.map((message) => (
                <article key={message.localId} className={`message-card role-${message.role}`}>
                  <span className="message-role">
                    {message.role === 'user' ? '用户' : message.role === 'assistant' ? 'HydroAgent' : '工具'}
                  </span>
                  <p>{message.content}</p>
                </article>
              ))
            )}
          </div>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}

        <div className="composer-shell">
          <div className="composer">
            <Textarea
              ref={composerRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  startTransition(submitMessage)
                }
              }}
              placeholder="输入灌溉策略问题、设备控制需求或数据分析请求"
              rows={1}
            />
            <div className="composer-actions">
              <span className="inline-muted">支持策略分析、灌溉建议与节点诊断。</span>
              <Button disabled={isPending || !input.trim()} onClick={() => startTransition(submitMessage)}>
                {isPending ? '发送中...' : '发送'}
              </Button>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
