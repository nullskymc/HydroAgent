'use client'

import { useEffect, useRef, useState, useTransition } from 'react'
import { marked } from 'marked'
import { ArrowUp, Bot, ChevronDown, LoaderCircle, Trash2, Waves, Workflow, Wrench } from 'lucide-react'
import { ChatMessage, ConversationDetail, ConversationSummary, IrrigationPlan, StreamEvent, ToolTrace as PersistedToolTrace } from '@/lib/types'
import { cn, parseJsonSafe } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge, StatusDot } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { ChatSidebar } from '@/components/chat-sidebar'

type ToolTraceEntry = {
  id: string
  title: string
  detail: string
  tone?: 'default' | 'success' | 'warning' | 'danger'
}

type ToolTrace = {
  trace_id?: string
  status: 'running' | 'completed' | 'error'
  entries: ToolTraceEntry[]
}

type LocalMessage = ChatMessage & {
  localId: string
  plan?: IrrigationPlan | null
  toolTrace?: ToolTrace | null
}

type NoticeTone = 'default' | 'success' | 'warning' | 'danger'

const quickPrompts = [
  '为 soil moisture 最低的分区生成灌溉计划',
  '检查待审批计划并说明风险',
  '查看已批准计划是否可以执行',
]

marked.setOptions({
  gfm: true,
  breaks: true,
})

function createLocalId() {
  return Math.random().toString(36).slice(2, 10)
}

function createToolTraceMessage(): LocalMessage {
  return {
    role: 'tool',
    content: null,
    localId: createLocalId(),
    toolTrace: {
      status: 'running',
      entries: [],
    },
  }
}

function createTraceEntry(title: string, detail: string, tone: NoticeTone = 'default'): ToolTraceEntry {
  return {
    id: createLocalId(),
    title,
    detail,
    tone,
  }
}

function eventToTraceEntry(event: StreamEvent): ToolTraceEntry | null {
  if (event.type === 'tool_call') {
    return createTraceEntry('工具调用', event.tool || event.content || '未知工具')
  }
  if (event.type === 'tool_result') {
    return createTraceEntry('工具返回', event.output_preview || `${event.tool || '当前工具'} 已返回结构化结果`, 'success')
  }
  if (event.type === 'approval_requested') {
    const reasons = Array.isArray(event.details?.reasons) ? event.details?.reasons.join('、') : 'start 操作需要审批'
    return createTraceEntry('审批边界', reasons, 'warning')
  }
  if (event.type === 'subagent_handoff') {
    return createTraceEntry(
      `委派 ${event.subagent || 'subagent'}`,
      `${event.zone_id || '待识别分区'} · ${event.task_description || '正在准备任务说明'}`,
      'default',
    )
  }
  if (event.type === 'subagent_result') {
    return createTraceEntry(
      `${event.subagent || 'subagent'} 已返回`,
      event.result_preview || '子代理已完成处理',
      'success',
    )
  }
  return null
}

function getMessageRoleLabel(message: LocalMessage) {
  if (message.role === 'assistant') return 'HydroAgent'
  if (message.plan) return '计划回执'
  if (message.toolTrace) return '工具链'
  return '工具回执'
}

function toLocalMessage(message: ChatMessage): LocalMessage {
  const persistedTrace = message.tool_trace as PersistedToolTrace | null | undefined
  return {
    ...message,
    localId: createLocalId(),
    toolTrace: persistedTrace
      ? {
          trace_id: persistedTrace.trace_id,
          status:
            persistedTrace.status === 'error'
              ? 'error'
              : persistedTrace.status === 'running'
                ? 'running'
                : 'completed',
          entries: persistedTrace.steps.map((step) => ({
            id: `${persistedTrace.trace_id}-${step.step_index}`,
            title: step.title,
            detail: step.detail,
            tone: step.status === 'error' ? 'danger' : step.status === 'running' ? 'warning' : 'success',
          })),
        }
      : null,
  }
}

function planMessage(plan: IrrigationPlan): LocalMessage {
  return {
    role: 'tool',
    content: null,
    localId: `plan-${plan.plan_id}`,
    plan,
  }
}

function formatPlanTone(plan: IrrigationPlan) {
  if (plan.execution_status === 'executed') return 'success'
  if (plan.approval_status === 'rejected' || plan.risk_level === 'high') return 'danger'
  if (plan.approval_status === 'pending' || plan.risk_level === 'medium') return 'warning'
  return 'default'
}

function renderMarkdown(content: string | null | undefined) {
  const safeSource = String(content || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return marked.parse(safeSource) as string
}

function MessageAvatar({ message }: { message: LocalMessage }) {
  if (message.role === 'user') {
    return <div className="message-avatar message-avatar-user">你</div>
  }
  if (message.role === 'assistant') {
    return <div className="message-avatar message-avatar-agent">H</div>
  }
  if (message.toolTrace) {
    return (
      <div className="message-avatar message-avatar-toolchain">
        <Workflow size={13} />
      </div>
    )
  }
  if (message.plan) {
    return (
      <div className="message-avatar message-avatar-toolchain">
        <Wrench size={13} />
      </div>
    )
  }
  return <div className="message-avatar message-avatar-toolchain">工</div>
}

function ToolTraceCard({ trace }: { trace: ToolTrace }) {
  const [expanded, setExpanded] = useState(false)
  const latestEntry = trace.entries.at(-1)
  const summary = latestEntry?.detail || (trace.status === 'running' ? '正在等待工具链返回状态…' : '本轮没有工具事件')
  const isRunning = trace.status === 'running'

  return (
    <div className="tool-trace-card">
      <button
        type="button"
        className="tool-trace-summary"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <div className="tool-trace-summary-copy">
          <div className="tool-trace-summary-head">
            <span className={cn('tool-trace-spinner', isRunning && 'is-running')}>
              <LoaderCircle size={14} />
            </span>
            <strong>{isRunning ? '工具链执行中' : trace.status === 'error' ? '工具链中断' : '工具链已完成'}</strong>
            <Badge tone={trace.status === 'error' ? 'danger' : isRunning ? 'warning' : 'success'}>
              {trace.entries.length} 步
            </Badge>
          </div>
          <p>{summary}</p>
        </div>
        <ChevronDown className={cn('tool-trace-chevron', expanded && 'is-open')} size={16} />
      </button>

      {expanded ? (
        <div className="tool-trace-entries">
          {trace.entries.map((entry, index) => (
            <div key={entry.id} className="tool-trace-entry">
              <div className="tool-trace-entry-rail">
                <span className={cn('tool-trace-entry-dot', entry.tone && `is-${entry.tone}`)} />
                {index < trace.entries.length - 1 ? <span className="tool-trace-entry-line" /> : null}
              </div>
              <div className="tool-trace-entry-copy">
                <div className="tool-trace-entry-head">
                  <span>{entry.title}</span>
                  <Badge tone={entry.tone}>{index + 1}</Badge>
                </div>
                <p>{entry.detail}</p>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
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
    (initialActiveConversation?.messages || []).map((message) => toLocalMessage(message)),
  )
  const [input, setInput] = useState('')
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)
  const [deletingConversationId, setDeletingConversationId] = useState<string | null>(null)
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

  async function refreshConversations() {
    const refreshed = await fetch('/api/conversations')
    const refreshedData = await refreshed.json()
    setConversations(refreshedData.conversations || [])
  }

  async function loadConversation(sessionId: string) {
    const response = await fetch(`/api/conversations/${sessionId}`)
    if (!response.ok) {
      throw new Error(await response.text())
    }

    const detail = (await response.json()) as ConversationDetail
    setActiveConversation(detail)
    setMessages(detail.messages.map((message) => toLocalMessage(message)))
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
    setError(null)
    setDeletingConversationId(sessionId)

    try {
      const response = await fetch(`/api/conversations/${sessionId}`, { method: 'DELETE' })
      const payload = (await response.json().catch(() => null)) as { detail?: string; message?: string } | null

      if (!response.ok) {
        throw new Error(payload?.detail || payload?.message || '会话删除失败')
      }

      const nextConversations = conversations.filter((item) => item.session_id !== sessionId)
      setConversations(nextConversations)
      if (activeConversation?.conversation.session_id === sessionId) {
        setActiveConversation(null)
        setMessages([])
        if (nextConversations[0]) {
          await loadConversation(nextConversations[0].session_id)
        }
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : '会话删除失败')
    } finally {
      setDeletingConversationId(null)
    }
  }

  function upsertPlan(plan: IrrigationPlan) {
    setMessages((current) => {
      const existing = current.find((item) => item.plan?.plan_id === plan.plan_id)
      if (!existing) return [...current, planMessage(plan)]
      return current.map((item) => (item.plan?.plan_id === plan.plan_id ? { ...item, plan } : item))
    })
  }

  function appendToolTraceEntry(traceId: string, entry: ToolTraceEntry) {
    setMessages((current) =>
      current.map((item) =>
        item.localId === traceId && item.toolTrace
          ? {
              ...item,
              toolTrace: {
                ...item.toolTrace,
                entries: [...item.toolTrace.entries, entry],
              },
            }
          : item,
      ),
    )
  }

  function setToolTraceStatus(traceId: string, status: ToolTrace['status']) {
    setMessages((current) =>
      current
        .map((item) =>
          item.localId === traceId && item.toolTrace
            ? {
                ...item,
                toolTrace: {
                  ...item.toolTrace,
                  status,
                },
              }
            : item,
        )
        .filter((item) => !(item.localId === traceId && item.toolTrace && item.toolTrace.entries.length === 0 && status === 'completed')),
    )
  }

  async function actOnPlan(planId: string, action: 'approve' | 'reject' | 'execute') {
    const response = await fetch(`/api/plans/${planId}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actor: 'chat-user' }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail || '计划操作失败')
    }
    if (payload.plan) {
      upsertPlan(payload.plan as IrrigationPlan)
    }
  }

  async function submitMessage(nextInput?: string) {
    const draft = (nextInput ?? input).trim()
    if (!draft) return

    setError(null)
    setInput('')

    let conversationId = activeConversation?.conversation.session_id
    if (!conversationId) {
      const detail = await createConversation()
      conversationId = detail?.conversation.session_id
    }
    if (!conversationId) throw new Error('会话创建失败')

    const userMessage: LocalMessage = { role: 'user', content: draft, localId: createLocalId() }
    const toolTraceMessage = createToolTraceMessage()
    const assistantMessage: LocalMessage = { role: 'assistant', content: '', localId: createLocalId() }
    setMessages((current) => [...current, userMessage, toolTraceMessage, assistantMessage])

    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, message: draft }),
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
        const line = chunk.split('\n').find((item) => item.startsWith('data: '))
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
        } else if (
          payload.type === 'plan_proposed' ||
          payload.type === 'plan_updated' ||
          payload.type === 'approval_result' ||
          payload.type === 'execution_result'
        ) {
          upsertPlan(payload.plan)
        } else if (payload.type === 'error') {
          setError(payload.content)
          setToolTraceStatus(toolTraceMessage.localId, 'error')
        } else if (payload.type !== 'done') {
          const traceEntry = eventToTraceEntry(payload)
          if (traceEntry) {
            appendToolTraceEntry(toolTraceMessage.localId, traceEntry)
          }
        }
      }
    }

    setToolTraceStatus(toolTraceMessage.localId, 'completed')
    await refreshConversations()
  }

  function renderPlan(plan: IrrigationPlan) {
    const tone = formatPlanTone(plan)
    const evidence = plan.evidence_summary || {}
    const safety = plan.safety_review || {}

    return (
      <div className="plan-card">
        <div className="plan-card-head">
          <div>
            <strong>{plan.zone_name || plan.zone_id}</strong>
            <p className="inline-muted">{plan.plan_id}</p>
          </div>
          <div className="chat-header-meta">
            <Badge tone={tone}>{plan.proposed_action}</Badge>
            <Badge>{plan.risk_level}</Badge>
            <Badge>{plan.status}</Badge>
          </div>
        </div>
        <p>{plan.reasoning_summary || '无摘要'}</p>
        <div className="plan-metric-grid">
          <div className="plan-metric">
            <span>审批</span>
            <strong>{plan.approval_status}</strong>
          </div>
          <div className="plan-metric">
            <span>执行</span>
            <strong>{plan.execution_status}</strong>
          </div>
          <div className="plan-metric">
            <span>建议时长</span>
            <strong>{plan.recommended_duration_minutes} 分钟</strong>
          </div>
          <div className="plan-metric">
            <span>风险</span>
            <strong>{plan.risk_level}</strong>
          </div>
        </div>
        <div className="plan-evidence-grid">
          <div className="plan-evidence-card">
            <span>证据摘要</span>
            <p>{JSON.stringify(evidence)}</p>
          </div>
          <div className="plan-evidence-card">
            <span>安全复核</span>
            <p>{JSON.stringify(safety)}</p>
          </div>
        </div>
        <div className="action-row">
          <Button
            disabled={isPending || plan.approval_status !== 'pending'}
            onClick={() => startTransition(async () => actOnPlan(plan.plan_id, 'approve'))}
          >
            批准
          </Button>
          <Button
            variant="secondary"
            disabled={isPending || plan.approval_status !== 'pending'}
            onClick={() => startTransition(async () => actOnPlan(plan.plan_id, 'reject'))}
          >
            拒绝
          </Button>
          <Button
            variant="ghost"
            disabled={isPending || plan.approval_status !== 'approved' || plan.execution_status === 'executed'}
            onClick={() => startTransition(async () => actOnPlan(plan.plan_id, 'execute'))}
          >
            执行
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="chat-workspace">
      <ChatSidebar
        quickPrompts={quickPrompts}
        conversations={conversations}
        activeConversationId={activeConversation?.conversation.session_id}
        deletingConversationId={deletingConversationId}
        onCreateConversation={() => {
          // 侧边栏新建入口仅触发会话创建，不承担其他状态更新。
          startTransition(async () => {
            await createConversation()
          })
        }}
        onSelectPrompt={(prompt) => {
          // 快捷动作只回填输入框，避免误触后直接发送。
          setInput(prompt)
          composerRef.current?.focus()
        }}
        onSelectConversation={(sessionId) => {
          // 会话切换统一交给加载函数，保持主面板状态来源单一。
          startTransition(async () => {
            await loadConversation(sessionId)
          })
        }}
        onDeleteConversation={(sessionId) => {
          startTransition(async () => {
            await deleteConversation(sessionId)
          })
        }}
      />

      <section className="chat-canvas">
        <div className="chat-thread-bar">
          <div className="chat-header-copy">
            <p className="eyebrow">Supervisor Thread</p>
            <div className="chat-header-main">
              <h2>{activeConversation?.conversation.title || '新对话'}</h2>
              <div className="chat-header-meta">
                <Badge><StatusDot tone="success" /> 流式</Badge>
                <Badge><Workflow size={12} /> Subagents</Badge>
                <Badge><Waves size={12} /> Plan Timeline</Badge>
              </div>
            </div>
            <p className="inline-muted">HydroAgent 会在对话中生成计划、请求审批并回写执行结果。</p>
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
              <div className="empty-state chat-empty-state chat-empty-state-rich">
                <Bot size={30} />
                <h3>从一个问题开始</h3>
                <p>例如：检查当前土壤湿度，判断是否需要生成灌溉计划。</p>
              </div>
            ) : (
              messages.map((message) => (
                <article
                  key={message.localId}
                  className={cn(
                    'message-row',
                    `role-${message.role}`,
                    message.toolTrace && 'message-card-tooltrace',
                    message.plan && 'message-card-plan',
                  )}
                >
                  <MessageAvatar message={message} />
                  <div className="message-body">
                    {message.role !== 'user' ? (
                      <span className="message-role">{getMessageRoleLabel(message)}</span>
                    ) : null}
                    {message.plan ? renderPlan(message.plan) : null}
                    {message.toolTrace ? <ToolTraceCard trace={message.toolTrace} /> : null}
                    {!message.plan && message.content ? (
                      <div
                        className={cn('message-content', message.role === 'assistant' && 'markdown-content')}
                        {...(message.role === 'assistant'
                          ? { dangerouslySetInnerHTML: { __html: renderMarkdown(message.content) } }
                          : {})}
                      >
                        {message.role === 'user' ? <p>{message.content}</p> : null}
                      </div>
                    ) : null}
                  </div>
                </article>
              ))
            )}
          </div>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}

        <div className="composer-shell composer-shell-rich">
          <div className="composer composer-rich">
            <div className="composer-input-frame">
              <Textarea
                ref={composerRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    startTransition(async () => submitMessage())
                  }
                }}
                placeholder="输入分区灌溉问题、计划生成请求、审批指令或执行指令"
                rows={1}
              />
              <Button
                size="icon"
                className="composer-send-button"
                disabled={isPending || !input.trim()}
                onClick={() => startTransition(async () => submitMessage())}
              >
                <ArrowUp size={16} />
              </Button>
            </div>
          </div>
          <p className="composer-footnote">支持计划生成、审批、执行回执与审计</p>
        </div>
      </section>
    </div>
  )
}
