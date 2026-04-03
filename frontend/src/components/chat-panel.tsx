'use client'

import { useEffect, useEffectEvent, useRef, useState, useTransition } from 'react'
import { ArrowUp, Bot, ChevronDown, LoaderCircle, Trash2, Waves, Workflow, Wrench } from 'lucide-react'
import {
  ChatMessage,
  ConversationDetail,
  ConversationSummary,
  IrrigationPlan,
  StreamEvent,
  ToolProgressStepViewModel,
  ToolProgressViewModel,
  ToolTrace as PersistedToolTrace,
} from '@/lib/types'
import { cn, parseJsonSafe } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge, StatusDot } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { ChatSidebar } from '@/components/chat-sidebar'
import { MessageRichText } from '@/components/message-rich-text'
import { toPlanCardViewModel, toToolProgressStep, toToolProgressViewModel } from '@/lib/presenters'

type LocalMessage = ChatMessage & {
  localId: string
  plan?: IrrigationPlan | null
  toolTrace?: ToolProgressViewModel | null
}

const quickPrompts = [
  '为 soil moisture 最低的分区生成灌溉计划',
  '检查待审批计划并说明风险',
  '查看已批准计划是否可以执行',
]

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
      headline: '正在分析灌溉条件',
      summary: '系统正在准备处理步骤…',
      steps: [],
    },
  }
}

function eventToTraceEntry(event: StreamEvent): ToolProgressStepViewModel | null {
  if (event.type === 'tool_call') {
    return toToolProgressStep({
      id: createLocalId(),
      title: '开始处理',
      detail: undefined,
      toolName: event.tool,
      agentName: event.agent_name,
      tone: 'default',
    })
  }
  if (event.type === 'tool_result') {
    return toToolProgressStep({
      id: createLocalId(),
      title: '步骤完成',
      detail: event.output_preview || undefined,
      toolName: event.tool,
      agentName: event.agent_name,
      durationMs: event.duration_ms,
      tone: 'success',
    })
  }
  if (event.type === 'approval_requested') {
    return toToolProgressStep({
      id: createLocalId(),
      title: '等待审批',
      detail: Array.isArray(event.details?.reasons) ? event.details?.reasons.join('、') : '执行启动计划前需要人工审批。',
      tone: 'warning',
    })
  }
  if (event.type === 'subagent_handoff') {
    return toToolProgressStep({
      id: createLocalId(),
      title: '分配分析任务',
      detail: event.task_description || '系统正在整理当前分区任务。',
      agentName: event.agent_name,
      subagentName: event.subagent,
      tone: 'default',
    })
  }
  if (event.type === 'subagent_result') {
    return toToolProgressStep({
      id: createLocalId(),
      title: '分析结果已返回',
      detail: event.result_preview || '相关分析已完成。',
      agentName: event.agent_name,
      subagentName: event.subagent,
      tone: 'success',
    })
  }
  return null
}

function getMessageRoleLabel(message: LocalMessage) {
  if (message.role === 'assistant') return 'HydroAgent'
  if (message.plan) return '计划回执'
  if (message.toolTrace) return '处理进度'
  return '工具回执'
}

function toLocalMessage(message: ChatMessage): LocalMessage {
  const persistedTrace = message.tool_trace as PersistedToolTrace | null | undefined
  return {
    ...message,
    localId: createLocalId(),
    plan: message.plan ?? null,
    toolTrace: persistedTrace ? toToolProgressViewModel(persistedTrace) : null,
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

function ToolTraceCard({ trace }: { trace: ToolProgressViewModel }) {
  const [expanded, setExpanded] = useState(false)
  const summary = trace.summary || (trace.status === 'running' ? '正在等待处理结果…' : '本轮没有处理步骤')
  const isRunning = trace.status === 'running'

  const sections = [
    {
      key: 'progress',
      label: '处理进度',
      entries: trace.steps,
    },
  ]

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
            <strong>{trace.headline}</strong>
            <Badge tone={trace.status === 'error' ? 'danger' : isRunning ? 'warning' : 'success'}>
              {trace.steps.length} 步
            </Badge>
          </div>
          <p>{summary}</p>
        </div>
        <ChevronDown className={cn('tool-trace-chevron', expanded && 'is-open')} size={16} />
      </button>

      {expanded ? (
        <div className="tool-trace-entries">
          {sections.map((section) => (
            <div key={section.key} className="tool-trace-section">
              <div className="tool-trace-entry-head">
                <span>{section.label}</span>
                <Badge>{section.entries.length}</Badge>
              </div>
              {section.entries.map((entry, index) => (
                <div key={entry.id} className="tool-trace-entry">
                  <div className="tool-trace-entry-rail">
                    <span className={cn('tool-trace-entry-dot', entry.tone && `is-${entry.tone}`)} />
                    {index < section.entries.length - 1 ? <span className="tool-trace-entry-line" /> : null}
                  </div>
                  <div className="tool-trace-entry-copy">
                    <div className="tool-trace-entry-head">
                      <span>{entry.title}</span>
                      <Badge tone={entry.tone}>{index + 1}</Badge>
                    </div>
                    <p>{entry.detail}</p>
                    {entry.meta.length > 0 ? (
                      <div className="audit-console-meta">
                        {entry.meta.map((metaItem) => (
                          <span key={`${entry.id}-${metaItem}`}>{metaItem}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
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
  initialPrompt,
  autoSendInitialPrompt = false,
  startFreshConversation = false,
}: {
  initialConversations: ConversationSummary[]
  initialActiveConversation: ConversationDetail | null
  initialPrompt?: string
  autoSendInitialPrompt?: boolean
  startFreshConversation?: boolean
}) {
  const [conversations, setConversations] = useState(initialConversations)
  const [activeConversation, setActiveConversation] = useState<ConversationDetail | null>(initialActiveConversation)
  const [messages, setMessages] = useState<LocalMessage[]>(
    (initialActiveConversation?.messages || []).map((message) => toLocalMessage(message)),
  )
  const [input, setInput] = useState('')
  const [isPending, startTransition] = useTransition()
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deletingConversationId, setDeletingConversationId] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const initialPromptHandledRef = useRef(false)

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

  function isRenderablePlan(plan: unknown): plan is IrrigationPlan {
    if (!plan || typeof plan !== 'object') return false
    const candidate = plan as Record<string, unknown>
    return typeof candidate.plan_id === 'string' && candidate.plan_id.trim().length > 0
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

  function appendToolTraceEntry(traceId: string, entry: ToolProgressStepViewModel) {
    setMessages((current) =>
      current.map((item) =>
        item.localId === traceId && item.toolTrace
          ? {
              ...item,
              toolTrace: {
                ...item.toolTrace,
                summary: entry.detail,
                steps: [...item.toolTrace.steps, entry],
              },
            }
          : item,
      ),
    )
  }

  function setToolTraceStatus(traceId: string, status: ToolProgressViewModel['status']) {
    setMessages((current) =>
      current
        .map((item) =>
          item.localId === traceId && item.toolTrace
            ? {
                ...item,
                toolTrace: {
                  ...item.toolTrace,
                  status,
                  headline:
                    status === 'error'
                      ? '处理出现问题'
                      : status === 'running'
                        ? '正在分析灌溉条件'
                        : '分析与计划已完成',
                },
              }
            : item,
        )
        .filter((item) => !(item.localId === traceId && item.toolTrace && item.toolTrace.steps.length === 0 && status === 'completed')),
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

  async function submitMessage(options?: { draft?: string; forceNewConversation?: boolean }) {
    const draft = (options?.draft ?? input).trim()
    if (!draft || isStreaming) return

    setError(null)
    setInput('')
    setIsStreaming(true)

    // 首页快捷入口需要强制新建对话，避免把临时问题发送到旧会话里。
    let conversationId = options?.forceNewConversation ? undefined : activeConversation?.conversation.session_id
    if (!conversationId) {
      const detail = await createConversation()
      conversationId = detail?.conversation.session_id
    }
    if (!conversationId) throw new Error('会话创建失败')

    const userMessage: LocalMessage = { role: 'user', content: draft, localId: createLocalId() }
    const toolTraceMessage = createToolTraceMessage()
    const assistantMessage: LocalMessage = { role: 'assistant', content: '', localId: createLocalId() }
    setMessages((current) => [...current, userMessage, toolTraceMessage, assistantMessage])
    let streamFailed = false

    try {
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
            // 现在主链路只有一个 supervisor，仍然只接正式文本事件，避免工具输出混入答案。
            if (payload.agent_name && payload.agent_name !== 'hydro-supervisor') {
              continue
            }
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
            if (isRenderablePlan(payload.plan)) {
              upsertPlan(payload.plan)
            }
          } else if (payload.type === 'error') {
            streamFailed = true
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
    } catch (error) {
      streamFailed = true
      setError(error instanceof Error ? error.message : '消息发送失败')
      setToolTraceStatus(toolTraceMessage.localId, 'error')
    } finally {
      if (!streamFailed) {
        setToolTraceStatus(toolTraceMessage.localId, 'completed')
      }
      setIsStreaming(false)
      await refreshConversations()
    }
  }

  const handleInitialPrompt = useEffectEvent(async (draft: string) => {
    if (autoSendInitialPrompt) {
      await submitMessage({ draft, forceNewConversation: startFreshConversation })
      return
    }

    setInput(draft)
    composerRef.current?.focus()
  })

  useEffect(() => {
    const draft = initialPrompt?.trim()
    if (initialPromptHandledRef.current || !draft) return
    initialPromptHandledRef.current = true
    void handleInitialPrompt(draft)
  }, [initialPrompt])

  function renderPlan(plan: IrrigationPlan) {
    const view = toPlanCardViewModel(plan)

    return (
      <div className="plan-card">
        <div className="plan-card-head">
          <div>
            <strong>{view.title}</strong>
            <p className="inline-muted">{view.summary}</p>
          </div>
          <div className="chat-header-meta">
            <Badge tone={view.actionTone}>{view.actionLabel}</Badge>
            <Badge tone={view.riskTone}>{view.riskLabel}</Badge>
            <Badge tone={view.statusTone}>{view.statusLabel}</Badge>
          </div>
        </div>
        <div className="plan-reason-list">
          {view.reasons.map((reason) => (
            <div key={`${view.planId}-${reason}`} className="plan-reason-item">
              <span className="plan-reason-dot" />
              <p>{reason}</p>
            </div>
          ))}
        </div>
        <div className="plan-metric-grid">
          {view.metrics.map((metric) => (
            <div key={`${view.planId}-${metric.label}`} className="plan-metric">
              <span>{metric.label}</span>
              <strong className={metric.tone ? `tone-${metric.tone}` : ''}>{metric.value}</strong>
            </div>
          ))}
        </div>
        <div className="plan-evidence-grid">
          {view.evidenceSections.map((section) => (
            <div key={`${view.planId}-${section.title}`} className="plan-evidence-card">
              <span>{section.title}</span>
              <div className="plan-evidence-list">
                {section.items.map((item) => (
                  <div key={`${section.title}-${item.label}`} className="plan-evidence-item">
                    <label>{item.label}</label>
                    <strong className={item.tone ? `tone-${item.tone}` : ''}>{item.value}</strong>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="plan-safety-panel">
          <span>风险与约束</span>
          <div className="plan-safety-list">
            {view.safetyItems.map((item) => (
              <div key={`${view.planId}-${item.label}-${item.detail}`} className="plan-safety-item">
                <strong className={item.tone ? `tone-${item.tone}` : ''}>{item.label}</strong>
                <p>{item.detail}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="action-row">
          <Button
            disabled={isPending || !view.canApprove}
            onClick={() => startTransition(async () => actOnPlan(plan.plan_id, 'approve'))}
          >
            批准
          </Button>
          <Button
            variant="secondary"
            disabled={isPending || !view.canReject}
            onClick={() => startTransition(async () => actOnPlan(plan.plan_id, 'reject'))}
          >
            拒绝
          </Button>
          <Button
            variant="ghost"
            disabled={isPending || !view.canExecute}
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
                <Badge><Workflow size={12} /> Direct Tools</Badge>
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
                      <div className={cn('message-content', message.role === 'assistant' && 'markdown-content')}>
                        {message.role === 'user' ? <p>{message.content}</p> : <MessageRichText content={message.content} />}
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
                    void submitMessage()
                  }
                }}
                placeholder="输入分区灌溉问题、计划生成请求、审批指令或执行指令"
                rows={1}
              />
              <Button
                size="icon"
                className="composer-send-button"
                disabled={isPending || isStreaming || !input.trim()}
                onClick={() => void submitMessage()}
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
