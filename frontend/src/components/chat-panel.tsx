'use client'

import { useEffect, useEffectEvent, useRef, useState, useTransition } from 'react'
import { Bot, ChevronDown, Copy, LoaderCircle, RotateCcw, Send, Workflow, Wrench } from 'lucide-react'
import {
  ChatMessage,
  ConversationDetail,
  ConversationSummary,
  IrrigationPlan,
  IrrigationSuggestion,
  StreamEvent,
  ToolProgressStepViewModel,
  ToolProgressViewModel,
  ToolTrace as PersistedToolTrace,
  WorkingMemory,
} from '@/lib/types'
import { cn, formatDateTime, parseJsonSafe } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { MessageRichText } from '@/components/message-rich-text'
import { ChatSidebar } from '@/components/chat-sidebar'
import { toPlanCardViewModel, toSuggestionCardViewModel, toToolProgressStep, toToolProgressViewModel } from '@/lib/presenters'

type LocalMessage = ChatMessage & {
  localId: string
  plan?: IrrigationPlan | null
  suggestion?: IrrigationSuggestion | null
  toolTrace?: ToolProgressViewModel | null
}

type ChatMode = 'advisor' | 'planner' | 'operator'

const quickPrompts = [
  '为 soil moisture 最低的分区生成灌溉计划',
  '检查待审批计划并说明风险',
  '查看已批准计划是否可以执行',
]

const chatModeOptions: Array<{ value: ChatMode; label: string; description: string }> = [
  { value: 'advisor', label: 'Advisor', description: '分析建议' },
  { value: 'planner', label: 'Planner', description: '生成计划' },
  { value: 'operator', label: 'Operator', description: '审批执行' },
]

const phaseOrder = ['evidence', 'analysis', 'planning', 'approval', 'execution', 'audit'] as const

const phaseLabels: Record<(typeof phaseOrder)[number], string> = {
  evidence: '证据',
  analysis: '分析',
  planning: '计划',
  approval: '审批',
  execution: '执行',
  audit: '审计',
}

function createLocalId() {
  return Math.random().toString(36).slice(2, 10)
}

function createStableMessageId(message: ChatMessage, index: number) {
  const parts = [
    message.id ?? 'message',
    message.trace_id ?? 'trace',
    message.plan?.plan_id ?? 'plan',
    message.suggestion?.suggestion_id ?? 'suggestion',
    message.tool_call_id ?? 'tool',
    message.tool_name ?? 'name',
    message.created_at ?? index,
    message.role,
  ]
  return parts.join(':')
}

function createToolTraceMessage(): LocalMessage {
  return {
    role: 'tool',
    content: null,
    localId: createLocalId(),
    created_at: new Date().toISOString(),
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
      phase: event.phase,
      activeSkills: event.active_skills,
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
      phase: event.phase,
      activeSkills: event.active_skills,
      durationMs: event.duration_ms,
      tone: 'success',
    })
  }
  if (event.type === 'approval_requested') {
    return toToolProgressStep({
      id: createLocalId(),
      title: '等待审批',
      detail: Array.isArray(event.details?.reasons) ? event.details?.reasons.join('、') : '执行启动计划前需要人工审批。',
      phase: event.phase,
      activeSkills: event.active_skills,
      tone: 'warning',
    })
  }
  return null
}

function getMessageRoleLabel(message: LocalMessage) {
  if (message.role === 'user') return '你'
  if (message.role === 'assistant') return 'HydroAgent'
  if (message.plan) return '计划回执'
  if (message.suggestion) return '建议回执'
  if (message.toolTrace) return '处理进度'
  return '工具回执'
}

function formatMessageTimestamp(value?: string | null) {
  const text = formatDateTime(value)
  return text === '--' ? '刚刚' : text.replace('/', '-')
}

function toLocalMessage(message: ChatMessage, index = 0): LocalMessage {
  const persistedTrace = message.tool_trace as PersistedToolTrace | null | undefined
  return {
    ...message,
    localId: createStableMessageId(message, index),
    plan: message.plan ?? null,
    suggestion: message.suggestion ?? null,
    toolTrace: persistedTrace ? toToolProgressViewModel(persistedTrace) : null,
  }
}

function planMessage(plan: IrrigationPlan): LocalMessage {
  return {
    role: 'tool',
    content: null,
    localId: `plan-${plan.plan_id}`,
    created_at: new Date().toISOString(),
    plan,
  }
}

function suggestionMessage(suggestion: IrrigationSuggestion): LocalMessage {
  return {
    role: 'tool',
    content: null,
    localId: `suggestion-${suggestion.suggestion_id}`,
    created_at: new Date().toISOString(),
    suggestion,
  }
}

function readWorkingMemory(detail: ConversationDetail | null | undefined): WorkingMemory | null {
  return detail?.working_memory ?? null
}

function shouldHideAssistantMessage(messages: LocalMessage[], index: number) {
  const message = messages[index]
  if (message.role !== 'assistant' || !message.content?.trim()) {
    return false
  }

  let turnStart = index
  while (turnStart > 0 && messages[turnStart - 1]?.role !== 'user') {
    turnStart -= 1
  }

  let turnEnd = index
  while (turnEnd < messages.length - 1 && messages[turnEnd + 1]?.role !== 'user') {
    turnEnd += 1
  }

  for (let cursor = turnStart; cursor <= turnEnd; cursor += 1) {
    if (cursor === index) continue
    if (messages[cursor]?.plan || messages[cursor]?.suggestion) {
      return true
    }
  }

  return false
}

function MessageAvatar({ message }: { message: LocalMessage }) {
  if (message.role === 'user') return <>你</>
  if (message.role === 'assistant') return <Bot size={12} />
  if (message.toolTrace) return <Workflow size={12} />
  if (message.plan || message.suggestion) return <Wrench size={12} />
  return <>工</>
}

function ToolTraceCard({ trace }: { trace: ToolProgressViewModel }) {
  const [expanded, setExpanded] = useState(false)
  const summary = trace.summary || (trace.status === 'running' ? '正在等待处理结果…' : '本轮没有处理步骤')
  const isRunning = trace.status === 'running'
  const sections: Array<{ key: string; label: string; entries: ToolProgressStepViewModel[] }> = phaseOrder
    .map((phase) => ({
      key: phase,
      label: phaseLabels[phase],
      entries: trace.steps.filter((entry) => entry.phase === phase),
    }))
    .filter((section) => section.entries.length > 0)
  const fallbackEntries = trace.steps.filter((entry) => !entry.phase)
  if (fallbackEntries.length > 0) {
    sections.push({ key: 'unclassified', label: '处理进度', entries: fallbackEntries })
  }

  return (
    <div className="w-full pl-3 text-xs text-slate-500">
      <button
        type="button"
        className="flex w-full items-start justify-between text-left focus:outline-none"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className={cn(isRunning ? 'animate-spin text-blue-500' : 'text-slate-400')}>
              <LoaderCircle size={14} />
            </span>
            <strong className="text-slate-700 font-medium">{trace.headline}</strong>
            <Badge className="h-4 px-1 py-0 text-[10px]">{trace.steps.length} 步</Badge>
          </div>
          <p className="text-[10px] text-slate-500">{summary}</p>
        </div>
        <ChevronDown className={cn('text-slate-400 transition-transform', expanded && 'rotate-180')} size={14} />
      </button>

      {expanded ? (
        <div className="mt-3 flex flex-col gap-3">
          {sections.map((section) => (
            <div key={section.key} className="flex flex-col gap-2">
              <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">{section.label}</div>
              {section.entries.map((entry) => (
                <div key={entry.id} className="flex gap-2 text-[10px] text-slate-600">
                  <span className="text-slate-300 mt-0.5">•</span>
                  <div className="flex-1">
                    <span className="font-medium text-slate-700">{entry.title}</span>
                    <p className="text-slate-500 mt-0.5">{entry.detail}</p>
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
    (initialActiveConversation?.messages || []).map((message, index) => toLocalMessage(message, index)),
  )
  const initialWorkingMemory = readWorkingMemory(initialActiveConversation)
  const [, setWorkingMemory] = useState<WorkingMemory | null>(initialWorkingMemory)
  const [input, setInput] = useState('')
  const [chatMode, setChatMode] = useState<ChatMode>('planner')
  const [isPending, startTransition] = useTransition()
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deletingConversationId, setDeletingConversationId] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLInputElement>(null)
  const initialPromptHandledRef = useRef(false)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [messages, isStreaming])

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
    setMessages(detail.messages.map((message, index) => toLocalMessage(message, index)))
    const nextMemory = readWorkingMemory(detail)
    setWorkingMemory(nextMemory)
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
    setWorkingMemory(null)
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

  function isRenderablePlan(plan: unknown): plan is IrrigationPlan {
    if (!plan || typeof plan !== 'object') return false
    const candidate = plan as Record<string, unknown>
    return typeof candidate.plan_id === 'string' && candidate.plan_id.trim().length > 0
  }

  function upsertPlan(plan: IrrigationPlan) {
    setMessages((current) => {
      const existing = current.find((item) => item.plan?.plan_id === plan.plan_id)
      if (!existing) return [...current, planMessage(plan)]
      return current.map((item) => (item.plan?.plan_id === plan.plan_id ? { ...item, plan } : item))
    })
  }

  function upsertSuggestion(suggestion: IrrigationSuggestion) {
    setMessages((current) => {
      const existing = current.find((item) => item.suggestion?.suggestion_id === suggestion.suggestion_id)
      if (!existing) return [...current, suggestionMessage(suggestion)]
      return current.map((item) => (item.suggestion?.suggestion_id === suggestion.suggestion_id ? { ...item, suggestion } : item))
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

    let conversationId = options?.forceNewConversation ? undefined : activeConversation?.conversation.session_id
    if (!conversationId) {
      const detail = await createConversation()
      conversationId = detail?.conversation.session_id
    }
    if (!conversationId) throw new Error('会话创建失败')

    const now = new Date().toISOString()
    const userMessage: LocalMessage = { role: 'user', content: draft, localId: createLocalId(), created_at: now }
    const toolTraceMessage = createToolTraceMessage()
    const assistantMessage: LocalMessage = { role: 'assistant', content: '', localId: createLocalId(), created_at: now }
    setMessages((current) => [...current, userMessage, toolTraceMessage, assistantMessage])
    let streamFailed = false

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationId,
          message: draft,
          mode: chatMode,
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
          const line = chunk.split('\n').find((item) => item.startsWith('data: '))
          if (!line) continue

          const payload = parseJsonSafe<StreamEvent>(line.slice(6), { type: 'error', content: '流式数据解析失败' })
          if (payload.type === 'text') {
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
          } else if (payload.type === 'suggestion_result') {
            upsertSuggestion(payload.suggestion)
          } else if (payload.type === 'error') {
            streamFailed = true
            setError(payload.content)
            setToolTraceStatus(toolTraceMessage.localId, 'error')
          } else if (payload.type === 'done') {
            if (payload.working_memory) {
              setWorkingMemory(payload.working_memory)
              setActiveConversation((current) =>
                current
                  ? {
                      ...current,
                      working_memory: payload.working_memory,
                    }
                  : current,
              )
            }
          } else {
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
      <div className="w-full border-l-2 border-slate-100 pl-3 text-xs">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <strong className="text-slate-800 text-sm block mb-0.5">{view.title}</strong>
            <p className="text-slate-500">{view.summary}</p>
          </div>
          <div className="flex gap-1">
            <Badge className="h-5 bg-white px-2 text-[10px]">{view.statusLabel}</Badge>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            className="h-7 text-xs px-3 bg-gradient-to-r from-[#0052FF] to-[#4D7CFF] text-white rounded-md"
            disabled={isPending || !view.canApprove}
            onClick={() => startTransition(async () => actOnPlan(plan.plan_id, 'approve'))}
          >
            批准
          </Button>
          <Button
            size="sm"
            variant="secondary"
            className="h-7 text-xs px-3 rounded-md border border-slate-200"
            disabled={isPending || !view.canReject}
            onClick={() => startTransition(async () => actOnPlan(plan.plan_id, 'reject'))}
          >
            拒绝
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs px-3 rounded-md"
            disabled={isPending || !view.canExecute}
            onClick={() => startTransition(async () => actOnPlan(plan.plan_id, 'execute'))}
          >
            执行
          </Button>
        </div>
      </div>
    )
  }

  function renderSuggestion(suggestion: IrrigationSuggestion) {
    const view = toSuggestionCardViewModel(suggestion)
    return (
      <div className="w-full border-l-2 border-slate-100 pl-3 text-xs">
        <div className="mb-2">
          <strong className="text-slate-800 text-sm block mb-0.5">{view.title}</strong>
          <p className="text-slate-500">{view.summary}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-1 bg-white">
      <ChatSidebar
        quickPrompts={quickPrompts}
        conversations={conversations}
        activeConversationId={activeConversation?.conversation.session_id}
        deletingConversationId={deletingConversationId}
        onCreateConversation={() => {
          startTransition(async () => {
            await createConversation()
          })
        }}
        onSelectPrompt={(prompt) => {
          setInput(prompt)
          composerRef.current?.focus()
        }}
        onSelectConversation={(sessionId) => {
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

      <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col bg-white">
        <div className="flex-1 min-h-0 overflow-y-auto" ref={scrollRef}>
        <div
          className={cn(
            'mx-auto w-full max-w-[1360px] px-5 py-8 sm:px-8 lg:px-10',
            messages.length === 0 ? 'flex h-full flex-col' : 'flex min-h-full flex-col justify-end',
          )}
        >
          {messages.length === 0 ? (
            <div className="mx-auto flex max-w-xl flex-col items-center justify-center pt-20 text-center">
              <div className="mb-5 flex size-10 items-center justify-center rounded-full bg-[#0052FF] text-white">
                <Bot size={18} />
              </div>
              <h3 className="m-0 text-base font-semibold text-slate-900">有什么需要 HydroAgent 分析？</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">
                可以询问天气、分区状态、灌溉计划、审批风险或执行结果。
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {quickPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    className="rounded-full bg-slate-100 px-3 py-1.5 text-xs text-slate-600 transition hover:bg-slate-200 hover:text-slate-900"
                    onClick={() => {
                      setInput(prompt)
                      composerRef.current?.focus()
                    }}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-8">
              {messages.map((message, index) => {
                const hideAssistantMessage = shouldHideAssistantMessage(messages, index)
                if (hideAssistantMessage && !message.plan && !message.suggestion && !message.toolTrace) {
                  return null
                }

                const isUser = message.role === 'user'
                const isPlainAssistant = message.role === 'assistant' && !message.plan && !message.suggestion && !message.toolTrace
                const previousUserMessage = messages
                  .slice(0, index)
                  .reverse()
                  .find((item) => item.role === 'user' && item.content?.trim())

                if (isUser) {
                  return (
                    <article key={message.localId} className="flex justify-end">
                      <div className="max-w-[76%] rounded-lg border-l-2 border-l-[#0052FF] bg-blue-50/60 px-3 py-2 text-sm leading-6 text-slate-900">
                        <p className="m-0 whitespace-pre-wrap">{message.content}</p>
                      </div>
                    </article>
                  )
                }

                return (
                  <article key={message.localId} className="flex items-start gap-3">
                    <div
                      className={cn(
                        'mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold',
                        message.role === 'assistant' ? 'bg-[#0052FF] text-white' : 'bg-slate-100 text-slate-500',
                      )}
                    >
                      <MessageAvatar message={message} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex items-center gap-2 text-[11px] font-medium text-slate-400">
                        <span>{getMessageRoleLabel(message)}</span>
                        <time dateTime={message.created_at || undefined}>{formatMessageTimestamp(message.created_at)}</time>
                      </div>

                      <div className="min-w-0 text-sm leading-6 text-slate-900">
                        {message.plan ? renderPlan(message.plan) : null}
                        {message.suggestion ? renderSuggestion(message.suggestion) : null}
                        {message.toolTrace ? <ToolTraceCard trace={message.toolTrace} /> : null}
                        {!message.plan && !message.suggestion && !hideAssistantMessage && message.content ? (
                          <div className="message-rich-text-canvas">
                            <MessageRichText content={message.content} />
                          </div>
                        ) : null}
                      </div>

                      {isPlainAssistant && message.content ? (
                        <div className="mt-3 flex items-center gap-1 text-slate-300">
                          <button
                            type="button"
                            className="rounded-md p-1 transition hover:bg-slate-100 hover:text-slate-500"
                            title="复制"
                            aria-label="复制回复"
                            onClick={() => void navigator.clipboard?.writeText(message.content || '')}
                          >
                            <Copy size={14} />
                          </button>
                          <button
                            type="button"
                            className="rounded-md p-1 transition hover:bg-slate-100 hover:text-slate-500"
                            title="重新生成"
                            aria-label="重新生成"
                            disabled={!previousUserMessage?.content}
                            onClick={() => {
                              if (!previousUserMessage?.content) return
                              void submitMessage({ draft: previousUserMessage.content })
                            }}
                          >
                            <RotateCcw size={14} />
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </article>
                )
              })}

              {isStreaming ? (
                <div className="flex items-center gap-3" aria-live="polite" aria-label="HydroAgent 正在生成">
                  <div className="flex size-8 items-center justify-center rounded-full bg-[#0052FF] text-white">
                    <Bot size={14} />
                  </div>
                  <span className="size-2 animate-pulse rounded-full bg-[#0052FF]" />
                </div>
              ) : null}
            </div>
          )}
        </div>
        </div>

        {error ? (
          <div className="mx-auto w-full max-w-[1360px] px-5 sm:px-8 lg:px-10">
            <div className="text-xs leading-5 text-rose-600">{error}</div>
          </div>
        ) : null}

        <div className="shrink-0 w-full bg-gradient-to-t from-white via-white to-transparent pt-6 pb-8 px-4">
          <div className="mx-auto w-full max-w-[1360px] px-1 sm:px-4 lg:px-6">
            <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white p-2 shadow-sm transition focus-within:border-[#0052FF]/40 focus-within:ring-2 focus-within:ring-[#0052FF]/10">
              <select
                aria-label="选择 HydroAgent 模式"
                value={chatMode}
                onChange={(event) => setChatMode(event.target.value as ChatMode)}
                className="h-8 shrink-0 rounded-full bg-slate-100 px-2 text-[11px] font-semibold text-slate-700 outline-none md:hidden"
              >
                {chatModeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <div className="hidden shrink-0 items-center rounded-full bg-slate-100 p-0.5 md:inline-flex" aria-label="选择 HydroAgent 模式">
                {chatModeOptions.map((option) => {
                  const selected = chatMode === option.value
                  return (
                    <button
                      key={option.value}
                      type="button"
                      className={cn(
                        'h-7 rounded-full px-2.5 text-[11px] font-semibold leading-none transition',
                        selected ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500 hover:text-slate-900',
                      )}
                      title={option.description}
                      aria-pressed={selected}
                      onClick={() => setChatMode(option.value)}
                    >
                      {option.label}
                    </button>
                  )
                })}
              </div>
              <input
                ref={composerRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    void submitMessage()
                  }
                }}
                className="min-h-8 flex-1 bg-transparent px-1 text-sm text-slate-900 outline-none ring-0 placeholder:text-slate-400"
                placeholder="给 HydroAgent 发送消息..."
              />
              <Button
                size="icon"
                className="size-8 shrink-0 rounded-full bg-blue-500 p-1.5 text-white shadow-none transition hover:bg-blue-600 disabled:bg-slate-200"
                aria-label="发送消息"
                disabled={isPending || isStreaming || !input.trim()}
                onClick={() => void submitMessage()}
              >
                <Send size={15} />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
